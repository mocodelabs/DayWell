from datetime import UTC, datetime, timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import OuterRef, Prefetch, Subquery
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import AuditEvent
from apps.accounts.services import audit
from apps.core.health import HEARTBEAT_KEY
from apps.core.scheduler import maybe_run_inline
from apps.core.timeutils import get_zone
from apps.core.viewsets import OwnedModelViewSet
from apps.preferences.models import NotificationPreference
from apps.preferences.services import in_quiet_hours

from . import actions, push, selectors
from .dispatch import dispatch_now
from .models import DeviceSubscription, NotificationDelivery, OccurrenceStatus, Reminder, ReminderOccurrence
from .serializers import (
    OccurrenceSerializer,
    PushSubscribeSerializer,
    ReminderSerializer,
    RescheduleSerializer,
    ShownSerializer,
    SnoozeSerializer,
    TestNotificationSerializer,
)
from .services import sync_reminder


def occurrence_context(request) -> dict:
    return {
        "request": request,
        "prefs": request.user.preferences,
        "cat_prefs": {p.category: p for p in NotificationPreference.objects.filter(user=request.user)},
    }


class ReminderViewSet(OwnedModelViewSet):
    serializer_class = ReminderSerializer
    filterset_fields = ["category", "kind", "enabled"]
    search_fields = ["title", "message"]

    def get_queryset(self):
        nxt = ReminderOccurrence.objects.filter(reminder=OuterRef("pk"), status=OccurrenceStatus.SCHEDULED, fire_at__gte=timezone.now()).order_by("fire_at")
        return Reminder.objects.filter(owner=self.request.user, is_test=False, archived=False).annotate(next_fire=Subquery(nxt.values("fire_at")[:1]))

    def perform_create(self, serializer):
        reminder = serializer.save(owner=self.request.user, kind=Reminder.Kind.ABSOLUTE, time_zone=serializer.validated_data.get("time_zone") or self.request.user.preferences.time_zone)
        sync_reminder(reminder)

    def perform_update(self, serializer):
        sync_reminder(serializer.save())

    def perform_destroy(self, instance):
        instance.occurrences.filter(status=OccurrenceStatus.SCHEDULED).update(status=OccurrenceStatus.CANCELLED, skip_reason="reminder_deleted")
        if instance.occurrences.filter(sent_at__isnull=False).exists():
            # Keep delivered history (notification centre): archive instead of deleting.
            instance.enabled = False
            instance.archived = True
            instance.save(update_fields=["enabled", "archived", "updated_at"])
        else:
            instance.delete()

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        upcoming = ReminderOccurrence.objects.filter(reminder_id=response.data["id"], status=OccurrenceStatus.SCHEDULED).order_by("fire_at")[:5]
        response.data["upcoming"] = [o.fire_at.isoformat() for o in upcoming]
        return response


class AlarmViewSet(viewsets.GenericViewSet):
    """In-app alarm surface + per-occurrence actions (snooze, dismiss, complete, keep, reschedule, shown)."""

    serializer_class = OccurrenceSerializer
    throttle_scope: str | None = None  # set per action (test notifications are rate limited)

    def get_queryset(self):
        return ReminderOccurrence.objects.filter(owner=self.request.user).select_related("reminder").prefetch_related("deliveries")

    def get_serializer_context(self):
        return occurrence_context(self.request)

    def _list(self, qs):
        items = list(qs.prefetch_related("deliveries"))
        if not items:  # the common case for polled endpoints: skip loading preferences entirely
            return Response([])
        return Response(OccurrenceSerializer(items, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def active(self, request):
        maybe_run_inline()
        return self._list(selectors.active_alarms(request.user)[:20])

    @action(detail=False, methods=["get"])
    def missed(self, request):
        return self._list(selectors.missed(request.user)[:50])

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        hours = min(max(int(request.query_params.get("hours", 24) or 24), 1), 24 * 14)
        return self._list(selectors.upcoming(request.user, hours=hours)[:100])

    def _act(self, occ):
        occ = self.get_queryset().get(pk=occ.pk)
        return Response(OccurrenceSerializer(occ, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def snooze(self, request, pk=None):
        ser = SnoozeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        child = actions.snooze(self.get_object(), ser.validated_data.get("minutes"))
        return Response({"snoozed_until": child.fire_at.isoformat(), "next_occurrence": child.id})

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        return self._act(actions.dismiss(self.get_object()))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._act(actions.complete(self.get_object()))

    @action(detail=True, methods=["post"])
    def keep(self, request, pk=None):
        return self._act(actions.keep(self.get_object()))

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        ser = RescheduleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        child = actions.reschedule(self.get_object(), ser.validated_data["at"])
        return Response({"rescheduled_for": child.fire_at.isoformat(), "next_occurrence": child.id})

    @action(detail=True, methods=["post"])
    def shown(self, request, pk=None):
        ser = ShownSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return self._act(actions.mark_shown(self.get_object(), audio=ser.validated_data["audio"]))

    @action(detail=False, methods=["get"])
    def diagnostics(self, request):
        prefs = request.user.preferences
        zone = get_zone(prefs.time_zone)
        now = datetime.now(UTC)
        beat = None
        try:
            beat = cache.get(HEARTBEAT_KEY)
        except Exception:  # cache outage is itself a diagnostic result
            beat = None
        subs = DeviceSubscription.objects.filter(owner=request.user)
        last_push = NotificationDelivery.objects.filter(occurrence__owner=request.user, channel="push").order_by("-attempted_at").first()
        return Response(
            {
                "server_time": now.isoformat(),
                "time_zone": prefs.time_zone,
                "local_time": now.astimezone(zone).isoformat(),
                "push_configured": push.push_configured(),
                "subscriptions": {
                    "active": subs.filter(active=True).count(),
                    "inactive": subs.filter(active=False).count(),
                    # Which devices can receive alarms while DayWell is closed (labels like "Chrome on Android" only).
                    "devices": [
                        {"label": d.device_label or "Unnamed device", "last_success_at": d.last_success_at}
                        for d in subs.filter(active=True).order_by("-last_success_at", "-id")[:10]
                    ],
                },
                "scheduler": {
                    "heartbeat_at": beat,
                    "healthy": bool(beat) and (now - datetime.fromisoformat(beat)).total_seconds() < 180,
                    "lag_seconds": round(selectors.scheduler_lag_seconds(now)),
                },
                "quiet_hours_active": in_quiet_hours(prefs, now.astimezone(zone)),
                "last_push": DeliveryResultSerializer(last_push).data if last_push else None,
                "pending_reminders": ReminderOccurrence.objects.filter(owner=request.user, status=OccurrenceStatus.SCHEDULED).count(),
            }
        )

    @action(detail=False, methods=["post"], throttle_classes=[ScopedRateThrottle], throttle_scope="test_notify")
    def test(self, request):
        """Create a real test reminder occurrence and dispatch it through the normal pipeline (honest end-to-end check)."""
        ser = TestNotificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        delay = ser.validated_data["delay_seconds"]
        now = timezone.now()
        fire = now + timedelta(seconds=delay)
        local = fire.astimezone(get_zone(request.user.preferences.time_zone))
        with transaction.atomic():
            reminder = Reminder.objects.create(
                owner=request.user,
                title="Test alarm",
                message="This is a DayWell test. If you can see (and hear) this, alarms work here.",
                category="custom",
                kind=Reminder.Kind.ABSOLUTE,
                dtstart_date=local.date(),
                dtstart_time=local.time(),
                time_zone=request.user.preferences.time_zone,
                is_test=True,
                bypass_quiet_hours=True,
            )
            occ = ReminderOccurrence.objects.create(
                reminder=reminder,
                owner=request.user,
                category="custom",
                title=reminder.title,
                body=reminder.message,
                scheduled_for=fire,
                fire_at=fire,
                idempotency_key=f"test:{reminder.id}",
            )
        outcome = dispatch_now(occ) if delay == 0 else "scheduled"
        occ.refresh_from_db()
        return Response({"outcome": outcome, "occurrence": OccurrenceSerializer(occ, context=self.get_serializer_context()).data}, status=status.HTTP_201_CREATED)


class DeliveryResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDelivery
        fields = ["attempted_at", "result", "http_status", "error", "confirmed_at"]


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Notification centre: the history of reminder occurrences that reached (or should have reached) the user."""

    serializer_class = OccurrenceSerializer
    HIDDEN = [OccurrenceStatus.SCHEDULED, OccurrenceStatus.DISPATCHING, OccurrenceStatus.CANCELLED]

    def get_queryset(self):
        qs = (
            ReminderOccurrence.objects.filter(owner=self.request.user, fire_at__lte=timezone.now())
            .exclude(status__in=self.HIDDEN)
            .select_related("reminder")
            .prefetch_related(Prefetch("deliveries", queryset=NotificationDelivery.objects.order_by("attempted_at")))
            .order_by("-fire_at")
        )
        params = self.request.query_params
        if params.get("category"):
            qs = qs.filter(category__in=params["category"].split(","))
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        return qs

    def get_serializer_context(self):
        return occurrence_context(self.request)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        ReminderOccurrence.objects.filter(pk=self.get_object().pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        n = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": n})


class PushConfigView(APIView):
    def get(self, request):
        from django.conf import settings

        return Response({"configured": push.push_configured(), "public_key": settings.VAPID_PUBLIC_KEY if push.push_configured() else ""})


class PushSubscriptionView(APIView):
    def get(self, request):
        subs = DeviceSubscription.objects.filter(owner=request.user)
        return Response(
            [
                {
                    "id": s.id,
                    "device_label": s.device_label,
                    "user_agent": s.user_agent,
                    "active": s.active,
                    "created_at": s.created_at,
                    "last_success_at": s.last_success_at,
                    "last_failure_at": s.last_failure_at,
                }
                for s in subs
            ]
        )

    def post(self, request):
        ser = PushSubscribeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        sub = push.store_subscription(
            request.user, data["endpoint"], data["keys"]["p256dh"], data["keys"]["auth"], label=data.get("label", ""), user_agent=request.headers.get("User-Agent", "")
        )
        audit(AuditEvent.Kind.PUSH_SUBSCRIBED, request)
        return Response({"id": sub.id, "active": sub.active}, status=status.HTTP_201_CREATED)


class PushSubscriptionDetailView(APIView):
    def delete(self, request, pk: int):
        deleted, _ = DeviceSubscription.objects.filter(owner=request.user, pk=pk).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        audit(AuditEvent.Kind.PUSH_UNSUBSCRIBED, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PushUnsubscribeByEndpointView(APIView):
    """The browser forgets its subscription (permission revoked / user turned push off on this device)."""

    def post(self, request):
        from apps.core.crypto import sha256_hex

        endpoint = str(request.data.get("endpoint", ""))[:1000]
        DeviceSubscription.objects.filter(owner=request.user, endpoint_hash=sha256_hex(endpoint)).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PushReceiptView(APIView):
    """Called by the service worker after it displays a push notification. Authenticated by a signed per-delivery token
    (service workers cannot send the CSRF token), so it can only ever mark that single delivery as displayed."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "receipt"

    def post(self, request):
        parsed = push.read_receipt_token(str(request.data.get("receipt", ""))[:2000])
        if parsed is None:
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": actions.push_receipt(*parsed)})
