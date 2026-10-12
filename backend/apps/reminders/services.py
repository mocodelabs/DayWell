"""Reminder definition management and occurrence materialisation ("sync").

``sync_reminder`` computes the *desired* future occurrences of a reminder within the horizon and reconciles them with
the stored ones:

* desired + missing          → created (``bulk_create(ignore_conflicts=True)`` on the unique idempotency key)
* desired + cancelled earlier → revived to ``scheduled`` (e.g. an event moved away and back)
* stored + no longer desired  → ``cancelled`` (obsolete after a reschedule/edit) — never deleted, history is kept

Only occurrences that are still ``scheduled`` and in the future are ever touched, so delivered history, snoozes and
user actions are preserved. Running sync twice is a no-op.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.recurrence import occurrences_between
from apps.core.timeutils import get_zone

from .models import OccurrenceStatus, Reminder, ReminderOccurrence

logger = logging.getLogger("daywell.reminders")


@dataclass(frozen=True)
class Desired:
    key: str
    scheduled_for: datetime
    target_key: str
    task_id: int | None
    title: str


def _utc_key(dt: datetime) -> str:
    from datetime import UTC

    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def horizon_end(now: datetime) -> datetime:
    return now + timedelta(days=settings.REMINDER_HORIZON_DAYS)


def desired_occurrences(reminder: Reminder, start: datetime, end: datetime) -> list[Desired]:
    """What *should* exist for this reminder in [start, end)."""
    out: list[Desired] = []
    offset = timedelta(minutes=reminder.offset_minutes)
    if reminder.kind == Reminder.Kind.ABSOLUTE:
        if not reminder.dtstart_date or not reminder.dtstart_time:
            return out
        zone = get_zone(reminder.time_zone)
        local_start = datetime.combine(reminder.dtstart_date, reminder.dtstart_time)
        for instant in occurrences_between(reminder.rrule, local_start, zone, start, end):
            key = f"r{reminder.id}:{_utc_key(instant)}"
            out.append(Desired(key, instant, f"habit:{reminder.habit_id}" if reminder.habit_id else "", None, reminder.title))
        return out

    if reminder.task_id or reminder.task_series_id:
        from apps.tasks.models import OPEN_STATUSES, Task

        tasks = Task.objects.filter(deleted_at__isnull=True, status__in=OPEN_STATUSES)
        tasks = tasks.filter(series_id=reminder.task_series_id) if reminder.task_series_id else tasks.filter(pk=reminder.task_id)
        field = "deadline" if reminder.anchor == Reminder.Anchor.DEADLINE else "scheduled_at"
        tasks = tasks.filter(**{f"{field}__gte": start + offset, f"{field}__lt": end + offset})
        for task in tasks.only("id", "title", field):
            base = getattr(task, field)
            fire = base - offset
            out.append(Desired(f"r{reminder.id}:task{task.id}:{reminder.anchor}:{_utc_key(base)}", fire, f"task:{task.id}", task.id, task.title))
        return out

    if reminder.event_id:
        from apps.events.models import CalendarEvent, EventStatus
        from apps.events.services import expand_event

        ev = CalendarEvent.objects.filter(pk=reminder.event_id).prefetch_related("exceptions").select_related("category").first()
        if ev is None or ev.status == EventStatus.CANCELLED:
            return out
        for occ in expand_event(ev, start + offset, end + offset):
            if occ.start - offset < start:
                continue
            out.append(Desired(f"r{reminder.id}:ev{ev.id}:{occ.key}:{_utc_key(occ.start)}", occ.start - offset, f"event:{ev.id}:{occ.key}", None, occ.title))
    return out


@transaction.atomic
def sync_reminder(reminder: Reminder, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    end = horizon_end(now)
    reminder = Reminder.objects.select_for_update(of=("self",)).get(pk=reminder.pk)
    desired = {d.key: d for d in (desired_occurrences(reminder, now, end) if reminder.enabled else [])}
    future = ReminderOccurrence.objects.filter(reminder=reminder, scheduled_for__gte=now, parent__isnull=True)

    cancelled = (
        future.filter(status=OccurrenceStatus.SCHEDULED).exclude(idempotency_key__in=list(desired)).update(status=OccurrenceStatus.CANCELLED, skip_reason="superseded", updated_at=now)
    )
    revived = future.filter(status=OccurrenceStatus.CANCELLED, idempotency_key__in=list(desired)).update(status=OccurrenceStatus.SCHEDULED, skip_reason="", updated_at=now)
    existing = set(ReminderOccurrence.objects.filter(idempotency_key__in=list(desired)).values_list("idempotency_key", flat=True))
    new = [
        ReminderOccurrence(
            reminder=reminder,
            owner_id=reminder.owner_id,
            category=reminder.category,
            title=d.title or reminder.title,
            body=reminder.message,
            scheduled_for=d.scheduled_for,
            fire_at=d.scheduled_for,
            target_key=d.target_key,
            task_id=d.task_id,
            idempotency_key=d.key,
        )
        for key, d in desired.items()
        if key not in existing
    ]
    ReminderOccurrence.objects.bulk_create(new, ignore_conflicts=True)
    # Keep titles fresh when the linked item was renamed.
    for key, d in desired.items():
        if key in existing:
            ReminderOccurrence.objects.filter(idempotency_key=key, status=OccurrenceStatus.SCHEDULED).exclude(title=d.title or reminder.title).update(
                title=d.title or reminder.title, body=reminder.message
            )
    Reminder.objects.filter(pk=reminder.pk).update(generated_until=end)
    return {"created": len(new), "cancelled": cancelled, "revived": revived}


def resync(reminders) -> None:
    for reminder in reminders:
        sync_reminder(reminder)


def resync_for_tasks(task_ids: list[int]) -> None:
    from apps.tasks.models import Task

    series_ids = set(Task.objects.filter(id__in=task_ids, series__isnull=False).values_list("series_id", flat=True))
    resync(Reminder.objects.filter(Q(task_id__in=task_ids) | Q(task_series_id__in=series_ids)))


def resync_for_event(event_id: int) -> None:
    resync(Reminder.objects.filter(event_id=event_id))


def resync_for_habit(habit_id: int) -> None:
    resync(Reminder.objects.filter(habit_id=habit_id))


def resync_for_owner(owner) -> None:
    resync(Reminder.objects.filter(owner=owner, enabled=True))


@transaction.atomic
def set_item_reminders(owner, offsets: list[dict], *, task=None, series=None, event=None) -> list[Reminder]:
    """Replace the relative reminders of a task / task series / event with ``offsets`` ([{offset_minutes, anchor}])."""
    if event is not None:
        existing = Reminder.objects.filter(owner=owner, event=event, kind=Reminder.Kind.RELATIVE)
        category, title = "events", event.title
    elif series is not None:
        existing = Reminder.objects.filter(owner=owner, task_series=series, kind=Reminder.Kind.RELATIVE)
        category, title = "tasks", series.title
    else:
        existing = Reminder.objects.filter(owner=owner, task=task, task_series__isnull=True, kind=Reminder.Kind.RELATIVE)
        category, title = "tasks", task.title
    wanted = {(int(o["offset_minutes"]), o.get("anchor", "start")) for o in offsets}
    keep: list[Reminder] = []
    for reminder in existing:
        if (reminder.offset_minutes, reminder.anchor) in wanted:
            wanted.discard((reminder.offset_minutes, reminder.anchor))
            keep.append(reminder)
        else:
            reminder.occurrences.filter(status=OccurrenceStatus.SCHEDULED).update(status=OccurrenceStatus.CANCELLED, skip_reason="reminder_removed")
            reminder.delete()
    for offset, anchor in sorted(wanted):
        keep.append(
            Reminder.objects.create(
                owner=owner,
                title=title,
                category=category,
                kind=Reminder.Kind.RELATIVE,
                time_zone=owner.preferences.time_zone,
                task=task if series is None else None,
                task_series=series,
                event=event,
                offset_minutes=offset,
                anchor=anchor,
            )
        )
    resync(keep)
    return keep


def sync_habit_reminder(habit) -> None:
    """Create/update/remove the single absolute reminder that belongs to a habit."""
    from apps.habits.models import HabitStatus

    reminder = Reminder.objects.filter(habit=habit, is_test=False).first()
    wanted = habit.reminder_time is not None and habit.status == HabitStatus.ACTIVE
    if not wanted:
        if reminder:
            reminder.enabled = False
            reminder.save(update_fields=["enabled", "updated_at"])
            sync_reminder(reminder)
        return
    rule = "FREQ=DAILY" if habit.times_per_week else habit.schedule_rule
    fields = {
        "title": habit.name,
        "category": habit.reminder_category,
        "kind": Reminder.Kind.ABSOLUTE,
        "dtstart_date": habit.start_date,
        "dtstart_time": habit.reminder_time,
        "rrule": rule,
        "time_zone": habit.time_zone,
        "enabled": True,
    }
    if reminder is None:
        reminder = Reminder.objects.create(owner=habit.owner, habit=habit, **fields)
    else:
        for k, v in fields.items():
            setattr(reminder, k, v)
        reminder.save()
    sync_reminder(reminder)


def extend_horizon(now: datetime | None = None) -> int:
    """Called periodically: top up every enabled reminder whose generated window is running out."""
    now = now or timezone.now()
    threshold = horizon_end(now) - timedelta(days=1)
    count = 0
    qs = Reminder.objects.filter(enabled=True, is_test=False).filter(Q(generated_until__isnull=True) | Q(generated_until__lt=threshold))
    for reminder in qs.iterator():
        try:
            sync_reminder(reminder, now)
            count += 1
        except Exception:  # one broken reminder must not stop the others — log with context and continue
            logger.exception("failed to sync reminder", extra={"reminder_id": reminder.id})
    return count


def upsert_system_reminder(owner, key: str, *, enabled: bool, title: str, category: str, at=None, rrule: str = "FREQ=DAILY", start_date=None, message: str = "") -> Reminder | None:
    """Create/update/disable the single module-owned reminder identified by ``key`` (e.g. "affirmation", "routine:7")."""
    from apps.core.timeutils import local_today

    reminder = Reminder.objects.filter(owner=owner, system_key=key).first()
    if not enabled or at is None:
        if reminder and reminder.enabled:
            reminder.enabled = False
            reminder.save(update_fields=["enabled", "updated_at"])
            sync_reminder(reminder)
        return reminder
    zone_name = owner.preferences.time_zone
    fields = {
        "title": title,
        "message": message,
        "category": category,
        "kind": Reminder.Kind.ABSOLUTE,
        "dtstart_time": at,
        "rrule": rrule,
        "time_zone": zone_name,
        "enabled": True,
        "archived": False,
        "dtstart_date": start_date or (reminder.dtstart_date if reminder else None) or local_today(get_zone(zone_name)),
    }
    if reminder is None:
        reminder = Reminder.objects.create(owner=owner, system_key=key, **fields)
    else:
        for k, v in fields.items():
            setattr(reminder, k, v)
        reminder.save()
    sync_reminder(reminder)
    return reminder


def system_reminder_state(owner, key: str) -> dict:
    r = Reminder.objects.filter(owner=owner, system_key=key).first()
    return {"enabled": bool(r and r.enabled), "time": r.dtstart_time.strftime("%H:%M") if r and r.dtstart_time else None, "rrule": r.rrule if r else ""}
