"""Habit scheduling, completion recording and progress/streak calculations.

Calculation rules (documented in docs/DATA_MODEL.md §Habits):

* A day is *scheduled* when it is on/after ``start_date`` and matches ``schedule_rule`` (every day is eligible for
  times-per-week habits). Paused/archived habits have no scheduled days after ``paused_at``.
* A completion is ``done`` when value ≥ target (binary habits store value 1), ``partial`` when 0 < value < target,
  ``skipped`` for a deliberate rest day. Rest days are neutral: they neither count as done nor break a streak.
* Completion rate = done ÷ (scheduled − skipped) over the period; ``None`` when nothing was scheduled (never 0 %).
* Streak (schedule habits): consecutive scheduled days that are done, walking back from today (today is not yet a miss).
  Streak (times-per-week habits): consecutive weeks that met the weekly target (current week counts once met).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.recurrence import occurrence_dates_between
from apps.core.timeutils import get_zone, local_today, week_start

from .models import CompletionStatus, Habit, HabitCompletion, HabitStatus, TargetType

STREAK_LOOKBACK_DAYS = 400


def scheduled_dates(habit: Habit, first: date, last: date) -> list[date]:
    first = max(first, habit.start_date)
    if habit.status != HabitStatus.ACTIVE and habit.paused_at:
        last = min(last, habit.paused_at.astimezone(get_zone(habit.time_zone)).date() - timedelta(days=1))
    if first > last:
        return []
    if habit.times_per_week:
        return [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return occurrence_dates_between(habit.schedule_rule, habit.start_date, first, last)


def is_scheduled(habit: Habit, day: date) -> bool:
    return bool(scheduled_dates(habit, day, day))


def _status_for(habit: Habit, value: Decimal) -> str:
    if habit.target_type == TargetType.BINARY:
        return CompletionStatus.DONE if value > 0 else CompletionStatus.PARTIAL
    return CompletionStatus.DONE if value >= habit.target_value else CompletionStatus.PARTIAL


@transaction.atomic
def record_completion(habit: Habit, day: date, *, value: Decimal | None = None, status: str | None = None, notes: str | None = None, mark_target: bool = False) -> HabitCompletion:
    """Upsert the single completion record for (habit, day). Safe to call repeatedly (unique constraint)."""
    if day > local_today(get_zone(habit.time_zone)):
        from apps.core.exceptions import BusinessRuleError

        raise BusinessRuleError("You can't log a habit for a future day.", code="invalid", status_code=400)
    comp, _ = HabitCompletion.objects.select_for_update().get_or_create(habit=habit, date=day)
    if status == CompletionStatus.SKIPPED:
        comp.status, comp.value = CompletionStatus.SKIPPED, Decimal(0)
    else:
        if mark_target or (value is None and habit.target_type == TargetType.BINARY):
            value = habit.target_value if habit.target_type != TargetType.BINARY else Decimal(1)
        comp.value = Decimal(value if value is not None else comp.value)
        comp.status = status or _status_for(habit, comp.value)
    if notes is not None:
        comp.notes = notes
    comp.completed_at = timezone.now() if comp.status == CompletionStatus.DONE else None
    comp.save()
    _resync(habit)
    return comp


@transaction.atomic
def increment(habit: Habit, day: date, amount: Decimal) -> HabitCompletion:
    comp = HabitCompletion.objects.select_for_update().filter(habit=habit, date=day).first()
    current = comp.value if comp and comp.status != CompletionStatus.SKIPPED else Decimal(0)
    new_value = max(Decimal(0), current + amount)
    return record_completion(habit, day, value=new_value)


@transaction.atomic
def undo(habit: Habit, day: date) -> None:
    HabitCompletion.objects.filter(habit=habit, date=day).delete()
    _resync(habit)


def _resync(habit: Habit) -> None:
    """A habit completed today must not keep reminding; reopening it must restore the reminder."""
    from apps.reminders.services import resync_for_habit

    resync_for_habit(habit.id)


@dataclass
class Progress:
    scheduled: int
    done: int
    partial: int
    skipped: int
    rate: float | None
    total_value: Decimal
    weekly_target: int | None = None
    weeks_met: int | None = None
    weeks: int | None = None

    def as_dict(self) -> dict:
        return {
            "scheduled": self.scheduled,
            "done": self.done,
            "partial": self.partial,
            "skipped": self.skipped,
            "rate": self.rate,
            "total_value": str(self.total_value),
            "weekly_target": self.weekly_target,
            "weeks_met": self.weeks_met,
            "weeks": self.weeks,
        }


def progress(habit: Habit, first: date, last: date, completions: dict[date, HabitCompletion] | None = None, week_starts_on: int = 0) -> Progress:
    if completions is None:
        completions = {c.date: c for c in habit.completions.filter(date__gte=first, date__lte=last)}
    days = scheduled_dates(habit, first, last)
    in_period = [completions[d] for d in completions if first <= d <= last]
    total = sum((c.value for c in in_period if c.status != CompletionStatus.SKIPPED), Decimal(0))
    if habit.times_per_week:
        weeks: dict[date, int] = {}
        for d in days:
            weeks.setdefault(week_start(d, week_starts_on), 0)
        for c in in_period:
            if c.status == CompletionStatus.DONE:
                weeks[week_start(c.date, week_starts_on)] = weeks.get(week_start(c.date, week_starts_on), 0) + 1
        met = sum(1 for n in weeks.values() if n >= habit.times_per_week)
        done = sum(1 for c in in_period if c.status == CompletionStatus.DONE)
        return Progress(
            scheduled=len(weeks) * habit.times_per_week,
            done=done,
            partial=sum(1 for c in in_period if c.status == CompletionStatus.PARTIAL),
            skipped=sum(1 for c in in_period if c.status == CompletionStatus.SKIPPED),
            rate=(min(done, len(weeks) * habit.times_per_week) / (len(weeks) * habit.times_per_week)) if weeks else None,
            total_value=total,
            weekly_target=habit.times_per_week,
            weeks_met=met,
            weeks=len(weeks),
        )
    day_set = set(days)
    done = sum(1 for d in day_set if d in completions and completions[d].status == CompletionStatus.DONE)
    partial = sum(1 for d in day_set if d in completions and completions[d].status == CompletionStatus.PARTIAL)
    skipped = sum(1 for d in day_set if d in completions and completions[d].status == CompletionStatus.SKIPPED)
    denominator = len(day_set) - skipped
    return Progress(scheduled=len(day_set), done=done, partial=partial, skipped=skipped, rate=(done / denominator) if denominator > 0 else None, total_value=total)


def streaks(habit: Habit, today: date, completions: dict[date, HabitCompletion] | None = None, week_starts_on: int = 0) -> dict:
    first = max(habit.start_date, today - timedelta(days=STREAK_LOOKBACK_DAYS))
    if completions is None:
        completions = {c.date: c for c in habit.completions.filter(date__gte=first, date__lte=today)}
    if habit.times_per_week:
        return _weekly_streaks(habit, today, first, completions, week_starts_on)
    days = scheduled_dates(habit, first, today)
    current = best = run = 0
    for d in days:  # chronological: compute best
        c = completions.get(d)
        if c and c.status == CompletionStatus.DONE:
            run += 1
            best = max(best, run)
        elif c and c.status == CompletionStatus.SKIPPED:
            continue
        elif d != today:
            run = 0
    for d in reversed(days):  # walk back for current
        c = completions.get(d)
        if c and c.status == CompletionStatus.DONE:
            current += 1
        elif (c and c.status == CompletionStatus.SKIPPED) or (d == today and not c):
            continue
        else:
            break
    return {"current": current, "best": best, "unit": "days"}


def _weekly_streaks(habit, today, first, completions, week_starts_on) -> dict:
    counts: dict[date, int] = {}
    for d, c in completions.items():
        if c.status == CompletionStatus.DONE:
            counts[week_start(d, week_starts_on)] = counts.get(week_start(d, week_starts_on), 0) + 1
    this_week = week_start(today, week_starts_on)
    weeks = []
    w = week_start(max(first, habit.start_date), week_starts_on)
    while w <= this_week:
        weeks.append(w)
        w += timedelta(days=7)
    best = run = 0
    for w in weeks:
        if counts.get(w, 0) >= habit.times_per_week:
            run += 1
            best = max(best, run)
        elif w != this_week:
            run = 0
    current = 0
    for w in reversed(weeks):
        if counts.get(w, 0) >= habit.times_per_week:
            current += 1
        elif w == this_week:
            continue
        else:
            break
    return {"current": current, "best": best, "unit": "weeks"}
