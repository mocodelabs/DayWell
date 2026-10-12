import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, User

pytestmark = pytest.mark.django_db
STRONG = "a-Very-good-passphrase-42"


def register(client, email="new@example.com", **extra):
    return client.post("/api/v1/auth/register/", {"email": email, "password": STRONG, "display_name": "Neo", "time_zone": "Africa/Nairobi", **extra})


class TestRegistrationAndLogin:
    def test_register_logs_in_and_creates_preferences(self, anon):
        res = register(anon)
        assert res.status_code == 201
        assert res.json()["preferences"]["time_zone"] == "Africa/Nairobi"
        assert anon.get("/api/v1/auth/me/").status_code == 200
        assert User.objects.get(email="new@example.com").notification_preferences.count() == 12
        assert len(mail.outbox) == 1 and "Confirm" in mail.outbox[0].subject

    def test_duplicate_email_case_insensitive(self, anon, user):
        res = register(anon, email="ADA@example.com")
        assert res.status_code == 400 and "email" in res.json()["error"]["fields"]

    def test_weak_password_rejected(self, anon):
        res = anon.post("/api/v1/auth/register/", {"email": "x@example.com", "password": "password"})
        assert res.status_code == 400

    def test_bad_timezone_rejected(self, anon):
        assert register(anon, time_zone="Mars/Olympus").status_code == 400

    def test_login_logout(self, anon, user):
        res = anon.post("/api/v1/auth/login/", {"email": "Ada@Example.com", "password": "correct horse battery"})
        assert res.status_code == 200 and res.json()["user"]["email"] == "ada@example.com"
        assert anon.post("/api/v1/auth/logout/").status_code == 204
        assert anon.get("/api/v1/auth/me/").status_code == 401

    def test_wrong_password_generic_message_and_audit(self, anon, user):
        res = anon.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "nope-nope-nope"})
        assert res.status_code == 400
        assert "don't match" in res.json()["error"]["message"]
        assert AuditEvent.objects.filter(kind="login_failed").exists()

    def test_lockout_after_repeated_failures(self, anon, user, settings):
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "auth": "1000/min"}}
        for _ in range(8):
            anon.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "wrong-password-x"})
        res = anon.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"})
        assert res.status_code == 429 and res.json()["error"]["code"] == "locked_out"

    def test_unauthenticated_api_is_401(self, anon):
        assert anon.get("/api/v1/tasks/").status_code == 401

    def test_csrf_enforced_for_session_writes(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        assert client.post("/api/v1/tasks/", {"title": "x"}).status_code == 403
        client.get("/api/v1/auth/csrf/")
        token = client.cookies["daywell_csrftoken"].value
        assert client.post("/api/v1/tasks/", {"title": "x"}, HTTP_X_CSRFTOKEN=token).status_code == 201


class TestPasswordReset:
    def test_full_reset_flow(self, anon, user):
        assert anon.post("/api/v1/auth/password/reset/", {"email": "ada@example.com"}).status_code == 200
        body = mail.outbox[-1].body
        uid, token = re.search(r"uid=([^&]+)&token=(\S+)", body).groups()
        res = anon.post("/api/v1/auth/password/reset/confirm/", {"uid": uid, "token": token, "new_password": STRONG})
        assert res.status_code == 200
        assert anon.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": STRONG}).status_code == 200
        # token is single-use
        assert anon.post("/api/v1/auth/password/reset/confirm/", {"uid": uid, "token": token, "new_password": STRONG + "x"}).status_code == 400

    def test_unknown_email_same_response(self, anon):
        res = anon.post("/api/v1/auth/password/reset/", {"email": "ghost@example.com"})
        assert res.status_code == 200 and len(mail.outbox) == 0

    def test_email_verification(self, anon):
        register(anon)
        uid, token = re.search(r"uid=([^&]+)&token=(\S+)", mail.outbox[0].body).groups()
        assert anon.post("/api/v1/auth/email/verify/", {"uid": uid, "token": token}).status_code == 200
        assert User.objects.get(email="new@example.com").email_verified_at is not None


class TestAccount:
    def test_change_password_requires_current(self, api):
        bad = api.post("/api/v1/auth/password/change/", {"current_password": "wrong", "new_password": STRONG})
        assert bad.status_code == 400 and "current_password" in bad.json()["error"]["fields"]
        assert api.post("/api/v1/auth/password/change/", {"current_password": "correct horse battery", "new_password": STRONG}).status_code == 200

    def test_export_contains_owned_data_only(self, api, other_api):
        api.post("/api/v1/tasks/", {"title": "Mine"})
        other_api.post("/api/v1/tasks/", {"title": "Theirs"})
        data = api.get("/api/v1/account/export/").json()
        titles = [t["title"] for t in data["data"]["tasks"]]
        assert titles == ["Mine"]
        assert "push_devices" in data["data"] and "journal_entries" in data["data"]

    def test_delete_account_removes_everything(self, api, user):
        api.post("/api/v1/tasks/", {"title": "Mine"})
        bad = api.post("/api/v1/account/delete/", {"password": "correct horse battery", "confirm": "nope"})
        assert bad.status_code == 400
        assert api.post("/api/v1/account/delete/", {"password": "correct horse battery", "confirm": "DELETE"}).status_code == 204
        assert not User.objects.filter(pk=user.pk).exists()
        from apps.tasks.models import Task

        assert Task.objects.count() == 0
        assert AuditEvent.objects.filter(kind="account_deleted", user__isnull=True).exists()

    def test_sessions_list_and_revoke(self, user):
        a, b = APIClient(), APIClient()
        a.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"})
        b.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"})
        sessions = a.get("/api/v1/auth/sessions/").json()
        assert len(sessions) == 2
        other = next(s for s in sessions if not s["current"])
        assert a.delete(f"/api/v1/auth/sessions/{other['session_key']}/").status_code == 204
        assert b.get("/api/v1/auth/me/").status_code == 401


class TestAnonymousCsrf:
    """Regression (found in the prod-stack run): anonymous auth endpoints must enforce CSRF (prevents login CSRF)."""

    @pytest.mark.parametrize("path", ["/api/v1/auth/login/", "/api/v1/auth/register/", "/api/v1/auth/password/reset/",
                                      "/api/v1/auth/password/reset/confirm/", "/api/v1/auth/email/verify/"])
    def test_rejected_without_token(self, path):
        client = APIClient(enforce_csrf_checks=True)
        assert client.post(path, {"email": "a@example.com"}).status_code == 403

    def test_login_works_with_token(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/v1/auth/csrf/")
        token = client.cookies["daywell_csrftoken"].value
        res = client.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"}, HTTP_X_CSRFTOKEN=token)
        assert res.status_code == 200


def test_revoked_session_stops_working_with_cached_sessions(user, settings):
    """Regression: with the cached_db session engine, revocation must clear the cached copy as well as the DB row."""
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.cached_db"
    a, b = APIClient(), APIClient()
    for c in (a, b):
        c.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"})
    assert b.get("/api/v1/auth/me/").status_code == 200  # b's session is now cached
    other = next(s for s in a.get("/api/v1/auth/sessions/").json() if not s["current"])
    assert a.delete(f"/api/v1/auth/sessions/{other['session_key']}/").status_code == 204
    assert b.get("/api/v1/auth/me/").status_code == 401
