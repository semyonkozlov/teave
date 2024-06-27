from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Location(BaseModel):
    city: str


class UserType(str, Enum):
    LEAD = "lead"
    FOLLOWER = "follower"


class Submit(BaseModel):
    id: int = 0

    user_type: UserType
    event_type: str
    location: Location
    start: datetime = None
    end: datetime = None
    num_attendees: int


class Event(BaseModel):
    id: str

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


class FlowUpdate(BaseModel):
    event_id: str
    type: str
    data: dict
