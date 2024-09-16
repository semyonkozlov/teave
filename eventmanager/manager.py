import logging
from collections.abc import Callable
from datetime import datetime

from common.executors import Executor
from common.models import Teavent
from common.errors import TeaventIsManaged, UnknownTeavent
from common.flow import TeaventFlow
from eventmanager.transitions_logger import TransitionsLogger

log = logging.getLogger(__name__)


class TeaventManager:
    def __init__(
        self,
        executor: Executor,
        listeners: list = None,
    ):
        self._executor: Executor = executor
        self._listeners: list = listeners or []

        self._statemachines: dict[str, TeaventFlow] = {}

    def list_teavents(self) -> list[Teavent]:
        return list(sm.teavent for sm in self._statemachines.values())

    def handle_teavent(self, teavent: Teavent):
        log.info(f"Handle teavent {teavent}")

        if teavent.id not in self._statemachines:
            self._manage(teavent)
        else:
            raise TeaventIsManaged(teavent)

    def handle_user_action(self, type: str, user_id: str, teavent_id: str):
        sm = self._teavent_sm(teavent_id)
        sm.send(
            type,
            user_id=user_id,
            now=self._executor.now(sm.teavent.tz),
            recurring_exceptions=self._get_recurring_exceptions(sm.teavent.id),
        )
        return sm.teavent

    def _manage(self, teavent: Teavent):
        assert teavent.id not in self._statemachines

        sm = TeaventFlow(
            model=teavent,
            state_field="state",
            listeners=[*self._listeners, self, TransitionsLogger()],
        )

        # all recurring_exceptions must be managed
        # TODO: handle recurring exceptions properly
        sm.init(
            now=self._executor.now(teavent.tz),
            recurring_exceptions=self._get_recurring_exceptions(teavent.id),
        )
        self._statemachines[teavent.id] = sm

    def _teavent_sm(self, teavent_id: str) -> TeaventFlow:
        try:
            return self._statemachines[teavent_id]
        except KeyError as e:
            raise UnknownTeavent(teavent_id) from e

    def _schedule(self, trigger: Callable, teavent: Teavent, at: datetime):
        group_id = f"{teavent.id}_sm"

        try:
            self._executor.cancel(group_id)
            log.info(f"Task group {group_id} is cancelled")
        except KeyError:
            pass

        delay = (at - self._executor.now(tz=at.tzinfo)).total_seconds()
        self._executor.schedule(
            lambda: trigger(self._teavent_sm(teavent.id)),
            group_id=group_id,
            name=trigger.name,
            delay_seconds=delay,
        )

    def _get_recurring_exceptions(self, recurring_teavent_id: str) -> list[Teavent]:
        return [
            t
            for t in self.list_teavents()
            if t.recurring_event_id == recurring_teavent_id
        ]

    # SM actions

    @TeaventFlow.created.enter
    def _schedule_start_poll(self, model: Teavent):
        self._schedule(
            TeaventFlow.start_poll,
            model,
            at=model.start_poll_at,
        )

    @TeaventFlow.poll_open.enter
    def _schedule_stop_poll(self, model: Teavent):
        self._schedule(
            TeaventFlow.stop_poll,
            model,
            at=model.stop_poll_at,
        )

    @TeaventFlow.planned.enter
    def _schedule_start(self, model: Teavent):
        self._schedule(
            TeaventFlow.start_,
            model,
            at=model.start,
        )

    @TeaventFlow.started.enter
    def _schedule_end(self, model: Teavent):
        self._schedule(TeaventFlow.end, model, at=model.end)

    @TeaventFlow.cancelled.enter
    @TeaventFlow.ended.enter
    def _recreate_or_finalize(self, model: Teavent):
        sm = self._teavent_sm(model.id)
        if model.is_reccurring:
            sm.recreate(
                now=model.end,  # allows correctly get next recurring instance
                recurring_exceptions=self._get_recurring_exceptions(model.id),
            )
        else:
            sm.finalize()

    @TeaventFlow.finalized.enter
    def _drop(self, model: Teavent):
        self._statemachines.pop(model.id)
