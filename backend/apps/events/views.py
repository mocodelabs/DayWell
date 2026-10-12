from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.viewsets import OwnedModelViewSet

from . import services
from .models import CalendarEvent
from .serializers import AttendanceSerializer, EventSerializer, OccurrenceChangeSerializer, RangeSerializer

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class EventViewSet(OwnedModelViewSet):
    serializer_class = EventSerializer
    search_fields = ["title", "description", "location"]
    filterset_fields = ["category", "status", "all_day"]

    def get_queryset(self):
        return CalendarEvent.objects.filter(owner=self.request.user).select_related("category").prefetch_related("reminders")

    def _save(self, serializer, **extra):
        data = dict(serializer.validated_data)
        offsets = data.pop("reminder_offsets", None)
        ev = serializer.instance or CalendarEvent(**extra)
        for k, v in data.items():
            setattr(ev, k, v)
        if not ev.time_zone:
            ev.time_zone = self.request.user.preferences.time_zone
        services.save_event(ev)
        if offsets is not None:
            from apps.reminders.services import set_item_reminders

            set_item_reminders(self.request.user, [{"offset_minutes": o, "anchor": "start"} for o in offsets], event=ev)
        serializer.instance = ev

    def perform_create(self, serializer):
        self._save(serializer, owner=self.request.user)

    def perform_update(self, serializer):
        self._save(serializer)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data["conflicts"] = self._conflicts_for(response.data["id"])
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response.data["conflicts"] = self._conflicts_for(response.data["id"])
        return response

    def _conflicts_for(self, event_id: int) -> list:
        ev = CalendarEvent.objects.get(pk=event_id)
        if ev.all_day:
            return []
        window_end = ev.end + timezone.timedelta(days=1) if not ev.rrule else ev.start + timezone.timedelta(days=60)
        occs = services.expand(self.request.user, ev.start - timezone.timedelta(days=1), window_end)
        return [c for c in services.find_conflicts(occs) if event_id in (c["a"]["event_id"], c["b"]["event_id"])][:10]

    def _range(self, request):
        ser = RangeSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        return ser.validated_data

    @action(detail=False, methods=["get"])
    def occurrences(self, request):
        """Expanded occurrences in [start, end). Required: start, end (ISO datetimes). Optional: category, q."""
        rng = self._range(request)
        qs = CalendarEvent.objects.filter(owner=request.user)
        if rng.get("category"):
            qs = qs.filter(category_id=rng["category"])
        if rng.get("q"):
            qs = qs.filter(Q(title__icontains=rng["q"]) | Q(description__icontains=rng["q"]) | Q(location__icontains=rng["q"]))
        occs = services.expand(request.user, rng["start"], rng["end"], queryset=qs)
        return Response({"results": [o.as_dict() for o in occs], "conflicts": services.find_conflicts(occs)})

    @action(detail=True, methods=["post", "delete"])
    def occurrence(self, request, pk=None):
        """POST: change one occurrence (move/edit/cancel). DELETE ?key=: cancel one occurrence."""
        ev = self.get_object()
        if request.method == "DELETE":
            key = request.query_params.get("key")
            if not key:
                raise serializers.ValidationError({"key": ["Which occurrence?"]})
            services.upsert_exception(ev, key, {"cancelled": True})
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = OccurrenceChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        changes = dict(ser.validated_data)
        key = changes.pop("key")
        services.upsert_exception(ev, key, changes)
        return Response({"ok": True, "key": key})

    @action(detail=True, methods=["post"])
    def attendance(self, request, pk=None):
        ev = self.get_object()
        ser = AttendanceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if ev.rrule:
            key = ser.validated_data.get("key")
            if not key:
                raise serializers.ValidationError({"key": ["Which occurrence?"]})
            services.upsert_exception(ev, key, {"attendance": ser.validated_data["attendance"]})
        else:
            ev.attendance = ser.validated_data["attendance"]
            ev.save(update_fields=["attendance", "updated_at"])
        return Response({"ok": True})

    @action(detail=False, methods=["get"])
    def conflicts(self, request):
        rng = self._range(request)
        return Response(services.find_conflicts(services.expand(request.user, rng["start"], rng["end"])))

    @action(detail=False, methods=["get"], url_path="export")
    def export_ics(self, request):
        response = HttpResponse(services.export_ics(request.user), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="daywell-calendar.ics"'
        return response

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_ics(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": ["Choose an .ics file to import."]})
        if upload.size > MAX_IMPORT_BYTES:
            raise serializers.ValidationError({"file": ["That file is larger than 2 MB."]})
        result = services.import_ics(request.user, upload.read(), default_zone=request.user.preferences.time_zone)
        return Response(result, status=status.HTTP_201_CREATED if result["created"] else status.HTTP_200_OK)
