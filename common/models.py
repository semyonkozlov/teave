from datetime import time, datetime, timedelta
import warnings

import yaml
from pydantic import BaseModel, Field

from common.errors import EventDescriptionParsingError
from common.pika_pydantic import TeaveModel


DEFAULT_MAX_PARTICIPANTS = 100


class TeaventConfig(BaseModel):
    max: int = DEFAULT_MAX_PARTICIPANTS
    min: int = 1

    start_poll_at: datetime | time | None = None
    stop_poll_at: datetime | time | None = None

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


DEFAULT_START_POLL_DELTA = timedelta(hours=5)
DEFAULT_STOP_POLL_DELTA = timedelta(hours=2)

assert DEFAULT_STOP_POLL_DELTA < DEFAULT_START_POLL_DELTA


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

    @property
    def start_poll_at(self) -> datetime:
        if self.config.start_poll_at is None:
            return self._adjust(self.start - DEFAULT_START_POLL_DELTA)

        return self._adjust(self.config.start_poll_at)

    @property
    def stop_poll_at(self) -> datetime:
        if self.config.stop_poll_at is None:
            return self._adjust(self.start - DEFAULT_STOP_POLL_DELTA)

        return self._adjust(self.config.stop_poll_at)

    def _adjust(self, t: datetime | time):
        assert isinstance(t, (datetime, time)), f"unknown time type: {type(t)}"

        if isinstance(t, datetime):
            return t
        elif isinstance(t, time):
            return self.start.replace(
                hour=t.hour,
                minute=t.minute,
                second=t.second,
            )


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
