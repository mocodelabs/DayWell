from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.modules import require_module
from apps.core.timeutils import get_zone, local_today
from apps.core.viewsets import OwnedModelViewSet, OwnedPrimaryKeyRelatedField
from apps.reminders.serializers import ModuleReminderSerializer, days_to_rrule, module_reminder_payload
from apps.reminders.services import system_reminder_state, upsert_system_reminder

from . import services
from .models import Book, BookNote, ReadingSession


class BookNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookNote
        fields = ["id", "kind", "text", "page", "created_at"]


class BookSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    minutes_total = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "author",
            "cover_url",
            "category",
            "status",
            "total_pages",
            "current_page",
            "start_date",
            "target_date",
            "completed_date",
            "daily_goal_minutes",
            "rating",
            "notes",
            "review",
            "progress",
            "minutes_total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_progress(self, obj) -> float | None:
        return round(min(obj.current_page / obj.total_pages, 1), 3) if obj.total_pages else None

    def validate_rating(self, value):
        if value is not None and not 1 <= value <= 5:
            raise serializers.ValidationError("Rate from 1 to 5.")
        return value

    def validate(self, attrs):
        total = attrs.get("total_pages", getattr(self.instance, "total_pages", None))
        current = attrs.get("current_page", getattr(self.instance, "current_page", 0))
        if total and current and current > total:
            raise serializers.ValidationError({"current_page": [f"This book has {total} pages."]})
        if attrs.get("status") == "completed" and not attrs.get("completed_date") and not getattr(self.instance, "completed_date", None):
            attrs["completed_date"] = local_today(get_zone(self.context["request"].user.preferences.time_zone))
        return attrs


class SessionSerializer(serializers.ModelSerializer):
    book = OwnedPrimaryKeyRelatedField(queryset=Book.objects.all())
    book_title = serializers.CharField(source="book.title", read_only=True)
    start_time = serializers.TimeField(write_only=True, required=False)

    class Meta:
        model = ReadingSession
        fields = ["id", "book", "book_title", "date", "started_at", "ended_at", "duration_minutes", "start_page", "end_page", "pages_read", "source", "notes", "start_time"]
        read_only_fields = ["id", "started_at", "ended_at", "source"]


class BookViewSet(OwnedModelViewSet):
    serializer_class = BookSerializer
    filterset_fields = ["status"]
    search_fields = ["title", "author", "category"]

    def get_queryset(self):
        from django.db.models import Sum

        return Book.objects.filter(owner=self.request.user).annotate(minutes_total=Sum("sessions__duration_minutes"))

    def perform_create(self, serializer):
        require_module(self.request.user, "reading")
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        book = self.get_object()
        services.complete_book(book, local_today(get_zone(request.user.preferences.time_zone)))
        return Response(BookSerializer(self.get_queryset().get(pk=book.pk), context={"request": request}).data)

    @action(detail=True, methods=["get", "post"], url_path="notes")
    def book_notes(self, request, pk=None):
        book = self.get_object()
        if request.method == "POST":
            ser = BookNoteSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            ser.save(book=book)
            return Response(ser.data, status=status.HTTP_201_CREATED)
        return Response(BookNoteSerializer(book.book_notes.all(), many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"notes/(?P<note_id>\d+)")
    def delete_note(self, request, pk=None, note_id=None):
        get_object_or_404(BookNote, pk=note_id, book=self.get_object()).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="timer/start")
    def start_timer(self, request, pk=None):
        require_module(request.user, "reading")
        session = services.start_timer(request.user, self.get_object())
        return Response(SessionSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class StopTimerSerializer(serializers.Serializer):
    end_page = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    pages_read = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class SessionViewSet(OwnedModelViewSet):
    serializer_class = SessionSerializer
    filterset_fields = ["book", "date", "source"]

    def get_queryset(self):
        return ReadingSession.objects.filter(owner=self.request.user).select_related("book")

    def perform_create(self, serializer):
        require_module(self.request.user, "reading")
        d = serializer.validated_data
        serializer.instance = services.log_manual(
            self.request.user,
            d["book"],
            day=d["date"],
            minutes=d.get("duration_minutes") or 0,
            start_time=d.get("start_time"),
            start_page=d.get("start_page"),
            end_page=d.get("end_page"),
            pages_read=d.get("pages_read"),
            notes=d.get("notes", ""),
        )

    @action(detail=False, methods=["get"])
    def running(self, request):
        s = self.get_queryset().filter(ended_at__isnull=True).first()
        return Response(SessionSerializer(s, context={"request": request}).data if s else None)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        ser = StopTimerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        s = services.stop_timer(self.get_object(), **ser.validated_data)
        return Response(SessionSerializer(s, context={"request": request}).data)


class ReadingStatsView(APIView):
    def get(self, request):
        return Response(services.stats(request.user))


class ReadingReminderView(APIView):
    KEY = "reading"

    def get(self, request):
        return Response(module_reminder_payload(system_reminder_state(request.user, self.KEY)))

    def put(self, request):
        ser = ModuleReminderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d["enabled"]:
            require_module(request.user, "reading")
        upsert_system_reminder(request.user, self.KEY, enabled=d["enabled"], title="Reading time", category="reading", at=d.get("time"), rrule=days_to_rrule(d.get("days", [])))
        return Response(module_reminder_payload(system_reminder_state(request.user, self.KEY)))
