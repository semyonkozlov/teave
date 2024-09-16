from datetime import datetime

from statemachine.exceptions import TransitionNotAllowed
import pytest

from common.models import Teavent
from common.flow import TeaventFlow

pytestmark = pytest.mark.skip(reason="Fix bug in python-statemachine")


@pytest.fixture
def flow(teavent: Teavent):
    return TeaventFlow(model=teavent, state_field="state")


def test_not_enough_participants(flow: TeaventFlow):
    assert flow.current_state == flow.created

    with pytest.raises(TransitionNotAllowed):
        flow.confirm(user_id="1")

    flow.start_poll()
    assert flow.current_state == flow.poll_open

    flow.confirm(user_id="1")
    flow.confirm(user_id="2")

    with pytest.raises(RuntimeError):
        flow.confirm(user_id="2")

    flow.stop_poll()
    assert flow.current_state == flow.cancelled

    assert flow.teavent.participant_ids == ["1", "2"]


def test_model_recreate(flow: TeaventFlow):
    tz = flow.teavent.tz

    flow.recreate(now=datetime(2024, 9, 16, 17, 0, tzinfo=tz), recurring_exceptions=[])

    assert flow.teavent.start == datetime(2024, 9, 16, 21, 0, tzinfo=tz)
