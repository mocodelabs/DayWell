from rest_framework import serializers

from apps.core.recurrence import RecurrenceError, normalize_rrule
from apps.core.timeutils import is_valid_timezone
from apps.core.viewsets import OwnedPrimaryKeyRelatedField
from apps.tasks.models import Category

from .models import Attendance, CalendarEvent


class EventSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    reminder_offsets = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=60 * 24 * 14), required=False, max_length=5)

    class Meta:
        model = CalendarEvent
        fields = [
            "id",
            "title",
            "description",
            "location",
            "meeting_url",
            "category",
            "all_day",
            "time_zone",
            "start_date",
            "start_time",
            "end_date",
            "end_time",
            "start",
            "end",
            "rrule",
            "series_end",
            "status",
            "attendance",
            "reminder_offsets",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "start", "end", "series_end", "created_at", "updated_at"]
        extra_kwargs = {"time_zone": {"required": False}, "end_date": {"required": False}}

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the event a title.")
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

    def validate(self, attrs):
        inst = self.instance
        all_day = attrs.get("all_day", getattr(inst, "all_day", False))
        start_date = attrs.get("start_date", getattr(inst, "start_date", None))
        attrs.setdefault("end_date", getattr(inst, "end_date", None) or start_date)
        if not all_day:
            if attrs.get("start_time", getattr(inst, "start_time", None)) is None:
                raise serializers.ValidationError({"start_time": ["Choose a start time, or mark the event as all-day."]})
            if attrs.get("end_time", getattr(inst, "end_time", None)) is None:
                raise serializers.ValidationError({"end_time": ["Choose an end time."]})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["reminder_offsets"] = sorted(r.offset_minutes for r in instance.reminders.all() if r.enabled) if instance.pk else []
        return data


class OccurrenceChangeSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=16)
    cancelled = serializers.BooleanField(required=False)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(max_length=300, required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    attendance = serializers.ChoiceField(choices=Attendance.choices, required=False, allow_blank=True)


class AttendanceSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=16, required=False)
    attendance = serializers.ChoiceField(choices=Attendance.choices, allow_blank=True)


class RangeSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    category = serializers.IntegerField(required=False)
    q = serializers.CharField(required=False, max_length=100)
