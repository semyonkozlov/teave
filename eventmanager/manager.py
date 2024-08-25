import asyncio
from collections.abc import Callable
import logging
from collections import defaultdict
from datetime import datetime

from attr import define

from common.models import Teavent
from eventmanager.errors import TeaventIsInFinalState, UnknownTeavent
from eventmanager.flow import TeaventFlow
from eventmanager.transitions_logger import TransitionsLogger

log = logging.getLogger(__name__)


@define(eq=False)  # eq=False for hashing by id
class TeaventManager:
    _listeners: list = []
    _statemachines: dict[str, TeaventFlow] = {}
    _tasks: dict[str, dict[str, asyncio.Task]] = defaultdict(dict)

    _finalized: dict[str, TeaventFlow] = {}

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
        if sm.current_state not in TeaventFlow.final_states:
            raise RuntimeError("Attempt to drop teavent in non-final state")
        return sm

    def _manage(self, teavent: Teavent):
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
        # TODO
        return 5
        # return (t - datetime.now(tz=t.tzinfo)).total_seconds()

    def _get_moved_teavents(self, recurring_teavent_id: str) -> list[Teavent]:
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
            model.id,
            delay_seconds=self._delay_seconds(model.start_poll_at),
        )

    @TeaventFlow.poll_open.enter
    def _schedule_stop_poll(self, model: Teavent):
        self._schedule(
            TeaventFlow.stop_poll,
            model.id,
            delay_seconds=self._delay_seconds(model.stop_poll_at),
        )

    @TeaventFlow.planned.enter
    def _schedule_start(self, model: Teavent):
        self._schedule(
            TeaventFlow.start_, model.id, delay_seconds=self._delay_seconds(model.start)
        )

    @TeaventFlow.started.enter
    def _schedule_end(self, model: Teavent):
        self._schedule(
            TeaventFlow.end, model.id, delay_seconds=self._delay_seconds(model.end)
        )

    @TeaventFlow.cancelled.enter
    @TeaventFlow.ended.enter
    def recreate_or_finalize(self, model: Teavent):
        sm = self._teavent_sm(model.id)
        if model.is_reccurring:
            sm.recreate(
                now=datetime.now(), moved_from_series=self._get_moved_teavents(model.id)
            )
        else:
            sm.finalize()
