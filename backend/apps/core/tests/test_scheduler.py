"""Request-driven scheduler (deployments without Celery beat): token-protected tick + opportunistic inline runs."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
import time_machine
from django.core.cache import cache

from apps.core import scheduler
from apps.reminders.models import OccurrenceStatus, Reminder, ReminderOccurrence
from apps.reminders.services import sync_reminder

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)
TOKEN = "t" * 40


def due_occurrence(user) -> ReminderOccurrence:
    r = Reminder.objects.create(
        owner=user, title="Stretch", category="custom", kind="absolute", dtstart_date=date(2026, 10, 9), dtstart_time=time(8, 0, 30), rrule="", time_zone="Africa/Nairobi"
    )
    sync_reminder(r, now=T0 - timedelta(minutes=5))
    return ReminderOccurrence.objects.get(reminder=r)


class TestTickEndpoint:
    def test_disabled_without_token(self, anon, settings):
        settings.SCHEDULER_TOKEN = ""
        assert anon.get("/internal/tick/").status_code == 404

    def test_rejects_wrong_or_missing_token(self, anon, settings):
        settings.SCHEDULER_TOKEN = TOKEN
        assert anon.get("/internal/tick/").status_code == 403
        assert anon.get("/internal/tick/", HTTP_AUTHORIZATION="Bearer nope").status_code == 403

    def test_runs_due_jobs_and_dispatches(self, anon, user, settings):
        settings.SCHEDULER_TOKEN = TOKEN
        occ = due_occurrence(user)
        with time_machine.travel(T0 + timedelta(minutes=1), tick=False):
            res = anon.post("/internal/tick/", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
            assert cache.get("scheduler:heartbeat")  # the scheduler health check sees a live clock
        assert res.status_code == 200
        assert set(res.json()["ran"]) == {name for name, _, _ in scheduler.JOBS}
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SENT

    def test_each_job_runs_at_most_once_per_interval(self, anon, settings):
        settings.SCHEDULER_TOKEN = TOKEN
        anon.get("/internal/tick/", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        again = anon.get("/internal/tick/", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        assert again.json()["ran"] == {}

    def test_failing_job_does_not_block_others_and_retries(self, monkeypatch):
        def boom():
            raise RuntimeError("x")

        monkeypatch.setattr(scheduler, "JOBS", [("a", timedelta(minutes=5), "x.boom"), ("b", timedelta(minutes=5), "x.ok")])
        monkeypatch.setattr(scheduler, "_load", lambda path: boom if path == "x.boom" else (lambda: "ok"))
        assert scheduler.run_due_jobs() == {"a": "error", "b": "ok"}
        assert scheduler.run_due_jobs() == {"a": "error"}  # failed job is retried next tick; the other is gated


class TestInlineScheduler:
    def test_alarm_poll_dispatches_when_enabled(self, api, user, settings):
        settings.INLINE_SCHEDULER = True
        occ = due_occurrence(user)
        with time_machine.travel(T0 + timedelta(minutes=1), tick=False):
            alarms = api.get("/api/v1/alarms/active/").json()
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SENT
        assert [a["id"] for a in alarms] == [occ.id]

    def test_off_by_default(self, api, user, settings):
        assert settings.INLINE_SCHEDULER is False
        occ = due_occurrence(user)
        with time_machine.travel(T0 + timedelta(minutes=1), tick=False):
            api.get("/api/v1/alarms/active/")
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SCHEDULED


class TestEmailCheck:
    def test_protected_like_the_tick(self, anon, settings):
        settings.SCHEDULER_TOKEN = ""
        assert anon.get("/internal/email-check/").status_code == 404
        settings.SCHEDULER_TOKEN = TOKEN
        assert anon.get("/internal/email-check/").status_code == 403

    def test_reports_the_failing_step_without_credentials(self, anon, settings):
        import smtplib
        from unittest import mock

        settings.SCHEDULER_TOKEN = TOKEN
        settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD, settings.EMAIL_USE_TLS = "me@example.com", "app-pass", True
        conn = mock.MagicMock()
        conn.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        with mock.patch("smtplib.SMTP", return_value=conn):
            body = anon.get("/internal/email-check/", HTTP_AUTHORIZATION=f"Bearer {TOKEN}").json()
        assert body["ok"] is False and body["failed_step"] == "login" and "535" in body["detail"]
        assert "app-pass" not in str(body) and body["password_set"] is True
