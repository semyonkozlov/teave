from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from common.pika_pydantic import TeaveModel


class Recurrence(BaseModel):
    schedule: list[str] | None = None
    recurring_event_id: str | None = None


class UserType(str, Enum):
    LEAD = "lead"
    FOLLOWER = "follower"


# TODO what is the relatiotionship between Submit, Event, Announcement? need refactor prbly


class Submit(TeaveModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    chat_id: str = None

    user_type: UserType
    event_type: str

    start: datetime | None = None
    end: datetime | None = None
    num_attendees: int


class Event(TeaveModel):
    id: str = Field(default_factory=lambda: uuid4().hex)

    lead: Submit
    followers: list[Submit] = []
    state: str = "created"
    num_confirmations: int = 0

    @property
    def confirmed(self) -> bool:
        return self.num_confirmations == self.num_attendees

    @property
    def num_attendees(self) -> int:
        return self.lead.num_attendees

    @property
    def packed(self) -> bool:
        return len(self.followers) + 1 >= self.lead.num_attendees

    @property
    def type(self) -> str:
        return self.lead.event_type

    @property
    def chat_id(self) -> str:
        return self.lead.chat_id


class Announcement(TeaveModel):
    id: str

    summary: str
    description: str
    location: str

    start: datetime
    end: datetime

    recurrence: Recurrence

    @classmethod
    def from_gcal_event(cls, gcal_event_item: dict) -> "Announcement":
        _ = gcal_event_item
        return Announcement(
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
        )


class FlowUpdate(TeaveModel):
    chat_id: str
    type: str
    data: dict = {}
