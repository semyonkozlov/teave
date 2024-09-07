import json
from pathlib import Path
from datetime import datetime, time

import pytest

from common.models import TeaventConfig, Teavent


@pytest.fixture
def testdatadir():
    path = Path("common/tests/data")
    assert path.exists()
    return path


@pytest.fixture
def gcal_event_items(testdatadir: Path):
    with open(testdatadir / "event_items.json") as f:
        return json.load(f)


@pytest.fixture
def description(testdatadir: Path):
    with open(testdatadir / "description.yaml") as f:
        return f.read()


def test_config_from_description(description: str):
    config = TeaventConfig.from_description(description)
    assert config is not None

    assert config.min == 2
    assert config.max == 8

    assert config.start_poll_at == time(11, 00)


def test_teavent_from_gcal_event(gcal_event_items):
    for item in gcal_event_items:
        Teavent.from_gcal_event(item, communication_ids=[])


@pytest.fixture
def now(teavent):
    return datetime(2024, 8, 27, tzinfo=teavent.tz)


def test_rrule_simple(teavent: Teavent, now: datetime):
    assert teavent.is_reccurring

    teavent.adjust(now, [])
    assert teavent.start == datetime(2024, 8, 28, 21, 00, tzinfo=teavent.tz)

    assert teavent.config.start_poll_at == time(11, 00)
    assert teavent.start_poll_at == datetime(2024, 8, 28, 11, 00, tzinfo=teavent.tz)


@pytest.fixture
def recurring_exception():
    return Teavent(
        id="2gud232jsatd8pmnu0mnng0if2_20240828T150000Z",
        cal_id="1b9c486302b14656cfb10dbdc28240b39054fc6b2c2060928c4c5d0aeccbb4a2@g",
        summary="Тренировка 2",
        description="Тренировка по настольному теннису",
        location="Arena 2, 2 University St, T'bilisi, Georgia",
        start=datetime(2024, 8, 28, 19, 0),
        end=datetime(2024, 8, 28, 21, 0),
        recurring_event_id="2gud232jsatd8pmnu0mnng0if2",
        participant_ids=[],
        state="created",
        config=TeaventConfig(max=5, min=3, start_poll_at="11:00", stop_poll_at="14:00"),
        communication_ids=[],
    )


def test_rrule_with_recurring_exceptions(
    now: datetime, teavent: Teavent, recurring_exception: Teavent
):
    teavent.adjust(now, [recurring_exception])

    assert teavent.start == datetime(2024, 8, 30, 21, 00, tzinfo=teavent.tz)
    assert teavent.start_poll_at == datetime(2024, 8, 30, 11, 00, tzinfo=teavent.tz)
