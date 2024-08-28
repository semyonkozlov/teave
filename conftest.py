from datetime import datetime, timedelta, timezone

import pytest

from common.models import Teavent, TeaventConfig


@pytest.fixture
def teavent():
    return Teavent(
        id="2gud232jsatd8pmnu0mnng0if2",
        link="https://www.example.com",
        summary="Тренировка 2",
        description="Тренировка по настольному теннису",
        location="Arena 2, 2 University St, T'bilisi, Georgia",
        start=datetime(2024, 7, 31, 21, 0, tzinfo=timezone(timedelta(hours=4))),
        end=datetime(2024, 7, 31, 23, 0, tzinfo=timezone(timedelta(hours=4))),
        rrule=["RRULE:FREQ=WEEKLY;WKST=MO;BYDAY=WE,MO,FR"],
        participant_ids=[],
        state="created",
        config=TeaventConfig(max=5, min=3, start_poll_at="11:00", stop_poll_at="14:00"),
        communication_ids=[],
    )
