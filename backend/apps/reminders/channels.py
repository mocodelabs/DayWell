"""Delivery channel abstraction.

A channel turns a due ``ReminderOccurrence`` into zero or more ``NotificationDelivery`` attempts. New providers (e.g. a
native Android/iOS app using FCM/APNs alarm APIs) implement ``DeliveryChannel`` and are added to ``CHANNELS`` — the
reminder business logic (sync, dispatch, snooze, quiet hours) does not change. No native channel ships in the first
release; see docs/NOTIFICATIONS_AND_ALARMS.md §"Adding a native channel".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from django.utils import timezone

from . import push
from .models import DeviceSubscription, NotificationDelivery, ReminderOccurrence

RETRY_BACKOFF = [timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=8)]


@dataclass
class DispatchContext:
    now: datetime
    silent: bool
    sound: str
    vibrate: bool
    snooze_minutes: int
    kind: str = NotificationDelivery.Kind.INITIAL


class DeliveryChannel(Protocol):
    name: str

    def deliver(self, occurrence: ReminderOccurrence, ctx: DispatchContext) -> list[NotificationDelivery]: ...


class InAppChannel:
    """Makes the occurrence available to the open app (polled via /alarms/active/). The app confirms display."""

    name = NotificationDelivery.Channel.IN_APP

    def deliver(self, occurrence, ctx):
        return [
            NotificationDelivery.objects.create(
                occurrence=occurrence,
                channel=self.name,
                kind=ctx.kind,
                attempted_at=ctx.now,
                result=NotificationDelivery.Result.ACCEPTED,
            )
        ]


class WebPushChannel:
    name = NotificationDelivery.Channel.PUSH

    def deliver(self, occurrence, ctx):
        if ctx.silent or not push.push_configured():
            return []
        subs = list(DeviceSubscription.objects.filter(owner_id=occurrence.owner_id, active=True))
        return [self.send_one(occurrence, sub, ctx) for sub in subs]

    def send_one(self, occurrence, sub, ctx, delivery: NotificationDelivery | None = None) -> NotificationDelivery:
        if delivery is None:
            delivery = NotificationDelivery.objects.create(
                occurrence=occurrence,
                channel=self.name,
                kind=ctx.kind,
                subscription=sub,
                attempted_at=ctx.now,
            )
        else:
            delivery.retry_count += 1
            delivery.attempted_at = ctx.now
        payload = build_payload(occurrence, delivery, ctx)
        result = push.send(sub, payload)
        delivery.http_status = result.status
        delivery.provider_ref = result.ref
        delivery.error = result.error[:300]
        delivery.transient = result.transient
        if result.ok:
            delivery.result = NotificationDelivery.Result.ACCEPTED
            delivery.retry_at = None
            sub.last_success_at = ctx.now
            sub.failure_count = 0
            sub.save(update_fields=["last_success_at", "failure_count", "updated_at"])
        else:
            delivery.result = NotificationDelivery.Result.EXPIRED if result.expired else NotificationDelivery.Result.FAILED
            can_retry = result.transient and delivery.retry_count < len(RETRY_BACKOFF)
            delivery.retry_at = ctx.now + RETRY_BACKOFF[delivery.retry_count] if can_retry else None
            sub.last_failure_at = ctx.now
            sub.failure_count += 1
            if result.expired or sub.failure_count >= 10:
                sub.active = False  # expired/invalid subscriptions are removed from rotation
            sub.save(update_fields=["last_failure_at", "failure_count", "active", "updated_at"])
        delivery.save()
        return delivery


def build_payload(occurrence: ReminderOccurrence, delivery: NotificationDelivery, ctx: DispatchContext) -> dict:
    return {
        "type": "reminder",
        "title": occurrence.title,
        "body": occurrence.body,
        "tag": f"occ-{occurrence.id}",  # the OS replaces rather than duplicates a notification with the same tag
        "occurrence_id": occurrence.id,
        "category": occurrence.category,
        "url": f"/?alarm={occurrence.id}",
        "receipt": push.receipt_token(occurrence.id, delivery.id),
        "requireInteraction": True,
        "vibrate": ctx.vibrate,
        "snooze_minutes": ctx.snooze_minutes,
        "sent_at": timezone.now().isoformat(),
    }


CHANNELS: dict[str, DeliveryChannel] = {
    NotificationDelivery.Channel.IN_APP: InAppChannel(),
    NotificationDelivery.Channel.PUSH: WebPushChannel(),
}
