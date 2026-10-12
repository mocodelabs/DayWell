from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SOUNDS, NotificationCategory, NotificationPreference
from .serializers import NotificationPreferenceSerializer, UserPreferenceSerializer
from .services import ensure_defaults

BRIEFING_FIELDS = {"morning_notification", "greeting_enabled", "greeting_time", "evening_summary", "evening_time"}


class PreferenceView(APIView):
    def get(self, request):
        return Response(UserPreferenceSerializer(ensure_defaults(request.user), context={"request": request}).data)

    def patch(self, request):
        ser = UserPreferenceSerializer(ensure_defaults(request.user), data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            prefs = ser.save()
            changed = set(ser.validated_data)
            if changed & BRIEFING_FIELDS:
                from apps.briefing.services import sync_briefing_reminders

                sync_briefing_reminders(request.user)
            if prefs.module_enabled("admin") and "modules" in changed:
                from apps.tasks.services import ensure_admin_categories

                ensure_admin_categories(request.user)
            if "time_zone" in changed:
                # "Floating" items follow the person (a 07:00 wake-up stays 07:00 after travelling): absolute reminders and
                # habits move to the new zone. Calendar events and timed tasks keep the zone they were created in.
                from apps.habits.models import Habit
                from apps.reminders.models import Reminder
                from apps.reminders.services import resync_for_owner

                Reminder.objects.filter(owner=request.user, kind=Reminder.Kind.ABSOLUTE).update(time_zone=prefs.time_zone)
                Habit.objects.filter(owner=request.user).update(time_zone=prefs.time_zone)
                resync_for_owner(request.user)
        return Response(UserPreferenceSerializer(prefs, context={"request": request}).data)


class SoundListView(APIView):
    def get(self, request):
        return Response([{"key": s, "url": f"/sounds/{s}.wav"} for s in SOUNDS])


class NotificationPreferenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationPreferenceSerializer
    pagination_class = None

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        ensure_defaults(request.user)
        order = {c: i for i, c in enumerate(NotificationCategory.values)}  # logical order, not alphabetical
        items = sorted(self.get_queryset(), key=lambda p: order.get(p.category, 99))
        return Response(self.get_serializer(items, many=True).data)
