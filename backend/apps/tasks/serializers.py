from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.core.recurrence import RecurrenceError, normalize_rrule
from apps.core.timeutils import get_zone, is_valid_timezone, local_today
from apps.core.viewsets import OwnedPrimaryKeyRelatedField

from .models import OPEN_STATUSES, PALETTE, Category, Task, TaskSubtask


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "color", "icon", "archived"]

    def validate_color(self, value):
        if value not in PALETTE:
            raise serializers.ValidationError(f"Choose one of: {', '.join(PALETTE)}.")
        return value

    def validate_name(self, value):
        value = value.strip()
        request = self.context["request"]
        qs = Category.objects.filter(owner=request.user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("You already have a category with this name.")
        return value


class SubtaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubtask
        fields = ["id", "title", "position", "done", "done_at"]
        read_only_fields = ["id", "done_at"]

    def update(self, instance, validated_data):
        if "done" in validated_data and validated_data["done"] != instance.done:
            instance.done_at = timezone.now() if validated_data["done"] else None
        return super().update(instance, validated_data)


class ReminderOffsetSerializer(serializers.Serializer):
    offset_minutes = serializers.IntegerField(min_value=0, max_value=60 * 24 * 14)
    anchor = serializers.ChoiceField(choices=["start", "deadline"], default="start")


def validate_tags(value):
    if not isinstance(value, list) or len(value) > 12:
        raise serializers.ValidationError("Use up to 12 tags.")
    cleaned = []
    for tag in value:
        if not isinstance(tag, str) or not tag.strip() or len(tag) > 30:
            raise serializers.ValidationError("Each tag must be 1–30 characters.")
        if tag.strip().lower() not in [t.lower() for t in cleaned]:
            cleaned.append(tag.strip())
    return cleaned


class TaskSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    subtasks = SubtaskSerializer(many=True, read_only=True)
    checklist = serializers.ListField(child=serializers.CharField(max_length=200), write_only=True, required=False, max_length=50)
    recurrence = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=300)
    reminders = ReminderOffsetSerializer(many=True, required=False)
    series_rule = serializers.CharField(source="series.rrule", read_only=True, default=None)
    is_overdue = serializers.SerializerMethodField()
    quadrant = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "notes",
            "priority",
            "important",
            "status",
            "category",
            "tags",
            "scheduled_date",
            "scheduled_time",
            "scheduled_at",
            "time_zone",
            "duration_minutes",
            "deadline",
            "link_url",
            "completed_at",
            "postponed_count",
            "series",
            "series_rule",
            "occurrence_date",
            "detached",
            "subtasks",
            "checklist",
            "recurrence",
            "reminders",
            "is_overdue",
            "quadrant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "scheduled_at",
            "completed_at",
            "postponed_count",
            "series",
            "occurrence_date",
            "detached",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"time_zone": {"required": False}}

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the task a title.")
        return value

    def validate_tags(self, value):
        return validate_tags(value)

    def validate_time_zone(self, value):
        if not is_valid_timezone(value):
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate_recurrence(self, value):
        try:
            return normalize_rrule(value)
        except RecurrenceError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, attrs):
        date = attrs.get("scheduled_date", getattr(self.instance, "scheduled_date", None))
        at = attrs.get("scheduled_time", getattr(self.instance, "scheduled_time", None))
        if at is not None and date is None:
            raise serializers.ValidationError({"scheduled_time": ["Pick a date for this time."]})
        if self.instance is not None and attrs.get("recurrence"):
            raise serializers.ValidationError({"recurrence": ["Repeat rules are set when the task is created. Edit the series instead."]})
        for reminder in attrs.get("reminders", []):
            if reminder["anchor"] == "start" and (at is None or date is None):
                raise serializers.ValidationError({"reminders": ["A reminder before the start needs a scheduled date and time."]})
            if reminder["anchor"] == "deadline" and not attrs.get("deadline", getattr(self.instance, "deadline", None)):
                raise serializers.ValidationError({"reminders": ["A reminder before the deadline needs a deadline."]})
        return attrs

    def get_is_overdue(self, obj: Task) -> bool:
        if obj.status not in OPEN_STATUSES:
            return False
        now = timezone.now()
        if obj.deadline and obj.deadline < now:
            return True
        if obj.scheduled_date:
            return obj.scheduled_date < local_today(get_zone(obj.time_zone), now)
        return False

    def get_quadrant(self, obj: Task) -> str:
        """Eisenhower quadrant: urgent = priority 'urgent' or a deadline within 48 hours; important = flag or high/urgent priority."""
        urgent = obj.priority == "urgent" or bool(obj.deadline and obj.deadline - timezone.now() < timedelta(hours=48))
        important = obj.important or obj.priority in ("high", "urgent")
        return {(True, True): "do", (False, True): "schedule", (True, False): "delegate", (False, False): "later"}[(urgent, important)]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        linked = list(instance.reminders.all()) if instance.pk else []
        if instance.pk and instance.series_id:
            linked += list(instance.series.reminders.all())
        data["reminders"] = [{"id": r.id, "offset_minutes": r.offset_minutes, "anchor": r.anchor, "series": r.task_series_id is not None} for r in linked if r.enabled]
        return data


class PostponeSerializer(serializers.Serializer):
    to_date = serializers.DateField(required=False)
    to_time = serializers.TimeField(required=False, allow_null=True)
    preset = serializers.ChoiceField(choices=["tomorrow", "next_week", "weekend"], required=False)

    def validate(self, attrs):
        if not attrs.get("to_date") and not attrs.get("preset"):
            raise serializers.ValidationError({"to_date": ["Choose a new date."]})
        return attrs
