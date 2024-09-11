from base64 import b64encode
from datetime import time, datetime, timedelta, date, timezone
import logging
import warnings

from dateutil.rrule import rruleset, rrulestr
import yaml
import pydantic
from pydantic import Field

from common.errors import EventDescriptionParsingError
from common.pika_pydantic import TeaveModel

log = logging.getLogger(__name__)

DEFAULT_MAX_PARTICIPANTS = 100


class TeaventConfig(pydantic.BaseModel):
    max: int = DEFAULT_MAX_PARTICIPANTS
    min: int = 1

    start_poll_at: datetime | time | None = None
    stop_poll_at: datetime | time | None = None

    model_config = {"extra": "forbid"}

    @staticmethod
    def from_description(description: str) -> "TeaventConfig":
        try:
            parsed = yaml.load(description, Loader=yaml.BaseLoader)
            if isinstance(parsed, dict) and (config := parsed.get("config")):
                return TeaventConfig(**config)
        except (pydantic.ValidationError, yaml.YAMLError) as e:
            raise EventDescriptionParsingError from e

        return TeaventConfig()


DEFAULT_START_POLL_DELTA = timedelta(hours=5)
DEFAULT_STOP_POLL_DELTA = timedelta(hours=2)

assert DEFAULT_STOP_POLL_DELTA < DEFAULT_START_POLL_DELTA


class Teavent(TeaveModel):
    id: str = Field(alias="_id")
    cal_id: str

    summary: str
    description: str
    location: str | None

    start: datetime
    end: datetime

    rrule: list[str] | None = None
    recurring_event_id: str | None = None

    participant_ids: list[str] = []
    state: str = "created"

    config: TeaventConfig = Field(default=TeaventConfig())

    communication_ids: list[str]

    model_config = {"extra": "forbid", "populate_by_name": True}

    @staticmethod
    def from_gcal_event(
        gcal_event_item: dict[str, str], communication_ids: list[str]
    ) -> "Teavent":
        _ = gcal_event_item
        description = _["description"].replace("\xa0", " ")

        return Teavent(
            id=_["id"],
            cal_id=_calid_from_email(_["organizer"]["email"]),
            summary=_["summary"],
            description=description,
            location=_.get("location"),
            start=datetime.fromisoformat(_["start"]["dateTime"]),
            end=datetime.fromisoformat(_["end"]["dateTime"]),
            rrule=_.get("recurrence"),
            recurring_event_id=_.get("recurringEventId"),
            config=TeaventConfig.from_description(description),
            communication_ids=communication_ids,
        )

    @property
    def link(self) -> str:
        if self.is_reccurring:
            start = self.start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            eid = f"{self.id}_{start} {self.cal_id}"
        else:
            # TODO: check non-recurring events
            eid = f"{self.id} {self.cal_id}"

        b64eid = b64encode(eid.encode()).rstrip(b"=").decode()
        return f"https://www.google.com/calendar/event?eid={b64eid}"

    @property
    def num_participants(self) -> int:
        return len(self.participant_ids)

    @property
    def ready(self) -> bool:
        return self.num_participants >= self.config.min

    @property
    def is_reccurring(self) -> bool:
        return bool(self.rrule)

    @property
    def is_recurring_exception(self) -> bool:
        return bool(self.recurring_event_id)

    def confirmed_by(self, user_id: str) -> bool:
        return user_id in self.participant_ids

    @property
    def start_poll_at(self) -> datetime:
        if self.config.start_poll_at is None:
            return self._to_dt(self.start - DEFAULT_START_POLL_DELTA)

        return self._to_dt(self.config.start_poll_at)

    @property
    def stop_poll_at(self) -> datetime:
        if self.config.stop_poll_at is None:
            return self._to_dt(self.start - DEFAULT_STOP_POLL_DELTA)

        return self._to_dt(self.config.stop_poll_at)

    @property
    def tz(self):
        return self.start.tzinfo

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def _to_dt(self, t: datetime | time) -> datetime:
        assert isinstance(t, (datetime, time)), f"unknown time type: {type(t)}"

        if isinstance(t, datetime):
            return t
        elif isinstance(t, time):
            return self.start.replace(
                hour=t.hour,
                minute=t.minute,
                second=t.second,
            )

    def _rruleset(self) -> rruleset:
        rr = rruleset()
        for r in self.rrule:
            rr.rrule(rrulestr(r, dtstart=self.start))
        return rr

    def adjust(self, now: datetime, recurring_exceptions: list["Teavent"]):
        assert self.is_reccurring

        rr = self._rruleset()
        for t in recurring_exceptions:
            assert t.rrule is None
            assert t.recurring_event_id is not None
            assert t.recurring_event_id == self.id
            exdate = datetime.combine(t.start.date(), self.start.time(), tzinfo=self.tz)
            rr.exdate(exdate)

        next_dt: datetime = rr.after(now)
        self.shift_to(next_dt.date())

    def shift_to(self, new_date: date):
        duration = self.duration

        self.start = datetime.combine(new_date, self.start.time(), self.start.tzinfo)
        self.end = self.start + duration

        log.info(f"Shift teavent {self.id} to {self.start}")

    def has_reserve(self) -> bool:
        return bool(self.reserve_participant_ids)

    @property
    def effective_participant_ids(self) -> list[str]:
        return self.participant_ids[: self.config.max]

    @property
    def reserve_participant_ids(self) -> list[str]:
        return self.participant_ids[self.config.max :]


def _calid_from_email(email: str) -> str:
    return email.split("@")[0] + "@g"
