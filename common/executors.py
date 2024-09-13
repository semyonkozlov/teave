import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import Any
from collections.abc import Awaitable, Callable
from collections import defaultdict

from attr import define


log = logging.getLogger(__name__)


@define
class Executor(ABC):
    _tasks: dict[str, dict[str, Any]] = defaultdict(dict)

    def _add_task(self, task: Any, group_id: str, name: str):
        if name in self._tasks[group_id]:
            raise RuntimeError(f"task '{name}' already exists in group '{group_id}")
        self._tasks[group_id][name] = task

    def _pop_group(self, group_id: str) -> dict[str, Any]:
        return self._tasks.pop(group_id)

    def _pop_task(self, group_id: str, name: str) -> Any:
        return self._tasks[group_id].pop(name)

    @abstractmethod
    def schedule(self, fn, group_id: str, name: str = None, delay_seconds: int = 0): ...

    @abstractmethod
    def cancel(self, group_id: str): ...

    @abstractmethod
    def now(self, tz=None) -> datetime: ...

    def tasks(self) -> list[Any]:
        return sum((list(group.values()) for group in self._tasks.values()), [])


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
        self,
        fn: Awaitable | Callable,
        group_id: str,
        name: str = None,
        delay_seconds: int = 0,
    ):
        if delay_seconds < 0:
            log.warning(f"Negative delay for task {name}")

        name = name or id(fn)

        fq_name = f"{group_id}:{name}"
        asynciotask = asyncio.create_task(
            _task(fn, fq_name, delay_seconds), name=fq_name
        )

        def _on_task_done(t: asyncio.Task):
            group_id, name = t.get_name().split(":")
            if not t.cancelled():
                self._pop_task(group_id, name)

        asynciotask.add_done_callback(_on_task_done)

        self._add_task(asynciotask, group_id, name)

    def cancel(self, group_id: str):
        for task in self._pop_group(group_id).values():
            task.cancel()

    def now(self, tz=None) -> datetime:
        return datetime.now(tz)
