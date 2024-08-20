import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from attr import define

from common.models import Teavent
from eventmanager.errors import InconsistencyError, UnknownTeavent
from eventmanager.flow import TeaventFlow


@define(hash=True)
class TeaventManager:
    _listeners: list = []
    _statemachines: dict[str, TeaventFlow] = {}
    _tasks: dict[str, dict[str, asyncio.Task]] = defaultdict(dict)

    def list_teavents(self) -> list[Teavent]:
        return list(sm.teavent for sm in self._statemachines.values())

    def handle_teavent(self, teavent: Teavent):
        if teavent.id not in self._statemachines:
            logging.info(f"Got new event {teavent}")
            self._manage(teavent)
            return

        logging.info(f"Got known event {teavent}")
        managed_teavent = self._teavent_sm(teavent.id).teavent
        self._check_consistency(teavent, managed_teavent)
        return managed_teavent

    def handle_user_action(self, type: str, user_id: str, teavent_id: str):
        return self._teavent_sm(teavent_id).send(type, user_id=user_id)

    def _manage(self, teavent: Teavent):
        self._statemachines[teavent.id] = TeaventFlow(
            model=teavent,
            state_field="state",
            listeners=[*self._listeners, self],
        )

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

    def _schedule(self, task_name: str, teavent_id: str, delay):
        async def _task():
            await asyncio.sleep(delay)
            self._teavent_sm(teavent_id).send(task_name)

        teavent_tasks = self._tasks[teavent_id]

        task = asyncio.create_task(_task(), name=task_name)
        teavent_tasks[task_name] = task

        def _on_task_done(t: asyncio.Task):
            teavent_tasks.pop(t.get_name())

        task.add_done_callback(_on_task_done)

    def _cancel_tasks(self, teavent_id: str):
        for task in self._tasks[teavent_id]:
            task.cancel()

    def _now() -> datetime:
        return datetime.now()

    # SM actions

    def on_enter_created(self, model: Teavent):
        delay = model.start_poll_delay(self._now())
        self._schedule("start_poll", model.id, delay=delay)

    def on_enter_poll_open(self, model: Teavent):
        delay = model.stop_poll_delay(self._now())
        self._schedule("stop_poll", model.id, delay=delay)

    def on_enter_planned(self, model: Teavent):
        # TODO: check state reenter
        delay = model.start_delay(self._now())
        self._schedule("start_", model.id, delay=delay)

    def on_enter_started(self, model: Teavent):
        delay = model.end_delay(self._now())
        self._schedule("finish", model.id, delay=delay)

    def on_update(self, model: Teavent):
        self._cancel_tasks(model.id)

    def on_enter_finished(self): ...
