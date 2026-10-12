from datetime import date, time, timedelta
from decimal import Decimal

import pytest
import time_machine

from apps.habits import services
from apps.habits.models import Habit
from apps.reminders.dispatch import dispatch_due
from apps.reminders.models import ReminderOccurrence

pytestmark = pytest.mark.django_db
TODAY = date(2026, 10, 9)  # Friday


@pytest.fixture(autouse=True)
def frozen():
    with time_machine.travel("2026-10-09T05:00:00Z", tick=False):
        yield


def habit(user, **kw):
    defaults = {"name": "Read", "start_date": TODAY - timedelta(days=30), "time_zone": "Africa/Nairobi"}
    return Habit.objects.create(owner=user, **{**defaults, **kw})


class TestCalculations:
    def test_binary_streak_and_rest_days(self, user):
        h = habit(user)
        for d in (1, 2, 4, 5):  # yesterday, 2 days ago, 4, 5 days ago — 3 days ago is a rest day
            services.record_completion(h, TODAY - timedelta(days=d))
        services.record_completion(h, TODAY - timedelta(days=3), status="skipped")
        s = services.streaks(h, TODAY)
        assert s["current"] == 4  # today not yet done is not a miss; rest day is neutral
        services.record_completion(h, TODAY)
        assert services.streaks(h, TODAY)["current"] == 5

    def test_missed_day_breaks_streak_but_keeps_history(self, user):
        h = habit(user)
        services.record_completion(h, TODAY - timedelta(days=1))
        services.record_completion(h, TODAY - timedelta(days=3))
        s = services.streaks(h, TODAY)
        assert s["current"] == 1 and s["best"] == 1
        assert h.completions.count() == 2

    def test_numeric_target_partial_then_done(self, user):
        h = habit(user, name="Water", target_type="count", target_value=8, unit="glasses")
        services.increment(h, TODAY, Decimal(3))
        assert h.completions.get(date=TODAY).status == "partial"
        services.increment(h, TODAY, Decimal(5))
        assert h.completions.get(date=TODAY).status == "done"
        services.increment(h, TODAY, Decimal(-10))
        assert h.completions.get(date=TODAY).value == 0

    def test_progress_rate_and_empty_period(self, user):
        h = habit(user, schedule_rule="FREQ=WEEKLY;BYDAY=MO,WE,FR", start_date=date(2026, 10, 5))
        services.record_completion(h, date(2026, 10, 5))
        services.record_completion(h, date(2026, 10, 7), status="skipped")
        p = services.progress(h, date(2026, 10, 5), date(2026, 10, 9))
        assert (p.scheduled, p.done, p.skipped) == (3, 1, 1)
        assert p.rate == 0.5  # done ÷ (scheduled − rest)
        assert services.progress(h, date(2026, 9, 1), date(2026, 9, 30)).rate is None  # nothing scheduled → no rate

    def test_times_per_week(self, user):
        h = habit(user, name="Gym", times_per_week=3, start_date=date(2026, 9, 28))
        for d in (date(2026, 9, 28), date(2026, 9, 30), date(2026, 10, 2), date(2026, 10, 5)):
            services.record_completion(h, d)
        s = services.streaks(h, TODAY)
        assert s == {"current": 1, "best": 1, "unit": "weeks"}  # last week met; this week (1/3) still in progress
        p = services.progress(h, date(2026, 10, 5), date(2026, 10, 11))
        assert p.weekly_target == 3 and p.weeks_met == 0

    def test_paused_habit_has_no_future_schedule(self, user):
        from django.utils import timezone

        h = habit(user)
        h.status, h.paused_at = "paused", timezone.now()
        h.save()
        assert not services.is_scheduled(h, TODAY + timedelta(days=1))

    def test_future_completion_rejected(self, api, user):
        h = habit(user)
        res = api.post(f"/api/v1/habits/{h.id}/complete/", {"date": "2026-10-20"})
        assert res.status_code == 400

    def test_duplicate_completion_impossible(self, user):
        h = habit(user)
        services.record_completion(h, TODAY)
        services.record_completion(h, TODAY)
        assert h.completions.count() == 1


class TestApi:
    def test_create_today_complete_undo(self, api):
        res = api.post("/api/v1/habits/", {"name": "Stretch", "category": "health", "schedule_rule": "FREQ=DAILY"})
        assert res.status_code == 201, res.json()
        hid = res.json()["id"]
        items = api.get("/api/v1/habits/today/").json()["items"]
        assert items[0]["scheduled"] and items[0]["completion"] is None
        state = api.post(f"/api/v1/habits/{hid}/complete/").json()
        assert state["completion"]["status"] == "done" and state["streak"]["current"] == 1
        state = api.post(f"/api/v1/habits/{hid}/undo/").json()
        assert state["completion"] is None

    def test_pause_keeps_history(self, api):
        hid = api.post("/api/v1/habits/", {"name": "Meditate", "schedule_rule": "FREQ=DAILY"}).json()["id"]
        api.post(f"/api/v1/habits/{hid}/complete/")
        assert api.post(f"/api/v1/habits/{hid}/pause/").json()["status"] == "paused"
        assert Habit.objects.get(pk=hid).completions.count() == 1
        assert api.get("/api/v1/habits/today/").json()["items"] == []
        assert api.post(f"/api/v1/habits/{hid}/resume/").json()["status"] == "active"

    def test_hourly_schedule_rejected(self, api):
        assert api.post("/api/v1/habits/", {"name": "x", "schedule_rule": "FREQ=HOURLY"}).status_code == 400

    def test_habit_reminder_skipped_once_done(self, api, user):
        hid = api.post("/api/v1/habits/", {"name": "Vitamins", "schedule_rule": "FREQ=DAILY", "reminder_time": "09:00"}).json()["id"]
        occ = ReminderOccurrence.objects.filter(reminder__habit_id=hid).order_by("fire_at").first()
        assert occ.fire_at.isoformat() == "2026-10-09T06:00:00+00:00"
        api.post(f"/api/v1/habits/{hid}/complete/")
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == "skipped" and occ.skip_reason == "habit_done"

    def test_pausing_disables_reminder(self, api):
        hid = api.post("/api/v1/habits/", {"name": "Vitamins", "schedule_rule": "FREQ=DAILY", "reminder_time": time(9, 0).isoformat()}).json()["id"]
        api.post(f"/api/v1/habits/{hid}/pause/")
        assert not ReminderOccurrence.objects.filter(reminder__habit_id=hid, status="scheduled").exists()

    def test_history(self, api):
        hid = api.post("/api/v1/habits/", {"name": "Walk", "schedule_rule": "FREQ=DAILY", "start_date": "2026-10-01"}).json()["id"]
        api.post(f"/api/v1/habits/{hid}/complete/", {"date": "2026-10-02"})
        res = api.get(f"/api/v1/habits/{hid}/history/?start=2026-10-01&end=2026-10-09").json()
        assert len(res["scheduled_dates"]) == 9 and res["progress"]["done"] == 1
