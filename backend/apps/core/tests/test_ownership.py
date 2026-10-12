"""Every user-owned resource must be invisible and immutable to other users, even with a known ID."""

import pytest
import time_machine

from apps.reminders.dispatch import dispatch_due
from apps.reminders.models import ReminderOccurrence

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen():
    with time_machine.travel("2026-10-09T05:00:00Z", tick=False):
        yield


@pytest.fixture
def owner_data(api):
    api.patch("/api/v1/preferences/", {"modules": {"reading": True, "fitness": True, "journal": True, "goals": True, "sleep": True, "hydration": True, "mindfulness": True}}, format="json")
    ids = {
        "tasks": api.post(
            "/api/v1/tasks/", {"title": "Secret task", "scheduled_date": "2026-10-09", "scheduled_time": "09:00", "reminders": [{"offset_minutes": 0, "anchor": "start"}]}
        ).json()["id"],
        "categories": api.post("/api/v1/categories/", {"name": "Private", "color": "forest"}).json()["id"],
        "calendar/events": api.post("/api/v1/calendar/events/", {"title": "Secret meeting", "start_date": "2026-10-10", "start_time": "09:00", "end_time": "10:00"}).json()["id"],
        "reminders": api.post("/api/v1/reminders/", {"title": "Secret reminder", "dtstart_date": "2026-10-10", "dtstart_time": "09:00"}).json()["id"],
        "habits": api.post("/api/v1/habits/", {"name": "Secret habit", "schedule_rule": "FREQ=DAILY"}).json()["id"],
        "reading/books": api.post("/api/v1/reading/books/", {"title": "Secret book"}).json()["id"],
        "fitness/routines": api.post("/api/v1/fitness/routines/", {"name": "Secret routine", "days": [1]}).json()["id"],
        "fitness/sessions": api.post("/api/v1/fitness/sessions/", {"date": "2026-10-09", "duration_minutes": 10}).json()["id"],
        "wellness/journal": api.post("/api/v1/wellness/journal/", {"date": "2026-10-09", "body": "Dear diary"}, format="json").json()["id"],
        "wellness/sleep": api.post("/api/v1/wellness/sleep/", {"bedtime_at": "2026-10-08T20:00:00Z", "wake_at": "2026-10-09T04:00:00Z"}).json()["id"],
        "goals": api.post("/api/v1/goals/", {"title": "Secret goal", "target_value": 3}).json()["id"],
        "insights/weekly-reviews": api.post("/api/v1/insights/weekly-reviews/", {"week_start": "2026-10-05", "went_well": "x"}).json()["id"],
        "affirmations/library": api.post("/api/v1/affirmations/library/", {"text": "Mine only", "category": "focus"}).json()["id"],
    }
    book = ids["reading/books"]
    ids["reading/sessions"] = api.post("/api/v1/reading/sessions/", {"book": book, "date": "2026-10-09", "duration_minutes": 15}).json()["id"]
    api.post("/api/v1/wellness/water/", {"amount": 250, "unit": "ml"})
    from apps.wellness.models import WaterIntake

    ids["wellness/water"] = WaterIntake.objects.get().id
    occ = ReminderOccurrence.objects.get(task_id=ids["tasks"])
    dispatch_due(now=occ.fire_at)
    ids["alarms"] = occ.id
    ids["notifications"] = occ.id
    return ids


RESOURCES = [
    "tasks",
    "categories",
    "calendar/events",
    "reminders",
    "habits",
    "reading/books",
    "reading/sessions",
    "fitness/routines",
    "fitness/sessions",
    "wellness/journal",
    "wellness/sleep",
    "wellness/water",
    "goals",
    "insights/weekly-reviews",
]


@pytest.mark.parametrize("resource", RESOURCES)
def test_other_user_cannot_read_change_or_delete(resource, owner_data, other_api, api):
    pk = owner_data[resource]
    url = f"/api/v1/{resource}/{pk}/"
    assert other_api.get(url).status_code == 404
    assert other_api.patch(url, {"title": "pwned", "name": "pwned", "body": "pwned"}, format="json").status_code in (404, 405)
    assert other_api.delete(url).status_code == 404
    listing = other_api.get(f"/api/v1/{resource}/").json()
    items = listing["results"] if isinstance(listing, dict) else listing
    assert pk not in [i.get("id") for i in items]
    assert api.get(url).status_code == 200  # still there for the owner


def test_custom_affirmation_private(owner_data, other_api):
    pk = owner_data["affirmations/library"]
    assert other_api.get(f"/api/v1/affirmations/library/{pk}/").status_code == 404


@pytest.mark.parametrize("verb", ["snooze", "dismiss", "complete", "keep", "shown"])
def test_other_user_cannot_act_on_alarm(verb, owner_data, other_api):
    assert other_api.post(f"/api/v1/alarms/{owner_data['alarms']}/{verb}/", {}).status_code == 404
    assert other_api.get(f"/api/v1/notifications/{owner_data['notifications']}/").status_code == 404
    assert other_api.get("/api/v1/alarms/active/").json() == []


def test_cannot_link_to_other_users_records(owner_data, other_api):
    cat = owner_data["categories"]
    res = other_api.post("/api/v1/tasks/", {"title": "x", "category": cat})
    assert res.status_code == 400 and "category" in res.json()["error"]["fields"]
    other_api.patch("/api/v1/preferences/", {"modules": {"reading": True, "fitness": True, "goals": True}}, format="json")
    assert other_api.post("/api/v1/reading/sessions/", {"book": owner_data["reading/books"], "date": "2026-10-09", "duration_minutes": 5}).status_code == 400
    assert other_api.post("/api/v1/fitness/sessions/", {"routine": owner_data["fitness/routines"], "date": "2026-10-09", "duration_minutes": 5}).status_code == 400
    assert other_api.post("/api/v1/goals/", {"title": "x", "metric": "habit_completions", "habit": owner_data["habits"], "target_value": 1}).status_code == 400
    assert other_api.post(f"/api/v1/tasks/{owner_data['tasks']}/subtasks/", {"title": "x"}).status_code == 404
    assert other_api.post(f"/api/v1/reading/books/{owner_data['reading/books']}/timer/start/").status_code == 404
    assert other_api.get(f"/api/v1/calendar/events/{owner_data['calendar/events']}/occurrence/?key=x").status_code in (404, 405)


def test_aggregates_do_not_leak(owner_data, other_api):
    dash = other_api.get("/api/v1/dashboard/today/").json()
    assert dash["agenda"] == [] and dash["tasks_today"] == [] and dash["reminders"]["missed"] == 0
    occ = other_api.get("/api/v1/calendar/events/occurrences/?start=2026-10-01T00:00:00Z&end=2026-10-31T00:00:00Z").json()
    assert occ["results"] == []
    export = other_api.get("/api/v1/account/export/").json()["data"]
    assert export["tasks"] == [] and export["journal_entries"] == [] and export["books"] == []
    assert other_api.get("/api/v1/insights/weekly/?week_start=2026-10-05").json()["tasks"]["planned"] == 0
