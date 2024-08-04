from datetime import datetime

import yaml
from pydantic import BaseModel, Field

from common.errors import EventDescriptionParsingError
from common.pika_pydantic import TeaveModel


DEFAULT_MAX_PARTICIPANTS = 100


class EventConfig(BaseModel):
    max: int = DEFAULT_MAX_PARTICIPANTS
    min: int = 0
    poll_at: str | None = None

    @staticmethod
    def from_description(description: str) -> "EventConfig":
        try:
            parsed = yaml.load(description, Loader=yaml.BaseLoader)
        except yaml.YAMLError as e:
            raise EventDescriptionParsingError from e

        if isinstance(parsed, dict) and (config := parsed.get("config")):
            return EventConfig(**config)

        return EventConfig()


class Recurrence(BaseModel):
    schedule: list[str] | None = None
    recurring_event_id: str | None = None


class Teavent(TeaveModel):
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

    config: EventConfig = Field(default=EventConfig())

    communication_ids: list[str]

    @staticmethod
    def from_gcal_event(
        gcal_event_item: dict, communication_ids: list[str]
    ) -> "Teavent":
        _ = gcal_event_item
        return Teavent(
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
    def ready(self) -> bool:
        return self.num_participants >= self.config.min


class FlowUpdate(TeaveModel):
    event_id: str
    communication_ids: list[str] = []
    type: str
    data: dict = {}

    @staticmethod
    def for_teavent(self, event: Teavent, type: str, **data) -> "FlowUpdate":
        "Create FlowUpdate fro event `event`"

        return FlowUpdate(
            event_id=event.id,
            communication_ids=event.communication_ids,
            type=type,
            data=data,
        )
