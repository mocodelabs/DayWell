"""Reminder engine: sync idempotency, dispatch rules, snooze/dismiss/complete, quiet hours, missed recovery, retries.

The clock is controlled: ``dispatch_due(now=...)`` / ``sync_reminder(now=...)`` and time_machine — no real waiting.
"""

from datetime import UTC, date, datetime, time, timedelta
from unittest import mock

import pytest
import time_machine

from apps.core.exceptions import BusinessRuleError
from apps.reminders import actions
from apps.reminders.dispatch import dispatch_due
from apps.reminders.models import NotificationDelivery, OccurrenceStatus, Reminder, ReminderOccurrence
from apps.reminders.push import PushResult, store_subscription
from apps.reminders.services import set_item_reminders, sync_reminder
from apps.tasks import services as task_services

T0 = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)  # 08:00 in Nairobi


def absolute(user, *, at=time(9, 0), rule="FREQ=DAILY", category="custom", day=date(2026, 10, 9), **kw):
    return Reminder.objects.create(owner=user, title="Stretch", category=category, kind="absolute", dtstart_date=day, dtstart_time=at, rrule=rule, time_zone="Africa/Nairobi", **kw)


pytestmark = pytest.mark.django_db


class TestSync:
    def test_materialises_horizon_in_local_time(self, user, settings):
        settings.REMINDER_HORIZON_DAYS = 7
        r = absolute(user)
        result = sync_reminder(r, now=T0)
        occs = list(ReminderOccurrence.objects.filter(reminder=r).order_by("fire_at"))
        assert result["created"] == 7 == len(occs)
        assert occs[0].fire_at == datetime(2026, 10, 9, 6, 0, tzinfo=UTC)  # 09:00 EAT

    def test_sync_is_idempotent(self, user):
        r = absolute(user)
        sync_reminder(r, now=T0)
        n = ReminderOccurrence.objects.count()
        again = sync_reminder(r, now=T0)
        assert again == {"created": 0, "cancelled": 0, "revived": 0}
        assert ReminderOccurrence.objects.count() == n

    def test_reschedule_cancels_obsolete_and_keeps_history(self, user):
        r = absolute(user, rule="")
        sync_reminder(r, now=T0)
        old = ReminderOccurrence.objects.get(reminder=r)
        r.dtstart_time = time(10, 0)
        r.save()
        sync_reminder(r, now=T0)
        old.refresh_from_db()
        assert old.status == OccurrenceStatus.CANCELLED
        assert ReminderOccurrence.objects.filter(reminder=r, status="scheduled").get().fire_at.hour == 7

    def test_moving_back_revives_instead_of_duplicating(self, user):
        r = absolute(user, rule="")
        sync_reminder(r, now=T0)
        r.dtstart_time = time(10, 0)
        r.save()
        sync_reminder(r, now=T0)
        r.dtstart_time = time(9, 0)
        r.save()
        res = sync_reminder(r, now=T0)
        assert res["revived"] == 1
        assert ReminderOccurrence.objects.filter(reminder=r, status="scheduled").count() == 1

    def test_disabled_reminder_has_no_future_occurrences(self, user):
        r = absolute(user)
        sync_reminder(r, now=T0)
        r.enabled = False
        r.save()
        sync_reminder(r, now=T0)
        assert not ReminderOccurrence.objects.filter(reminder=r, status="scheduled").exists()

    def test_task_reminder_follows_postpone(self, user):
        with time_machine.travel(T0, tick=False):
            task = task_services.create_task(user, {"title": "Call the supplier", "scheduled_date": date(2026, 10, 10), "scheduled_time": time(10, 0)})
            set_item_reminders(user, [{"offset_minutes": 15, "anchor": "start"}], task=task)
            occ = ReminderOccurrence.objects.get(task=task)
            assert occ.fire_at == datetime(2026, 10, 10, 6, 45, tzinfo=UTC)  # 09:45 EAT
            task_services.postpone(task, to_date=date(2026, 10, 12))
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.CANCELLED
        assert ReminderOccurrence.objects.get(task=task, status="scheduled").fire_at == datetime(2026, 10, 12, 6, 45, tzinfo=UTC)


class TestDispatch:
    def _due(self, user, **kw):
        r = absolute(user, rule="", **kw)
        sync_reminder(r, now=T0)
        return r, ReminderOccurrence.objects.get(reminder=r)

    def test_due_occurrence_is_sent_in_app(self, user):
        _, occ = self._due(user)
        assert dispatch_due(now=occ.fire_at - timedelta(seconds=1)).get("sent") is None
        stats = dispatch_due(now=occ.fire_at + timedelta(seconds=5))
        occ.refresh_from_db()
        assert stats["sent"] == 1 and occ.status == OccurrenceStatus.SENT
        delivery = occ.deliveries.get()
        assert delivery.channel == "in_app" and delivery.result == NotificationDelivery.Result.ACCEPTED
        assert occ.delivered_at is None  # not delivered until the app confirms display
        assert occ.audio_played_at is None  # never claim audio played

    def test_dispatch_twice_never_duplicates(self, user):
        _, occ = self._due(user)
        dispatch_due(now=occ.fire_at)
        dispatch_due(now=occ.fire_at + timedelta(seconds=30))
        assert occ.deliveries.count() == 1

    def test_stale_occurrence_becomes_missed_not_pushed(self, user, settings):
        _, occ = self._due(user)
        dispatch_due(now=occ.fire_at + settings.REMINDER_STALE_AFTER + timedelta(minutes=1))
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.MISSED and occ.deliveries.count() == 0

    def test_disabled_module_never_fires(self, user):
        user.preferences.modules = {**user.preferences.modules, "fitness": False}
        user.preferences.save()
        _, occ = self._due(user, category="fitness")
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SKIPPED and occ.skip_reason == "module_disabled"

    def test_category_switched_off(self, user):
        user.notification_preferences.filter(category="custom").update(enabled=False)
        _, occ = self._due(user)
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.skip_reason == "category_disabled"

    def test_completed_task_reminder_is_skipped(self, user):
        with time_machine.travel(T0, tick=False):
            task = task_services.create_task(user, {"title": "Report", "scheduled_date": date(2026, 10, 9), "scheduled_time": time(11, 0)})
            set_item_reminders(user, [{"offset_minutes": 30, "anchor": "start"}], task=task)
            occ = ReminderOccurrence.objects.get(task=task)
            task_services.complete(task)
        occ.refresh_from_db()
        # Completion triggers a resync; the pending occurrence is no longer desired and is cancelled.
        assert occ.status in (OccurrenceStatus.CANCELLED, OccurrenceStatus.SKIPPED)

    def test_quiet_hours_delay(self, user):
        p = user.preferences
        p.quiet_enabled, p.quiet_start, p.quiet_end, p.quiet_behavior = True, time(22, 0), time(7, 0), "delay"
        p.save()
        r = absolute(user, rule="", at=time(23, 0))
        sync_reminder(r, now=T0)
        occ = ReminderOccurrence.objects.get(reminder=r)
        assert dispatch_due(now=occ.fire_at)["delayed"] == 1
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SCHEDULED
        assert occ.fire_at == datetime(2026, 10, 10, 4, 0, tzinfo=UTC)  # 07:00 EAT next morning
        assert occ.scheduled_for == datetime(2026, 10, 9, 20, 0, tzinfo=UTC)  # original preserved
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SENT

    def test_quiet_hours_silent_and_explicit_bypass(self, user):
        p = user.preferences
        p.quiet_enabled, p.quiet_start, p.quiet_end, p.quiet_behavior = True, time(22, 0), time(7, 0), "silent"
        p.save()
        _, occ = self._due(user, at=time(23, 0))
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SENT and occ.silent
        _, critical = self._due(user, at=time(23, 30), bypass_quiet_hours=True)
        dispatch_due(now=critical.fire_at)
        critical.refresh_from_db()
        assert not critical.silent

    def test_frequency_cap(self, user):
        user.notification_preferences.filter(category="hydration").update(min_gap_minutes=120)
        user.preferences.modules = {**user.preferences.modules, "hydration": True}
        user.preferences.save()
        _, first = self._due(user, category="hydration", at=time(9, 0))
        _, second = self._due(user, category="hydration", at=time(10, 0))
        dispatch_due(now=first.fire_at)
        dispatch_due(now=second.fire_at)
        second.refresh_from_db()
        assert second.skip_reason == "frequency_limit"

    def test_concurrent_claims_do_not_overlap(self, user):
        from apps.reminders.dispatch import claim_batch

        _, occ = self._due(user)
        first = claim_batch(occ.fire_at, 10)
        second = claim_batch(occ.fire_at, 10)
        assert first == [occ.id] and second == []

    def test_stuck_dispatch_is_recovered(self, user):
        _, occ = self._due(user)
        ReminderOccurrence.objects.filter(pk=occ.pk).update(status="dispatching", claimed_at=occ.fire_at)
        dispatch_due(now=occ.fire_at + timedelta(minutes=6))
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SENT


class TestActions:
    def _sent(self, user):
        r = absolute(user, rule="")
        sync_reminder(r, now=T0)
        occ = ReminderOccurrence.objects.get(reminder=r)
        dispatch_due(now=occ.fire_at)
        occ.refresh_from_db()
        return occ

    def test_snooze_creates_one_child_and_keeps_history(self, user):
        occ = self._sent(user)
        with time_machine.travel(occ.fire_at, tick=False):
            child = actions.snooze(occ, 10)
            again = actions.snooze(occ, 10)  # double-tap
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.SNOOZED and occ.snoozed_until == occ.fire_at + timedelta(minutes=10)
        assert child.id == again.id and child.parent_id == occ.id
        assert ReminderOccurrence.objects.filter(parent=occ, status="scheduled").count() == 1
        dispatch_due(now=child.fire_at)
        child.refresh_from_db()
        assert child.status == OccurrenceStatus.SENT

    def test_dismiss_does_not_complete_task(self, user):
        with time_machine.travel(T0, tick=False):
            task = task_services.create_task(user, {"title": "Pay rent", "scheduled_date": date(2026, 10, 9), "scheduled_time": time(9, 0)})
            set_item_reminders(user, [{"offset_minutes": 0, "anchor": "start"}], task=task)
        occ = ReminderOccurrence.objects.get(task=task)
        dispatch_due(now=occ.fire_at)
        actions.dismiss(occ)
        task.refresh_from_db()
        occ.refresh_from_db()
        assert occ.status == OccurrenceStatus.DISMISSED and occ.dismissed_at
        assert task.status == "pending"

    def test_complete_completes_linked_task(self, user):
        with time_machine.travel(T0, tick=False):
            task = task_services.create_task(user, {"title": "Pay rent", "scheduled_date": date(2026, 10, 9), "scheduled_time": time(9, 0)})
            set_item_reminders(user, [{"offset_minutes": 0, "anchor": "start"}], task=task)
        occ = ReminderOccurrence.objects.get(task=task)
        dispatch_due(now=occ.fire_at)
        actions.complete(occ)
        task.refresh_from_db()
        assert task.status == "completed"

    def test_handled_alarm_cannot_be_acted_on_twice(self, user):
        occ = self._sent(user)
        actions.dismiss(occ)
        with pytest.raises(BusinessRuleError):
            actions.snooze(occ, 5)

    def test_shown_records_audio_honestly(self, user):
        occ = self._sent(user)
        actions.mark_shown(occ, audio="blocked")
        occ.refresh_from_db()
        assert occ.delivered_at and occ.audio_status == "blocked" and occ.audio_played_at is None
        actions.mark_shown(occ, audio="played")
        occ.refresh_from_db()
        assert occ.audio_played_at is not None
        assert occ.deliveries.get(channel="in_app").result == "delivered"


class TestPush:
    def _setup(self, user, settings):
        settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "pub", "priv"
        sub = store_subscription(user, "https://push.example.com/abc", "p256", "authkey")
        r = absolute(user, rule="")
        sync_reminder(r, now=T0)
        return sub, ReminderOccurrence.objects.get(reminder=r)

    def test_accepted_push_is_not_delivered_until_receipt(self, user, settings):
        _sub, occ = self._setup(user, settings)
        with mock.patch("apps.reminders.push.send", return_value=PushResult(ok=True, status=201)):
            dispatch_due(now=occ.fire_at)
        push_delivery = occ.deliveries.get(channel="push")
        assert push_delivery.result == "accepted"
        from apps.reminders.push import read_receipt_token, receipt_token

        assert actions.push_receipt(*read_receipt_token(receipt_token(occ.id, push_delivery.id)))
        push_delivery.refresh_from_db()
        assert push_delivery.result == "delivered"

    def test_transient_failure_is_retried_with_backoff(self, user, settings):
        _sub, occ = self._setup(user, settings)
        with mock.patch("apps.reminders.push.send", return_value=PushResult(ok=False, status=503, transient=True, error="503")):
            dispatch_due(now=occ.fire_at)
        d = occ.deliveries.get(channel="push")
        assert d.result == "failed" and d.retry_at == occ.fire_at + timedelta(seconds=30)
        with mock.patch("apps.reminders.push.send", return_value=PushResult(ok=True, status=201)) as sent:
            dispatch_due(now=occ.fire_at + timedelta(seconds=31))
        d.refresh_from_db()
        assert sent.call_count == 1 and d.result == "accepted" and d.retry_count == 1

    def test_expired_subscription_is_deactivated(self, user, settings):
        sub, occ = self._setup(user, settings)
        with mock.patch("apps.reminders.push.send", return_value=PushResult(ok=False, status=410, expired=True)):
            dispatch_due(now=occ.fire_at)
        sub.refresh_from_db()
        assert not sub.active and occ.deliveries.get(channel="push").result == "expired"

    def test_subscription_keys_are_encrypted(self, user, settings):
        sub, _ = self._setup(user, settings)
        assert "push.example.com" not in sub.endpoint_encrypted and "authkey" not in sub.keys_encrypted


class TestSnoozeAudioRegression:
    """Regression: snoozing must schedule exactly one repeat, keep history and never invent audio playback."""

    def test_blocked_audio_then_snooze_chain(self, user):
        r = absolute(user, rule="")
        sync_reminder(r, now=T0)
        occ = ReminderOccurrence.objects.get(reminder=r)
        dispatch_due(now=occ.fire_at)
        actions.mark_shown(occ, audio="blocked")
        with time_machine.travel(occ.fire_at, tick=False):
            child = actions.snooze(occ, 5)
        occ.refresh_from_db()
        assert occ.status == "snoozed" and occ.audio_status == "blocked" and occ.audio_played_at is None
        assert child.audio_status == "" and child.audio_played_at is None and child.delivered_at is None
        # The repeat fires, is shown silently-blocked again, and is snoozed again: still one pending repeat in total.
        dispatch_due(now=child.fire_at)
        child.refresh_from_db()
        actions.mark_shown(child, audio="blocked")
        with time_machine.travel(child.fire_at, tick=False):
            grandchild = actions.snooze(child, 5)
        pending = ReminderOccurrence.objects.filter(reminder=r, status="scheduled")
        assert list(pending) == [grandchild]
        assert ReminderOccurrence.objects.filter(reminder=r, audio_played_at__isnull=False).count() == 0
        assert [o.status for o in ReminderOccurrence.objects.filter(reminder=r).order_by("id")] == ["snoozed", "snoozed", "scheduled"]
        assert grandchild.snooze_count == 2 and grandchild.parent_id == child.id


class TestDiagnosticsDevices:
    def test_lists_which_devices_get_alarms_while_closed(self, api, user):
        store_subscription(user, "https://push.example/a", "p", "a", label="Chrome on Windows")
        body = api.get("/api/v1/alarms/diagnostics/").json()
        assert body["subscriptions"]["active"] == 1
        assert [d["label"] for d in body["subscriptions"]["devices"]] == ["Chrome on Windows"]


class TestPushClientReport:
    def test_device_failure_is_logged_without_personal_data(self, api, user, caplog):
        res = api.post("/api/v1/push/client-report/", {"stage": "subscribe", "error_name": "AbortError", "message": "Registration failed - push service error"}, HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 10; K)")
        assert res.status_code == 204
        rec = next(r for r in caplog.records if r.getMessage() == "push enable failed on device")
        assert (rec.platform, rec.stage, rec.error_name) == ("android", "subscribe", "AbortError")

    def test_rejects_unknown_stage(self, api):
        assert api.post("/api/v1/push/client-report/", {"stage": "whatever"}).status_code == 400
