"""Optional modules (affirmations, reading, fitness, wellness), insights accuracy, dashboard and planner."""

from datetime import date, datetime, time

import pytest
import time_machine

from apps.reminders.models import Reminder, ReminderOccurrence

pytestmark = pytest.mark.django_db
NOW = "2026-10-09T05:00:00Z"  # Friday 08:00 Nairobi


@pytest.fixture(autouse=True)
def frozen():
    with time_machine.travel(NOW, tick=False):
        yield


def enable(api, **mods):
    res = api.patch("/api/v1/preferences/", {"modules": mods}, format="json")
    assert res.status_code == 200, res.json()


class TestModules:
    def test_disabled_module_blocks_writes_but_keeps_data(self, api):
        enable(api, reading=False)
        res = api.post("/api/v1/reading/books/", {"title": "Dune"})
        assert res.status_code == 403 and res.json()["error"]["code"] == "module_disabled"
        enable(api, reading=True)
        assert api.post("/api/v1/reading/books/", {"title": "Dune"}).status_code == 201
        enable(api, reading=False)
        assert api.get("/api/v1/reading/books/").json()["count"] == 1

    def test_affirmation_daily_is_stable_and_trackable(self, api):
        a = api.get("/api/v1/affirmations/today/").json()
        b = api.get("/api/v1/affirmations/today/").json()
        assert a["id"] == b["id"] and a["affirmation"]["text"]
        res = api.post(f"/api/v1/affirmations/daily/{a['id']}/acknowledge/").json()
        assert res["acknowledged_at"] and res["viewed_at"]
        api.post(f"/api/v1/affirmations/library/{a['affirmation']['id']}/favorite/")
        assert api.get("/api/v1/affirmations/library/?favorites=true").json()["count"] == 1

    def test_library_is_read_only_custom_is_editable(self, api):
        lib = api.get("/api/v1/affirmations/library/").json()["results"][0]
        assert api.patch(f"/api/v1/affirmations/library/{lib['id']}/", {"text": "hacked"}).status_code == 403
        mine = api.post("/api/v1/affirmations/library/", {"text": "I am steady.", "category": "calmness"}).json()
        assert api.patch(f"/api/v1/affirmations/library/{mine['id']}/", {"text": "I am steady and kind."}).status_code == 200

    def test_affirmation_reminder(self, api):
        res = api.put("/api/v1/affirmations/reminder/", {"enabled": True, "time": "07:30", "days": [0, 1, 2, 3, 4]}, format="json").json()
        assert res == {"enabled": True, "time": "07:30", "days": [0, 1, 2, 3, 4]}
        r = Reminder.objects.get(system_key="affirmation")
        assert r.rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_reading_timer_and_manual(self, api):
        enable(api, reading=True)
        book = api.post("/api/v1/reading/books/", {"title": "Atomic Habits", "total_pages": 300}).json()
        session = api.post(f"/api/v1/reading/books/{book['id']}/timer/start/").json()
        assert api.post(f"/api/v1/reading/books/{book['id']}/timer/start/").status_code == 409  # one running timer
        with time_machine.travel("2026-10-09T05:25:00Z", tick=False):
            stopped = api.post(f"/api/v1/reading/sessions/{session['id']}/stop/", {"end_page": 40}).json()
        assert stopped["duration_minutes"] == 25
        manual = api.post("/api/v1/reading/sessions/", {"book": book["id"], "date": "2026-10-08", "duration_minutes": 30, "pages_read": 20})
        assert manual.status_code == 201, manual.json()
        stats = api.get("/api/v1/reading/stats/").json()
        assert stats["week"]["minutes"] == 55 and stats["week"]["pages"] == 20 and stats["streak"]["current"] == 2
        b = api.get(f"/api/v1/reading/books/{book['id']}/").json()
        assert b["current_page"] == 40 and b["status"] == "reading"
        assert api.post("/api/v1/reading/sessions/", {"book": book["id"], "date": "2026-10-20", "duration_minutes": 10}).status_code == 400

    def test_fitness_routine_reminder_and_stats(self, api):
        enable(api, fitness=True)
        r = api.post("/api/v1/fitness/routines/", {"name": "Strength", "days": [0, 2, 4], "time": "18:00", "prep_buffer_minutes": 30, "reminder_enabled": True}).json()
        rem = Reminder.objects.get(system_key=f"routine:{r['id']}")
        assert rem.dtstart_time == time(17, 30) and rem.rrule == "FREQ=WEEKLY;BYDAY=MO,WE,FR"
        api.post("/api/v1/fitness/sessions/", {"routine": r["id"], "date": "2026-10-09", "duration_minutes": 50, "status": "completed"})
        api.post("/api/v1/fitness/sessions/", {"date": "2026-10-08", "duration_minutes": 20, "workout_type": "Walk", "status": "completed"})
        stats = api.get("/api/v1/fitness/stats/").json()
        assert stats["week"]["sessions"] == 2 and stats["week"]["minutes"] == 70
        assert stats["week"]["planned"] == 1  # routine created today (Friday) → only today is planned
        assert stats["week"]["rate"] == 1.0
        assert api.get("/api/v1/fitness/sessions/today/").json()["plan"][0]["logged_status"] == "completed"

    def test_disabled_fitness_module_stops_reminders(self, api, user):
        enable(api, fitness=True)
        r = api.post("/api/v1/fitness/routines/", {"name": "Run", "days": [4], "time": "18:00", "reminder_enabled": True}).json()
        enable(api, fitness=False)
        from apps.reminders.dispatch import dispatch_due

        occ = ReminderOccurrence.objects.filter(reminder__system_key=f"routine:{r['id']}").order_by("fire_at").first()
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == "skipped" and occ.skip_reason == "module_disabled"

    def test_hydration(self, api):
        enable(api, hydration=True)
        api.patch("/api/v1/preferences/", {"hydration_target": 8, "hydration_unit": "glass", "glass_size_ml": 250}, format="json")
        res = api.post("/api/v1/wellness/water/", {"amount": 2}).json()
        assert res["total_ml"] == 500 and res["total"] == 2.0 and res["progress"] == 0.25
        rem = api.put("/api/v1/wellness/water-reminder/", {"enabled": True, "time": "09:00", "until": "17:00", "every_minutes": 120}, format="json")
        assert rem.status_code == 200, rem.json()
        assert Reminder.objects.get(system_key="hydration").rrule == "FREQ=DAILY;BYHOUR=9,11,13,15,17;BYMINUTE=0"

    def test_sleep_log(self, api):
        enable(api, sleep=True)
        res = api.post("/api/v1/wellness/sleep/", {"bedtime_at": "2026-10-08T19:30:00Z", "wake_at": "2026-10-09T03:30:00Z", "quality": 4})
        assert res.status_code == 201 and res.json()["duration_minutes"] == 480 and res.json()["date"] == "2026-10-09"
        dup = api.post("/api/v1/wellness/sleep/", {"bedtime_at": "2026-10-08T20:00:00Z", "wake_at": "2026-10-09T04:00:00Z"})
        assert dup.status_code == 400

    def test_journal_private_and_searchable(self, api, other_api):
        enable(api, journal=True)
        api.post("/api/v1/wellness/journal/", {"date": "2026-10-09", "body": "Grateful for a quiet morning", "gratitude": ["coffee"], "mood": 4}, format="json")
        assert api.get("/api/v1/wellness/journal/?q=quiet").json()["count"] == 1
        assert other_api.get("/api/v1/wellness/journal/?q=quiet").json()["count"] == 0


class TestInsights:
    def test_weekly_counts_are_reproducible(self, api):
        a = api.post("/api/v1/tasks/", {"title": "A", "scheduled_date": "2026-10-05"}).json()
        b = api.post("/api/v1/tasks/", {"title": "B", "scheduled_date": "2026-10-06"}).json()
        c = api.post("/api/v1/tasks/", {"title": "C", "scheduled_date": "2026-10-07"}).json()
        api.post("/api/v1/tasks/", {"title": "D", "scheduled_date": "2026-10-08"})
        api.post(f"/api/v1/tasks/{a['id']}/complete/")
        api.post(f"/api/v1/tasks/{b['id']}/cancel/")
        api.post(f"/api/v1/tasks/{c['id']}/postpone/", {"to_date": "2026-10-12"})
        w = api.get("/api/v1/insights/weekly/?week_start=2026-10-05").json()
        # planned: A, B, D (+C postponed out of the week) = 4; completed 1; cancelled 1 → rate 1/3
        assert w["tasks"]["planned"] == 4 and w["tasks"]["completed"] == 1 and w["tasks"]["cancelled"] == 1 and w["tasks"]["postponed"] == 1
        assert w["tasks"]["completion_rate"] == round(1 / 3, 4)
        assert w["week_start"] == "2026-10-05" and len(w["days"]) == 7
        assert "definitions" in w and w["suggestions"]
        again = api.get("/api/v1/insights/weekly/?week_start=2026-10-07").json()  # mid-week date normalises
        assert again["tasks"] == w["tasks"]

    def test_empty_week_has_no_rates(self, api):
        w = api.get("/api/v1/insights/weekly/").json()
        assert w["tasks"]["completion_rate"] is None and w["habits"]["consistency"] is None and not w["has_activity"]

    def test_weekly_review_snapshot(self, api):
        res = api.post("/api/v1/insights/weekly-reviews/", {"week_start": "2026-10-07", "went_well": "Kept routines"})
        assert res.status_code == 201 and res.json()["week_start"] == "2026-10-05" and "tasks" in res.json()["stats_snapshot"]
        again = api.post("/api/v1/insights/weekly-reviews/", {"week_start": "2026-10-05", "went_well": "Updated"})
        assert again.status_code == 200 and again.json()["went_well"] == "Updated"

    def test_goal_progress_derived_and_manual(self, api):
        enable(api, goals=True, reading=True)
        book = api.post("/api/v1/reading/books/", {"title": "X"}).json()
        api.post(f"/api/v1/reading/books/{book['id']}/complete/")
        g = api.post("/api/v1/goals/", {"title": "Read 12 books", "metric": "books_completed", "target_value": 12, "start_date": "2026-01-01"}).json()
        assert g["progress"]["value"] == "1" and g["progress"]["progress"] == round(1 / 12, 4)
        m = api.post("/api/v1/goals/", {"title": "Save", "metric": "manual", "target_value": 1000, "unit": "USD"}).json()
        res = api.post(f"/api/v1/goals/{m['id']}/check-ins/", {"value": 250}).json()
        assert res["progress"]["progress"] == 0.25

    def test_monthly_and_yearly(self, api):
        assert api.get("/api/v1/insights/monthly/?month=2026-10").status_code == 200
        assert len(api.get("/api/v1/insights/yearly/?year=2026").json()["months"]) == 10
        assert api.get("/api/v1/insights/monthly/?month=bad").status_code == 400


class TestDashboard:
    def test_today_reflects_real_data_only(self, api):
        empty = api.get("/api/v1/dashboard/today/").json()
        assert empty["agenda"] == [] and empty["priorities"] == [] and empty["progress"]["overall"] is None
        assert "open" in empty["briefing"]["schedule"].lower() or "nothing" in empty["briefing"]["schedule"].lower()
        assert empty["greeting"]["headline"].startswith(("Good morning", "Happy"))
        api.post("/api/v1/calendar/events/", {"title": "Standup", "start_date": "2026-10-09", "start_time": "09:00", "end_time": "09:15"})
        api.post("/api/v1/tasks/", {"title": "Ship release", "scheduled_date": "2026-10-09", "priority": "urgent"})
        api.post("/api/v1/tasks/", {"title": "Old thing", "scheduled_date": "2026-10-01"})
        d = api.get("/api/v1/dashboard/today/").json()
        assert d["local"]["date"] == "2026-10-09" and d["local"]["time"] == "08:00"
        assert d["next_up"]["title"] == "Standup"
        assert "Standup" in d["briefing"]["schedule"] and "09:00" in d["briefing"]["schedule"]
        assert [p["title"] for p in d["priorities"]] == ["Old thing", "Ship release"]
        assert d["overdue"]["count"] == 1 and d["progress"]["tasks_total"] == 1
        assert d["affirmation"]["text"]
        assert "reading" not in d  # module off by default

    def test_tone_minimal_and_greeting_disabled(self, api):
        api.patch("/api/v1/preferences/", {"tone": "minimal"}, format="json")
        assert api.get("/api/v1/dashboard/today/").json()["greeting"]["message"] == ""
        api.patch("/api/v1/preferences/", {"greeting_enabled": False}, format="json")
        assert api.get("/api/v1/dashboard/today/").json()["greeting"] is None

    def test_evening_recap(self, api):
        t = api.post("/api/v1/tasks/", {"title": "A", "scheduled_date": "2026-10-09"}).json()
        api.post("/api/v1/tasks/", {"title": "B", "scheduled_date": "2026-10-09"})
        api.post(f"/api/v1/tasks/{t['id']}/complete/")
        with time_machine.travel("2026-10-09T18:00:00Z", tick=False):  # 21:00 Nairobi
            ev = api.get("/api/v1/dashboard/today/").json()["evening"]
        assert "1 of your 2 planned tasks" in ev["message"] and "move the remaining 1 task" in ev["message"]

    def test_morning_briefing_notification_uses_real_data(self, api, user):
        api.patch("/api/v1/preferences/", {"morning_notification": True, "greeting_time": "07:00"}, format="json")
        api.post("/api/v1/calendar/events/", {"title": "Doctor", "start_date": "2026-10-10", "start_time": "11:00", "end_time": "12:00"})
        from apps.reminders.dispatch import dispatch_due

        occ = ReminderOccurrence.objects.filter(reminder__system_key="briefing:morning").order_by("fire_at").first()
        assert occ.fire_at == datetime.fromisoformat("2026-10-10T04:00:00+00:00")
        with time_machine.travel(occ.fire_at, tick=False):
            dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == "sent" and "Doctor" in occ.body and "11:00" in occ.body


class TestPlanner:
    def test_suggests_around_fixed_events_without_moving_them(self, api):
        api.patch("/api/v1/preferences/", {"work_start": "09:00", "work_end": "12:00", "work_days": [0, 1, 2, 3, 4], "planning_buffer_minutes": 0}, format="json")
        api.post("/api/v1/calendar/events/", {"title": "Meeting", "start_date": "2026-10-09", "start_time": "09:00", "end_time": "10:00"})
        a = api.post("/api/v1/tasks/", {"title": "Deep work", "scheduled_date": "2026-10-09", "duration_minutes": 60, "priority": "high"}).json()
        b = api.post("/api/v1/tasks/", {"title": "Email", "scheduled_date": "2026-10-09", "duration_minutes": 90}).json()
        plan = api.get("/api/v1/planner/suggest/?date=2026-10-09").json()
        assert [s["title"] for s in plan["suggestions"]] == ["Deep work"] and plan["suggestions"][0]["start_time"] == "10:00"
        assert [u["title"] for u in plan["unplaced"]] == ["Email"] and plan["overloaded"]
        assert api.get(f"/api/v1/tasks/{a['id']}/").json()["scheduled_time"] is None  # nothing changed yet
        api.post("/api/v1/planner/apply/", {"date": "2026-10-09", "items": [{"task_id": a["id"], "start_time": "10:00"}]}, format="json")
        assert api.get(f"/api/v1/tasks/{a['id']}/").json()["scheduled_time"] == "10:00:00"
        assert api.get(f"/api/v1/tasks/{b['id']}/").json()["scheduled_time"] is None

    def test_cannot_apply_someone_elses_task(self, api, other_api):
        t = other_api.post("/api/v1/tasks/", {"title": "Theirs"}).json()
        res = api.post("/api/v1/planner/apply/", {"date": "2026-10-09", "items": [{"task_id": t["id"], "start_time": "10:00"}]}, format="json")
        assert res.status_code == 400


def test_timezone_change_moves_floating_reminders(api, user):
    api.post("/api/v1/habits/", {"name": "Wake", "schedule_rule": "FREQ=DAILY", "reminder_time": "07:00"})
    api.patch("/api/v1/preferences/", {"time_zone": "Europe/London"}, format="json")
    occ = ReminderOccurrence.objects.filter(reminder__habit__name="Wake", status="scheduled").order_by("fire_at").first()
    assert occ.fire_at.isoformat() == "2026-10-09T06:00:00+00:00"  # 07:00 BST today (it is 06:00 in London now)
    assert date(2026, 10, 10)


def test_briefing_never_names_a_commitment_that_is_over(api):
    api.post("/api/v1/calendar/events/", {"title": "Standup", "start_date": "2026-10-09", "start_time": "09:00", "end_time": "09:30"})
    before = api.get("/api/v1/dashboard/today/").json()["briefing"]["schedule"]
    assert "next up is Standup at 09:00" in before and "time to prepare" in before
    with time_machine.travel("2026-10-09T06:10:00Z", tick=False):  # 09:10 Nairobi — in progress
        during = api.get("/api/v1/dashboard/today/").json()["briefing"]["schedule"]
    assert "Standup is happening now" in during and "prepare" not in during
    with time_machine.travel("2026-10-09T07:00:00Z", tick=False):  # 10:00 — over
        after = api.get("/api/v1/dashboard/today/").json()
    assert "Standup" not in after["briefing"]["schedule"] and after["next_up"] is None


def test_future_days_do_not_lower_rates(api):
    api.post("/api/v1/habits/", {"name": "Stretch", "schedule_rule": "FREQ=DAILY", "start_date": "2026-10-08"})
    t = api.post("/api/v1/tasks/", {"title": "Today", "scheduled_date": "2026-10-09"}).json()
    api.post("/api/v1/tasks/", {"title": "Tomorrow", "scheduled_date": "2026-10-10"})
    api.post(f"/api/v1/tasks/{t['id']}/complete/")
    w = api.get("/api/v1/insights/weekly/?week_start=2026-10-05").json()
    assert w["tasks"]["planned"] == 1 and w["tasks"]["completion_rate"] == 1.0  # tomorrow's task isn't counted yet
    assert w["habits"]["scheduled"] == 2  # Oct 8 and 9 only, not the rest of the week
    assert len(w["days"]) == 7
    assert not any("seems to be working" in s for s in w["suggestions"])  # habit at 0% → no praise


def test_personal_admin_module_creates_real_lists(api):
    enable(api, admin=True)
    cats = {c["name"]: c["id"] for c in api.get("/api/v1/categories/").json()}
    assert {"Home & chores", "Errands", "Bills & renewals", "Shopping"} <= set(cats)
    enable(api, admin=True)  # idempotent
    assert len(api.get("/api/v1/categories/").json()) == 4
    api.post("/api/v1/tasks/", {"title": "Pay electricity", "category": cats["Bills & renewals"], "deadline": "2026-10-15T09:00:00Z",
                                "reminders": [{"offset_minutes": 1440, "anchor": "deadline"}]}, format="json")
    api.post("/api/v1/tasks/", {"title": "Write report"})
    assert [t["title"] for t in api.get("/api/v1/tasks/?admin=true").json()["results"]] == ["Pay electricity"]
    assert ReminderOccurrence.objects.filter(task__title="Pay electricity").exists()


def test_positive_message_only_when_earned(api):
    t = api.post("/api/v1/tasks/", {"title": "Done", "scheduled_date": "2026-10-09"}).json()
    api.post(f"/api/v1/tasks/{t['id']}/complete/")
    w = api.get("/api/v1/insights/weekly/?week_start=2026-10-05").json()
    assert w["tasks"]["completion_rate"] == 1.0
    assert any("seems to be working" in s for s in w["suggestions"])
    api.post("/api/v1/tasks/", {"title": "Not done", "scheduled_date": "2026-10-08"})
    api.post("/api/v1/tasks/", {"title": "Not done 2", "scheduled_date": "2026-10-07"})
    w = api.get("/api/v1/insights/weekly/?week_start=2026-10-05").json()
    assert w["tasks"]["completion_rate"] < 0.6 and not any("seems to be working" in s for s in w["suggestions"])


def test_dashboard_overdue_count_is_not_capped_and_urgent_first(api, user):
    """Regression (found in the performance review): overdue count was len() of a 20-row list."""
    from datetime import date as d

    from apps.tasks.models import Task

    Task.objects.bulk_create([Task(owner=user, title=f"Old {i}", scheduled_date=d(2026, 9, 1), time_zone="Africa/Nairobi") for i in range(30)])
    Task.objects.create(owner=user, title="Urgent old", priority="urgent", scheduled_date=d(2026, 8, 1), time_zone="Africa/Nairobi")
    dash = api.get("/api/v1/dashboard/today/").json()
    assert dash["overdue"]["count"] == 31
    assert "31 tasks are waiting" in dash["briefing"]["overdue"]
    assert dash["priorities"][0]["title"] == "Urgent old"
