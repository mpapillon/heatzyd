import math
from datetime import UTC, date, datetime, timedelta
from enum import IntEnum
from zoneinfo import ZoneInfo

from app.domain.modes import Mode

_DAY_IN_SECONDS = 86400

MIN_DEROGATION_DAYS = 1
MAX_DEROGATION_DAYS = 255


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


def derogation_bounds(tz: ZoneInfo | None = None) -> tuple[date, date]:
    today = datetime.now(tz).date()
    return (
        today + timedelta(days=MIN_DEROGATION_DAYS),
        today + timedelta(days=MAX_DEROGATION_DAYS),
    )


def days_until(ends_at: datetime, *, now: datetime, tz: ZoneInfo | None = None) -> int:
    delta = _to_instant(ends_at, tz) - _to_instant(now, tz)
    days = math.ceil(delta.total_seconds() / _DAY_IN_SECONDS)
    if days < MIN_DEROGATION_DAYS:
        raise ValueError("ends_at must be in the future")
    if days > MAX_DEROGATION_DAYS:
        raise ValueError(f"derogation cannot last more than {MAX_DEROGATION_DAYS} days")
    return days


def _to_instant(value: datetime, tz: ZoneInfo | None) -> datetime:
    if value.tzinfo is None and tz is not None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(UTC)
