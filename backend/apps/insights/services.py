"""Insights computed directly from source records over local-date ranges.

Every number is reproducible from stored data; the ``definitions`` block in each response states the rule.
Rates are ``None`` (shown as "—") when the denominator is zero, never a misleading 0 % or 100 %.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate

from apps.core.timeutils import get_zone, local_today, range_bounds
from apps.events.services import expand
from apps.fitness.models import SessionStatus, WorkoutSession
from apps.habits import services as habit_services
from apps.habits.models import CompletionStatus, Habit, HabitCompletion, HabitStatus
from apps.reading.models import Book, BookStatus, ReadingSession
from apps.tasks.models import OPEN_STATUSES, Task, TaskActivity, TaskStatus

from .models import Goal, GoalMetric

DEFINITIONS = {
    "period": "Only days up to and including today are counted, so future plans never lower a rate.",
    "tasks_planned": "Tasks whose scheduled date falls in the period (as they are now), plus tasks postponed out of the period.",
    "tasks_completed": "Planned tasks that are now completed.",
    "task_completion_rate": "Completed ÷ (planned − cancelled). Postponed tasks count as planned-but-not-completed for the original day.",
    "completed_any_day": "Tasks marked complete during the period, whatever day they were scheduled for.",
    "postponed": "Number of times a task was postponed away from a day in the period.",
    "habit_consistency": "Done ÷ (scheduled − rest days), across all active habits. Partly done days are not counted as done.",
    "events": "Calendar occurrences in the period; attended counts those you marked attended or completed.",
    "reading_minutes": "Sum of finished reading sessions.",
    "workouts": "Workout sessions logged as completed or partly done.",
    "most_productive_days": "Days with the most tasks completed (ties broken by date).",
}


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den > 0 else None


def range_stats(user, first: date, last: date) -> dict:
    prefs = user.preferences
    zone = get_zone(prefs.time_zone)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    per_day: dict[date, dict] = {d: defaultdict(int) for d in days}
    # Count only up to today: a week that isn't over yet must not be judged on days that haven't happened.
    last = min(last, local_today(zone))
    if last < first:
        last = first - timedelta(days=1)  # entirely in the future → nothing counted
    start, end = range_bounds(first, max(last, first), zone)
    if last < first:
        end = start

    tasks = Task.objects.filter(owner=user, deleted_at__isnull=True)
    planned = tasks.filter(scheduled_date__gte=first, scheduled_date__lte=last)
    postponed_out = TaskActivity.objects.filter(task__owner=user, kind=TaskActivity.Kind.POSTPONED, from_date__gte=first, from_date__lte=last)
    for row in planned.values("scheduled_date", "status"):
        d = per_day[row["scheduled_date"]]
        d["tasks_planned"] += 1
        if row["status"] == TaskStatus.COMPLETED:
            d["tasks_completed"] += 1
        elif row["status"] == TaskStatus.CANCELLED:
            d["tasks_cancelled"] += 1
    for row in postponed_out.values("from_date").annotate(n=Count("id")):
        per_day[row["from_date"]]["tasks_planned"] += row["n"]
        per_day[row["from_date"]]["tasks_postponed"] += row["n"]
    completed_any = tasks.filter(completed_at__gte=start, completed_at__lt=end, status=TaskStatus.COMPLETED)
    for row in completed_any.annotate(d=TruncDate("completed_at", tzinfo=zone)).values("d").annotate(n=Count("id")):
        if row["d"] in per_day:
            per_day[row["d"]]["completed_any_day"] += row["n"]

    habits = list(Habit.objects.filter(owner=user).exclude(status=HabitStatus.ARCHIVED, paused_at__lt=start))
    comps = defaultdict(dict)
    for c in HabitCompletion.objects.filter(habit__in=habits, date__gte=first, date__lte=last):
        comps[c.habit_id][c.date] = c
    habit_rows = []
    for h in habits:
        p = habit_services.progress(h, first, last, comps[h.id], prefs.week_start)
        habit_rows.append({"id": h.id, "name": h.name, "icon": h.icon, **p.as_dict()})
        for d in habit_services.scheduled_dates(h, first, last) if not h.times_per_week else []:
            c = comps[h.id].get(d)
            if c and c.status == CompletionStatus.SKIPPED:
                continue
            per_day[d]["habits_scheduled"] += 1
            if c and c.status == CompletionStatus.DONE:
                per_day[d]["habits_done"] += 1

    for row in (
        ReadingSession.objects.filter(owner=user, date__gte=first, date__lte=last, ended_at__isnull=False)
        .values("date")
        .annotate(m=Sum("duration_minutes"), p=Sum("pages_read"), n=Count("id"))
    ):
        per_day[row["date"]]["reading_minutes"] += row["m"] or 0
        per_day[row["date"]]["reading_pages"] += row["p"] or 0
        per_day[row["date"]]["reading_sessions"] += row["n"]
    for row in (
        WorkoutSession.objects.filter(owner=user, date__gte=first, date__lte=last, status__in=[SessionStatus.COMPLETED, SessionStatus.PARTIAL])
        .values("date")
        .annotate(m=Sum("duration_minutes"), n=Count("id"))
    ):
        per_day[row["date"]]["workout_minutes"] += row["m"] or 0
        per_day[row["date"]]["workouts"] += row["n"]

    occurrences = expand(user, start, end) if (last - first).days <= 400 else []
    attended = 0
    for o in occurrences:
        d = o.start.astimezone(zone).date()
        if d in per_day:
            per_day[d]["events"] += 1
            if o.attendance in ("attended", "completed"):
                per_day[d]["events_attended"] += 1
                attended += 1

    totals = defaultdict(int)
    for d in days:
        for k, v in per_day[d].items():
            totals[k] += v
    task_den = totals["tasks_planned"] - totals["tasks_cancelled"]
    productive = sorted((d for d in days if per_day[d]["completed_any_day"]), key=lambda d: (-per_day[d]["completed_any_day"], d))[:3]
    habit_scheduled = sum(r["scheduled"] - r["skipped"] for r in habit_rows if not r["weekly_target"])
    habit_done = sum(r["done"] for r in habit_rows if not r["weekly_target"])
    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "time_zone": prefs.time_zone,
        "days": [
            {
                "date": d.isoformat(),
                **{
                    k: per_day[d].get(k, 0)
                    for k in (
                        "tasks_planned",
                        "tasks_completed",
                        "tasks_cancelled",
                        "tasks_postponed",
                        "completed_any_day",
                        "habits_scheduled",
                        "habits_done",
                        "reading_minutes",
                        "workouts",
                        "workout_minutes",
                        "events",
                        "events_attended",
                    )
                },
            }
            for d in days
        ],
        "tasks": {
            "planned": totals["tasks_planned"],
            "completed": totals["tasks_completed"],
            "cancelled": totals["tasks_cancelled"],
            "postponed": totals["tasks_postponed"],
            "completed_any_day": totals["completed_any_day"],
            "open_now": planned.filter(status__in=OPEN_STATUSES).count(),
            "rescheduled": TaskActivity.objects.filter(task__owner=user, kind=TaskActivity.Kind.RESCHEDULED, at__gte=start, at__lt=end).count(),
            "completion_rate": _rate(totals["tasks_completed"], task_den),
        },
        "habits": {"items": habit_rows, "consistency": _rate(habit_done, habit_scheduled), "done": habit_done, "scheduled": habit_scheduled},
        "events": {"total": totals["events"], "attended": attended},
        "reading": {
            "minutes": totals["reading_minutes"],
            "pages": totals["reading_pages"],
            "sessions": totals["reading_sessions"],
            "books_completed": Book.objects.filter(owner=user, status=BookStatus.COMPLETED, completed_date__gte=first, completed_date__lte=last).count(),
        },
        "fitness": {"sessions": totals["workouts"], "minutes": totals["workout_minutes"]},
        "most_productive_days": [{"date": d.isoformat(), "completed": per_day[d]["completed_any_day"]} for d in productive],
        "has_activity": any(totals.values()),
        "definitions": DEFINITIONS,
    }


def goal_progress(goal: Goal, today: date | None = None) -> dict:
    user = goal.owner
    zone = get_zone(user.preferences.time_zone)
    today = today or local_today(zone)
    last = min(today, goal.due_date) if goal.due_date else today
    first = goal.start_date
    value = Decimal(0)
    if goal.metric == GoalMetric.MANUAL:
        value = goal.current_value
    elif first <= last:
        if goal.metric == GoalMetric.BOOKS_COMPLETED:
            value = Decimal(Book.objects.filter(owner=user, status=BookStatus.COMPLETED, completed_date__gte=first, completed_date__lte=last).count())
        elif goal.metric == GoalMetric.READING_MINUTES:
            value = Decimal(ReadingSession.objects.filter(owner=user, date__gte=first, date__lte=last).aggregate(s=Sum("duration_minutes"))["s"] or 0)
        elif goal.metric in (GoalMetric.WORKOUT_SESSIONS, GoalMetric.WORKOUT_MINUTES):
            qs = WorkoutSession.objects.filter(owner=user, date__gte=first, date__lte=last, status__in=[SessionStatus.COMPLETED, SessionStatus.PARTIAL])
            value = Decimal(qs.count() if goal.metric == GoalMetric.WORKOUT_SESSIONS else (qs.aggregate(s=Sum("duration_minutes"))["s"] or 0))
        elif goal.metric == GoalMetric.HABIT_COMPLETIONS and goal.habit_id:
            value = Decimal(HabitCompletion.objects.filter(habit_id=goal.habit_id, date__gte=first, date__lte=last, status=CompletionStatus.DONE).count())
        elif goal.metric == GoalMetric.TASKS_COMPLETED:
            s, e = range_bounds(first, last, zone)
            value = Decimal(Task.objects.filter(owner=user, status=TaskStatus.COMPLETED, completed_at__gte=s, completed_at__lt=e).count())
    pct = float(min(value / goal.target_value, 1)) if goal.target_value else None
    expected = None
    if goal.due_date and goal.due_date > goal.start_date:
        expected = min(max((today - goal.start_date).days / (goal.due_date - goal.start_date).days, 0), 1)
    return {
        "value": str(value),
        "target": str(goal.target_value),
        "progress": round(pct, 4) if pct is not None else None,
        "expected_progress": round(expected, 4) if expected is not None else None,
        "reached": value >= goal.target_value,
    }


def monthly_trend(user, first: date, last: date) -> list[dict]:
    """Per-calendar-month buckets between first..last (used for yearly and multi-month views)."""
    out = []
    cursor = first.replace(day=1)
    while cursor <= last:
        nxt = (cursor + timedelta(days=32)).replace(day=1)
        stats = range_stats(user, max(cursor, first), min(nxt - timedelta(days=1), last))
        out.append(
            {
                "month": cursor.strftime("%Y-%m"),
                "tasks_completed": stats["tasks"]["completed_any_day"],
                "task_completion_rate": stats["tasks"]["completion_rate"],
                "habit_consistency": stats["habits"]["consistency"],
                "reading_minutes": stats["reading"]["minutes"],
                "books_completed": stats["reading"]["books_completed"],
                "workouts": stats["fitness"]["sessions"],
            }
        )
        cursor = nxt
    return out


def accomplishments(user, first: date, last: date) -> list[str]:
    """Plain-language wins built only from recorded data."""
    s = range_stats(user, first, last)
    wins = []
    if s["tasks"]["completed_any_day"]:
        wins.append(f"Completed {s['tasks']['completed_any_day']} task{'s' if s['tasks']['completed_any_day'] != 1 else ''}.")
    if s["reading"]["books_completed"]:
        wins.append(f"Finished {s['reading']['books_completed']} book{'s' if s['reading']['books_completed'] != 1 else ''}.")
    if s["reading"]["minutes"]:
        wins.append(f"Read for {s['reading']['minutes']} minutes.")
    if s["fitness"]["sessions"]:
        wins.append(f"Logged {s['fitness']['sessions']} workout{'s' if s['fitness']['sessions'] != 1 else ''}.")
    for h in s["habits"]["items"]:
        if h["rate"] is not None and h["rate"] >= 0.8 and h["scheduled"] >= 3:
            wins.append(f"Kept up “{h['name']}” on {h['done']} of {h['scheduled'] - h['skipped']} days.")
    for g in Goal.objects.filter(owner=user, completed_at__date__gte=first, completed_at__date__lte=last):
        wins.append(f"Reached your goal: {g.title}.")
    return wins


def outstanding_tasks(user, limit: int = 20) -> list[dict]:
    zone = get_zone(user.preferences.time_zone)
    today = local_today(zone)
    qs = Task.objects.filter(owner=user, deleted_at__isnull=True, status__in=OPEN_STATUSES).filter(Q(scheduled_date__lt=today) | Q(scheduled_date__isnull=True, deadline__isnull=False))
    return list(qs.order_by("scheduled_date")[:limit].values("id", "title", "scheduled_date", "priority"))
