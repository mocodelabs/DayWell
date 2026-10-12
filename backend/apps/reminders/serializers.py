from rest_framework import serializers

from apps.core.recurrence import RecurrenceError, normalize_rrule
from apps.core.timeutils import is_valid_timezone
from apps.preferences.models import SOUNDS, NotificationCategory

from .models import NotificationDelivery, OccurrenceStatus, Reminder, ReminderOccurrence


class ReminderSerializer(serializers.ModelSerializer):
    next_fire_at = serializers.SerializerMethodField()
    linked = serializers.SerializerMethodField()

    class Meta:
        model = Reminder
        fields = [
            "id",
            "title",
            "message",
            "category",
            "kind",
            "priority",
            "dtstart_date",
            "dtstart_time",
            "rrule",
            "time_zone",
            "offset_minutes",
            "anchor",
            "task",
            "task_series",
            "event",
            "habit",
            "sound",
            "vibrate",
            "snooze_minutes",
            "bypass_quiet_hours",
            "repeat_until_ack",
            "repeat_every_minutes",
            "enabled",
            "next_fire_at",
            "linked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "kind", "offset_minutes", "anchor", "task", "task_series", "event", "habit", "created_at", "updated_at"]
        extra_kwargs = {"time_zone": {"required": False}}

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the reminder a title.")
        return value

    def validate_time_zone(self, value):
        if not is_valid_timezone(value):
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate_rrule(self, value):
        try:
            return normalize_rrule(value)
        except RecurrenceError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_sound(self, value):
        if value and value not in SOUNDS:
            raise serializers.ValidationError(f"Choose one of: {', '.join(SOUNDS)}.")
        return value

    def validate_snooze_minutes(self, value):
        if value is not None and not 1 <= value <= 240:
            raise serializers.ValidationError("Snooze must be between 1 and 240 minutes.")
        return value

    def validate_repeat_every_minutes(self, value):
        if not 1 <= value <= 60:
            raise serializers.ValidationError("Repeat every 1–60 minutes.")
        return value

    def validate_category(self, value):
        if value == NotificationCategory.BRIEFING:
            raise serializers.ValidationError("Daily briefings are configured in Settings → Daily briefing.")
        return value

    def validate(self, attrs):
        kind = self.instance.kind if self.instance else Reminder.Kind.ABSOLUTE
        if kind == Reminder.Kind.ABSOLUTE:
            date = attrs.get("dtstart_date", getattr(self.instance, "dtstart_date", None))
            time = attrs.get("dtstart_time", getattr(self.instance, "dtstart_time", None))
            if not date:
                raise serializers.ValidationError({"dtstart_date": ["Choose a date."]})
            if not time:
                raise serializers.ValidationError({"dtstart_time": ["Choose a time."]})
        return attrs

    def get_next_fire_at(self, obj):
        nxt = getattr(obj, "next_fire", None)
        return nxt.isoformat() if nxt else None

    def get_linked(self, obj):
        if obj.task_id:
            return {"type": "task", "id": obj.task_id}
        if obj.task_series_id:
            return {"type": "task_series", "id": obj.task_series_id}
        if obj.event_id:
            return {"type": "event", "id": obj.event_id}
        if obj.habit_id:
            return {"type": "habit", "id": obj.habit_id}
        return None


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDelivery
        fields = ["id", "channel", "kind", "attempted_at", "result", "error", "confirmed_at", "retry_count"]


class OccurrenceSerializer(serializers.ModelSerializer):
    deliveries = DeliverySerializer(many=True, read_only=True)
    reminder_title = serializers.CharField(source="reminder.title", read_only=True)
    sound = serializers.SerializerMethodField()
    snooze_minutes = serializers.SerializerMethodField()
    linked = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    can_complete = serializers.SerializerMethodField()

    class Meta:
        model = ReminderOccurrence
        fields = [
            "id",
            "reminder",
            "reminder_title",
            "last_error",
            "title",
            "body",
            "category",
            "status",
            "status_label",
            "skip_reason",
            "silent",
            "scheduled_for",
            "fire_at",
            "sent_at",
            "delivered_at",
            "audio_status",
            "audio_played_at",
            "acted_at",
            "dismissed_at",
            "completed_at",
            "snoozed_until",
            "read_at",
            "escalations",
            "snooze_count",
            "parent",
            "target_key",
            "task",
            "sound",
            "snooze_minutes",
            "linked",
            "can_complete",
            "deliveries",
        ]

    def _prefs(self):
        return self.context.get("prefs")

    def get_sound(self, obj):
        cat = (self.context.get("cat_prefs") or {}).get(obj.category)
        prefs = self._prefs()
        return obj.reminder.sound or (cat.sound if cat else "") or (prefs.default_sound if prefs else "chime")

    def get_snooze_minutes(self, obj):
        cat = (self.context.get("cat_prefs") or {}).get(obj.category)
        return obj.reminder.snooze_minutes or (cat.snooze_minutes if cat else 10)

    def get_linked(self, obj):
        key = obj.target_key or ""
        parts = key.split(":")
        if parts[0] == "task" and len(parts) > 1:
            return {"type": "task", "id": int(parts[1])}
        if parts[0] == "event" and len(parts) > 2:
            return {"type": "event", "id": int(parts[1]), "key": ":".join(parts[2:])}
        if parts[0] == "habit" and len(parts) > 1:
            return {"type": "habit", "id": int(parts[1])}
        return None

    def get_can_complete(self, obj) -> bool:
        return bool(obj.task_id or obj.reminder.habit_id) and obj.status not in (OccurrenceStatus.COMPLETED, OccurrenceStatus.CANCELLED)


class SnoozeSerializer(serializers.Serializer):
    minutes = serializers.IntegerField(min_value=1, max_value=1440, required=False)


class RescheduleSerializer(serializers.Serializer):
    at = serializers.DateTimeField()


class ShownSerializer(serializers.Serializer):
    audio = serializers.ChoiceField(choices=["played", "blocked", "muted", "unsupported", ""], required=False, default="")


class PushSubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
    keys = serializers.DictField(child=serializers.CharField(max_length=300))
    label = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_endpoint(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("Push endpoints must use HTTPS.")
        return value

    def validate_keys(self, value):
        if not value.get("p256dh") or not value.get("auth"):
            raise serializers.ValidationError("Subscription keys p256dh and auth are required.")
        return value


class TestNotificationSerializer(serializers.Serializer):
    delay_seconds = serializers.IntegerField(min_value=0, max_value=600, required=False, default=0)


DAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def days_to_rrule(days: list[int]) -> str:
    days = sorted(set(days))
    if not days or len(days) == 7:
        return "FREQ=DAILY"
    return "FREQ=WEEKLY;BYDAY=" + ",".join(DAY_CODES[d] for d in days)


def rrule_to_days(rule: str) -> list[int]:
    if "BYDAY=" not in rule:
        return list(range(7))
    codes = rule.split("BYDAY=")[1].split(";")[0].split(",")
    return [DAY_CODES.index(c) for c in codes if c in DAY_CODES]


class ModuleReminderSerializer(serializers.Serializer):
    """Simple "remind me at HH:MM on these days" config used by optional modules."""

    enabled = serializers.BooleanField()
    time = serializers.TimeField(required=False, allow_null=True)
    days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False, max_length=7)

    def validate(self, attrs):
        if attrs["enabled"] and not attrs.get("time"):
            raise serializers.ValidationError({"time": ["Choose a time for the reminder."]})
        return attrs


def module_reminder_payload(state: dict) -> dict:
    return {"enabled": state["enabled"], "time": state["time"], "days": rrule_to_days(state["rrule"]) if state["rrule"] else list(range(7))}
