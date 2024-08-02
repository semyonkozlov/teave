import json
from pathlib import Path

import pytest

from common.models import EventConfig, Event


@pytest.fixture
def testdatadir():
    path = Path("common/tests/data")
    assert path.exists()
    return path


@pytest.fixture
def gcal_event_items(testdatadir):
    with open(testdatadir / "event_items.json") as f:
        return json.load(f)


@pytest.fixture
def description(testdatadir):
    with open(testdatadir / "description.yaml") as f:
        return f.read()


def test_config_from_description(description):
    config = EventConfig.from_description(description)
    assert config is not None

    assert config.min == 2
    assert config.max == 8
    assert config.poll_at == "11:00"


def test_event_from_gcal_event(gcal_event_items):
    for item in gcal_event_items:
        Event.from_gcal_event(item, communication_ids=[])
