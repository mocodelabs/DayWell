import importlib
import sys

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

pytestmark = pytest.mark.django_db


def test_live_and_ready(anon):
    assert anon.get("/health/live/").json() == {"status": "ok"}
    res = anon.get("/health/ready/")
    assert res.status_code == 200 and res.json()["checks"] == {"database": "ok", "cache": "ok"}


def test_scheduler_reports_stalled_without_heartbeat(anon):
    res = anon.get("/health/scheduler/")
    assert res.status_code == 503 and res.json()["status"] == "stalled"
    from apps.reminders.tasks import heartbeat

    heartbeat()
    res = anon.get("/health/scheduler/")
    assert res.status_code == 200 and res.json()["beat_age_seconds"] < 5
    cache.clear()


def test_request_id_is_echoed(anon):
    res = anon.get("/health/live/", HTTP_X_REQUEST_ID="abc12345-trace")
    assert res["X-Request-ID"] == "abc12345-trace"
    assert len(anon.get("/health/live/", HTTP_X_REQUEST_ID="bad id!")["X-Request-ID"]) == 32


def test_unhandled_errors_use_the_envelope_and_hide_details(api, monkeypatch):
    from apps.briefing import views

    monkeypatch.setattr(views.services, "today_payload", lambda *a, **k: 1 / 0)
    api.raise_request_exception = False
    res = api.get("/api/v1/dashboard/today/")
    assert res.status_code == 500
    assert res.json() == {"error": {"code": "server_error", "message": "Something went wrong on our side. Please try again.", "fields": {}}}


def test_prod_settings_refuse_weak_secret(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "short")
    monkeypatch.setenv("DATABASE_URL", "postgres://x:x@localhost/x")
    for mod in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(mod, None)
    with pytest.raises(ImproperlyConfigured):
        importlib.import_module("config.settings.prod")
    for mod in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(mod, None)


def test_prod_settings_are_secure(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 50)
    monkeypatch.setenv("DATABASE_URL", "postgres://x:x@localhost/x")
    for mod in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(mod, None)
    prod = importlib.import_module("config.settings.prod")
    assert not prod.DEBUG and prod.SESSION_COOKIE_SECURE and prod.CSRF_COOKIE_SECURE and prod.SESSION_COOKIE_HTTPONLY
    assert prod.SECURE_SSL_REDIRECT and prod.SECURE_HSTS_SECONDS >= 31536000
    for mod in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(mod, None)


def test_request_id_reaches_djangos_own_error_log_lines(anon):
    """Regression: Django logs 4xx/5xx after the middleware chain returns; the id must still be set then."""
    import logging

    from apps.core.logging import RequestIdFilter

    seen = []

    class Capture(logging.Handler):
        def emit(self, record):
            seen.append(getattr(record, "request_id", None))

    handler = Capture()
    handler.addFilter(RequestIdFilter())
    logger = logging.getLogger("django.request")
    logger.addHandler(handler)
    try:
        res = anon.get("/api/v1/tasks/", HTTP_X_REQUEST_ID="trace-12345678")
    finally:
        logger.removeHandler(handler)
    assert res.status_code == 401 and seen == ["trace-12345678"]


def test_health_probe_bypasses_host_check_and_https_redirect(anon, settings):
    """Regression (found running the prod stack): container probes use http://127.0.0.1:8000, which prod rejects."""
    settings.ALLOWED_HOSTS = ["daywell.example.com"]
    settings.SECURE_SSL_REDIRECT = True
    assert anon.get("/health/live/", HTTP_HOST="127.0.0.1:8000").status_code == 200
    assert anon.get("/health/ready/", HTTP_HOST="127.0.0.1:8000").status_code == 200
    assert anon.get("/api/v1/auth/csrf/", HTTP_HOST="127.0.0.1:8000").status_code == 400  # everything else still validated
    assert anon.get("/api/v1/auth/csrf/", HTTP_HOST="daywell.example.com").status_code == 301  # and redirected to HTTPS


def test_check_scheduler_command():
    from django.core.management import call_command

    with pytest.raises(SystemExit):
        call_command("check_scheduler")
    from apps.reminders.tasks import heartbeat

    heartbeat()
    call_command("check_scheduler")  # no SystemExit → healthy
    cache.clear()


def test_database_outage_is_a_503_not_a_bug(api, monkeypatch):
    from django.db import OperationalError

    from apps.briefing import views

    def down(*a, **k):
        raise OperationalError("could not connect to server")

    monkeypatch.setattr(views.services, "today_payload", down)
    api.raise_request_exception = False
    res = api.get("/api/v1/dashboard/today/")
    assert res.status_code == 503 and res["Retry-After"] == "30"
    assert res.json()["error"]["code"] == "service_unavailable"


def test_resilient_cache_degrades_to_misses():
    """Regression (found in the prod-stack run): a Redis outage took every API request down via throttling."""
    from apps.core.cache import ResilientRedisCache

    dead = ResilientRedisCache("redis://127.0.0.1:1/0", {"OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2}})
    assert dead.get("k", "fallback") == "fallback"
    assert dead.set("k", 1) is None
    assert dead.add("k", 1) is False
    assert dead.get_many(["a", "b"]) == {}
    with pytest.raises(ValueError):
        dead.incr("k")


def test_api_and_login_keep_working_when_cache_is_down(api, anon, user, settings):
    settings.CACHES = {"default": {"BACKEND": "apps.core.cache.ResilientRedisCache", "LOCATION": "redis://127.0.0.1:1/0",
                                   "OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2}}}
    # pytest-django's settings fixture fires setting_changed, which rebuilds the cache handlers.
    assert api.post("/api/v1/tasks/", {"title": "still works"}).status_code == 201
    assert anon.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "correct horse battery"}).status_code == 200
    assert anon.get("/health/ready/").status_code == 503  # monitoring still sees the outage
