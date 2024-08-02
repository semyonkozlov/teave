from datetime import datetime

import yaml
from pydantic import BaseModel

from common.errors import EventDescriptionParsingError
from common.pika_pydantic import TeaveModel


class EventConfig(BaseModel):
    max: int | None = None
    min: int | None = None
    poll_at: str | None = None

    @staticmethod
    def from_description(description: str) -> "EventConfig | None":
        try:
            parsed = yaml.load(description, Loader=yaml.BaseLoader)
        except yaml.YAMLError as e:
            raise EventDescriptionParsingError from e

        if not isinstance(parsed, dict):
            return None

        config: dict = parsed.get("config")
        if not config:
            return None

        return EventConfig(**config)


class Recurrence(BaseModel):
    schedule: list[str] | None = None
    recurring_event_id: str | None = None


class Event(TeaveModel):
    id: str
    link: str

    summary: str
    description: str
    location: str

    start: datetime
    end: datetime

    recurrence: Recurrence | None = None

    participant_ids: list[str] = []
    state: str = "created"

    config: EventConfig | None = None

    communication_ids: list[str]

    @staticmethod
    def from_gcal_event(gcal_event_item: dict, communication_ids: list[str]) -> "Event":
        _ = gcal_event_item
        return Event(
            id=_["id"],
            link=_["htmlLink"],
            summary=_["summary"],
            description=_["description"],
            location=_["location"],
            start=datetime.fromisoformat(_["start"]["dateTime"]),
            end=datetime.fromisoformat(_["end"]["dateTime"]),
            recurrence=Recurrence(
                schedule=_.get("recurrence"),
                recurring_event_id=_.get("recurringEventId"),
            ),
            config=EventConfig.from_description(_["description"]),
            communication_ids=communication_ids,
        )

    @property
    def num_participants(self) -> int:
        return len(self.participant_ids)

    @property
    def packed(self) -> bool:
        return self.num_participants >= self.config.max


class FlowUpdate(TeaveModel):
    communication_ids: list[str] = []
    type: str
    data: dict = {}
