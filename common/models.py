from datetime import datetime

from pydantic import BaseModel


class Location(BaseModel):
    city: str


class Submit(BaseModel):
    user_type: str
    event_type: str
    location: Location
    start: datetime = None
    end: datetime = None
