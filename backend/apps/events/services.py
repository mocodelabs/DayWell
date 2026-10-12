"""Calendar business logic: computing UTC bounds, expanding recurring series, exceptions, conflicts and ICS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q

from apps.core.exceptions import BusinessRuleError
from apps.core.recurrence import build_rrule, occurrences_between
from apps.core.timeutils import day_bounds, get_zone, localize

from .models import CalendarEvent, EventException, EventStatus

MAX_RANGE_DAYS = 400


def occurrence_key(local_start: datetime | date, all_day: bool) -> str:
    if all_day:
        d = local_start.date() if isinstance(local_start, datetime) else local_start
        return d.isoformat()
    return local_start.strftime("%Y-%m-%dT%H:%M")


def parse_key(key: str, all_day: bool) -> datetime:
    try:
        if all_day:
            return datetime.combine(date.fromisoformat(key), time.min)
        return datetime.strptime(key, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise BusinessRuleError("Unknown occurrence.", code="invalid", status_code=400) from None


def _local_start(ev) -> datetime:
    return datetime.combine(ev.start_date, time.min if ev.all_day else ev.start_time)


def _local_end(ev) -> datetime:
    return datetime.combine(ev.end_date, time.min if ev.all_day else ev.end_time)


def _bounds(start_date, start_time, end_date, end_time, all_day, zone) -> tuple[datetime, datetime]:
    if all_day:
        return day_bounds(start_date, zone)[0], day_bounds(end_date, zone)[1]
    return localize(datetime.combine(start_date, start_time), zone), localize(datetime.combine(end_date, end_time), zone)


def refresh_bounds(ev: CalendarEvent) -> None:
    """Compute start/end/series_end (UTC) from the wall-clock fields and the rule."""
    zone = get_zone(ev.time_zone)
    if ev.all_day:
        ev.start_time = ev.end_time = None
    elif ev.start_time is None or ev.end_time is None:
        raise BusinessRuleError("Timed events need a start and end time.", code="invalid", status_code=400)
    if _local_end(ev) < _local_start(ev) or (not ev.all_day and _local_end(ev) == _local_start(ev)):
        raise BusinessRuleError("The event must end after it starts.", code="invalid", status_code=400)
    ev.start, ev.end = _bounds(ev.start_date, ev.start_time, ev.end_date, ev.end_time, ev.all_day, zone)
    ev.series_end = ev.end
    if ev.rrule:
        parts = ev.rrule.upper()
        if "COUNT=" in parts or "UNTIL=" in parts:
            instances = list(build_rrule(ev.rrule, _local_start(ev)))  # bounded by COUNT/UNTIL (COUNT ≤ 2000)
            last = instances[-1] if instances else None
            if last is None:
                raise BusinessRuleError("That repeat rule produces no occurrences.", code="invalid", status_code=400)
            span = _local_end(ev) - _local_start(ev)
            if ev.all_day:
                ev.series_end = day_bounds((last + span).date(), zone)[1]
            else:
                ev.series_end = localize(last + span, zone)
        else:
            ev.series_end = None


@dataclass
class Occurrence:
    event_id: int
    key: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    time_zone: str
    description: str = ""
    location: str = ""
    meeting_url: str = ""
    category: int | None = None
    color: str | None = None
    status: str = EventStatus.CONFIRMED
    attendance: str = ""
    is_recurring: bool = False
    is_exception: bool = False
    rrule: str = ""
    local_start: str = ""
    local_end: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        return d


def _occurrence(ev: CalendarEvent, local_start: datetime, exc: EventException | None) -> Occurrence | None:
    zone = get_zone(ev.time_zone)
    span = _local_end(ev) - _local_start(ev)
    key = occurrence_key(local_start, ev.all_day)
    if exc and exc.cancelled:
        return None
    ls, le = local_start, local_start + span
    if exc and exc.start_date:
        ls = datetime.combine(exc.start_date, time.min if ev.all_day else (exc.start_time or time.min))
        le = datetime.combine(exc.end_date or exc.start_date, time.min if ev.all_day else (exc.end_time or time.min))
    if ev.all_day:
        start, end = day_bounds(ls.date(), zone)[0], day_bounds(le.date(), zone)[1]
    else:
        start, end = localize(ls, zone), localize(le, zone)
    return Occurrence(
        event_id=ev.id,
        key=key,
        title=(exc.title if exc and exc.title else ev.title),
        start=start,
        end=end,
        all_day=ev.all_day,
        time_zone=ev.time_zone,
        description=(exc.description if exc and exc.description else ev.description),
        location=(exc.location if exc and exc.location else ev.location),
        meeting_url=ev.meeting_url,
        category=ev.category_id,
        color=(ev.category.color if ev.category_id else None),
        status=ev.status,
        attendance=(exc.attendance if exc and exc.attendance else ("" if ev.rrule else ev.attendance)),
        is_recurring=bool(ev.rrule),
        is_exception=exc is not None,
        rrule=ev.rrule,
        local_start=ls.isoformat(timespec="minutes"),
        local_end=le.isoformat(timespec="minutes"),
    )


def expand_event(ev: CalendarEvent, start: datetime, end: datetime, exceptions: dict[str, EventException] | None = None) -> list[Occurrence]:
    """Occurrences of one event overlapping [start, end)."""
    if exceptions is None:
        exceptions = {e.original_key: e for e in ev.exceptions.all()}
    zone = get_zone(ev.time_zone)
    if not ev.rrule:
        occ = _occurrence(ev, _local_start(ev), None)
        return [occ] if occ and occ.start < end and occ.end > start else []
    span = ev.end - ev.start
    # Search from (start - span) so occurrences that began before the window but overlap it are included.
    instants = occurrences_between(ev.rrule, _local_start(ev), zone, start - span - timedelta(days=1), end)
    seen: set[str] = set()
    out: list[Occurrence] = []
    for instant in instants:
        local = instant.astimezone(zone).replace(tzinfo=None)
        if ev.all_day:
            local = datetime.combine(local.date(), time.min)
        key = occurrence_key(local, ev.all_day)
        seen.add(key)
        occ = _occurrence(ev, local, exceptions.get(key))
        if occ and occ.start < end and occ.end > start:
            out.append(occ)
    # Occurrences moved INTO this window from outside the expanded range.
    for key, exc in exceptions.items():
        if key in seen or exc.cancelled or exc.override_start is None:
            continue
        if exc.override_start < end and (exc.override_end or exc.override_start) > start:
            occ = _occurrence(ev, parse_key(key, ev.all_day), exc)
            if occ:
                out.append(occ)
    return out


def expand(owner, start: datetime, end: datetime, *, include_cancelled: bool = False, queryset=None) -> list[Occurrence]:
    if end <= start:
        return []
    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise BusinessRuleError(f"Please request at most {MAX_RANGE_DAYS} days at a time.", code="invalid", status_code=400)
    qs = queryset if queryset is not None else CalendarEvent.objects.filter(owner=owner)
    if not include_cancelled:
        qs = qs.exclude(status=EventStatus.CANCELLED)
    moved_ids = EventException.objects.filter(event__owner=owner, override_start__lt=end, override_end__gt=start).values("event_id")
    qs = qs.filter(Q(start__lt=end) & (Q(series_end__isnull=True) | Q(series_end__gt=start)) | Q(id__in=moved_ids)).select_related("category").prefetch_related("exceptions")
    out: list[Occurrence] = []
    for ev in qs:
        out.extend(expand_event(ev, start, end))
    out.sort(key=lambda o: (o.start, o.end, o.event_id))
    return out


def find_conflicts(occurrences: list[Occurrence]) -> list[dict]:
    """Pairs of overlapping timed, non-cancelled occurrences. All-day events never conflict."""
    timed = sorted((o for o in occurrences if not o.all_day and o.status != EventStatus.CANCELLED), key=lambda o: o.start)
    conflicts = []
    active: list[Occurrence] = []
    for occ in timed:
        active = [a for a in active if a.end > occ.start]
        for other in active:
            conflicts.append(
                {
                    "a": {"event_id": other.event_id, "key": other.key, "title": other.title, "start": other.start.isoformat(), "end": other.end.isoformat()},
                    "b": {"event_id": occ.event_id, "key": occ.key, "title": occ.title, "start": occ.start.isoformat(), "end": occ.end.isoformat()},
                }
            )
        active.append(occ)
    return conflicts


@transaction.atomic
def upsert_exception(ev: CalendarEvent, key: str, changes: dict) -> EventException:
    """Change one occurrence of a recurring event (``changes`` may include cancelled, title, times, attendance)."""
    if not ev.rrule:
        raise BusinessRuleError("This event doesn't repeat — edit it directly.", code="invalid", status_code=400)
    original = parse_key(key, ev.all_day)
    zone = get_zone(ev.time_zone)
    window_start = localize(original, zone) - timedelta(days=1)
    real = {
        occurrence_key(i.astimezone(zone).replace(tzinfo=None), ev.all_day) for i in occurrences_between(ev.rrule, _local_start(ev), zone, window_start, window_start + timedelta(days=2))
    }
    if key not in real:
        raise BusinessRuleError("That occurrence isn't part of this series.", code="invalid", status_code=400)
    exc, _ = EventException.objects.select_for_update().get_or_create(event=ev, original_key=key)
    for field_name, value in changes.items():
        setattr(exc, field_name, value)
    if exc.start_date:
        sd, st = exc.start_date, exc.start_time
        ed, et = exc.end_date or exc.start_date, exc.end_time
        if not ev.all_day and (st is None or et is None):
            raise BusinessRuleError("A moved occurrence needs a start and end time.", code="invalid", status_code=400)
        exc.override_start, exc.override_end = _bounds(sd, st, ed, et, ev.all_day, zone)
        if exc.override_end <= exc.override_start and not ev.all_day:
            raise BusinessRuleError("The event must end after it starts.", code="invalid", status_code=400)
    else:
        exc.override_start = exc.override_end = None
    exc.save()
    _resync(ev)
    return exc


def _resync(ev: CalendarEvent) -> None:
    from apps.reminders.services import resync_for_event

    resync_for_event(ev.id)


def save_event(ev: CalendarEvent) -> CalendarEvent:
    with transaction.atomic():
        refresh_bounds(ev)
        ev.save()
        _resync(ev)
    return ev


# --- ICS import / export ---------------------------------------------------------------------------------------------


def export_ics(owner) -> bytes:
    from icalendar import Calendar, Event, vRecur

    cal = Calendar()
    cal.add("prodid", "-//DayWell//Calendar export//EN")
    cal.add("version", "2.0")
    for ev in CalendarEvent.objects.filter(owner=owner).prefetch_related("exceptions"):
        zone = get_zone(ev.time_zone)
        item = Event()
        item.add("uid", ev.ical_uid or f"daywell-{ev.id}@daywell")
        item.add("summary", ev.title)
        if ev.description:
            item.add("description", ev.description)
        if ev.location:
            item.add("location", ev.location)
        if ev.meeting_url:
            item.add("url", ev.meeting_url)
        if ev.all_day:
            item.add("dtstart", ev.start_date)
            item.add("dtend", ev.end_date + timedelta(days=1))
        else:
            item.add("dtstart", _local_start(ev).replace(tzinfo=zone))
            item.add("dtend", _local_end(ev).replace(tzinfo=zone))
        if ev.status != EventStatus.CONFIRMED:
            item.add("status", ev.status.upper())
        if ev.rrule:
            item.add("rrule", vRecur.from_ical(ev.rrule))
            for exc in ev.exceptions.all():
                if exc.cancelled:
                    original = parse_key(exc.original_key, ev.all_day)
                    item.add("exdate", original.date() if ev.all_day else original.replace(tzinfo=zone))
        cal.add_component(item)
    return cal.to_ical()


def import_ics(owner, payload: bytes, *, default_zone: str) -> dict:
    """Import VEVENTs. Events with a UID already imported are skipped (re-importing the same file is idempotent)."""
    from icalendar import Calendar

    from apps.core.recurrence import RecurrenceError, normalize_rrule
    from apps.core.timeutils import is_valid_timezone

    try:
        cal = Calendar.from_ical(payload)
    except Exception:
        raise BusinessRuleError("That file isn't a valid iCalendar (.ics) file.", code="invalid", status_code=400) from None
    created, skipped, errors = 0, 0, []
    existing = set(CalendarEvent.objects.filter(owner=owner).exclude(ical_uid="").values_list("ical_uid", flat=True))
    for comp in cal.walk("VEVENT"):
        uid = str(comp.get("uid", ""))[:255]
        title = str(comp.get("summary", "Untitled event"))[:200]
        if uid and uid in existing:
            skipped += 1
            continue
        try:
            dtstart = comp.decoded("dtstart")
            dtend = comp.decoded("dtend") if comp.get("dtend") else None
            ev = CalendarEvent(owner=owner, title=title, ical_uid=uid, description=str(comp.get("description", ""))[:5000], location=str(comp.get("location", ""))[:300])
            if isinstance(dtstart, datetime):
                tzname = getattr(dtstart.tzinfo, "key", None) or str(dtstart.tzinfo or "")
                ev.time_zone = tzname if is_valid_timezone(tzname) else default_zone
                zone = get_zone(ev.time_zone)
                ls = dtstart.astimezone(zone).replace(tzinfo=None) if dtstart.tzinfo else dtstart
                le = (dtend.astimezone(zone).replace(tzinfo=None) if dtend and dtend.tzinfo else dtend) or ls + timedelta(hours=1)
                ev.start_date, ev.start_time, ev.end_date, ev.end_time = ls.date(), ls.time(), le.date(), le.time()
            else:
                ev.all_day, ev.time_zone = True, default_zone
                ev.start_date = dtstart
                ev.end_date = (dtend - timedelta(days=1)) if dtend and dtend > dtstart else dtstart
            if comp.get("rrule"):
                try:
                    ev.rrule = normalize_rrule(comp.get("rrule").to_ical().decode())
                except RecurrenceError as exc:
                    errors.append(f"{title}: repeat rule not supported ({exc}); imported as a single event.")
            with transaction.atomic():
                refresh_bounds(ev)
                ev.save()
                for exdate in _exdates(comp):
                    if ev.rrule:
                        local = exdate.astimezone(get_zone(ev.time_zone)).replace(tzinfo=None) if isinstance(exdate, datetime) and exdate.tzinfo else exdate
                        EventException.objects.get_or_create(event=ev, original_key=occurrence_key(local, ev.all_day), defaults={"cancelled": True})
            created += 1
            if uid:
                existing.add(uid)
        except BusinessRuleError as exc:
            errors.append(f"{title}: {exc.detail}")
        except Exception as exc:  # malformed component — report and continue with the rest of the file
            errors.append(f"{title}: could not be read ({exc.__class__.__name__}).")
    return {"created": created, "skipped": skipped, "errors": errors[:50]}


def _exdates(comp) -> list:
    raw = comp.get("exdate")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for item in items:
        out.extend(d.dt for d in item.dts)
    return out
