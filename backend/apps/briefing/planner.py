"""Smart daily planning: *suggests* time slots for flexible tasks around fixed commitments.

Rules:
* Fixed blocks = timed calendar occurrences + tasks that already have a time. They are never moved.
* The planning window is the user's working hours on work days, otherwise wake-up+1h → bedtime−1h.
  For today, planning starts at the next quarter hour.
* Flexible candidates = open, untimed tasks scheduled for the day, plus overdue untimed tasks, plus undated tasks whose
  deadline is within 3 days. Order: overdue, priority, deadline, creation.
* Each task needs ``duration_minutes`` (default 30) plus the user's buffer between blocks.
* Nothing changes until the user accepts individual suggestions (``apply``).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.timeutils import day_bounds, get_zone, local_today, localize
from apps.events.services import expand
from apps.tasks import services as task_services
from apps.tasks.models import OPEN_STATUSES, PRIORITY_RANK, Task

DEFAULT_TASK_MINUTES = 30


def _window(prefs, day: date, zone) -> tuple[datetime, datetime]:
    if day.weekday() in (prefs.work_days or []):
        s, e = prefs.work_start, prefs.work_end
    else:
        s = (datetime.combine(day, prefs.wake_time) + timedelta(hours=1)).time()
        e = (datetime.combine(day, prefs.bedtime) - timedelta(hours=1)).time()
        if e <= s:
            s, e = time(9, 0), time(18, 0)
    return localize(datetime.combine(day, s), zone), localize(datetime.combine(day, e), zone)


def suggest(user, day: date, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    prefs = user.preferences
    zone = get_zone(prefs.time_zone)
    today = local_today(zone, now)
    if day < today:
        raise BusinessRuleError("Planning is for today or a future day.", code="invalid", status_code=400)
    buffer = timedelta(minutes=prefs.planning_buffer_minutes)
    w_start, w_end = _window(prefs, day, zone)
    if day == today:
        q = now + timedelta(minutes=(15 - now.astimezone(zone).minute % 15) % 15)
        w_start = max(w_start, q.replace(second=0, microsecond=0))
    d_start, d_end = day_bounds(day, zone)

    fixed: list[tuple[datetime, datetime, str]] = []
    for o in expand(user, d_start, d_end):
        if not o.all_day:
            fixed.append((o.start, o.end, o.title))
    tasks = Task.objects.filter(owner=user, deleted_at__isnull=True, status__in=OPEN_STATUSES)
    for t in tasks.filter(scheduled_date=day, scheduled_at__isnull=False):
        fixed.append((t.scheduled_at, t.scheduled_at + timedelta(minutes=t.duration_minutes or DEFAULT_TASK_MINUTES), t.title))
    fixed.sort()

    flexible = list(
        tasks.filter(scheduled_time__isnull=True).filter(Q(scheduled_date=day) | Q(scheduled_date__lt=today) | Q(scheduled_date__isnull=True, deadline__lte=now + timedelta(days=3)))
    )

    def order(t: Task):
        overdue = bool(t.scheduled_date and t.scheduled_date < today) or bool(t.deadline and t.deadline < now)
        return (not overdue, PRIORITY_RANK.get(t.priority, 2), t.deadline or datetime.max.replace(tzinfo=now.tzinfo), t.created_at)

    flexible.sort(key=order)

    busy = [(s - buffer, e + buffer) for s, e, _ in fixed]
    suggestions, unplaced = [], []
    for t in flexible:
        need = timedelta(minutes=t.duration_minutes or DEFAULT_TASK_MINUTES)
        cursor = w_start
        placed = None
        for b_start, b_end in sorted(busy):
            if cursor + need <= b_start and cursor + need <= w_end:
                placed = cursor
                break
            cursor = max(cursor, b_end)
        if placed is None and cursor + need <= w_end:
            placed = cursor
        if placed is None:
            unplaced.append({"task_id": t.id, "title": t.title, "duration_minutes": int(need.total_seconds() // 60), "reason": "No free slot long enough within your planning hours."})
            continue
        busy.append((placed - buffer, placed + need + buffer))
        local = placed.astimezone(zone)
        reason = "Overdue" if t.scheduled_date and t.scheduled_date < today else ("Deadline soon" if t.deadline else f"{t.get_priority_display()} priority")
        suggestions.append(
            {
                "task_id": t.id,
                "title": t.title,
                "start": placed.isoformat(),
                "end": (placed + need).isoformat(),
                "start_time": local.strftime("%H:%M"),
                "duration_minutes": int(need.total_seconds() // 60),
                "reason": reason,
            }
        )

    window_minutes = max(0, int((w_end - w_start).total_seconds() // 60))
    fixed_minutes = sum(int((min(e, w_end) - max(s, w_start)).total_seconds() // 60) for s, e, _ in fixed if e > w_start and s < w_end)
    needed = sum((t.duration_minutes or DEFAULT_TASK_MINUTES) for t in flexible)
    free = max(0, window_minutes - fixed_minutes)
    return {
        "date": day.isoformat(),
        "window": {"start": w_start.isoformat(), "end": w_end.isoformat()},
        "fixed": [{"start": s.isoformat(), "end": e.isoformat(), "title": title} for s, e, title in fixed],
        "suggestions": suggestions,
        "unplaced": unplaced,
        "free_minutes": free,
        "needed_minutes": needed,
        "overloaded": needed > free,
        "note": "These are suggestions. Nothing changes until you accept them, and fixed appointments are never moved.",
    }


@transaction.atomic
def apply(user, day: date, items: list[dict]) -> list[int]:
    """Schedule the accepted tasks at their chosen local times (one occurrence each; series are not altered)."""
    updated = []
    for item in items:
        task = Task.objects.filter(owner=user, pk=item["task_id"], deleted_at__isnull=True, status__in=OPEN_STATUSES).first()
        if task is None:
            raise BusinessRuleError("One of those tasks is no longer open.", code="invalid", status_code=400)
        task_services.update_task(task, {"scheduled_date": day, "scheduled_time": item["start_time"]}, scope="this")
        updated.append(task.id)
    return updated
