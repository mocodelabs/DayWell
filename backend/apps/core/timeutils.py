"""Time-zone helpers. All absolute timestamps are stored in UTC; users' IANA zones are applied at the edges.

DST policy (documented in docs/DATA_MODEL.md and docs/NOTIFICATIONS_AND_ALARMS.md):

* Nonexistent local time (spring-forward gap, e.g. 02:30 when clocks jump 02:00→03:00):
  the time is shifted forward by the length of the gap (02:30 → 03:30). This is the RFC 5545 §3.3.5 behaviour.
* Ambiguous local time (fall-back, e.g. 01:30 occurs twice): the FIRST occurrence (the earlier instant) is used.

Both rules fall out of ``naive.replace(tzinfo=zone, fold=0)`` with :mod:`zoneinfo`, which we then normalise to UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

DEFAULT_ZONE = "UTC"


@lru_cache(maxsize=1)
def _all_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    return bool(name) and name in _all_zones()


def get_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_ZONE)


def user_zone(user) -> ZoneInfo:
    prefs = getattr(user, "preferences", None)
    return get_zone(getattr(prefs, "time_zone", None))


def localize(naive: datetime, zone: ZoneInfo) -> datetime:
    """Attach ``zone`` to a wall-clock time using the DST policy above and return an aware UTC datetime."""
    if naive.tzinfo is not None:
        return naive.astimezone(UTC)
    return naive.replace(tzinfo=zone, fold=0).astimezone(UTC)


def wall_time_exists(naive: datetime, zone: ZoneInfo) -> bool:
    """False when the wall time falls in a DST gap (it will be shifted by :func:`localize`)."""
    aware = naive.replace(tzinfo=zone, fold=0)
    return aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive


def wall_time_is_ambiguous(naive: datetime, zone: ZoneInfo) -> bool:
    a = naive.replace(tzinfo=zone, fold=0).utcoffset()
    b = naive.replace(tzinfo=zone, fold=1).utcoffset()
    return a != b and wall_time_exists(naive, zone)


def to_local(dt: datetime, zone: ZoneInfo) -> datetime:
    return dt.astimezone(zone)


def local_naive(dt: datetime, zone: ZoneInfo) -> datetime:
    return dt.astimezone(zone).replace(tzinfo=None)


def local_today(zone: ZoneInfo, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(zone).date()


def combine(day: date, at: time, zone: ZoneInfo) -> datetime:
    """Local date + local time → aware UTC datetime (DST policy applied)."""
    return localize(datetime.combine(day, at), zone)


def day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC [start, end) of a local calendar day. Handles 23/25-hour DST days correctly."""
    start = localize(datetime.combine(day, time.min), zone)
    end = localize(datetime.combine(day + timedelta(days=1), time.min), zone)
    return start, end


def range_bounds(first: date, last: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC [start, end) covering local days first..last inclusive."""
    return day_bounds(first, zone)[0], day_bounds(last, zone)[1]


def week_start(day: date, week_starts_on: int) -> date:
    """``week_starts_on``: 0=Monday … 6=Sunday (Python weekday numbering)."""
    return day - timedelta(days=(day.weekday() - week_starts_on) % 7)
