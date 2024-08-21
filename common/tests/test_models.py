import json
from pathlib import Path
from datetime import datetime, timedelta, time

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

    assert config.start_poll_at == time(hour=11)


def test_teavent_from_gcal_event(gcal_event_items):
    for item in gcal_event_items:
        Teavent.from_gcal_event(item, communication_ids=[])
