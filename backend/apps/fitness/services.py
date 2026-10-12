"""Fitness statistics computed from logged sessions and routine schedules only.

* Planned sessions in a period = routine scheduled days (active routines, created on/before the day) up to today.
* Completed = sessions with status completed or partial. Skipped sessions are recorded but never counted as done.
* Planned-vs-completed rate is ``None`` when nothing was planned (no misleading 0 %).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import Count, Sum

from apps.core.timeutils import get_zone, local_today, week_start
from apps.reminders.serializers import days_to_rrule
from apps.reminders.services import upsert_system_reminder

from .models import SessionStatus, WorkoutRoutine, WorkoutSession

DONE = [SessionStatus.COMPLETED, SessionStatus.PARTIAL]


def sync_routine_reminder(routine: WorkoutRoutine) -> None:
    at = None
    if routine.time:
        at = (datetime.combine(date(2000, 1, 3), routine.time) - timedelta(minutes=routine.prep_buffer_minutes)).time()
    body = f"{routine.name} starts at {routine.time:%H:%M}." if routine.time else ""
    if routine.location:
        body += f" ({routine.location})"
    upsert_system_reminder(
        routine.owner,
        f"routine:{routine.id}",
        enabled=routine.reminder_enabled and routine.active and bool(routine.days),
        title=f"Workout: {routine.name}",
        category="fitness",
        at=at,
        rrule=days_to_rrule(routine.days),
        message=body + " Even a shorter session helps you keep your routine.",
    )


def planned_count(owner, first: date, last: date) -> int:
    n = 0
    zone = get_zone(owner.preferences.time_zone)
    for r in WorkoutRoutine.objects.filter(owner=owner, active=True):
        created = r.created_at.astimezone(zone).date()
        d = max(first, created)
        while d <= last:
            if d.weekday() in r.days:
                n += 1
            d += timedelta(days=1)
    return n


def _summary(owner, first: date, last: date) -> dict:
    qs = WorkoutSession.objects.filter(owner=owner, date__gte=first, date__lte=last)
    done = qs.filter(status__in=DONE)
    agg = done.aggregate(n=Count("id"), minutes=Sum("duration_minutes"))
    planned = planned_count(owner, first, last)
    routine_done = done.filter(routine__isnull=False).count()
    return {
        "sessions": agg["n"],
        "minutes": agg["minutes"] or 0,
        "skipped": qs.filter(status=SessionStatus.SKIPPED).count(),
        "planned": planned,
        "planned_completed": min(routine_done, planned),
        "rate": (min(routine_done, planned) / planned) if planned else None,
    }


def stats(owner) -> dict:
    prefs = owner.preferences
    today = local_today(get_zone(prefs.time_zone))
    wk = week_start(today, prefs.week_start)
    trend = []
    for i in range(7, -1, -1):
        start = wk - timedelta(days=7 * i)
        end = min(start + timedelta(days=6), today)
        qs = WorkoutSession.objects.filter(owner=owner, date__gte=start, date__lte=end, status__in=DONE)
        trend.append({"week_start": start.isoformat(), "sessions": qs.count(), "minutes": qs.aggregate(m=Sum("duration_minutes"))["m"] or 0})
    return {
        "week": _summary(owner, wk, today),
        "month": _summary(owner, today.replace(day=1), today),
        "total_minutes": WorkoutSession.objects.filter(owner=owner, status__in=DONE).aggregate(m=Sum("duration_minutes"))["m"] or 0,
        "weekly_goal": prefs.weekly_workout_goal or None,
        "trend": trend,
        "definitions": {
            "planned": "Days on which an active routine was scheduled, from the routine's creation up to today.",
            "rate": "Routine sessions completed (or partly done) ÷ planned sessions. Not shown when nothing was planned.",
        },
    }


def today_plan(owner, day: date) -> list[dict]:
    out = []
    logged = {s.routine_id: s for s in WorkoutSession.objects.filter(owner=owner, date=day, routine__isnull=False)}
    for r in WorkoutRoutine.objects.filter(owner=owner, active=True):
        if day.weekday() in r.days:
            s = logged.get(r.id)
            out.append(
                {
                    "routine_id": r.id,
                    "name": r.name,
                    "time": r.time.strftime("%H:%M") if r.time else None,
                    "duration_minutes": r.duration_minutes,
                    "location": r.location,
                    "logged_status": s.status if s else None,
                }
            )
    out.sort(key=lambda x: x["time"] or "99:99")
    return out


def default_time() -> time:
    return time(18, 0)
