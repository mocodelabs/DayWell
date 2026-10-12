from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.timeutils import get_zone, local_today, week_start
from apps.core.viewsets import OwnedModelViewSet
from apps.reminders.services import sync_habit_reminder

from . import services
from .models import Habit, HabitCompletion, HabitStatus
from .serializers import CompleteSerializer, CompletionSerializer, DateSerializer, HabitSerializer, IncrementSerializer, RangeSerializer


def habit_state(habit: Habit, day, completions: dict, week_starts_on: int) -> dict:
    """Everything the checklist needs for one habit on one day (computed from stored completions only)."""
    comp = completions.get(day)
    wk = week_start(day, week_starts_on)
    data = {
        "habit": HabitSerializer(habit).data,
        "date": day.isoformat(),
        "scheduled": services.is_scheduled(habit, day),
        "completion": CompletionSerializer(comp).data if comp else None,
        "week": services.progress(habit, wk, wk + timedelta(days=6), completions, week_starts_on).as_dict(),
    }
    if habit.streaks_enabled:
        data["streak"] = services.streaks(habit, day, completions, week_starts_on)
    return data


class HabitViewSet(OwnedModelViewSet):
    serializer_class = HabitSerializer
    filterset_fields = ["status", "category"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        return Habit.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        prefs = self.request.user.preferences
        zone = get_zone(serializer.validated_data.get("time_zone") or prefs.time_zone)
        with transaction.atomic():
            habit = serializer.save(
                owner=self.request.user,
                time_zone=serializer.validated_data.get("time_zone") or prefs.time_zone,
                start_date=serializer.validated_data.get("start_date") or local_today(zone),
                position=Habit.objects.filter(owner=self.request.user).count(),
            )
            sync_habit_reminder(habit)

    def perform_update(self, serializer):
        with transaction.atomic():
            sync_habit_reminder(serializer.save())

    def _day(self, habit, data):
        return data.get("date") or local_today(get_zone(habit.time_zone))

    def _state(self, habit, day):
        prefs = self.request.user.preferences
        comps = {c.date: c for c in habit.completions.filter(date__gte=day - timedelta(days=services.STREAK_LOOKBACK_DAYS), date__lte=day)}
        return Response(habit_state(habit, day, comps, prefs.week_start))

    @action(detail=False, methods=["get"])
    def today(self, request):
        """The daily checklist: active habits with today's state, scheduled ones first."""
        prefs = request.user.preferences
        ser = DateSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        day = ser.validated_data.get("date") or local_today(get_zone(prefs.time_zone))
        habits = list(self.get_queryset().filter(status=HabitStatus.ACTIVE))
        comps_by_habit: dict[int, dict] = {h.id: {} for h in habits}
        for c in HabitCompletion.objects.filter(habit__in=habits, date__gte=day - timedelta(days=services.STREAK_LOOKBACK_DAYS), date__lte=day):
            comps_by_habit[c.habit_id][c.date] = c
        items = [habit_state(h, day, comps_by_habit[h.id], prefs.week_start) for h in habits]
        items.sort(key=lambda i: (not i["scheduled"], i["habit"]["position"]))
        return Response({"date": day.isoformat(), "items": items})

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        habit = self.get_object()
        ser = CompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        day = self._day(habit, d)
        services.record_completion(habit, day, value=d.get("value"), status=d.get("status"), notes=d.get("notes"), mark_target=d.get("value") is None and d.get("status") in (None, "done"))
        return self._state(habit, day)

    @action(detail=True, methods=["post"])
    def increment(self, request, pk=None):
        habit = self.get_object()
        ser = IncrementSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        day = self._day(habit, ser.validated_data)
        services.increment(habit, day, ser.validated_data["amount"])
        return self._state(habit, day)

    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        habit = self.get_object()
        ser = DateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        day = self._day(habit, ser.validated_data)
        services.undo(habit, day)
        return self._state(habit, day)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        habit = self.get_object()
        with transaction.atomic():
            habit.status, habit.paused_at = HabitStatus.PAUSED, timezone.now()
            habit.save(update_fields=["status", "paused_at", "updated_at"])
            sync_habit_reminder(habit)
        return Response(HabitSerializer(habit).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        habit = self.get_object()
        with transaction.atomic():
            habit.status, habit.paused_at = HabitStatus.ACTIVE, None
            habit.save(update_fields=["status", "paused_at", "updated_at"])
            sync_habit_reminder(habit)
        return Response(HabitSerializer(habit).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        habit = self.get_object()
        with transaction.atomic():
            habit.status = HabitStatus.ARCHIVED
            habit.paused_at = habit.paused_at or timezone.now()
            habit.save(update_fields=["status", "paused_at", "updated_at"])
            sync_habit_reminder(habit)
        return Response(HabitSerializer(habit).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        habit = self.get_object()
        ser = RangeSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        start, end = ser.validated_data["start"], ser.validated_data["end"]
        comps = {c.date: c for c in habit.completions.filter(date__gte=start, date__lte=end)}
        return Response(
            {
                "scheduled_dates": [d.isoformat() for d in services.scheduled_dates(habit, start, end)],
                "completions": CompletionSerializer(comps.values(), many=True).data,
                "progress": services.progress(habit, start, end, comps, request.user.preferences.week_start).as_dict(),
            }
        )

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            ids = []
        owned = {h.id: h for h in self.get_queryset().filter(id__in=ids)}
        for pos, hid in enumerate(i for i in ids if i in owned):
            Habit.objects.filter(pk=hid).update(position=pos)
        return Response({"ok": True})
