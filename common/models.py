from datetime import datetime
import warnings

import yaml
from pydantic import BaseModel, Field

from common.errors import EventDescriptionParsingError
from common.pika_pydantic import TeaveModel


DEFAULT_MAX_PARTICIPANTS = 100


class TeaventConfig(BaseModel):
    max: int = DEFAULT_MAX_PARTICIPANTS
    min: int = 0
    poll_at: str | None = None

    @staticmethod
    def from_description(description: str) -> "TeaventConfig":
        try:
            parsed = yaml.load(description, Loader=yaml.BaseLoader)
        except yaml.YAMLError as e:
            raise EventDescriptionParsingError from e

        if isinstance(parsed, dict) and (config := parsed.get("config")):
            return TeaventConfig(**config)

        return TeaventConfig()


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

    config: TeaventConfig = Field(default=TeaventConfig())

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
            config=TeaventConfig.from_description(_["description"]),
            communication_ids=communication_ids,
        )

    @property
    def num_participants(self) -> int:
        return len(self.participant_ids)

    @property
    def ready(self) -> bool:
        return self.num_participants >= self.config.min

    @property
    def packed(self) -> bool:
        if self.num_participants > self.config.max:
            warnings.warn("num_participants > config.max")
        return self.num_participants >= self.config.max

    def confirmed_by(self, user_id: str) -> bool:
        return user_id in self.participant_ids


class FlowUpdate(TeaveModel):
    teavent_id: str
    user_id: str = ""
    communication_ids: list[str] = []
    type: str
    data: dict = {}

    @staticmethod
    def for_teavent(teavent: Teavent, type: str, **data) -> "FlowUpdate":
        "Create FlowUpdate for `teavent`"

        return FlowUpdate(
            teavent_id=teavent.id,
            communication_ids=teavent.communication_ids,
            type=type,
            data=data,
        )
