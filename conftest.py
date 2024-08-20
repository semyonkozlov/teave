from datetime import datetime

import pytest

from common.models import Recurrence, Teavent, TeaventConfig


@pytest.fixture
def teavent():
    return Teavent(
        id="2gud232jsatd8pmnu0mnng0if2",
        link="https://www.example.com",
        summary="Тренировка 2",
        description="Тренировка по настольному теннису",
        location="Arena 2, 2 University St, T'bilisi, Georgia",
        start=datetime(2024, 7, 31, 21, 0),
        end=datetime(2024, 7, 31, 23, 0),
        recurrence=Recurrence(
            schedule=["RRULE:FREQ=WEEKLY;WKST=MO;BYDAY=WE,MO,FR"],
        ),
        participant_ids=[],
        state="created",
        config=TeaventConfig(max=5, min=3),
        communication_ids=[],
    )
