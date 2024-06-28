from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class Location(BaseModel):
    city: str


class UserType(str, Enum):
    LEAD = "lead"
    FOLLOWER = "follower"


class Submit(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    chat_id: str = None

    user_type: UserType
    event_type: str
    location: Location
    start: datetime | None = None
    end: datetime | None = None
    num_attendees: int

    delivery_tag: int = 0


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)

    lead: Submit
    followers: list[Submit] = []
    state: str = "created"
    num_confirmations: int = 0

    delivery_tag: int = 0

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


class FlowUpdate(BaseModel):
    chat_id: str
    type: str
    data: dict = {}
