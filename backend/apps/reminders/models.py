"""Reminder & alarm engine data model.

* ``Reminder`` — the definition. Either *absolute* (local start + optional RRULE in an IANA zone) or *relative*
  (N minutes before a task's start/deadline, a task series' instances, or an event's occurrences).
* ``ReminderOccurrence`` — one concrete firing, materialised for a rolling horizon. ``idempotency_key`` is UNIQUE,
  so retries, concurrent syncs and reconnects can never create duplicates. Snoozes are child occurrences.
* ``NotificationDelivery`` — one attempt on one channel. ``result`` only becomes ``delivered`` with client evidence
  (the app or service worker confirmed it displayed the notification); a push service accepting a message is
  recorded as ``accepted``, never as delivered.
* ``DeviceSubscription`` — a Web Push subscription; endpoint and keys are encrypted at rest.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OwnedModel
from apps.events.models import CalendarEvent
from apps.habits.models import Habit
from apps.preferences.models import NotificationCategory
from apps.tasks.models import Task, TaskSeries


class Reminder(OwnedModel):
    class Kind(models.TextChoices):
        ABSOLUTE = "absolute", "At a set time"
        RELATIVE = "relative", "Before a task or event"

    class Anchor(models.TextChoices):
        START = "start", "Start"
        DEADLINE = "deadline", "Deadline"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    title = models.CharField(max_length=200)
    message = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=16, choices=NotificationCategory.choices, default=NotificationCategory.CUSTOM)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.ABSOLUTE)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    # Absolute schedule (local wall time in time_zone)
    dtstart_date = models.DateField(null=True, blank=True)
    dtstart_time = models.TimeField(null=True, blank=True)
    rrule = models.CharField(max_length=300, blank=True)
    time_zone = models.CharField(max_length=64)
    # Relative schedule
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    task_series = models.ForeignKey(TaskSeries, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    event = models.ForeignKey(CalendarEvent, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    offset_minutes = models.PositiveIntegerField(default=0)
    anchor = models.CharField(max_length=8, choices=Anchor.choices, default=Anchor.START)
    # Linked habit (absolute schedule; skipped automatically once the habit is done for the day)
    habit = models.ForeignKey(Habit, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    # Behaviour
    sound = models.CharField(max_length=20, blank=True)  # blank → category / user default
    vibrate = models.BooleanField(default=True)
    snooze_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    bypass_quiet_hours = models.BooleanField(default=False)  # explicit per-reminder opt-in
    repeat_until_ack = models.BooleanField(default=False)  # escalation: re-alert if not acted on
    repeat_every_minutes = models.PositiveSmallIntegerField(default=5)
    enabled = models.BooleanField(default=True)
    is_test = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)  # deleted by the user but kept for notification history
    # Module-owned reminders (e.g. "affirmation", "reading", "routine:7", "winddown", "briefing:morning"); one per owner+key.
    system_key = models.CharField(max_length=40, blank=True)
    generated_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["enabled", "generated_until"]),
            models.Index(fields=["owner", "category"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["owner", "system_key"], condition=~models.Q(system_key=""), name="reminder_owner_system_key_unique"),
        ]

    def __str__(self) -> str:
        return self.title


class OccurrenceStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    DISPATCHING = "dispatching", "Dispatching"
    SENT = "sent", "Sent"  # at least one channel accepted it; awaiting the user
    SNOOZED = "snoozed", "Snoozed"
    DISMISSED = "dismissed", "Dismissed"
    COMPLETED = "completed", "Completed"
    ACKNOWLEDGED = "acknowledged", "Kept for later"
    RESCHEDULED = "rescheduled", "Rescheduled"
    MISSED = "missed", "Missed"  # its time passed while it could not be delivered (e.g. downtime)
    SKIPPED = "skipped", "Skipped"  # intentionally not sent (module/category off, item already done, limits)
    FAILED = "failed", "Failed"  # every channel failed after bounded retries
    CANCELLED = "cancelled", "Cancelled"  # superseded by an edit / reschedule / deletion


PENDING_STATUSES = (OccurrenceStatus.SCHEDULED, OccurrenceStatus.DISPATCHING)
FINAL_ACTION_STATUSES = (
    OccurrenceStatus.SNOOZED,
    OccurrenceStatus.DISMISSED,
    OccurrenceStatus.COMPLETED,
    OccurrenceStatus.ACKNOWLEDGED,
    OccurrenceStatus.RESCHEDULED,
)


class ReminderOccurrence(models.Model):
    reminder = models.ForeignKey(Reminder, on_delete=models.CASCADE, related_name="occurrences")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    category = models.CharField(max_length=16, choices=NotificationCategory.choices)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    scheduled_for = models.DateTimeField()  # the originally planned instant
    fire_at = models.DateTimeField()  # when the dispatcher should act (moved by quiet-hour delays)
    target_key = models.CharField(max_length=64, blank=True)  # e.g. "task:12", "event:5:2026-10-09T09:00"
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=OccurrenceStatus.choices, default=OccurrenceStatus.SCHEDULED)
    skip_reason = models.CharField(max_length=40, blank=True)
    silent = models.BooleanField(default=False)  # delivered without sound/push (quiet hours "silent" behaviour)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)  # first client-confirmed display
    audio_played_at = models.DateTimeField(null=True, blank=True)  # only set when the app confirms playback succeeded
    audio_status = models.CharField(max_length=12, blank=True)  # played | blocked | muted | unsupported
    acted_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    escalations = models.PositiveSmallIntegerField(default=0)
    last_alerted_at = models.DateTimeField(null=True, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    snooze_count = models.PositiveSmallIntegerField(default=0)
    idempotency_key = models.CharField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fire_at"]
        indexes = [
            models.Index(fields=["status", "fire_at"]),
            models.Index(fields=["owner", "status", "fire_at"]),
            models.Index(fields=["owner", "-fire_at"]),
            models.Index(fields=["reminder", "status", "scheduled_for"]),
        ]


class DeviceSubscription(OwnedModel):
    endpoint_hash = models.CharField(max_length=64, unique=True)  # sha256(endpoint) — dedupe without decrypting
    endpoint_encrypted = models.TextField()
    keys_encrypted = models.TextField()  # Fernet(JSON{p256dh, auth})
    device_label = models.CharField(max_length=120, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class NotificationDelivery(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        PUSH = "push", "Web Push"

    class Result(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"  # handed to the channel (push service 201 / available in app)
        DELIVERED = "delivered", "Delivered"  # client confirmed it was displayed
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Subscription expired"

    class Kind(models.TextChoices):
        INITIAL = "initial"
        RETRY = "retry"
        ESCALATION = "escalation"
        TEST = "test"

    occurrence = models.ForeignKey(ReminderOccurrence, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=8, choices=Channel.choices)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.INITIAL)
    subscription = models.ForeignKey(DeviceSubscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries")
    attempted_at = models.DateTimeField()
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING)
    transient = models.BooleanField(default=False)  # failure that may succeed on retry
    retry_count = models.PositiveSmallIntegerField(default=0)
    retry_at = models.DateTimeField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    provider_ref = models.CharField(max_length=300, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["attempted_at"]
        indexes = [models.Index(fields=["result", "retry_at"])]
