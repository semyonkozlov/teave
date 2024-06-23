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
    lead: Submit
    followers: list[Submit] = []

    @property
    def packed(self) -> bool:
        return len(self.followers) + 1 >= self.lead.num_attendees

    @property
    def type(self) -> str:
        return self.lead.event_type
