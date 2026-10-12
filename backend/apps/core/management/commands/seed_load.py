"""Generate a realistic load-test dataset: N "heavy" users, each with a year of history.

    python manage.py seed_load --users 100            # development
    python manage.py seed_load --users 100 --force    # an isolated load-test environment with DEBUG off

Per user (defaults): ~1,500 historical tasks (+ today/upcoming), 3 recurring task series, ~150 one-off events plus 5 recurring
series with exceptions, 20 daily reminders (14-day horizon materialised) plus a year of delivered-reminder history,
8 habits with a year of completions, 20 books / 300 reading sessions, 150 workouts, 1,500 water entries, 200 journal entries.
Users are created as loadtest-<n>@daywell.loadtest with password from --password. Never run against real user data.
"""

import random
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

DOMAIN = "daywell.loadtest"


class Command(BaseCommand):
    help = "Create load-test users with a year of realistic data (non-production only)."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=50)
        parser.add_argument("--password", default="Loadtest-password-2026")
        parser.add_argument("--history-days", type=int, default=365)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("seed_load creates synthetic users. Use --force only on an isolated load-test environment.")
        from apps.accounts.models import User

        existing = User.objects.filter(email__endswith=f"@{DOMAIN}").count()
        for n in range(existing, existing + opts["users"]):
            self._user(n, opts["password"], opts["history_days"], random.Random(n))  # noqa: S311 (synthetic data, not crypto)
            self.stdout.write(f"user {n + 1}/{existing + opts['users']}")
        self.stdout.write(self.style.SUCCESS(f"{User.objects.filter(email__endswith=f'@{DOMAIN}').count()} load-test users present."))

    @transaction.atomic
    def _user(self, n, password, days, rnd):
        from apps.accounts.models import User
        from apps.core.timeutils import combine, get_zone, local_today
        from apps.events.models import CalendarEvent, EventException
        from apps.events.services import refresh_bounds
        from apps.fitness.models import WorkoutRoutine, WorkoutSession
        from apps.habits.models import Habit, HabitCompletion
        from apps.reading.models import Book, ReadingSession
        from apps.reminders.models import Reminder, ReminderOccurrence
        from apps.reminders.services import set_item_reminders, sync_reminder
        from apps.tasks import services as task_services
        from apps.tasks.models import Task, TaskActivity
        from apps.wellness.models import JournalEntry, WaterIntake

        user = User.objects.create_user(email=f"loadtest-{n}@{DOMAIN}", password=password, display_name=f"Load {n}")
        prefs = user.preferences
        prefs.time_zone = "Africa/Nairobi"
        prefs.onboarding_completed_at = timezone.now()
        prefs.modules = {**prefs.modules, "reading": True, "fitness": True, "hydration": True, "journal": True, "goals": True}
        prefs.save()
        zone = get_zone(prefs.time_zone)
        today = local_today(zone)
        now = timezone.now()

        # Tasks: a year of history + today/upcoming.
        tasks = []
        for i in range(int(days * 4.1)):
            d = today - timedelta(days=rnd.randint(1, days))
            status = rnd.choices(["completed", "cancelled", "pending", "postponed"], [70, 10, 15, 5])[0]
            t = time(rnd.randint(7, 19), rnd.choice([0, 15, 30, 45])) if rnd.random() < 0.4 else None
            tasks.append(Task(owner=user, title=f"Task {i}", priority=rnd.choice(["low", "normal", "normal", "high", "urgent"]), status=status,
                              scheduled_date=d, scheduled_time=t, scheduled_at=combine(d, t, zone) if t else None, time_zone=prefs.time_zone,
                              completed_at=combine(d, time(18, 0), zone) if status == "completed" else None, duration_minutes=rnd.choice([None, 15, 30, 60])))
        for i in range(30):
            d = today + timedelta(days=rnd.randint(0, 14))
            t = time(rnd.randint(8, 18), 0) if rnd.random() < 0.5 else None
            tasks.append(Task(owner=user, title=f"Upcoming {i}", priority=rnd.choice(["normal", "high", "urgent"]), scheduled_date=d, scheduled_time=t,
                              scheduled_at=combine(d, t, zone) if t else None, time_zone=prefs.time_zone, duration_minutes=30))
        Task.objects.bulk_create(tasks, batch_size=1000)
        created = list(Task.objects.filter(owner=user, status="completed").values_list("id", "completed_at")[:1500])
        TaskActivity.objects.bulk_create([TaskActivity(task_id=i, kind="completed", at=at) for i, at in created], batch_size=1000)
        for title, rule in [("Water plants", "FREQ=WEEKLY;BYDAY=MO,TH"), ("Standup notes", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"), ("Review budget", "FREQ=MONTHLY;BYMONTHDAY=1")]:
            task_services.create_task(user, {"title": title, "scheduled_date": today - timedelta(days=10), "scheduled_time": time(9, 0)}, rrule=rule)
        timed_today = Task.objects.filter(owner=user, scheduled_date=today, scheduled_time__isnull=False).first()
        if timed_today:
            set_item_reminders(user, [{"offset_minutes": 15, "anchor": "start"}], task=timed_today)

        # Events: one-offs over the year and next month, plus recurring series with exceptions.
        events = []
        for i in range(150):
            d = today + timedelta(days=rnd.randint(-days, 30))
            h = rnd.randint(8, 17)
            ev = CalendarEvent(owner=user, title=f"Meeting {i}", time_zone=prefs.time_zone, start_date=d, start_time=time(h, 0), end_date=d, end_time=time(h, 45),
                               location=rnd.choice(["", "Office", "Online"]))
            refresh_bounds(ev)
            events.append(ev)
        CalendarEvent.objects.bulk_create(events, batch_size=500)
        for j, (title, rule) in enumerate([("Standup", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"), ("Gym class", "FREQ=WEEKLY;BYDAY=TU,TH"), ("1:1", "FREQ=WEEKLY;INTERVAL=2"),
                                           ("Family call", "FREQ=WEEKLY;BYDAY=SU"), ("Book club", "FREQ=MONTHLY;BYMONTHDAY=15")]):
            start = today - timedelta(days=days)
            ev = CalendarEvent(owner=user, title=title, time_zone=prefs.time_zone, start_date=start, start_time=time(9 + j * 2, 0), end_date=start,
                               end_time=time(9 + j * 2, 30), rrule=rule)
            refresh_bounds(ev)
            ev.save()
            for _ in range(2):
                d = today - timedelta(days=rnd.randint(1, 60))
                EventException.objects.get_or_create(event=ev, original_key=f"{d.isoformat()}T{9 + j * 2:02d}:00", defaults={"cancelled": True})
            set_item_reminders(user, [{"offset_minutes": 10, "anchor": "start"}], event=ev)

        # Reminders: 20 daily reminders (horizon materialised) + a year of delivered history.
        reminders = []
        for i in range(20):
            reminders.append(Reminder.objects.create(owner=user, title=f"Reminder {i}", category="custom", dtstart_date=today - timedelta(days=days),
                                                     dtstart_time=time(7 + i % 14, 0), rrule="FREQ=DAILY", time_zone=prefs.time_zone))
        for r in reminders:
            sync_reminder(r)
        history = []
        for d in range(1, days + 1):
            for r in reminders[:5]:
                at = combine(today - timedelta(days=d), r.dtstart_time, zone)
                history.append(ReminderOccurrence(reminder=r, owner=user, category="custom", title=r.title, scheduled_for=at, fire_at=at, sent_at=at,
                                                  status=rnd.choice(["dismissed", "completed", "snoozed", "missed"]), acted_at=at + timedelta(minutes=2),
                                                  read_at=at, idempotency_key=f"load:{r.id}:{d}"))
        ReminderOccurrence.objects.bulk_create(history, batch_size=2000)

        # Habits with a year of completions.
        habits = [Habit.objects.create(owner=user, name=f"Habit {i}", start_date=today - timedelta(days=days), time_zone=prefs.time_zone,
                                       target_type="count" if i % 3 == 0 else "binary", target_value=8 if i % 3 == 0 else 1,
                                       schedule_rule="FREQ=DAILY" if i % 2 == 0 else "FREQ=WEEKLY;BYDAY=MO,WE,FR", position=i) for i in range(8)]
        comps = [HabitCompletion(habit=h, date=today - timedelta(days=d), status="done", value=Decimal(h.target_value), completed_at=now)
                 for h in habits for d in range(1, days + 1) if rnd.random() < 0.7]
        HabitCompletion.objects.bulk_create(comps, batch_size=2000)

        books = [Book(owner=user, title=f"Book {i}", status="completed" if i < 15 else "reading", total_pages=300, current_page=300 if i < 15 else 120,
                      completed_date=today - timedelta(days=rnd.randint(1, days)) if i < 15 else None) for i in range(20)]
        Book.objects.bulk_create(books)
        books = list(Book.objects.filter(owner=user))
        sess = []
        for _ in range(300):
            d = today - timedelta(days=rnd.randint(1, days))
            st = combine(d, time(21, 0), zone)
            sess.append(ReadingSession(owner=user, book=rnd.choice(books), date=d, started_at=st, ended_at=st + timedelta(minutes=25), duration_minutes=25, pages_read=15))
        ReadingSession.objects.bulk_create(sess, batch_size=1000)
        routine = WorkoutRoutine.objects.create(owner=user, name="Strength", days=[0, 2, 4], time=time(18, 0))
        WorkoutSession.objects.bulk_create([WorkoutSession(owner=user, routine=routine, date=today - timedelta(days=rnd.randint(1, days)), duration_minutes=45)
                                            for _ in range(150)], batch_size=1000)
        WaterIntake.objects.bulk_create([WaterIntake(owner=user, date=today - timedelta(days=i % days), at=now - timedelta(days=i % days), amount_ml=250)
                                         for i in range(1500)], batch_size=2000)
        JournalEntry.objects.bulk_create([JournalEntry(owner=user, date=today - timedelta(days=i), body="Synthetic load-test entry.") for i in range(200)])
