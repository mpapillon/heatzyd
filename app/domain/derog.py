import math
from datetime import UTC, datetime
from enum import IntEnum
from zoneinfo import ZoneInfo

from app.domain.modes import Mode

_DAY_IN_SECONDS = 86400


class DerogMode(IntEnum):
    NONE = 0
    VACATIONS = 1
    BOOST = 2
    PRESENCE = 3

    @property
    def mode(self) -> Mode | None:
        match self:
            case DerogMode.BOOST:
                return Mode.CONFORT
            case DerogMode.VACATIONS:
                return Mode.HORS_GEL
            case _:
                return None


def days_until(ends_at: datetime, *, now: datetime, tz: ZoneInfo | None = None) -> int:
    delta = _to_instant(ends_at, tz) - _to_instant(now, tz)
    days = math.ceil(delta.total_seconds() / _DAY_IN_SECONDS)
    if days < 1:
        raise ValueError("ends_at must be in the future")
    if days > 255:
        raise ValueError("derogation cannot last more than 255 days")
    return days


def _to_instant(value: datetime, tz: ZoneInfo | None) -> datetime:
    if value.tzinfo is None and tz is not None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(UTC)
