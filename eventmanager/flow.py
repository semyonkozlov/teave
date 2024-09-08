from datetime import datetime

from common.models import Teavent
from eventmanager.errors import TeaventIsInFinalState

from statemachine import State, StateMachine


class TeaventFlow(StateMachine):
    # states
    created = State(initial=True)
    poll_open = State()
    planned = State()
    started = State()
    cancelled = State()
    ended = State()

    finalized = State(final=True)

    # transitions
    # fmt: off
    start_poll = created.to(poll_open)
    confirm = poll_open.to(planned, cond="packed") | poll_open.to(poll_open) | planned.to(planned, unless="packed")
    reject = planned.to(planned) | poll_open.to(poll_open)
    stop_poll = poll_open.to(planned, cond="ready") | poll_open.to(cancelled, unless="ready")
    cancel = cancelled.from_(poll_open, planned)
    start_ = planned.to(started)
    end = started.to(ended)
    finalize = finalized.from_(cancelled, ended)
    recreate = created.from_(cancelled, ended)

    init = created.to.itself() | poll_open.to.itself() | planned.to.itself() | started.to.itself() | cancelled.to.itself() | ended.to.itself()
    # fmt: on

    @property
    def teavent(self) -> Teavent:
        return self.model

    @init.validators
    def not_in_final_state(self, model: Teavent):
        if self.current_state.final:
            raise TeaventIsInFinalState(model)

    @init.on
    def adjust_timings(self, model: Teavent, now: datetime, recurring_exceptions: list):
        if model.is_reccurring:
            model.adjust(now, recurring_exceptions)

    @confirm.on
    def add_participant(self, user_id: str, model: Teavent):
        model.participant_ids.append(user_id)

    @reject.on
    def remove_participant(self, user_id: str, model: Teavent):
        model.participant_ids.remove(user_id)

    @confirm.validators
    def not_confirmed_before(self, user_id: str, model: Teavent):
        if model.confirmed_by(user_id):
            raise RuntimeError("Already confirmed")

    @recreate.validators
    def is_recurring(self, model: Teavent):
        if not model.is_reccurring:
            raise RuntimeError("Teavent must be recurring to recreate")

    @recreate.on
    def reset_participants(self, model: Teavent):
        model.participant_ids = []
