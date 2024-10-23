from datetime import datetime

from common.models import Teavent
from common.errors import TeaventIsInFinalState

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
    confirm = created.to.itself(internal=True, cond="forced") | poll_open.to.itself(internal=True) | planned.to.itself(internal=True)
    reject = created.to.itself(internal=True) | poll_open.to.itself(internal=True) | planned.to.itself(internal=True, validators="has_reserve") 
    stop_poll = poll_open.to(planned, cond="ready") | poll_open.to(cancelled, unless="ready")
    cancel = cancelled.from_(created, poll_open, planned)
    start_ = planned.to(started)
    i_am_late = started.to.itself(internal=True)
    end = started.to(ended)
    finalize = finalized.from_(cancelled, ended)
    recreate = created.from_(created, cancelled, ended)

    init = created.to.itself() | poll_open.to.itself() | planned.to.itself() | started.to.itself() | cancelled.to.itself() | ended.to.itself()
    # fmt: on

    @property
    def teavent(self) -> Teavent:
        return self.model

    def forced(self, force: bool) -> bool:
        return force

    def has_reserve(self, model: Teavent, force: bool):
        if force:
            return

        if not model.has_reserve():
            raise RuntimeError("No reserve")

    @poll_open.exit
    def set_effective_max(self, model: Teavent):
        model.effective_max = len(model.participant_ids)

    @i_am_late.on
    def add_latee(self, user_id: str, model: Teavent):
        if user_id not in model.latees:
            model.latees.append(user_id)

    @init.validators
    def not_in_final_state(self, model: Teavent):
        if self.current_state.final:
            raise TeaventIsInFinalState(model)

    @recreate.on
    def adjust_timings(self, model: Teavent, now: datetime, recurring_exceptions: list):
        model.adjust(now, recurring_exceptions)

    @confirm.on
    def add_participant(self, user_id: str, model: Teavent):
        model.participant_ids.append(user_id)

    @confirm.validators
    def not_confirmed_before(self, user_id: str, model: Teavent):
        if model.confirmed_by(user_id):
            raise RuntimeError(f"'{user_id}' has already confirmed")

    @i_am_late.validators
    @reject.validators
    def confirmed_before(self, user_id: str, model: Teavent):
        if not model.confirmed_by(user_id):
            raise RuntimeError(f"it is not confirmed by '{user_id}'")

    @reject.on
    def remove_participant(self, user_id: str, model: Teavent):
        model.participant_ids.remove(user_id)

    @recreate.validators
    def is_recurring(self, model: Teavent):
        if not model.is_reccurring:
            raise RuntimeError("Teavent must be recurring to recreate")

    @recreate.on
    def reset_participants(self, model: Teavent):
        model.participant_ids = []
        model.latees = []
        model.effective_max = None
