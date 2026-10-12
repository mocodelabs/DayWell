from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefing.messages import pick
from apps.core.modules import require_module
from apps.core.timeutils import get_zone, local_today
from apps.core.viewsets import OwnedModelViewSet
from apps.reminders.serializers import ModuleReminderSerializer, days_to_rrule, module_reminder_payload
from apps.reminders.services import system_reminder_state, upsert_system_reminder

from . import services
from .models import JournalEntry, MindfulnessSession, SleepLog, WaterIntake


def today_for(user):
    return local_today(get_zone(user.preferences.time_zone))


# --- Hydration ---------------------------------------------------------------------------------------------------------


class WaterIntakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterIntake
        fields = ["id", "date", "at", "amount_ml"]
        read_only_fields = fields


class AddWaterSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=Decimal("0.1"), max_value=Decimal("5000"))
    unit = serializers.ChoiceField(choices=["ml", "oz", "glass"], required=False)
    date = serializers.DateField(required=False)


class HydrationViewSet(OwnedModelViewSet):
    serializer_class = WaterIntakeSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = WaterIntake.objects.filter(owner=self.request.user)
        if self.request.query_params.get("date"):
            qs = qs.filter(date=self.request.query_params["date"])
        return qs

    def create(self, request, *args, **kwargs):
        require_module(request.user, "hydration")
        ser = AddWaterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prefs = request.user.preferences
        day = ser.validated_data.get("date") or today_for(request.user)
        if day > today_for(request.user):
            raise serializers.ValidationError({"date": ["You can't log water for a future day."]})
        ml = services.to_ml(ser.validated_data["amount"], ser.validated_data.get("unit") or prefs.hydration_unit, prefs.glass_size_ml)
        WaterIntake.objects.create(owner=request.user, date=day, at=timezone.now(), amount_ml=ml)
        return Response(services.hydration_day(request.user, day), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        day = today_for(request.user)
        return Response({"today": services.hydration_day(request.user, day), "week": services.hydration_week(request.user, day)})


class HydrationReminderSerializer(ModuleReminderSerializer):
    every_minutes = serializers.ChoiceField(choices=[60, 90, 120, 180], default=120)
    until = serializers.TimeField(required=False, allow_null=True)


class HydrationReminderView(APIView):
    """Gentle repeating reminders between a start time and an end time (e.g. every 2 h, 09:00–19:00)."""

    KEY = "hydration"

    def get(self, request):
        state = system_reminder_state(request.user, self.KEY)
        payload = module_reminder_payload(state)
        rule = state["rrule"]
        payload["every_minutes"] = 120
        if "INTERVAL=" in rule:
            payload["every_minutes"] = int(rule.split("INTERVAL=")[1].split(";")[0]) * (60 if "FREQ=HOURLY" in rule else 1)
        if "BYHOUR=" in rule:
            payload["until"] = f"{int(rule.split('BYHOUR=')[1].split(';')[0].split(',')[-1]):02d}:00"
        return Response(payload)

    def put(self, request):
        ser = HydrationReminderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d["enabled"]:
            require_module(request.user, "hydration")
        rule = ""
        if d["enabled"]:
            start, until = d["time"], d.get("until") or d["time"].replace(hour=min(d["time"].hour + 10, 23))
            step_h = max(1, int(d["every_minutes"]) // 60)
            hours = list(range(start.hour, until.hour + 1, step_h)) or [start.hour]
            rule = f"FREQ=DAILY;BYHOUR={','.join(str(h) for h in hours)};BYMINUTE={start.minute}"
            if d.get("days") and len(set(d["days"])) < 7:
                rule = days_to_rrule(d["days"]) + f";BYHOUR={','.join(str(h) for h in hours)};BYMINUTE={start.minute}"
        upsert_system_reminder(
            request.user,
            self.KEY,
            enabled=d["enabled"],
            title="Water break",
            category="hydration",
            at=d.get("time"),
            rrule=rule or "FREQ=DAILY",
            message="A glass of water would be a kind thing to do right now.",
        )
        return self.get(request)


# --- Sleep -------------------------------------------------------------------------------------------------------------


class SleepLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SleepLog
        fields = ["id", "date", "bedtime_at", "wake_at", "duration_minutes", "quality", "notes"]
        read_only_fields = ["id", "date", "duration_minutes"]

    def validate(self, attrs):
        bed = attrs.get("bedtime_at", getattr(self.instance, "bedtime_at", None))
        wake = attrs.get("wake_at", getattr(self.instance, "wake_at", None))
        if bed and wake:
            if wake <= bed or wake - bed > timedelta(hours=20):
                raise serializers.ValidationError({"wake_at": ["Wake-up must be after bedtime (and within 20 hours)."]})
            if wake > timezone.now() + timedelta(minutes=5):
                raise serializers.ValidationError({"wake_at": ["That's in the future."]})
            attrs["duration_minutes"] = round((wake - bed).total_seconds() / 60)
            attrs["date"] = wake.astimezone(get_zone(self.context["request"].user.preferences.time_zone)).date()
            qs = SleepLog.objects.filter(owner=self.context["request"].user, date=attrs["date"])
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"wake_at": ["You already logged sleep for that morning."]})
        q = attrs.get("quality")
        if q is not None and not 1 <= q <= 5:
            raise serializers.ValidationError({"quality": ["Rate from 1 to 5."]})
        return attrs


class SleepViewSet(OwnedModelViewSet):
    serializer_class = SleepLogSerializer

    def get_queryset(self):
        return SleepLog.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        require_module(self.request.user, "sleep")
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        prefs = request.user.preferences
        return Response(
            {
                "summary": services.sleep_summary(request.user),
                "planned": {"bedtime": prefs.bedtime.strftime("%H:%M"), "wake_time": prefs.wake_time.strftime("%H:%M")},
                "reminders": {
                    "winddown": module_reminder_payload(system_reminder_state(request.user, "winddown")),
                    "wake": module_reminder_payload(system_reminder_state(request.user, "wake")),
                },
            }
        )


class SleepReminderView(APIView):
    """kind = winddown (before bedtime) | wake."""

    def put(self, request, kind: str):
        if kind not in ("winddown", "wake"):
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = ModuleReminderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d["enabled"]:
            require_module(request.user, "sleep")
        title, msg = (
            ("Time to wind down", "It's nearly time to wind down. Your future self will thank you.")
            if kind == "winddown"
            else ("Good morning", "Time to wake up. Take it slow — a new day is here.")
        )
        upsert_system_reminder(request.user, kind, enabled=d["enabled"], title=title, category="sleep", at=d.get("time"), rrule=days_to_rrule(d.get("days", [])), message=msg)
        return Response(module_reminder_payload(system_reminder_state(request.user, kind)))


# --- Journal -----------------------------------------------------------------------------------------------------------


class JournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = ["id", "date", "title", "body", "gratitude", "mood", "prompt", "tags", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_gratitude(self, value):
        if not isinstance(value, list) or len(value) > 3 or any(not isinstance(v, str) or len(v) > 300 for v in value):
            raise serializers.ValidationError("Up to three short gratitude notes.")
        return [v.strip() for v in value if v.strip()]

    def validate_mood(self, value):
        if value is not None and not 1 <= value <= 5:
            raise serializers.ValidationError("Mood is 1–5.")
        return value

    def validate_tags(self, value):
        from apps.tasks.serializers import validate_tags

        return validate_tags(value)


class JournalViewSet(OwnedModelViewSet):
    serializer_class = JournalSerializer

    def get_queryset(self):
        qs = JournalEntry.objects.filter(owner=self.request.user)
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q) | Q(gratitude__icontains=q))
        if self.request.query_params.get("date"):
            qs = qs.filter(date=self.request.query_params["date"])
        return qs

    def perform_create(self, serializer):
        require_module(self.request.user, "journal")
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"])
    def prompt(self, request):
        day = today_for(request.user)
        return Response({"prompt": pick(services.JOURNAL_PROMPTS, f"{request.user.pk}:{day}")})


# --- Mindfulness -------------------------------------------------------------------------------------------------------


class MindfulnessSerializer(serializers.ModelSerializer):
    class Meta:
        model = MindfulnessSession
        fields = ["id", "date", "kind", "planned_seconds", "completed_seconds", "notes", "created_at"]
        read_only_fields = ["id", "date", "created_at"]

    def validate(self, attrs):
        if not 30 <= attrs.get("planned_seconds", 60) <= 3 * 3600:
            raise serializers.ValidationError({"planned_seconds": ["Sessions are between 30 seconds and 3 hours."]})
        if attrs.get("completed_seconds", 0) > attrs.get("planned_seconds", 0) + 3600:
            raise serializers.ValidationError({"completed_seconds": ["That doesn't match the planned length."]})
        return attrs


class MindfulnessViewSet(OwnedModelViewSet):
    serializer_class = MindfulnessSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return MindfulnessSession.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        require_module(self.request.user, "mindfulness")
        serializer.save(owner=self.request.user, date=today_for(self.request.user))
