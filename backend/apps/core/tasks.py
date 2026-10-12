import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.sessions.models import Session
from django.utils import timezone

logger = logging.getLogger("daywell.core")


@shared_task(name="core.cleanup")
def cleanup() -> dict:
    """Nightly housekeeping: expired sessions and old delivery-attempt logs (history of occurrences is kept)."""
    from apps.accounts.models import UserSession
    from apps.reminders.models import NotificationDelivery

    now = timezone.now()
    expired, _ = Session.objects.filter(expire_date__lt=now).delete()
    stale_sessions, _ = UserSession.objects.filter(expires_at__lt=now).delete()
    old_deliveries, _ = NotificationDelivery.objects.filter(attempted_at__lt=now - timedelta(days=180)).delete()
    result = {"sessions": expired, "user_sessions": stale_sessions, "deliveries": old_deliveries}
    logger.info("cleanup done", extra=result)
    return result
