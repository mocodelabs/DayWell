"""Today dashboard / morning briefing / evening recap — computed from the user's real records only.

No external AI is called. Greeting variety comes from rule-based templates in :mod:`apps.briefing.messages`.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.timeutils import day_bounds, get_zone, local_today
from apps.events.services import expand, find_conflicts
from apps.tasks.models import OPEN_STATUSES, PRIORITY_RANK, Task, TaskStatus
from apps.tasks.views import PRIORITY_ORDER

from . import messages


def _fmt_time(dt: datetime, prefs) -> str:
    local = dt.astimezone(get_zone(prefs.time_zone))
    if prefs.time_format == "12h":
        return local.strftime("%I:%M %p").lstrip("0")
    return local.strftime("%H:%M")


def task_card(t: Task, today) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "priority": t.priority,
        "status": t.status,
        "scheduled_date": t.scheduled_date.isoformat() if t.scheduled_date else None,
        "scheduled_time": t.scheduled_time.strftime("%H:%M") if t.scheduled_time else None,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "duration_minutes": t.duration_minutes,
        "category": t.category_id,
        "is_overdue": t.status in OPEN_STATUSES and ((t.scheduled_date and t.scheduled_date < today) or bool(t.deadline and t.deadline < timezone.now())),
        "is_recurring": t.series_id is not None,
    }


def recommend_priorities(tasks: list[Task], today, limit: int = 3) -> list[Task]:
    """Three suggested priorities: overdue first, then priority, deadline, then scheduled time. Suggestions only."""
    now = timezone.now()
    far = datetime.max.replace(tzinfo=UTC)

    def key(t: Task):
        overdue = bool((t.scheduled_date and t.scheduled_date < today) or (t.deadline and t.deadline < now))
        return (not overdue, PRIORITY_RANK.get(t.priority, 2), t.deadline or far, t.scheduled_time or time.max, t.created_at)

    return sorted(tasks, key=key)[:limit]


def today_payload(user, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    prefs = user.preferences
    zone = get_zone(prefs.time_zone)
    local_now = now.astimezone(zone)
    today = local_now.date()
    start, end = day_bounds(today, zone)
    seed = f"{user.pk}:{today.isoformat()}"
    modules = {k: prefs.module_enabled(k) for k in prefs.modules}

    # Tasks
    base = Task.objects.filter(owner=user, deleted_at__isnull=True)
    today_tasks = list(base.filter(scheduled_date=today).exclude(status=TaskStatus.CANCELLED).select_related("category"))
    overdue_qs = base.filter(status__in=OPEN_STATUSES).filter(Q(scheduled_date__lt=today) | Q(deadline__lt=now))
    overdue_count = overdue_qs.count()  # the list below is capped; the count must not be
    # Most important first so the "top priorities" suggestion can't miss an urgent task among many old ones.
    overdue = list(overdue_qs.annotate(priority_rank=PRIORITY_ORDER).order_by("priority_rank", "-scheduled_date")[:20])
    open_candidates = [t for t in today_tasks if t.status in OPEN_STATUSES] + [t for t in overdue if t.scheduled_date != today]
    priorities = recommend_priorities(open_candidates, today)

    # Calendar
    occurrences = expand(user, start, end)
    conflicts = find_conflicts(occurrences)
    agenda = []
    for o in occurrences:
        agenda.append(
            {
                "type": "event",
                "id": o.event_id,
                "key": o.key,
                "title": o.title,
                "start": o.start.isoformat(),
                "end": o.end.isoformat(),
                "all_day": o.all_day,
                "location": o.location,
                "meeting_url": o.meeting_url,
                "attendance": o.attendance,
                "color": o.color,
                "is_recurring": o.is_recurring,
            }
        )
    for t in today_tasks:
        if t.scheduled_at:
            agenda.append(
                {
                    "type": "task",
                    "id": t.id,
                    "title": t.title,
                    "start": t.scheduled_at.isoformat(),
                    "end": (t.scheduled_at + timedelta(minutes=t.duration_minutes or 30)).isoformat(),
                    "all_day": False,
                    "status": t.status,
                }
            )
    agenda.sort(key=lambda a: (not a["all_day"], a["start"]))
    timed = [a for a in agenda if not a["all_day"] and a.get("status") not in (TaskStatus.COMPLETED,)]
    now_iso = now.isoformat()
    remaining = [a for a in timed if a["end"] > now_iso]  # ongoing or still to come — never name something already over
    next_up = remaining[0] if remaining else None
    first_commitment = next((a for a in remaining if a["type"] == "event"), None) or next_up

    # Habits
    from apps.habits.models import CompletionStatus, Habit, HabitCompletion, HabitStatus
    from apps.habits.services import is_scheduled

    habits = [h for h in Habit.objects.filter(owner=user, status=HabitStatus.ACTIVE) if is_scheduled(h, today)]
    comps = {c.habit_id: c for c in HabitCompletion.objects.filter(habit__in=habits, date=today)}
    habit_items = [
        {
            "id": h.id,
            "name": h.name,
            "icon": h.icon,
            "color": h.color,
            "target_type": h.target_type,
            "target_value": str(h.target_value),
            "unit": h.unit,
            "value": str(comps[h.id].value) if h.id in comps else "0",
            "status": comps[h.id].status if h.id in comps else None,
            "times_per_week": h.times_per_week,
        }
        for h in habits
    ]
    habits_done = sum(1 for h in habit_items if h["status"] == CompletionStatus.DONE)
    habits_rest = sum(1 for h in habit_items if h["status"] == CompletionStatus.SKIPPED)

    # Reminders
    from apps.reminders import selectors

    upcoming = list(selectors.upcoming(user, hours=max(1, int((end - now).total_seconds() // 3600) + 1), now=now).filter(fire_at__lt=end)[:5])
    reminder_summary = {
        "upcoming": [{"id": o.id, "title": o.title, "fire_at": o.fire_at.isoformat(), "category": o.category} for o in upcoming],
        "active": selectors.active_alarms(user, now).count(),
        "missed": selectors.missed(user, now).count(),
    }

    # Progress (only counts things that were actually planned for today)
    tasks_total = len(today_tasks)
    tasks_done = len([t for t in today_tasks if t.status == TaskStatus.COMPLETED])
    events_timed = [o for o in occurrences if not o.all_day]
    attended = sum(1 for o in occurrences if o.attendance in ("attended", "completed"))
    total_items = tasks_total + (len(habit_items) - habits_rest)
    done_items = tasks_done + habits_done
    progress = {
        "tasks_done": tasks_done,
        "tasks_total": tasks_total,
        "habits_done": habits_done,
        "habits_total": len(habit_items) - habits_rest,
        "events_total": len(occurrences),
        "events_attended": attended,
        "overall": round(done_items / total_items, 3) if total_items else None,
    }

    # Briefing text
    tone = prefs.tone
    greet = messages.greeting(user.greeting_name, local_now, tone, seed) if prefs.greeting_enabled else None
    first_label = first_commitment["title"] if first_commitment else None
    first_time = _fmt_time(datetime.fromisoformat(first_commitment["start"]), prefs) if first_commitment else None
    open_today = [t for t in today_tasks if t.status in OPEN_STATUSES]
    briefing = {
        "style": prefs.briefing_style,
        "schedule": messages.schedule_sentence(
            len(events_timed) + len([o for o in occurrences if o.all_day]), len(open_today), first_label, first_time, tone,
            minutes_until=int((datetime.fromisoformat(first_commitment["start"]) - now).total_seconds() // 60) if first_commitment else None,
        ),
        "getting_started": messages.getting_started(priorities[0].title if priorities else None, tone, seed),
        "conflicts": (f"Heads up: {len(conflicts)} scheduling conflict{'s' if len(conflicts) != 1 else ''} today." if conflicts else ""),
        "overdue": (
            f"{overdue_count} task{'s are' if overdue_count != 1 else ' is'} waiting from earlier. No pressure — pick what still matters."
            if overdue_count and tone != "direct"
            else (f"Overdue: {overdue_count}." if overdue_count else "")
        ),
    }

    payload = {
        "generated_at": now.isoformat(),
        "local": {"date": today.isoformat(), "time": local_now.strftime("%H:%M"), "iso": local_now.isoformat(), "time_zone": prefs.time_zone, "weekday": local_now.strftime("%A")},
        "greeting": greet,
        "briefing": briefing,
        "agenda": agenda,
        "next_up": next_up,
        "tasks_today": [task_card(t, today) for t in sorted(today_tasks, key=lambda t: (t.status == TaskStatus.COMPLETED, t.scheduled_time or time.max, PRIORITY_RANK.get(t.priority, 2)))],
        "priorities": [task_card(t, today) for t in priorities],
        "overdue": {"count": overdue_count, "items": [task_card(t, today) for t in overdue[:5]]},
        "habits": {"items": habit_items, "done": habits_done, "total": len(habit_items) - habits_rest},
        "reminders": reminder_summary,
        "progress": progress,
        "conflicts": conflicts,
        "modules": modules,
        "layout": prefs.dashboard_layout,
        "evening": evening_payload(user, prefs, local_now, today_tasks, tone) if local_now.time() >= min(prefs.evening_time, time(17, 0)) else None,
    }
    if modules.get("affirmations"):
        from apps.affirmations.services import for_day

        ua = for_day(user, today)
        payload["affirmation"] = {"id": ua.id, "text": ua.affirmation.text, "category": ua.affirmation.category, "acknowledged": ua.acknowledged_at is not None} if ua else None
    if modules.get("reading"):
        from apps.reading.models import Book, BookStatus, ReadingSession
        from apps.reading.services import reading_streak

        current = Book.objects.filter(owner=user, status=BookStatus.READING).order_by("-updated_at").first()
        minutes = sum(ReadingSession.objects.filter(owner=user, date=today, ended_at__isnull=False).values_list("duration_minutes", flat=True))
        payload["reading"] = {
            "current_book": {
                "id": current.id,
                "title": current.title,
                "author": current.author,
                "current_page": current.current_page,
                "total_pages": current.total_pages,
                "daily_goal_minutes": current.daily_goal_minutes,
            }
            if current
            else None,
            "minutes_today": minutes,
            "streak": reading_streak(user, today),
            "running_session": ReadingSession.objects.filter(owner=user, ended_at__isnull=True).values("id", "book_id", "started_at").first(),
        }
    if modules.get("fitness"):
        from apps.fitness.services import today_plan

        payload["fitness"] = {"plan": today_plan(user, today)}
    if modules.get("hydration"):
        from apps.wellness.services import hydration_day

        payload["hydration"] = hydration_day(user, today)
    return payload


def evening_payload(user, prefs, local_now, today_tasks, tone) -> dict:
    planned = list(today_tasks)
    done = [t for t in planned if t.status == TaskStatus.COMPLETED]
    remaining = [t for t in planned if t.status in OPEN_STATUSES]
    return {
        "message": messages.evening_sentence(len(done), len(planned), len(remaining), tone),
        "remaining": [{"id": t.id, "title": t.title} for t in remaining],
        "headline": "Your day in review" if tone != "minimal" else "Today",
    }


# --- Briefing notifications (delivered through the reminder engine as system reminders) ---------------------------------


def sync_briefing_reminders(user) -> None:
    from apps.reminders.services import upsert_system_reminder

    prefs = user.preferences
    upsert_system_reminder(
        user,
        "briefing:morning",
        enabled=prefs.morning_notification and prefs.greeting_enabled,
        title="Your morning briefing",
        category="briefing",
        at=prefs.greeting_time,
        rrule="FREQ=DAILY",
    )
    upsert_system_reminder(user, "briefing:evening", enabled=prefs.evening_summary, title="Your evening recap", category="briefing", at=prefs.evening_time, rrule="FREQ=DAILY")


def briefing_push_text(occ, reminder, now: datetime) -> tuple[str, str]:
    """(title, body) for a due briefing push, computed at send time from real data.

    De-duplication rule: if the day's first event has its own reminder firing within 60 minutes, the briefing does not
    repeat that event's details — it only gives counts — so the same event never triggers two messages in a row.
    """
    user = occ.owner
    data = today_payload(user, now)
    if reminder.system_key == "briefing:evening":
        ev = data["evening"] or evening_payload(user, user.preferences, now.astimezone(get_zone(user.preferences.time_zone)), [], user.preferences.tone)
        return "Your day in review", ev["message"]
    from apps.reminders.models import OccurrenceStatus, ReminderOccurrence

    nxt = data["next_up"]
    covered = (
        nxt
        and ReminderOccurrence.objects.filter(
            owner=user, status=OccurrenceStatus.SCHEDULED, target_key__startswith=f"{nxt['type']}:{nxt['id']}", fire_at__gte=now, fire_at__lte=now + timedelta(minutes=60)
        ).exists()
    )
    events = len([a for a in data["agenda"] if a["type"] == "event"])
    tasks = len([t for t in data["tasks_today"] if t["status"] in OPEN_STATUSES])
    if covered or not nxt:
        body = messages.schedule_sentence(events, tasks, None, None, user.preferences.tone)
    else:
        body = data["briefing"]["schedule"]
    title = data["greeting"]["headline"] if data["greeting"] else "Good morning"
    return title, body


def tomorrow_date(user):
    return local_today(get_zone(user.preferences.time_zone)) + timedelta(days=1)
