"""The authoritative reminder clock.

Celery beat runs ``dispatch_due`` every 30 s. Each run:

1. **Recovers** occurrences stuck in ``dispatching`` (worker crashed mid-send) back to ``scheduled``.
2. **Claims** due occurrences with ``SELECT … FOR UPDATE SKIP LOCKED`` and marks them ``dispatching`` in a short
   transaction — two workers can never claim the same row.
3. **Evaluates** each claimed occurrence outside the claim transaction (rules below) and delivers it.
4. **Retries** transient push failures with bounded backoff and sends **escalations** for reminders that repeat until
   acknowledged.

Evaluation order (first match wins):
    reminder disabled/deleted              → cancelled
    older than REMINDER_STALE_AFTER        → missed      (surfaced in-app on the next visit; never pushed late)
    module disabled for the category       → skipped
    category notifications switched off    → skipped
    linked task closed / habit done/paused → skipped
    inside quiet hours (no bypass)         → delayed to quiet-hours end, or delivered silently in-app
    category frequency cap reached         → skipped     (high/critical priority exempt)
    same target already alerted ±60 s      → skipped     (deduplication)
    otherwise                              → delivered on the enabled channels → ``sent`` (or retried / ``failed``)

Delivery is at-least-once at the transport level; duplicates are collapsed on the device because every notification
carries ``tag = occ-<id>``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.timeutils import get_zone, localize
from apps.preferences.models import CATEGORY_MODULE, UserPreference
from apps.preferences.services import in_quiet_hours, notification_pref, quiet_hours_end

from .channels import CHANNELS, DispatchContext, WebPushChannel
from .models import NotificationDelivery, OccurrenceStatus, Reminder, ReminderOccurrence

logger = logging.getLogger("daywell.dispatch")
CLAIM_TIMEOUT = timedelta(minutes=5)
DEDUPE_WINDOW = timedelta(seconds=60)
MAX_ESCALATIONS = 3


def _skip(occ: ReminderOccurrence, reason: str, status: str = OccurrenceStatus.SKIPPED) -> str:
    occ.status = status
    occ.skip_reason = reason
    occ.claimed_at = None
    occ.save(update_fields=["status", "skip_reason", "claimed_at", "updated_at"])
    return reason


def recover_stuck(now: datetime) -> int:
    return ReminderOccurrence.objects.filter(status=OccurrenceStatus.DISPATCHING, claimed_at__lt=now - CLAIM_TIMEOUT).update(
        status=OccurrenceStatus.SCHEDULED, claimed_at=None, last_error="recovered after stalled dispatch"
    )


def claim_batch(now: datetime, limit: int) -> list[int]:
    with transaction.atomic():
        ids = list(
            ReminderOccurrence.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(status=OccurrenceStatus.SCHEDULED, fire_at__lte=now)
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by("fire_at")
            .values_list("id", flat=True)[:limit]
        )
        if ids:
            ReminderOccurrence.objects.filter(id__in=ids).update(status=OccurrenceStatus.DISPATCHING, claimed_at=now)
    return ids


def _linked_item_closed(occ: ReminderOccurrence, reminder: Reminder, prefs: UserPreference) -> str | None:
    if occ.task_id:
        from apps.tasks.models import OPEN_STATUSES, Task

        task = Task.objects.filter(pk=occ.task_id).only("status", "deleted_at").first()
        if task is None or task.deleted_at or task.status not in OPEN_STATUSES:
            return "task_closed"
    if reminder.habit_id:
        from apps.habits.models import CompletionStatus, HabitStatus

        habit = reminder.habit
        if habit.status != HabitStatus.ACTIVE:
            return "habit_paused"
        local_day = occ.scheduled_for.astimezone(get_zone(habit.time_zone)).date()
        if habit.completions.filter(date=local_day, status__in=[CompletionStatus.DONE, CompletionStatus.SKIPPED]).exists():
            return "habit_done"
    return None


def evaluate_and_deliver(occ: ReminderOccurrence, now: datetime) -> str:
    """Decide what happens to one claimed occurrence. Returns a short outcome label (for stats/tests)."""
    reminder = Reminder.objects.filter(pk=occ.reminder_id).select_related("habit").first()
    if reminder is None or not reminder.enabled:
        return _skip(occ, "reminder_disabled", OccurrenceStatus.CANCELLED)
    if now - occ.fire_at > settings.REMINDER_STALE_AFTER and occ.attempts == 0:
        return _skip(occ, "stale", OccurrenceStatus.MISSED)

    prefs = UserPreference.objects.get(user_id=occ.owner_id)
    module = CATEGORY_MODULE.get(occ.category)
    if module and not prefs.module_enabled(module):
        return _skip(occ, "module_disabled")
    cat_pref = notification_pref(occ.owner, occ.category)
    if not cat_pref.enabled and not reminder.is_test:
        return _skip(occ, "category_disabled")
    closed = _linked_item_closed(occ, reminder, prefs)
    if closed:
        return _skip(occ, closed)

    zone = get_zone(prefs.time_zone)
    local_now = now.astimezone(zone)
    bypass = reminder.bypass_quiet_hours or cat_pref.bypass_quiet_hours or reminder.is_test
    silent = False
    if not bypass and in_quiet_hours(prefs, local_now):
        if prefs.quiet_behavior == UserPreference.QuietBehavior.DELAY:
            occ.fire_at = localize(quiet_hours_end(prefs, local_now, zone), zone)
            occ.status = OccurrenceStatus.SCHEDULED
            occ.claimed_at = None
            occ.skip_reason = "delayed_quiet_hours"
            occ.save(update_fields=["fire_at", "status", "claimed_at", "skip_reason", "updated_at"])
            return "delayed"
        silent = True

    if cat_pref.min_gap_minutes and reminder.priority == Reminder.Priority.NORMAL and not reminder.is_test:
        recent = ReminderOccurrence.objects.filter(owner_id=occ.owner_id, category=occ.category, sent_at__gte=now - timedelta(minutes=cat_pref.min_gap_minutes)).exclude(pk=occ.pk)
        if recent.exists():
            return _skip(occ, "frequency_limit")
    if occ.target_key and not occ.parent_id:
        dup = ReminderOccurrence.objects.filter(
            owner_id=occ.owner_id,
            target_key=occ.target_key,
            sent_at__isnull=False,
            fire_at__gte=occ.fire_at - DEDUPE_WINDOW,
            fire_at__lte=occ.fire_at + DEDUPE_WINDOW,
        ).exclude(pk=occ.pk)
        if dup.exists():
            return _skip(occ, "duplicate")

    if reminder.system_key.startswith("briefing:"):
        from apps.briefing.services import briefing_push_text

        occ.title, occ.body = briefing_push_text(occ, reminder, now)
    elif not occ.body:
        from apps.briefing.messages import reminder_body

        occ.body = reminder_body(occ, reminder, prefs, now)
    ctx = DispatchContext(
        now=now,
        silent=silent,
        sound=reminder.sound or cat_pref.sound or prefs.default_sound,
        vibrate=reminder.vibrate and cat_pref.vibrate,
        snooze_minutes=reminder.snooze_minutes or cat_pref.snooze_minutes,
        kind=NotificationDelivery.Kind.TEST if reminder.is_test else (NotificationDelivery.Kind.RETRY if occ.attempts else NotificationDelivery.Kind.INITIAL),
    )
    channels = set(cat_pref.channels) if not reminder.is_test else {"in_app", "push"}
    if silent:
        channels = {"in_app"}
    deliveries: list[NotificationDelivery] = []
    for name in ("in_app", "push"):
        if name in channels:
            deliveries.extend(CHANNELS[name].deliver(occ, ctx))

    occ.attempts += 1
    occ.silent = silent
    occ.claimed_at = None
    accepted = [d for d in deliveries if d.result == NotificationDelivery.Result.ACCEPTED]
    if accepted:
        occ.status = OccurrenceStatus.SENT
        occ.sent_at = occ.last_alerted_at = now
        occ.last_error = ""
        outcome = "sent"
    elif any(d.transient for d in deliveries) and occ.attempts < settings.REMINDER_MAX_ATTEMPTS:
        occ.status = OccurrenceStatus.SCHEDULED
        occ.next_attempt_at = now + timedelta(seconds=30 * (2**occ.attempts))
        occ.last_error = "; ".join({d.error for d in deliveries if d.error})[:300]
        outcome = "retry"
    else:
        occ.status = OccurrenceStatus.FAILED
        occ.last_error = ("; ".join({d.error for d in deliveries if d.error}) or "No delivery channel is available (enable in-app or push).")[:300]
        outcome = "failed"
    occ.save()
    return outcome


def retry_failed_pushes(now: datetime) -> int:
    """Re-send transient push failures for occurrences the user hasn't acted on yet."""
    channel: WebPushChannel = CHANNELS["push"]  # type: ignore[assignment]
    count = 0
    pending = NotificationDelivery.objects.filter(
        channel=NotificationDelivery.Channel.PUSH,
        result=NotificationDelivery.Result.FAILED,
        retry_at__lte=now,
        occurrence__status=OccurrenceStatus.SENT,
        occurrence__acted_at__isnull=True,
        occurrence__fire_at__gte=now - settings.REMINDER_STALE_AFTER,
        subscription__active=True,
    ).select_related("occurrence", "subscription")[:200]
    for delivery in pending:
        occ = delivery.occurrence
        ctx = DispatchContext(now=now, silent=False, sound="", vibrate=True, snooze_minutes=10, kind=NotificationDelivery.Kind.RETRY)
        channel.send_one(occ, delivery.subscription, ctx, delivery=delivery)
        count += 1
    return count


def send_escalations(now: datetime) -> int:
    """Re-alert reminders configured to repeat until acknowledged (max MAX_ESCALATIONS times)."""
    count = 0
    qs = ReminderOccurrence.objects.filter(
        status=OccurrenceStatus.SENT,
        acted_at__isnull=True,
        silent=False,
        reminder__repeat_until_ack=True,
        escalations__lt=MAX_ESCALATIONS,
        fire_at__gte=now - timedelta(hours=2),
    ).select_related("reminder")
    for occ in qs[:200]:
        interval = timedelta(minutes=max(1, occ.reminder.repeat_every_minutes))
        if occ.last_alerted_at and occ.last_alerted_at + interval > now:
            continue
        with transaction.atomic():
            locked = ReminderOccurrence.objects.select_for_update(skip_locked=True, of=("self",)).filter(pk=occ.pk, status=OccurrenceStatus.SENT).first()
            if locked is None:
                continue
            ctx = DispatchContext(now=now, silent=False, sound="", vibrate=True, snooze_minutes=10, kind=NotificationDelivery.Kind.ESCALATION)
            CHANNELS["in_app"].deliver(locked, ctx)
            CHANNELS["push"].deliver(locked, ctx)
            locked.escalations += 1
            locked.last_alerted_at = now
            locked.save(update_fields=["escalations", "last_alerted_at", "updated_at"])
            count += 1
    return count


def dispatch_due(now: datetime | None = None) -> dict:
    now = now or timezone.now()
    stats: dict[str, int] = {"recovered": recover_stuck(now)}
    while True:
        ids = claim_batch(now, settings.REMINDER_DISPATCH_BATCH)
        if not ids:
            break
        for occ in ReminderOccurrence.objects.filter(id__in=ids).select_related("owner"):
            try:
                outcome = evaluate_and_deliver(occ, now)
            except Exception as exc:  # isolate failures per occurrence; bounded retries, then "failed"
                logger.exception("dispatch failed", extra={"occurrence_id": occ.id})
                give_up = occ.attempts + 1 >= settings.REMINDER_MAX_ATTEMPTS
                ReminderOccurrence.objects.filter(pk=occ.pk).update(
                    status=OccurrenceStatus.FAILED if give_up else OccurrenceStatus.SCHEDULED,
                    attempts=F("attempts") + 1,
                    claimed_at=None,
                    next_attempt_at=now + timedelta(minutes=2),
                    last_error=f"internal error: {exc.__class__.__name__}"[:300],
                )
                outcome = "error"
            stats[outcome] = stats.get(outcome, 0) + 1
        if len(ids) < settings.REMINDER_DISPATCH_BATCH:
            break
    stats["push_retries"] = retry_failed_pushes(now)
    stats["escalations"] = send_escalations(now)
    if any(v for k, v in stats.items()):
        logger.info("dispatch run", extra={"stats": stats})
    return stats


def dispatch_now(occ: ReminderOccurrence) -> str:
    """Dispatch one occurrence immediately (used by the test-notification endpoint)."""
    now = timezone.now()
    updated = ReminderOccurrence.objects.filter(pk=occ.pk, status=OccurrenceStatus.SCHEDULED).update(status=OccurrenceStatus.DISPATCHING, claimed_at=now)
    if not updated:
        return "already_handled"
    occ.refresh_from_db()
    return evaluate_and_deliver(occ, now)
