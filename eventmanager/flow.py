from common.models import Teavent

from statemachine import State, StateMachine


class TeaventFlow(StateMachine):
    # states
    created = State(initial=True)
    poll_open = State()
    planned = State()
    started = State()
    cancelled = State(final=True)
    finished = State(final=True)

    # transitions
    # fmt: off
    start_poll = created.to(poll_open)
    confirm = poll_open.to(planned, cond="packed") | poll_open.to(poll_open) | planned.to(planned, unless="packed")
    reject = planned.to(planned) | poll_open.to(poll_open)
    stop_poll = poll_open.to(planned, cond="ready") | poll_open.to(cancelled, unless="ready")
    cancel = cancelled.from_(poll_open, planned)
    start_ = planned.to(started)
    finish = started.to(finished)
    # fmt: on

    @property
    def teavent(self) -> Teavent:
        return self.model

    @planned.to(planned)
    def reject(self): ...

    @poll_open.to(poll_open)
    def reject(self): ...

    def on_confirm(self, user_id: str, model: Teavent):
        model.participant_ids.append(user_id)

    def on_reject(self, user_id: str, model: Teavent):
        model.participant_ids.remove(user_id)

    @confirm.validators
    def not_confirmed_before(self, user_id: str, model: Teavent):
        if model.confirmed_by(user_id):
            raise RuntimeError("Already confirmed")