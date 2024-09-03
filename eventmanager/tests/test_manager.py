from datetime import datetime

import pytest

from common.executors import Executor, Task
from common.models import Teavent
from eventmanager.manager import TeaventManager


class NoTasks(Exception):
    "No tasks to execute"


class FakeExecutor(Executor):
    def schedule(self, task: Task, delay_seconds: int):
        self._tasks[task.group_id][task.name] = task

    def cancel(self, group_id: str):
        pass

    def now(self, tz=None):
        return datetime(2024, 7, 31, 17, 0, tzinfo=tz)

    def execute_current_tasks(self):
        if not (tasks := self.tasks()):
            raise NoTasks

        for t in tasks:
            t.fn()
            self._tasks[t.group_id].pop(t.name)


@pytest.fixture
def fake_executor():
    return FakeExecutor()


@pytest.fixture
def manager(fake_executor):
    return TeaventManager(executor=fake_executor)


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
