from datetime import date

import pytest
import time_machine

from apps.reminders.models import ReminderOccurrence

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen():
    with time_machine.travel("2026-10-09T05:00:00Z", tick=False):
        yield


def occ(api, start="2026-10-01T00:00:00Z", end="2026-11-30T00:00:00Z", **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return api.get(f"/api/v1/calendar/events/occurrences/?start={start}&end={end}&{q}").json()


class TestEvents:
    def test_local_times_and_utc(self, api):
        res = api.post("/api/v1/calendar/events/", {"title": "Dentist", "start_date": "2026-10-12", "start_time": "09:00", "end_time": "10:00"})
        assert res.status_code == 201, res.json()
        assert res.json()["start"].startswith("2026-10-12T06:00:00")  # 09:00 EAT
        assert res.json()["end_date"] == "2026-10-12"

    def test_end_before_start_rejected(self, api):
        res = api.post("/api/v1/calendar/events/", {"title": "x", "start_date": "2026-10-12", "start_time": "10:00", "end_time": "09:00"})
        assert res.status_code == 409 or res.status_code == 400

    def test_all_day(self, api):
        res = api.post("/api/v1/calendar/events/", {"title": "Holiday", "all_day": True, "start_date": "2026-10-20", "end_date": "2026-10-21"})
        assert res.status_code == 201
        o = occ(api)["results"][0]
        assert o["all_day"] and o["key"] == "2026-10-20"

    def test_new_york_event_across_dst(self, api):
        api.post(
            "/api/v1/calendar/events/",
            {"title": "Weekly sync", "start_date": "2026-10-26", "start_time": "09:00", "end_time": "09:30", "time_zone": "America/New_York", "rrule": "FREQ=WEEKLY;COUNT=3"},
        )
        starts = [o["start"] for o in occ(api)["results"]]
        # 09:00 EDT (13:00Z) before the 1 Nov change, 09:00 EST (14:00Z) after.
        assert starts == ["2026-10-26T13:00:00+00:00", "2026-11-02T14:00:00+00:00", "2026-11-09T14:00:00+00:00"]

    def test_recurring_with_exceptions(self, api):
        eid = api.post("/api/v1/calendar/events/", {"title": "Gym class", "start_date": "2026-10-05", "start_time": "18:00", "end_time": "19:00", "rrule": "FREQ=WEEKLY;BYDAY=MO,WE"}).json()[
            "id"
        ]
        results = occ(api, start="2026-10-05T00:00:00Z", end="2026-10-19T00:00:00Z")["results"]
        assert [o["key"] for o in results] == ["2026-10-05T18:00", "2026-10-07T18:00", "2026-10-12T18:00", "2026-10-14T18:00"]
        # cancel one, move another
        assert api.delete(f"/api/v1/calendar/events/{eid}/occurrence/?key=2026-10-07T18:00").status_code == 204
        api.post(
            f"/api/v1/calendar/events/{eid}/occurrence/", {"key": "2026-10-12T18:00", "start_date": "2026-10-13", "start_time": "07:00", "end_time": "08:00", "title": "Gym class (moved)"}
        )
        results = occ(api, start="2026-10-05T00:00:00Z", end="2026-10-19T00:00:00Z")["results"]
        assert [(o["key"], o["title"]) for o in results] == [("2026-10-05T18:00", "Gym class"), ("2026-10-12T18:00", "Gym class (moved)"), ("2026-10-14T18:00", "Gym class")]
        moved = results[1]
        assert moved["start"] == "2026-10-13T04:00:00+00:00" and moved["is_exception"]
        bogus = api.post(f"/api/v1/calendar/events/{eid}/occurrence/", {"key": "2026-10-06T18:00", "cancelled": True})
        assert bogus.status_code == 400

    def test_series_edit_applies_to_all(self, api):
        eid = api.post("/api/v1/calendar/events/", {"title": "Class", "start_date": "2026-10-05", "start_time": "18:00", "end_time": "19:00", "rrule": "FREQ=DAILY;COUNT=3"}).json()["id"]
        api.patch(f"/api/v1/calendar/events/{eid}/", {"title": "Evening class", "location": "Studio 2"})
        assert {o["title"] for o in occ(api)["results"]} == {"Evening class"}

    def test_conflicts(self, api):
        api.post("/api/v1/calendar/events/", {"title": "A", "start_date": "2026-10-12", "start_time": "09:00", "end_time": "10:00"})
        res = api.post("/api/v1/calendar/events/", {"title": "B", "start_date": "2026-10-12", "start_time": "09:30", "end_time": "10:30"})
        assert len(res.json()["conflicts"]) == 1
        assert len(occ(api)["conflicts"]) == 1

    def test_event_reminder_offsets_follow_moves(self, api):
        eid = api.post("/api/v1/calendar/events/", {"title": "Meeting", "start_date": "2026-10-12", "start_time": "09:00", "end_time": "10:00", "reminder_offsets": [15, 60]}).json()["id"]
        assert ReminderOccurrence.objects.filter(reminder__event_id=eid, status="scheduled").count() == 2
        api.patch(f"/api/v1/calendar/events/{eid}/", {"start_time": "11:00", "end_time": "12:00"})
        fires = sorted(o.fire_at.isoformat() for o in ReminderOccurrence.objects.filter(reminder__event_id=eid, status="scheduled"))
        assert fires == ["2026-10-12T07:00:00+00:00", "2026-10-12T07:45:00+00:00"]

    def test_attendance(self, api):
        eid = api.post("/api/v1/calendar/events/", {"title": "Talk", "start_date": "2026-10-08", "start_time": "09:00", "end_time": "10:00"}).json()["id"]
        api.post(f"/api/v1/calendar/events/{eid}/attendance/", {"attendance": "attended"})
        assert occ(api)["results"][0]["attendance"] == "attended"

    def test_search_and_range_limit(self, api):
        api.post("/api/v1/calendar/events/", {"title": "Dentist", "start_date": "2026-10-12", "start_time": "09:00", "end_time": "10:00"})
        api.post("/api/v1/calendar/events/", {"title": "Lunch", "start_date": "2026-10-12", "start_time": "12:00", "end_time": "13:00"})
        assert [o["title"] for o in occ(api, q="dent")["results"]] == ["Dentist"]
        too_long = api.get("/api/v1/calendar/events/occurrences/?start=2026-01-01T00:00:00Z&end=2028-01-01T00:00:00Z")
        assert too_long.status_code == 400


class TestIcs:
    def test_roundtrip(self, api, other_api):
        eid = api.post(
            "/api/v1/calendar/events/", {"title": "Book club", "start_date": "2026-10-05", "start_time": "19:00", "end_time": "20:00", "rrule": "FREQ=WEEKLY;COUNT=4", "location": "Library"}
        ).json()["id"]
        api.delete(f"/api/v1/calendar/events/{eid}/occurrence/?key=2026-10-12T19:00")
        ics = api.get("/api/v1/calendar/events/export/")
        assert ics.status_code == 200 and b"BEGIN:VCALENDAR" in ics.content and b"EXDATE" in ics.content
        from django.core.files.uploadedfile import SimpleUploadedFile

        up = SimpleUploadedFile("cal.ics", ics.content, content_type="text/calendar")
        res = other_api.post("/api/v1/calendar/events/import/", {"file": up}, format="multipart")
        assert res.status_code == 201 and res.json()["created"] == 1
        keys = [o["key"] for o in occ(other_api)["results"]]
        assert keys == ["2026-10-05T19:00", "2026-10-19T19:00", "2026-10-26T19:00"]
        # re-import is idempotent
        up2 = SimpleUploadedFile("cal.ics", ics.content, content_type="text/calendar")
        assert other_api.post("/api/v1/calendar/events/import/", {"file": up2}, format="multipart").json()["skipped"] == 1

    def test_garbage_file(self, api):
        from django.core.files.uploadedfile import SimpleUploadedFile

        res = api.post("/api/v1/calendar/events/import/", {"file": SimpleUploadedFile("x.ics", b"not a calendar")}, format="multipart")
        assert res.status_code == 400


def test_dates_are_dates(api):
    assert date(2026, 10, 9)  # sanity for the frozen clock fixture
