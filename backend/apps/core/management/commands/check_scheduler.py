"""Exit 0 when the reminder scheduler is healthy, 1 otherwise. Used by the beat container's health check and monitoring.

Healthy = the heartbeat task (scheduled by beat every minute, executed by a worker) ran within --max-age seconds and the
oldest due reminder isn't lagging more than --max-lag seconds.
"""

import sys
from datetime import UTC, datetime

from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check the Celery beat heartbeat and reminder dispatch lag."

    def add_arguments(self, parser):
        parser.add_argument("--max-age", type=int, default=180)
        parser.add_argument("--max-lag", type=int, default=300)

    def handle(self, *args, **opts):
        from apps.core.health import HEARTBEAT_KEY
        from apps.reminders.selectors import scheduler_lag_seconds

        now = datetime.now(UTC)
        try:
            beat = cache.get(HEARTBEAT_KEY)
        except Exception as exc:  # cache down → scheduler can't be confirmed
            self.stderr.write(f"cache unavailable: {exc.__class__.__name__}")
            sys.exit(1)
        lag = scheduler_lag_seconds(now)
        if beat is None:
            self.stderr.write("no scheduler heartbeat yet")
            sys.exit(1)
        age = (now - datetime.fromisoformat(beat)).total_seconds()
        if age > opts["max_age"] or lag > opts["max_lag"]:
            self.stderr.write(f"scheduler unhealthy: heartbeat {age:.0f}s old, dispatch lag {lag:.0f}s")
            sys.exit(1)
        self.stdout.write(f"ok: heartbeat {age:.0f}s old, dispatch lag {lag:.0f}s")
