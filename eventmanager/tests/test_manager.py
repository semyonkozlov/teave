from collections.abc import Callable
from datetime import datetime

import pytest

from common.executors import Executor, Task
from common.models import Teavent
from eventmanager.manager import TeaventManager


class FakeExecutor(Executor):
    def schedule(self, task: Task, delay_seconds: int):
        assert delay_seconds > 0

        self._tasks[task.group_id][task.name] = task

    def cancel(self, group_id: str):
        pass

    def now(self, tz=None):
        return datetime(2024, 7, 31, 17, 0, tzinfo=tz)


@pytest.fixture
def fake_executor():
    return FakeExecutor()


@pytest.fixture
def manager(fake_executor):
    return TeaventManager(executor=fake_executor)


def _execute(tasks: list[Callable]):
    for t in tasks:
        t.fn()


def test_handle_created_teavent_after_start_poll_before_start(
    manager: TeaventManager, teavent: Teavent, fake_executor: FakeExecutor
):
    assert teavent.state == "created"
    assert teavent.start_poll_at < fake_executor.now(teavent.tz) < teavent.start

    manager.handle_teavent(teavent)
    tasks = fake_executor.tasks(teavent.id)
    _execute(tasks)

    assert teavent.state == "poll_open"
