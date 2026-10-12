"""Read-side queries for the alarm UI, notification centre and health checks."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Min, Q
from django.utils import timezone

from .models import OccurrenceStatus, ReminderOccurrence

ACTIVE_WINDOW = timedelta(minutes=60)


def active_alarms(user, now: datetime | None = None):
    """Alarms the open app should be showing/ringing now: sent, not acted on, recent, delivered on the in-app channel."""
    now = now or timezone.now()
    return (
        ReminderOccurrence.objects.filter(owner=user, status=OccurrenceStatus.SENT, acted_at__isnull=True, fire_at__gte=now - ACTIVE_WINDOW)
        .filter(deliveries__channel="in_app")
        .select_related("reminder")
        .distinct()
        .order_by("fire_at")
    )


def missed(user, now: datetime | None = None):
    """Needs attention on return: missed during downtime, failed, or alerted but never acted on for over an hour."""
    now = now or timezone.now()
    prefs = user.preferences
    if prefs.missed_policy == "hide":
        return ReminderOccurrence.objects.none()
    return (
        ReminderOccurrence.objects.filter(owner=user, acted_at__isnull=True, fire_at__gte=now - timedelta(days=7))
        .filter(Q(status__in=[OccurrenceStatus.MISSED, OccurrenceStatus.FAILED]) | Q(status=OccurrenceStatus.SENT, fire_at__lt=now - ACTIVE_WINDOW))
        .select_related("reminder")
        .order_by("-fire_at")
    )


def upcoming(user, *, hours: int = 24, now: datetime | None = None):
    now = now or timezone.now()
    return (
        ReminderOccurrence.objects.filter(owner=user, status=OccurrenceStatus.SCHEDULED, fire_at__gte=now - timedelta(minutes=1), fire_at__lt=now + timedelta(hours=hours))
        .select_related("reminder")
        .order_by("fire_at")
    )


def scheduler_lag_seconds(now: datetime | None = None) -> float:
    """How overdue the oldest still-scheduled occurrence is (0 when the dispatcher is keeping up)."""
    now = now or timezone.now()
    oldest = ReminderOccurrence.objects.filter(status=OccurrenceStatus.SCHEDULED, fire_at__lte=now, next_attempt_at__isnull=True).aggregate(m=Min("fire_at"))["m"]
    return max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
