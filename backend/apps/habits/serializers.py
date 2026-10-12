from rest_framework import serializers

from apps.core.recurrence import RecurrenceError, normalize_rrule
from apps.core.timeutils import is_valid_timezone

from .models import CompletionStatus, Habit, HabitCompletion, TargetType


class HabitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = [
            "id",
            "name",
            "description",
            "category",
            "icon",
            "color",
            "target_type",
            "target_value",
            "unit",
            "schedule_rule",
            "times_per_week",
            "start_date",
            "time_zone",
            "reminder_time",
            "status",
            "paused_at",
            "streaks_enabled",
            "position",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "paused_at", "created_at", "updated_at"]
        extra_kwargs = {"time_zone": {"required": False}, "start_date": {"required": False}}

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the habit a name.")
        return value

    def validate_schedule_rule(self, value):
        try:
            rule = normalize_rrule(value)
        except RecurrenceError as exc:
            raise serializers.ValidationError(str(exc))
        if not rule:
            raise serializers.ValidationError("Choose how often this habit happens.")
        if rule.split(";")[0] == "FREQ=HOURLY":
            raise serializers.ValidationError("Habits are tracked per day. Use a count target for several times a day.")
        return rule

    def validate_time_zone(self, value):
        if not is_valid_timezone(value):
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate_times_per_week(self, value):
        if value is not None and not 1 <= value <= 7:
            raise serializers.ValidationError("Choose 1–7 times per week.")
        return value

    def validate(self, attrs):
        ttype = attrs.get("target_type", getattr(self.instance, "target_type", TargetType.BINARY))
        target = attrs.get("target_value", getattr(self.instance, "target_value", 1))
        if ttype == TargetType.BINARY:
            attrs["target_value"] = 1
        elif target is None or target <= 0:
            raise serializers.ValidationError({"target_value": ["Set a target greater than zero."]})
        if ttype == TargetType.DURATION and not attrs.get("unit", getattr(self.instance, "unit", "")):
            attrs["unit"] = "min"
        return attrs


class CompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HabitCompletion
        fields = ["id", "habit", "date", "status", "value", "notes", "completed_at"]
        read_only_fields = fields


class CompleteSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    value = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, min_value=0)
    status = serializers.ChoiceField(choices=CompletionStatus.choices, required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class IncrementSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    amount = serializers.DecimalField(max_digits=8, decimal_places=2, default=1)


class DateSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class RangeSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["end"] < attrs["start"] or (attrs["end"] - attrs["start"]).days > 400:
            raise serializers.ValidationError("Choose a range of up to 400 days.")
        return attrs
