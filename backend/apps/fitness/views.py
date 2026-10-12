from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.modules import require_module
from apps.core.timeutils import get_zone, local_today
from apps.core.viewsets import OwnedModelViewSet, OwnedPrimaryKeyRelatedField
from apps.reminders.models import Reminder

from . import services
from .models import WorkoutRoutine, WorkoutSession


class RoutineSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutRoutine
        fields = ["id", "name", "workout_type", "days", "time", "duration_minutes", "location", "prep_buffer_minutes", "reminder_enabled", "notes", "active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_days(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or not 0 <= d <= 6 for d in value):
            raise serializers.ValidationError("Days must be numbers 0 (Monday) to 6 (Sunday).")
        return sorted(set(value))

    def validate(self, attrs):
        if attrs.get("reminder_enabled", getattr(self.instance, "reminder_enabled", False)) and not attrs.get("time", getattr(self.instance, "time", None)):
            raise serializers.ValidationError({"time": ["Set a workout time to get reminders."]})
        return attrs


class ExerciseSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    sets = serializers.IntegerField(min_value=0, max_value=100, required=False, allow_null=True)
    reps = serializers.IntegerField(min_value=0, max_value=1000, required=False, allow_null=True)
    weight = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True, coerce_to_string=False)
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True)


class SessionSerializer(serializers.ModelSerializer):
    routine = OwnedPrimaryKeyRelatedField(queryset=WorkoutRoutine.objects.all(), allow_null=True, required=False)
    routine_name = serializers.CharField(source="routine.name", read_only=True, default=None)
    exercises = ExerciseSerializer(many=True, required=False)

    class Meta:
        model = WorkoutSession
        fields = [
            "id",
            "routine",
            "routine_name",
            "date",
            "started_at",
            "ended_at",
            "workout_type",
            "planned_minutes",
            "duration_minutes",
            "status",
            "distance",
            "distance_unit",
            "exercises",
            "effort",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_date(self, value):
        if value > local_today(get_zone(self.context["request"].user.preferences.time_zone)):
            raise serializers.ValidationError("You can't log a workout for a future day.")
        return value

    def validate_effort(self, value):
        if value is not None and not 1 <= value <= 10:
            raise serializers.ValidationError("Effort is 1–10.")
        return value

    def validate_duration_minutes(self, value):
        if value > 24 * 60:
            raise serializers.ValidationError("That's longer than a day.")
        return value

    def validate(self, attrs):
        s, e = attrs.get("started_at"), attrs.get("ended_at")
        if s and e:
            if e <= s:
                raise serializers.ValidationError({"ended_at": ["End must be after the start."]})
            if not attrs.get("duration_minutes"):
                attrs["duration_minutes"] = round((e - s).total_seconds() / 60)
        routine = attrs.get("routine")
        if routine and not attrs.get("planned_minutes"):
            attrs["planned_minutes"] = routine.duration_minutes
        if routine and not attrs.get("workout_type"):
            attrs["workout_type"] = routine.workout_type
        attrs["exercises"] = [dict(x) for x in attrs.get("exercises", [])]
        return attrs


class RoutineViewSet(OwnedModelViewSet):
    serializer_class = RoutineSerializer

    def get_queryset(self):
        return WorkoutRoutine.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        require_module(self.request.user, "fitness")
        with transaction.atomic():
            services.sync_routine_reminder(serializer.save(owner=self.request.user))

    def perform_update(self, serializer):
        with transaction.atomic():
            services.sync_routine_reminder(serializer.save())

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.reminder_enabled = False
            services.sync_routine_reminder(instance)
            Reminder.objects.filter(owner=instance.owner, system_key=f"routine:{instance.id}").update(system_key="", archived=True)
            instance.delete()


class SessionViewSet(OwnedModelViewSet):
    serializer_class = SessionSerializer
    filterset_fields = ["routine", "status", "date"]

    def get_queryset(self):
        qs = WorkoutSession.objects.filter(owner=self.request.user).select_related("routine")
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(date__lte=p["end"])
        return qs

    def perform_create(self, serializer):
        require_module(self.request.user, "fitness")
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"])
    def today(self, request):
        day = local_today(get_zone(request.user.preferences.time_zone))
        return Response({"date": day.isoformat(), "plan": services.today_plan(request.user, day)})


class FitnessStatsView(APIView):
    def get(self, request):
        return Response(services.stats(request.user))
