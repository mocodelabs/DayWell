from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.modules import require_module
from apps.core.timeutils import get_zone, local_today, week_start
from apps.core.viewsets import OwnedModelViewSet, OwnedPrimaryKeyRelatedField
from apps.habits.models import Habit

from . import services
from .models import Goal, GoalCheckIn, GoalMetric, GoalStatus, WeeklyReview


def _today(user) -> date:
    return local_today(get_zone(user.preferences.time_zone))


class RangeSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["end"] < attrs["start"] or (attrs["end"] - attrs["start"]).days > 400:
            raise serializers.ValidationError("Choose a range of up to 400 days.")
        return attrs


class SummaryView(APIView):
    """Generic range summary: /insights/summary/?start=YYYY-MM-DD&end=YYYY-MM-DD."""

    def get(self, request):
        ser = RangeSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        return Response(services.range_stats(request.user, ser.validated_data["start"], ser.validated_data["end"]))


class DailyView(APIView):
    def get(self, request):
        day = serializers.DateField().to_internal_value(request.query_params["date"]) if request.query_params.get("date") else _today(request.user)
        data = services.range_stats(request.user, day, day)
        data["outstanding"] = services.outstanding_tasks(request.user)
        return Response(data)


def suggestions(stats: dict, outstanding: int) -> list[str]:
    """Rule-based, gentle suggestions for the coming week. Never prescriptive, never shaming."""
    out = []
    t = stats["tasks"]
    if t["planned"] >= 10 and t["completion_rate"] is not None and t["completion_rate"] < 0.5:
        out.append("You planned quite a lot this week. Planning fewer tasks per day can make each day feel more achievable.")
    if t["postponed"] >= 5:
        out.append(f"{t['postponed']} tasks were postponed. Consider whether some can be dropped or broken into smaller steps.")
    for h in stats["habits"]["items"]:
        if h["rate"] is not None and h["rate"] < 0.4 and h["scheduled"] >= 4:
            out.append(f"“{h['name']}” was hard to fit in. Fewer days or a smaller target might suit this season better.")
    if outstanding:
        out.append(f"You have {outstanding} outstanding task{'s' if outstanding != 1 else ''}. A short review could clear the decks.")
    rates = [r for r in (t["completion_rate"], stats["habits"]["consistency"]) if r is not None]
    if not out and rates and min(rates) >= 0.6:
        out.append("Your plan seems to be working. Keep the rhythm that felt good this week.")
    return out[:5]


class WeeklyView(APIView):
    def get(self, request):
        prefs = request.user.preferences
        ws = serializers.DateField().to_internal_value(request.query_params["week_start"]) if request.query_params.get("week_start") else None
        ws = week_start(ws or _today(request.user), prefs.week_start)
        we = ws + timedelta(days=6)
        stats = services.range_stats(request.user, ws, we)
        outstanding = services.outstanding_tasks(request.user)
        review = WeeklyReview.objects.filter(owner=request.user, week_start=ws).first()
        return Response(
            {
                **stats,
                "week_start": ws.isoformat(),
                "outstanding": outstanding,
                "accomplishments": services.accomplishments(request.user, ws, we),
                "suggestions": suggestions(stats, len(outstanding)),
                "review": WeeklyReviewSerializer(review).data if review else None,
                "reflection_questions": ["What went well this week?", "What was challenging?", "What would you like to focus on next week?"],
            }
        )


class MonthlyView(APIView):
    def get(self, request):
        raw = request.query_params.get("month")
        today = _today(request.user)
        try:
            first = date.fromisoformat(f"{raw}-01") if raw else today.replace(day=1)
        except ValueError:
            raise serializers.ValidationError({"month": ["Use YYYY-MM."]})
        last = min((first + timedelta(days=32)).replace(day=1) - timedelta(days=1), today) if first <= today else first
        stats = services.range_stats(request.user, first, last)
        return Response({**stats, "month": first.strftime("%Y-%m"), "accomplishments": services.accomplishments(request.user, first, last)})


class YearlyView(APIView):
    def get(self, request):
        today = _today(request.user)
        year = int(request.query_params.get("year") or today.year)
        first, last = date(year, 1, 1), min(date(year, 12, 31), today)
        if first > today:
            return Response({"year": year, "months": []})
        return Response({"year": year, "months": services.monthly_trend(request.user, first, last), "accomplishments": services.accomplishments(request.user, first, last)})


class WeeklyReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyReview
        fields = ["id", "week_start", "went_well", "challenges", "next_focus", "wins", "adjustments", "stats_snapshot", "completed_at", "created_at"]
        read_only_fields = ["id", "stats_snapshot", "completed_at", "created_at"]


class WeeklyReviewViewSet(OwnedModelViewSet):
    serializer_class = WeeklyReviewSerializer

    def get_queryset(self):
        return WeeklyReview.objects.filter(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        """Upsert the review for a week (normalised to the user's week start) and snapshot its statistics."""
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ws = week_start(ser.validated_data["week_start"], request.user.preferences.week_start)
        stats = services.range_stats(request.user, ws, ws + timedelta(days=6))
        snapshot = {
            "tasks": stats["tasks"],
            "habits": {k: v for k, v in stats["habits"].items() if k != "items"},
            "reading": stats["reading"],
            "fitness": stats["fitness"],
            "events": stats["events"],
        }
        fields = {k: v for k, v in ser.validated_data.items() if k != "week_start"}
        with transaction.atomic():
            review, created = WeeklyReview.objects.update_or_create(owner=request.user, week_start=ws, defaults={**fields, "stats_snapshot": snapshot, "completed_at": timezone.now()})
        return Response(WeeklyReviewSerializer(review).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class GoalSerializer(serializers.ModelSerializer):
    habit = OwnedPrimaryKeyRelatedField(queryset=Habit.objects.all(), allow_null=True, required=False)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = ["id", "title", "description", "metric", "habit", "target_value", "unit", "current_value", "start_date", "due_date", "status", "completed_at", "progress", "created_at"]
        read_only_fields = ["id", "status", "completed_at", "created_at"]
        extra_kwargs = {"start_date": {"required": False}}

    def get_progress(self, obj):
        return services.goal_progress(obj)

    def validate_target_value(self, value):
        if value <= 0:
            raise serializers.ValidationError("Set a target above zero.")
        return value

    def validate(self, attrs):
        metric = attrs.get("metric", getattr(self.instance, "metric", GoalMetric.MANUAL))
        if metric == GoalMetric.HABIT_COMPLETIONS and not attrs.get("habit", getattr(self.instance, "habit", None)):
            raise serializers.ValidationError({"habit": ["Choose the habit this goal tracks."]})
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if start and due and due < start:
            raise serializers.ValidationError({"due_date": ["The due date must be after the start date."]})
        return attrs


class CheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalCheckIn
        fields = ["id", "date", "value", "note", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"date": {"required": False}}


class GoalViewSet(OwnedModelViewSet):
    serializer_class = GoalSerializer
    filterset_fields = ["status", "metric"]

    def get_queryset(self):
        return Goal.objects.filter(owner=self.request.user).select_related("owner__preferences")

    def perform_create(self, serializer):
        require_module(self.request.user, "goals")
        serializer.save(owner=self.request.user, start_date=serializer.validated_data.get("start_date") or _today(self.request.user))

    @action(detail=True, methods=["get", "post"], url_path="check-ins")
    def check_ins(self, request, pk=None):
        goal = self.get_object()
        if request.method == "POST":
            ser = CheckInSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            with transaction.atomic():
                ser.save(goal=goal, date=ser.validated_data.get("date") or _today(request.user))
                if goal.metric == GoalMetric.MANUAL:
                    goal.current_value = ser.validated_data["value"]
                    goal.save(update_fields=["current_value", "updated_at"])
            return Response(GoalSerializer(goal, context={"request": request}).data, status=status.HTTP_201_CREATED)
        return Response(CheckInSerializer(goal.check_ins.all()[:100], many=True).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        goal = self.get_object()
        goal.status, goal.completed_at = GoalStatus.COMPLETED, timezone.now()
        goal.save(update_fields=["status", "completed_at", "updated_at"])
        return Response(GoalSerializer(goal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        goal = self.get_object()
        goal.status = GoalStatus.ARCHIVED
        goal.save(update_fields=["status", "updated_at"])
        return Response(GoalSerializer(goal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        goal = self.get_object()
        goal.status, goal.completed_at = GoalStatus.ACTIVE, None
        goal.save(update_fields=["status", "completed_at", "updated_at"])
        return Response(GoalSerializer(goal, context={"request": request}).data)
