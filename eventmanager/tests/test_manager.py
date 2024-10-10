from collections.abc import Callable
from datetime import datetime

from attr import define
import pytest

from common.executors import Executor
from common.models import Teavent
from eventmanager.manager import TeaventManager


class FakeExecutor(Executor):
    def __init__(self, now: datetime):
        self._now = now

        super().__init__()

    def schedule(self, fn, group_id: str, name: str, delay_seconds: int):
        self._add_task(fn, group_id, name)

    def cancel(self, group_id: str):
        self._pop_group(group_id)

    def now(self, tz=None):
        return self._now.replace(tzinfo=tz)

    def execute_current_tasks(self):
        tasks = self.tasks()
        assert tasks

        self._tasks.clear()

        for fn in tasks:
            fn()


@pytest.fixture
def fake_executor(request):
    return FakeExecutor(now=request.param["now"])


@pytest.fixture
def manager(fake_executor):
    return TeaventManager(executor=fake_executor)


@pytest.mark.parametrize("teavent", [{"state": "created"}], indirect=True)
@pytest.mark.parametrize(
    "fake_executor", [{"now": datetime(2024, 7, 31, 17, 0)}], indirect=True
)
def test_handle_created_teavent_after_start_poll_before_start(
    manager: TeaventManager, teavent: Teavent, fake_executor: FakeExecutor
):
    assert teavent.state == "created"
    # handling teavent after start_poll timing but before start
    assert teavent.start_poll_at < fake_executor.now(teavent.tz) < teavent.start

    manager.handle_teavent(teavent)

    fake_executor.execute_current_tasks()
    assert teavent.state == "poll_open"

    fake_executor.execute_current_tasks()
    # cancel and recreate teavent according to rrule
    assert teavent.state == "created"
    assert fake_executor.now(teavent.tz) < teavent.start_poll_at
