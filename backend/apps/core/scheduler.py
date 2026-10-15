"""Request-driven scheduler for hosts without a long-running Celery beat (e.g. serverless functions).

The same periodic jobs Celery beat runs (see CELERY_BEAT_SCHEDULE) are run here on demand: from the protected
``/internal/tick/`` endpoint (called by an external pinger / platform cron) and, when ``INLINE_SCHEDULER`` is on,
opportunistically from the in-app alarm poll. Each job is gated by a cache key that lives for its interval, so any number
of callers run each job at most once per interval. Correctness still rests on the dispatcher's SKIP LOCKED claims.
"""

from __future__ import annotations

import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("daywell.scheduler")

# name -> (interval, dotted task path). Order matters: horizon before dispatch so new occurrences can fire this tick.
JOBS: list[tuple[str, timedelta, str]] = [
    ("extend-reminder-horizon", timedelta(minutes=15), "apps.reminders.tasks.extend_horizon"),
    ("extend-task-series", timedelta(hours=1), "apps.tasks.tasks.extend_series"),
    ("dispatch-due-reminders", timedelta(seconds=25), "apps.reminders.tasks.dispatch_due"),
    ("scheduler-heartbeat", timedelta(seconds=55), "apps.reminders.tasks.heartbeat"),
    ("cleanup", timedelta(hours=24), "apps.core.tasks.cleanup"),
]


def _load(path: str):
    module, name = path.rsplit(".", 1)
    return getattr(__import__(module, fromlist=[name]), name)


def run_due_jobs(only: set[str] | None = None) -> dict[str, object]:
    """Run every job whose interval has elapsed. Failures are logged and reported, never raised."""
    results: dict[str, object] = {}
    for name, interval, path in JOBS:
        if only is not None and name not in only:
            continue
        if not cache.add(f"sched:{name}", "1", timeout=int(interval.total_seconds())):
            continue  # ran within its interval (here or in another instance)
        try:
            results[name] = _load(path)()
        except Exception:  # one failing job must not block the others
            logger.exception("scheduled job failed", extra={"job": name})
            cache.delete(f"sched:{name}")  # retry on the next tick
            results[name] = "error"
    return results


def maybe_run_inline() -> None:
    """Called from the alarm poll: keep reminders flowing while anyone has the app open."""
    if not settings.INLINE_SCHEDULER:
        return
    try:
        run_due_jobs()
    except Exception:  # never break the poll
        logger.exception("inline scheduler tick failed")


@csrf_exempt
def tick(request):
    """``GET|POST /internal/tick/`` with ``Authorization: Bearer <SCHEDULER_TOKEN>``. 404 when not configured."""
    token = settings.SCHEDULER_TOKEN
    if not token or request.method not in ("GET", "POST"):
        raise Http404
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        return JsonResponse({"detail": "forbidden"}, status=403)
    return JsonResponse({"ran": run_due_jobs()}, json_dumps_params={"default": str})
