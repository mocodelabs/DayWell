from datetime import date, timedelta

import pytest
import time_machine

from apps.reminders.models import ReminderOccurrence
from apps.tasks.models import Task, TaskActivity

pytestmark = pytest.mark.django_db
NOW = "2026-10-09T05:00:00Z"  # 08:00 Nairobi, Friday


@pytest.fixture(autouse=True)
def frozen():
    with time_machine.travel(NOW, tick=False):
        yield


class TestTaskCrud:
    def test_create_with_time_computes_utc(self, api):
        res = api.post(
            "/api/v1/tasks/",
            {
                "title": "Call the supplier",
                "scheduled_date": "2026-10-10",
                "scheduled_time": "10:00",
                "priority": "high",
                "tags": ["work", "Work", "calls"],
                "checklist": ["Find number", "Prepare notes"],
            },
        )
        assert res.status_code == 201, res.json()
        body = res.json()
        assert body["scheduled_at"].startswith("2026-10-10T07:00:00")  # 10:00 EAT
        assert body["tags"] == ["work", "calls"]
        assert [s["title"] for s in body["subtasks"]] == ["Find number", "Prepare notes"]

    def test_time_without_date_rejected(self, api):
        res = api.post("/api/v1/tasks/", {"title": "x", "scheduled_time": "10:00"})
        assert res.status_code == 400 and "scheduled_time" in res.json()["error"]["fields"]

    def test_blank_title_rejected(self, api):
        assert api.post("/api/v1/tasks/", {"title": "   "}).status_code == 400

    def test_complete_reopen_postpone_cancel(self, api):
        tid = api.post("/api/v1/tasks/", {"title": "Write report", "scheduled_date": "2026-10-09"}).json()["id"]
        assert api.post(f"/api/v1/tasks/{tid}/complete/").json()["status"] == "completed"
        assert api.post(f"/api/v1/tasks/{tid}/complete/").status_code == 200  # idempotent
        assert api.post(f"/api/v1/tasks/{tid}/reopen/").json()["status"] == "pending"
        res = api.post(f"/api/v1/tasks/{tid}/postpone/", {"preset": "tomorrow"}).json()
        assert res["status"] == "postponed" and res["scheduled_date"] == "2026-10-10" and res["postponed_count"] == 1
        assert TaskActivity.objects.filter(task_id=tid, kind="postponed", from_date=date(2026, 10, 9)).exists()
        assert api.post(f"/api/v1/tasks/{tid}/postpone/", {"to_date": "2026-10-01"}).status_code == 400
        assert api.post(f"/api/v1/tasks/{tid}/cancel/").json()["status"] == "cancelled"
        assert api.post(f"/api/v1/tasks/{tid}/complete/").status_code == 409

    def test_delete(self, api):
        tid = api.post("/api/v1/tasks/", {"title": "x"}).json()["id"]
        assert api.delete(f"/api/v1/tasks/{tid}/").status_code == 204
        assert not Task.objects.filter(pk=tid).exists()

    def test_filters(self, api):
        api.post("/api/v1/tasks/", {"title": "Old", "scheduled_date": "2026-10-01"})
        api.post("/api/v1/tasks/", {"title": "Today", "scheduled_date": "2026-10-09", "priority": "urgent"})
        api.post("/api/v1/tasks/", {"title": "Inbox"})
        titles = lambda q: [t["title"] for t in api.get(f"/api/v1/tasks/?{q}").json()["results"]]  # noqa: E731
        assert titles("overdue=true") == ["Old"]
        assert titles("inbox=true") == ["Inbox"]
        assert titles("priority=urgent") == ["Today"]
        assert titles("search=tod") == ["Today"]
        assert api.get("/api/v1/tasks/1/").status_code in (200, 404)

    def test_overdue_flag(self, api):
        res = api.post("/api/v1/tasks/", {"title": "Old", "scheduled_date": "2026-10-01"}).json()
        assert res["is_overdue"] is True

    def test_reminders_via_task(self, api):
        res = api.post("/api/v1/tasks/", {"title": "Call", "scheduled_date": "2026-10-10", "scheduled_time": "10:00", "reminders": [{"offset_minutes": 15, "anchor": "start"}]})
        assert res.status_code == 201, res.json()
        assert res.json()["reminders"][0]["offset_minutes"] == 15
        assert ReminderOccurrence.objects.filter(task_id=res.json()["id"]).count() == 1
        bad = api.post("/api/v1/tasks/", {"title": "No time", "reminders": [{"offset_minutes": 15, "anchor": "start"}]})
        assert bad.status_code == 400

    def test_subtasks(self, api):
        tid = api.post("/api/v1/tasks/", {"title": "Shopping"}).json()["id"]
        sid = api.post(f"/api/v1/tasks/{tid}/subtasks/", {"title": "Milk"}).json()["id"]
        res = api.patch(f"/api/v1/tasks/{tid}/subtasks/{sid}/", {"done": True}).json()
        assert res["done"] and res["done_at"]


class TestRecurringTasks:
    def test_weekday_series_materialises_and_edits(self, api):
        res = api.post("/api/v1/tasks/", {"title": "Standup notes", "scheduled_date": "2026-10-09", "scheduled_time": "09:00", "recurrence": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"})
        assert res.status_code == 201, res.json()
        first = res.json()
        assert first["series_rule"] == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        instances = Task.objects.filter(series_id=first["series"]).order_by("occurrence_date")
        assert all(t.occurrence_date.weekday() < 5 for t in instances)
        assert instances.count() >= 15
        # Edit just this one
        api.patch(f"/api/v1/tasks/{first['id']}/?scope=this", {"title": "Standup (short)"})
        assert Task.objects.get(pk=first["id"]).detached
        second = instances[1]
        assert second.title == "Standup notes"
        # Edit the series from the second one onwards
        api.patch(f"/api/v1/tasks/{second.id}/?scope=series", {"title": "Daily notes"})
        assert Task.objects.get(pk=first["id"]).title == "Standup (short)"
        assert set(Task.objects.filter(series_id=first["series"]).exclude(pk=first["id"]).values_list("title", flat=True)) == {"Daily notes"}

    def test_materialisation_is_idempotent(self, api):
        from apps.tasks.services import extend_all_series

        sid = api.post("/api/v1/tasks/", {"title": "Water plants", "scheduled_date": "2026-10-09", "recurrence": "FREQ=DAILY"}).json()["series"]
        n = Task.objects.filter(series_id=sid).count()
        extend_all_series()
        extend_all_series()
        assert Task.objects.filter(series_id=sid).count() == n

    def test_delete_one_occurrence_is_not_regenerated(self, api, settings):
        res = api.post("/api/v1/tasks/", {"title": "Water plants", "scheduled_date": "2026-10-09", "recurrence": "FREQ=DAILY"}).json()
        api.delete(f"/api/v1/tasks/{res['id']}/?scope=this")
        from apps.tasks.models import TaskSeries
        from apps.tasks.services import materialize_series

        series = TaskSeries.objects.get(pk=res["series"])
        series.generated_until = None
        materialize_series(series)
        assert Task.objects.get(pk=res["id"]).deleted_at is not None
        assert Task.objects.filter(series=series, occurrence_date=date(2026, 10, 9)).count() == 1
        assert api.get(f"/api/v1/tasks/{res['id']}/").status_code == 404

    def test_delete_series_keeps_completed_history(self, api):
        res = api.post("/api/v1/tasks/", {"title": "Journal", "scheduled_date": "2026-10-09", "recurrence": "FREQ=DAILY"}).json()
        api.post(f"/api/v1/tasks/{res['id']}/complete/")
        nxt = Task.objects.filter(series_id=res["series"], occurrence_date=date(2026, 10, 10)).get()
        api.delete(f"/api/v1/tasks/{nxt.id}/?scope=series")
        assert Task.objects.get(pk=res["id"]).status == "completed"
        assert not Task.objects.filter(series_id=res["series"], occurrence_date__gte=date(2026, 10, 10), deleted_at__isnull=True).exists()

    def test_bad_rule(self, api):
        res = api.post("/api/v1/tasks/", {"title": "x", "scheduled_date": "2026-10-09", "recurrence": "FREQ=SECONDLY"})
        assert res.status_code == 400 and "recurrence" in res.json()["error"]["fields"]

    def test_monthly_fifth_until(self, api):
        res = api.post("/api/v1/tasks/", {"title": "Pay rent", "scheduled_date": "2026-10-05", "recurrence": "FREQ=MONTHLY;BYMONTHDAY=5;COUNT=3"})
        assert res.status_code == 201
        assert Task.objects.filter(series_id=res.json()["series"]).count() == 1  # only one within the 21-day horizon
        from apps.tasks.models import TaskSeries
        from apps.tasks.services import materialize_series

        materialize_series(TaskSeries.objects.get(pk=res.json()["series"]), until=date(2027, 6, 1))
        assert [t.occurrence_date for t in Task.objects.filter(series_id=res.json()["series"]).order_by("occurrence_date")] == [date(2026, 10, 5), date(2026, 11, 5), date(2026, 12, 5)]


def test_recurring_instance_shows_series_reminders(api):
    with time_machine.travel(NOW, tick=False):
        res = api.post(
            "/api/v1/tasks/",
            {"title": "Meds", "scheduled_date": "2026-10-09", "scheduled_time": "20:00", "recurrence": "FREQ=DAILY", "reminders": [{"offset_minutes": 0, "anchor": "start"}]},
        ).json()
        nxt = Task.objects.filter(series_id=res["series"]).order_by("occurrence_date")[1]
        body = api.get(f"/api/v1/tasks/{nxt.id}/").json()
        assert body["reminders"] and body["reminders"][0]["series"] is True
        assert ReminderOccurrence.objects.filter(task__series_id=res["series"]).count() >= 14
        assert ReminderOccurrence.objects.filter(task=nxt, fire_at=nxt.scheduled_at).exists()
        assert (nxt.scheduled_at - timedelta(days=1)).date() >= date(2026, 10, 9)
