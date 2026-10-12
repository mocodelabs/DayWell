"""RFC 5545 recurrence (RRULE) handling built on :mod:`dateutil.rrule`.

Rules are expanded in the owner's *local wall-clock time* (a floating DTSTART), and each generated wall time is then
attached to the IANA zone with :func:`apps.core.timeutils.localize`. "Every weekday at 06:30" therefore stays at 06:30
local across DST changes — we never add a fixed number of seconds to the previous occurrence.

Only a safe subset of RRULE is accepted (see ``ALLOWED_PARTS``). ``UNTIL`` is interpreted in local time: a bare date
means "through the end of that local day".
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrule, rrulestr

from .timeutils import localize

ALLOWED_FREQ = {"HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
ALLOWED_PARTS = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "BYSETPOS", "WKST", "BYHOUR", "BYMINUTE"}
MAX_COUNT = 2000
MAX_INTERVAL = 999
MAX_EXPANSION = 5000  # hard ceiling on instances returned for one query window


class RecurrenceError(ValueError):
    pass


def _split(rule: str) -> dict[str, str]:
    text = rule.strip()
    if text.upper().startswith("RRULE:"):
        text = text[6:]
    parts: dict[str, str] = {}
    for chunk in filter(None, text.split(";")):
        if "=" not in chunk:
            raise RecurrenceError(f"Malformed recurrence part '{chunk}'.")
        key, value = chunk.split("=", 1)
        key = key.strip().upper()
        if key in parts:
            raise RecurrenceError(f"Recurrence part {key} appears twice.")
        parts[key] = value.strip().upper()
    return parts


def _parse_until(value: str) -> datetime:
    """UNTIL as local wall time. YYYYMMDD → end of that day; YYYYMMDDTHHMMSS[Z] → that wall time (Z ignored: floating)."""
    try:
        if len(value) == 8:
            return datetime.combine(datetime.strptime(value, "%Y%m%d").date(), time(23, 59, 59))
        return datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        raise RecurrenceError("UNTIL must be YYYYMMDD or YYYYMMDDTHHMMSS.") from None


def normalize_rrule(rule: str | None) -> str:
    """Validate and canonicalise an RRULE string. Returns '' for no recurrence. Raises RecurrenceError."""
    if not rule or not rule.strip():
        return ""
    parts = _split(rule)
    unknown = set(parts) - ALLOWED_PARTS
    if unknown:
        raise RecurrenceError(f"Unsupported recurrence part(s): {', '.join(sorted(unknown))}.")
    freq = parts.get("FREQ")
    if freq not in ALLOWED_FREQ:
        raise RecurrenceError("FREQ must be one of HOURLY, DAILY, WEEKLY, MONTHLY or YEARLY.")
    if "COUNT" in parts and "UNTIL" in parts:
        raise RecurrenceError("Use either an end date or a number of occurrences, not both.")
    if "INTERVAL" in parts and (not parts["INTERVAL"].isdigit() or not 1 <= int(parts["INTERVAL"]) <= MAX_INTERVAL):
        raise RecurrenceError(f"INTERVAL must be between 1 and {MAX_INTERVAL}.")
    if "COUNT" in parts and (not parts["COUNT"].isdigit() or not 1 <= int(parts["COUNT"]) <= MAX_COUNT):
        raise RecurrenceError(f"COUNT must be between 1 and {MAX_COUNT}.")
    if "UNTIL" in parts:
        _parse_until(parts["UNTIL"])
    order = ["FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYMONTH", "BYSETPOS", "BYHOUR", "BYMINUTE", "WKST", "COUNT", "UNTIL"]
    canonical = ";".join(f"{k}={parts[k]}" for k in order if k in parts)
    try:
        build_rrule(canonical, datetime(2000, 1, 1, 9, 0))
    except RecurrenceError:
        raise
    except Exception as exc:  # dateutil raises ValueError/TypeError with technical messages
        raise RecurrenceError(f"Invalid recurrence rule: {exc}") from None
    return canonical


def build_rrule(rule: str, dtstart_local: datetime) -> rrule:
    """Build a dateutil rrule over floating local wall time starting at ``dtstart_local`` (naive)."""
    if dtstart_local.tzinfo is not None:
        raise RecurrenceError("dtstart_local must be a naive local wall time.")
    parts = _split(rule)
    until = parts.pop("UNTIL", None)
    body = ";".join(f"{k}={v}" for k, v in parts.items())
    r = rrulestr(body, dtstart=dtstart_local)
    if not isinstance(r, rrule):
        raise RecurrenceError("Only a single RRULE is supported.")
    if until:
        r = r.replace(until=_parse_until(until))
    return r


def iter_local(rule: str, dtstart_local: datetime) -> Iterator[datetime]:
    """All local wall times of the series (may be infinite — always bound the consumer)."""
    if not rule:
        yield dtstart_local
        return
    yield from build_rrule(rule, dtstart_local)


def occurrences_between(
    rule: str,
    dtstart_local: datetime,
    zone: ZoneInfo,
    start: datetime,
    end: datetime,
    *,
    exclude_local: Iterable[datetime] = (),
) -> list[datetime]:
    """UTC instants of the series within [start, end). ``exclude_local`` holds original local wall times to skip (EXDATE)."""
    excluded = set(exclude_local)
    # Widen the local search window by a day each side: offsets never exceed ±14h, so nothing is missed at the edges.
    lo = start.astimezone(zone).replace(tzinfo=None) - timedelta(days=1)
    hi = end.astimezone(zone).replace(tzinfo=None) + timedelta(days=1)
    if not rule:
        candidates = [dtstart_local] if lo <= dtstart_local <= hi else []
    else:
        candidates = build_rrule(rule, dtstart_local).between(lo, hi, inc=True)
    out: list[datetime] = []
    for wall in candidates:
        if wall in excluded:
            continue
        instant = localize(wall, zone)
        if start <= instant < end:
            out.append(instant)
            if len(out) >= MAX_EXPANSION:
                break
    return out


def occurrence_dates_between(rule: str, dtstart: date, first: date, last: date) -> list[date]:
    """Local calendar dates of a date-based series (tasks, habits) between first..last inclusive."""
    start = datetime.combine(dtstart, time.min)
    if not rule:
        return [dtstart] if first <= dtstart <= last else []
    r = build_rrule(rule, start)
    return [d.date() for d in r.between(datetime.combine(first, time.min), datetime.combine(last, time.min), inc=True)][:MAX_EXPANSION]


def next_local_after(rule: str, dtstart_local: datetime, after_local: datetime) -> datetime | None:
    if not rule:
        return dtstart_local if dtstart_local > after_local else None
    return build_rrule(rule, dtstart_local).after(after_local, inc=False)
