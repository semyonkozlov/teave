import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Callable

from attr import define


log = logging.getLogger(__name__)


@define
class Task:
    fn: Callable
    name: str

    @property
    def group_id(self) -> str:
        return self.name.split(":")[0]


@define
class Executor(ABC):
    _tasks: dict[str, dict[str, Any]] = defaultdict(dict)

    @abstractmethod
    def schedule(self, task: Task, delay_seconds: int): ...

    @abstractmethod
    def cancel(self, group_id: str): ...

    @abstractmethod
    def now(self, tz=None) -> datetime: ...

    def tasks(self, group_id: str) -> list:
        return list(self._tasks[group_id].values())


@define
class AsyncioExecutor(Executor):
    def schedule(self, task: Task, delay_seconds: int):
        if delay_seconds < 0:
            raise RuntimeError(f"Negative delay for task {task.name}")

        async def _task():
            at = datetime.now() + timedelta(seconds=delay_seconds)
            log.info(
                f"Schedule '{task.name}' to run in {delay_seconds} seconds (at {at} UTC)"
            )
            await asyncio.sleep(delay_seconds)
            task.fn()

        grouped_tasks = self._tasks[task.group_id]
        asynciotask = asyncio.create_task(_task(), name=task.name)
        grouped_tasks[task.name] = asynciotask

        def _on_task_done(t: asyncio.Task):
            grouped_tasks.pop(t.get_name())

        asynciotask.add_done_callback(_on_task_done)

    def cancel(self, group_id: str):
        for t in self._tasks[group_id]:
            t.cancel()

    def now(self, tz=None) -> datetime:
        return datetime.now(tz)
