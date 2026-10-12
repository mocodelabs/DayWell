"""User actions on reminder occurrences. Each runs in a transaction with a row lock and is idempotent."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import FINAL_ACTION_STATUSES, NotificationDelivery, OccurrenceStatus, ReminderOccurrence

ACTIONABLE = (OccurrenceStatus.SENT, OccurrenceStatus.MISSED, OccurrenceStatus.FAILED, OccurrenceStatus.SCHEDULED)
MAX_SNOOZES = 12


def _lock(occ: ReminderOccurrence) -> ReminderOccurrence:
    return ReminderOccurrence.objects.select_for_update(of=("self",)).select_related("reminder").get(pk=occ.pk)


def _ensure_actionable(occ: ReminderOccurrence) -> None:
    if occ.status not in ACTIONABLE:
        raise BusinessRuleError("This reminder has already been handled.", code="already_handled")


def _cancel_pending_children(occ: ReminderOccurrence, now: datetime) -> None:
    occ.children.filter(status=OccurrenceStatus.SCHEDULED).update(status=OccurrenceStatus.CANCELLED, skip_reason="superseded", updated_at=now)


def _child(occ: ReminderOccurrence, at: datetime, suffix: str) -> ReminderOccurrence:
    key = f"{occ.idempotency_key}:{suffix}"
    child, _ = ReminderOccurrence.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "reminder_id": occ.reminder_id,
            "owner_id": occ.owner_id,
            "category": occ.category,
            "title": occ.title,
            "body": occ.body,
            "scheduled_for": at,
            "fire_at": at,
            "target_key": occ.target_key,
            "task_id": occ.task_id,
            "parent": occ,
            "snooze_count": occ.snooze_count + 1,
        },
    )
    return child


@transaction.atomic
def snooze(occ: ReminderOccurrence, minutes: int | None = None, *, now: datetime | None = None) -> ReminderOccurrence:
    """Record the snooze and schedule exactly one follow-up occurrence. Original history is preserved."""
    now = now or timezone.now()
    occ = _lock(occ)
    if occ.status == OccurrenceStatus.SNOOZED:
        return occ.children.filter(status=OccurrenceStatus.SCHEDULED).order_by("-fire_at").first() or occ
    _ensure_actionable(occ)
    if occ.snooze_count >= MAX_SNOOZES:
        raise BusinessRuleError("This reminder has been snoozed many times. Reschedule or dismiss it instead.")
    from apps.preferences.services import notification_pref

    minutes = minutes or occ.reminder.snooze_minutes or notification_pref(occ.owner, occ.category).snooze_minutes
    if not 1 <= minutes <= 24 * 60:
        raise BusinessRuleError("Snooze for between 1 minute and 24 hours.", code="invalid", status_code=400)
    _cancel_pending_children(occ, now)
    until = now + timedelta(minutes=minutes)
    occ.status = OccurrenceStatus.SNOOZED
    occ.acted_at = now
    occ.snoozed_until = until
    occ.save(update_fields=["status", "acted_at", "snoozed_until", "updated_at"])
    return _child(occ, until, f"snooze{occ.snooze_count + 1}")


@transaction.atomic
def dismiss(occ: ReminderOccurrence, *, now: datetime | None = None) -> ReminderOccurrence:
    """Dismissal is recorded; it never completes the linked task or habit."""
    now = now or timezone.now()
    occ = _lock(occ)
    if occ.status == OccurrenceStatus.DISMISSED:
        return occ
    _ensure_actionable(occ)
    _cancel_pending_children(occ, now)
    occ.status = OccurrenceStatus.DISMISSED
    occ.acted_at = occ.dismissed_at = now
    occ.save(update_fields=["status", "acted_at", "dismissed_at", "updated_at"])
    return occ


@transaction.atomic
def complete(occ: ReminderOccurrence, *, now: datetime | None = None) -> ReminderOccurrence:
    """Completes the linked task / habit-for-the-day *and* records the occurrence as completed."""
    now = now or timezone.now()
    occ = _lock(occ)
    if occ.status == OccurrenceStatus.COMPLETED:
        return occ
    _ensure_actionable(occ)
    if occ.task_id:
        from apps.tasks import services as task_services
        from apps.tasks.models import Task

        task = Task.objects.filter(pk=occ.task_id, owner_id=occ.owner_id).first()
        if task is not None:
            task_services.complete(task, at=now)
    elif occ.reminder.habit_id:
        from apps.core.timeutils import get_zone
        from apps.habits.services import record_completion

        habit = occ.reminder.habit
        record_completion(habit, occ.scheduled_for.astimezone(get_zone(habit.time_zone)).date(), mark_target=True)
    _cancel_pending_children(occ, now)
    occ.status = OccurrenceStatus.COMPLETED
    occ.acted_at = occ.completed_at = now
    occ.save(update_fields=["status", "acted_at", "completed_at", "updated_at"])
    return occ


@transaction.atomic
def keep(occ: ReminderOccurrence, *, now: datetime | None = None) -> ReminderOccurrence:
    """Missed-reminder recovery: acknowledge it and leave the linked item overdue."""
    now = now or timezone.now()
    occ = _lock(occ)
    if occ.status == OccurrenceStatus.ACKNOWLEDGED:
        return occ
    _ensure_actionable(occ)
    occ.status = OccurrenceStatus.ACKNOWLEDGED
    occ.acted_at = now
    occ.save(update_fields=["status", "acted_at", "updated_at"])
    return occ


@transaction.atomic
def reschedule(occ: ReminderOccurrence, at: datetime, *, now: datetime | None = None) -> ReminderOccurrence:
    now = now or timezone.now()
    if at <= now:
        raise BusinessRuleError("Choose a time in the future.", code="invalid", status_code=400)
    occ = _lock(occ)
    _ensure_actionable(occ)
    _cancel_pending_children(occ, now)
    occ.status = OccurrenceStatus.RESCHEDULED
    occ.acted_at = now
    occ.save(update_fields=["status", "acted_at", "updated_at"])
    return _child(occ, at, f"resched{int(at.timestamp())}")


@transaction.atomic
def mark_shown(occ: ReminderOccurrence, *, audio: str = "", now: datetime | None = None) -> ReminderOccurrence:
    """The open app confirms it displayed the alarm (and whether audio actually played)."""
    now = now or timezone.now()
    occ = _lock(occ)
    NotificationDelivery.objects.filter(occurrence=occ, channel=NotificationDelivery.Channel.IN_APP, result=NotificationDelivery.Result.ACCEPTED).update(
        result=NotificationDelivery.Result.DELIVERED, confirmed_at=now
    )
    fields = ["updated_at"]
    if occ.delivered_at is None:
        occ.delivered_at = now
        fields.append("delivered_at")
    if audio:
        occ.audio_status = audio
        fields.append("audio_status")
        if audio == "played" and occ.audio_played_at is None:
            occ.audio_played_at = now
            fields.append("audio_played_at")
    occ.save(update_fields=fields)
    return occ


@transaction.atomic
def push_receipt(occurrence_id: int, delivery_id: int, *, now: datetime | None = None) -> bool:
    """The service worker confirms it displayed a push notification."""
    now = now or timezone.now()
    updated = NotificationDelivery.objects.filter(
        pk=delivery_id,
        occurrence_id=occurrence_id,
        channel=NotificationDelivery.Channel.PUSH,
        result__in=[NotificationDelivery.Result.ACCEPTED, NotificationDelivery.Result.DELIVERED],
    ).update(result=NotificationDelivery.Result.DELIVERED, confirmed_at=now)
    if updated:
        ReminderOccurrence.objects.filter(pk=occurrence_id, delivered_at__isnull=True).update(delivered_at=now)
    return bool(updated)


def is_final(occ: ReminderOccurrence) -> bool:
    return occ.status in FINAL_ACTION_STATUSES
