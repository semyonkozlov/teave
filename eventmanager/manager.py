import asyncio
from collections.abc import Callable
import logging
from collections import defaultdict
from datetime import datetime

from attr import define

from common.models import Teavent
from eventmanager.errors import InconsistencyError, UnknownTeavent
from eventmanager.flow import TeaventFlow
from eventmanager.transitions_logger import TransitionsLogger

log = logging.getLogger("manager")


@define(eq=False)  # eq=False for hashing by id
class TeaventManager:
    _listeners: list = []
    _statemachines: dict[str, TeaventFlow] = {}
    _tasks: dict[str, dict[str, asyncio.Task]] = defaultdict(dict)

    def list_teavents(self) -> list[Teavent]:
        return list(sm.teavent for sm in self._statemachines.values())

    def handle_teavent(self, teavent: Teavent):
        if teavent.id not in self._statemachines:
            log.info(f"Got new teavent {teavent}")
            self._manage(teavent)
            return

        log.info(f"Got known teavent {teavent.id}")
        managed_teavent = self._teavent_sm(teavent.id).teavent
        self._check_consistency(teavent, managed_teavent)
        return managed_teavent

    def handle_user_action(self, type: str, user_id: str, teavent_id: str):
        return self._teavent_sm(teavent_id).send(type, user_id=user_id)

    def _manage(self, teavent: Teavent):
        sm = TeaventFlow(
            model=teavent,
            state_field="state",
            listeners=[*self._listeners, self, TransitionsLogger()],
        )
        self._statemachines[teavent.id] = sm
        sm.init()

    def _check_consistency(self, new_teavent: Teavent, managed_teavent: Teavent):
        assert new_teavent.id == managed_teavent.id

        if new_teavent.state != managed_teavent.state:
            # TODO handle it somewhere
            raise InconsistencyError(
                f"Event {managed_teavent.id} has state '{managed_teavent.state}', but '{new_teavent.state}' received"
            )

    def _teavent_sm(self, teavent_id: str) -> TeaventFlow:
        try:
            return self._statemachines[teavent_id]
        except KeyError as e:
            raise UnknownTeavent(teavent_id) from e

    def _schedule(self, event: Callable, teavent_id: str, delay_seconds: int):
        task_name = f"{teavent_id}:{event.name}"

        log.info(f"Schedule '{task_name}' to run in {delay_seconds} seconds")

        async def _task():
            log.info(f"Sleeping {delay_seconds} seconds...")
            await asyncio.sleep(delay_seconds)
            event(self._teavent_sm(teavent_id))

        teavent_tasks = self._tasks[teavent_id]

        task = asyncio.create_task(_task(), name=task_name)
        teavent_tasks[task_name] = task

        def _on_task_done(t: asyncio.Task):
            teavent_tasks.pop(t.get_name())
            log.info(f"Task '{task_name}' is done, result: {t.result()}")

        task.add_done_callback(_on_task_done)

    def _cancel_tasks(self, teavent_id: str):
        for task in self._tasks[teavent_id]:
            task.cancel()

    def _delay_seconds(self, t: datetime) -> int:
        return (t - datetime.now(tz=t.tzinfo)).total_seconds()

    # SM actions

    # TODO: check state reenter

    def on_enter_created(self, model: Teavent):
        self._schedule(
            TeaventFlow.start_poll,
            model.id,
            delay_seconds=self._delay_seconds(model.start_poll_at),
        )

    def on_enter_poll_open(self, model: Teavent):
        self._schedule(
            TeaventFlow.stop_poll,
            model.id,
            delay_seconds=self._delay_seconds(model.stop_poll_at),
        )

    def on_enter_planned(self, model: Teavent):
        self._schedule(
            TeaventFlow.start_, model.id, delay_seconds=self._delay_seconds(model.start)
        )

    def on_enter_started(self, model: Teavent):
        self._schedule(
            TeaventFlow.finish, model.id, delay_seconds=self._delay_seconds(model.end)
        )

    def on_update(self, model: Teavent):
        self._cancel_tasks(model.id)

    def on_enter_finished(self): ...
