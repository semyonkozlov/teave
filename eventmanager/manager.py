import logging
from collections.abc import Callable
from datetime import datetime

from common.executors import Executor, Task
from common.models import Teavent
from eventmanager.errors import (
    TeaventIsInFinalState,
    UnknownTeavent,
)
from eventmanager.flow import TeaventFlow
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

    def handle_teavent(self, teavent: Teavent) -> Teavent | None:
        log.info(
            f"Handle teavent {teavent.id} state={teavent.state} delivery_tag={teavent._delivery_tag}"
        )

        if teavent.id not in self._statemachines:
            log.info(f"Got new teavent {teavent}")
            self._manage(teavent)
            return

        managed_teavent = self._teavent_sm(teavent.id).teavent

        log.info(f"Teavent {teavent.id} is managed with state={managed_teavent.state}")
        return managed_teavent

    def handle_user_action(self, type: str, user_id: str, teavent_id: str):
        return self._teavent_sm(teavent_id).send(type, user_id=user_id)

    def drop(self, teavent_id: str):
        sm = self._statemachines.pop(teavent_id)
        if not sm.current_state.final:
            raise RuntimeError("Attempt to drop teavent in non-final state")
        return sm

    def _manage(self, teavent: Teavent):
        if teavent.is_reccurring:
            # all recurring_exceptions must be managed
            # TODO: handle recurring exceptions properly
            teavent.shift_timings(
                self._executor.now(teavent.tz),
                self._get_recurring_exceptions(teavent.id),
            )

        sm = TeaventFlow(
            model=teavent,
            state_field="state",
            listeners=[*self._listeners, self, TransitionsLogger()],
        )

        if sm.current_state.final:
            raise TeaventIsInFinalState(teavent)

        self._statemachines[teavent.id] = sm
        self._init(sm)

    def _init(self, sm: TeaventFlow):
        match sm.current_state:
            case TeaventFlow.created:
                self._schedule_start_poll(sm.teavent)
            case TeaventFlow.poll_open:
                self._schedule_stop_poll(sm.teavent)
            case TeaventFlow.planned:
                self._schedule_start(sm.teavent)
            case TeaventFlow.started:
                self._schedule_end(sm.teavent)

    def _teavent_sm(self, teavent_id: str) -> TeaventFlow:
        try:
            return self._statemachines[teavent_id]
        except KeyError as e:
            raise UnknownTeavent(teavent_id) from e

    def _schedule(self, trigger: Callable, teavent: Teavent, at: datetime):
        task = Task(
            fn=lambda: trigger(self._teavent_sm(teavent.id)),
            name=f"{teavent.id}:{trigger.name}",
        )
        delay = (at - self._executor.now(tz=at.tzinfo)).total_seconds()
        self._executor.schedule(task, delay_seconds=delay)

    def _get_recurring_exceptions(self, recurring_teavent_id: str) -> list[Teavent]:
        return [
            t
            for t in self.list_teavents()
            if t.recurring_event_id == recurring_teavent_id
        ]

    # SM actions

    # TODO: check state reenter (ex planned -> planned)

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
                now=self._executor.now(tz=model.tz),
                recurring_exceptions=self._get_recurring_exceptions(model.id),
            )
        else:
            sm.finalize()
