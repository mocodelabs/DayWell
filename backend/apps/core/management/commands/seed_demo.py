"""Create (or refresh) a local demo account with realistic sample data. Never run against production.

python manage.py seed_demo                      # demo@daywell.test / DayWell-demo-2026
python manage.py seed_demo --email you@x.test --password '...'
"""

from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

DEMO_EMAIL = "demo@daywell.test"
DEMO_PASSWORD = "DayWell-demo-2026"  # local development only — documented in README.md


class Command(BaseCommand):
    help = "Create a demo user with sample tasks, events, reminders, habits, books and workouts (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEMO_EMAIL)
        parser.add_argument("--password", default=DEMO_PASSWORD)
        parser.add_argument("--time-zone", default="Africa/Nairobi")
        parser.add_argument("--force", action="store_true", help="Allow running with DEBUG off (still never use real data).")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("seed_demo is for development. Use --force if you really mean it.")
        from apps.accounts.models import User
        from apps.core.timeutils import get_zone, local_today
        from apps.events.models import CalendarEvent
        from apps.events.services import save_event
        from apps.fitness.models import WorkoutRoutine, WorkoutSession
        from apps.fitness.services import sync_routine_reminder
        from apps.habits.models import Habit
        from apps.habits.services import record_completion
        from apps.reading.models import Book, BookStatus, ReadingSession
        from apps.reminders.models import Reminder
        from apps.reminders.services import set_item_reminders, sync_reminder
        from apps.tasks import services as task_services

        User.objects.filter(email__iexact=opts["email"]).delete()
        user = User.objects.create_user(email=opts["email"], password=opts["password"], display_name="Amani")
        prefs = user.preferences
        prefs.time_zone = opts["time_zone"]
        prefs.onboarding_completed_at = timezone.now()
        prefs.modules = {**prefs.modules, "reading": True, "fitness": True, "hydration": True, "journal": True, "goals": True}
        prefs.reading_yearly_goal = 12
        prefs.save()
        zone = get_zone(prefs.time_zone)
        today = local_today(zone)

        t = task_services.create_task(user, {"title": "Send the quarterly report", "priority": "high", "scheduled_date": today, "scheduled_time": time(11, 0), "duration_minutes": 60})
        set_item_reminders(user, [{"offset_minutes": 15, "anchor": "start"}], task=t)
        task_services.create_task(user, {"title": "Call the supplier", "scheduled_date": today, "priority": "urgent"})
        task_services.create_task(user, {"title": "Book dentist appointment", "scheduled_date": today - timedelta(days=2)})
        task_services.create_task(user, {"title": "Plan the weekend trip", "scheduled_date": today + timedelta(days=2)}, subtasks=["Pick a place", "Book a room", "Pack"])
        task_services.create_task(user, {"title": "Water the plants", "scheduled_date": today}, rrule="FREQ=WEEKLY;BYDAY=MO,TH")
        done = task_services.create_task(user, {"title": "Reply to emails", "scheduled_date": today})
        task_services.complete(done)

        for title, day, start, end, rule in [
            ("Team standup", today, time(9, 0), time(9, 15), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
            ("Lunch with Wanjiru", today, time(13, 0), time(14, 0), ""),
            ("Book club", today + timedelta(days=3), time(18, 30), time(20, 0), ""),
        ]:
            ev = CalendarEvent(owner=user, title=title, time_zone=prefs.time_zone, start_date=day, start_time=start, end_date=day, end_time=end, rrule=rule)
            save_event(ev)
            set_item_reminders(user, [{"offset_minutes": 10, "anchor": "start"}], event=ev)

        r = Reminder.objects.create(owner=user, title="Take vitamins", category="custom", dtstart_date=today, dtstart_time=time(8, 30), rrule="FREQ=DAILY", time_zone=prefs.time_zone)
        sync_reminder(r)

        water = Habit.objects.create(
            owner=user, name="Drink water", category="hydration", target_type="count", target_value=8, unit="glasses", start_date=today - timedelta(days=10), time_zone=prefs.time_zone
        )
        stretch = Habit.objects.create(owner=user, name="Stretch", category="health", start_date=today - timedelta(days=10), time_zone=prefs.time_zone, position=1)
        Habit.objects.create(owner=user, name="Gym", category="fitness", times_per_week=3, start_date=today - timedelta(days=14), time_zone=prefs.time_zone, position=2)
        for d in range(1, 8):
            record_completion(stretch, today - timedelta(days=d))
            record_completion(water, today - timedelta(days=d), value=6 + d % 3)

        book = Book.objects.create(owner=user, title="Atomic Habits", author="James Clear", status=BookStatus.READING, total_pages=320, current_page=96, start_date=today - timedelta(days=9))
        Book.objects.create(owner=user, title="The Overstory", author="Richard Powers", status=BookStatus.WANT)
        for d in range(1, 6):
            start = timezone.now() - timedelta(days=d)
            ReadingSession.objects.create(
                owner=user, book=book, date=today - timedelta(days=d), started_at=start, ended_at=start + timedelta(minutes=20 + d), duration_minutes=20 + d, pages_read=12
            )

        routine = WorkoutRoutine.objects.create(
            owner=user, name="Strength", days=[0, 2, 4], time=time(18, 0), duration_minutes=45, location="Neighbourhood gym", prep_buffer_minutes=20, reminder_enabled=True
        )
        sync_routine_reminder(routine)
        for d in (2, 4, 7):
            WorkoutSession.objects.create(owner=user, routine=routine, date=today - timedelta(days=d), duration_minutes=40 + d, workout_type="Gym")

        # The shared demo must never fall into read-only mode.
        from apps.billing.services import account_for

        acct = account_for(user)
        acct.complimentary = True
        acct.save(update_fields=["complimentary", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Demo account ready: {opts['email']} (time zone {prefs.time_zone})."))
