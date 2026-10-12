import logging
from datetime import UTC, datetime

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger("daywell.reminders")


@shared_task(name="reminders.dispatch_due", ignore_result=True)
def dispatch_due() -> dict:
    """Beat every 30 s. A Redis lock keeps overlapping runs from piling up (correctness relies on SKIP LOCKED anyway)."""
    from .dispatch import dispatch_due as run

    lock = cache.add("lock:dispatch_due", "1", timeout=120)
    if not lock:
        return {"skipped": "already running"}
    try:
        return run()
    finally:
        cache.delete("lock:dispatch_due")


@shared_task(name="reminders.extend_horizon", ignore_result=True)
def extend_horizon() -> int:
    from .services import extend_horizon as run

    return run()


@shared_task(name="reminders.sync_reminder", ignore_result=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_reminder(reminder_id: int) -> dict:
    from .models import Reminder
    from .services import sync_reminder as run

    reminder = Reminder.objects.filter(pk=reminder_id).first()
    return run(reminder) if reminder else {}


@shared_task(name="reminders.heartbeat", ignore_result=True)
def heartbeat() -> float:
    from apps.core.health import HEARTBEAT_KEY

    from .selectors import scheduler_lag_seconds

    now = datetime.now(UTC)
    cache.set(HEARTBEAT_KEY, now.isoformat(), timeout=600)
    lag = scheduler_lag_seconds(now)
    if lag > 120:
        logger.warning("reminder dispatch is lagging", extra={"lag_seconds": round(lag)})
    return lag
