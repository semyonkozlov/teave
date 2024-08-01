from datetime import datetime

from pydantic import BaseModel

from common.pika_pydantic import TeaveModel


class Config(BaseModel):
    max_participants: int | None = None
    min_participants: int | None = None


class Recurrence(BaseModel):
    schedule: list[str] | None = None
    recurring_event_id: str | None = None


class Event(TeaveModel):
    id: str

    summary: str
    description: str
    location: str

    start: datetime
    end: datetime

    recurrence: Recurrence | None = None

    participant_ids: list[str] = []
    state: str = "created"

    config: Config | None = None

    communication_ids: list[str]

    @classmethod
    def from_gcal_event(
        cls, gcal_event_item: dict, communication_ids: list[str]
    ) -> "Event":
        _ = gcal_event_item
        return Event(
            id=_["id"],
            summary=_["summary"],
            description=_["description"],
            location=_["location"],
            start=datetime.fromisoformat(_["start"]["dateTime"]),
            end=datetime.fromisoformat(_["end"]["dateTime"]),
            recurrence=Recurrence(
                schedule=_.get("recurrence"),
                recurring_event_id=_.get("recurringEventId"),
            ),
            communication_ids=communication_ids,
        )

    @property
    def num_participants(self) -> int:
        return len(self.participant_ids)

    @property
    def packed(self) -> bool:
        return self.num_participants >= self.config.max_participants


class FlowUpdate(TeaveModel):
    communication_ids: list[str] = []
    type: str
    data: dict = {}
