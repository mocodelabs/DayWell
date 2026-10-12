"""Liveness / readiness / scheduler health endpoints (unauthenticated, no user data)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("daywell.health")

HEARTBEAT_KEY = "scheduler:heartbeat"


def live(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    checks: dict[str, str] = {}
    ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # report, don't crash the probe
        logger.warning("readiness: database check failed: %s", exc)
        checks["database"] = "error"
        ok = False
    try:
        cache.set("health:ping", "1", 5)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "error"
    except Exception as exc:
        logger.warning("readiness: cache check failed: %s", exc)
        checks["cache"] = "error"
    ok = ok and checks["cache"] == "ok"
    return JsonResponse({"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503)


def scheduler(request):
    """Reports the Celery beat heartbeat and dispatcher lag so monitoring can alert on a stalled scheduler."""
    from apps.reminders.selectors import scheduler_lag_seconds

    beat = None
    try:
        beat = cache.get(HEARTBEAT_KEY)
    except Exception as exc:
        logger.warning("scheduler health: cache unavailable: %s", exc)
    now = datetime.now(UTC)
    beat_age = (now - datetime.fromisoformat(beat)).total_seconds() if beat else None
    lag = scheduler_lag_seconds(now)
    healthy = beat_age is not None and beat_age < 180 and lag < 300
    return JsonResponse(
        {"status": "ok" if healthy else "stalled", "beat_age_seconds": beat_age, "oldest_due_lag_seconds": lag},
        status=200 if healthy else 503,
    )
