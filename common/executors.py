import asyncio
import inspect
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Awaitable, Callable

from attr import define


log = logging.getLogger(__name__)


@define
class Executor(ABC):
    _tasks: dict[str, set] = defaultdict(set)

    @abstractmethod
    def schedule(self, fn, name: str = None, delay_seconds: int = 0): ...

    @abstractmethod
    def cancel(self, group_id: str): ...

    @abstractmethod
    def now(self, tz=None) -> datetime: ...

    def tasks(self, group_id: str | None = None) -> list:
        if group_id is None:
            return sum((self.tasks(gid) for gid in self._tasks), [])
        return list(self._tasks[group_id])


async def _task(fn: Awaitable | Callable, name: str, delay_seconds: int):
    at = datetime.now() + timedelta(seconds=delay_seconds)
    log.info(f"Schedule '{name}' to run in {delay_seconds} seconds (at {at} UTC)")

    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    if inspect.isawaitable(fn):
        await fn
    else:
        fn()


@define
class AsyncioExecutor(Executor):
    def schedule(
        self, fn: Awaitable | Callable, name: str = None, delay_seconds: int = 0
    ):
        if delay_seconds < 0:
            log.warning(f"Negative delay for task {name}")

        asynciotask = asyncio.create_task(_task(fn, name, delay_seconds), name=name)

        name = name or f"anon:{id(fn)}"
        group_id = name.split(":")[0]

        task_group = self._tasks[group_id]

        assert name not in task_group
        task_group.add(asynciotask)

        def _on_task_done(t: asyncio.Task):
            task_group.discard(t)

        asynciotask.add_done_callback(_on_task_done)

    def cancel(self, group_id: str):
        for t in self._tasks[group_id]:
            t.cancel()

    def now(self, tz=None) -> datetime:
        return datetime.now(tz)
