from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.modules import require_module
from apps.core.timeutils import get_zone, local_today
from apps.reminders.serializers import ModuleReminderSerializer, days_to_rrule, module_reminder_payload
from apps.reminders.services import system_reminder_state, upsert_system_reminder

from . import services
from .models import Affirmation, AffirmationCategory, AffirmationFavorite, UserAffirmation


class AffirmationSerializer(serializers.ModelSerializer):
    custom = serializers.SerializerMethodField()
    favorite = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Affirmation
        fields = ["id", "text", "category", "custom", "favorite", "active"]
        read_only_fields = ["id"]

    def get_custom(self, obj) -> bool:
        return obj.owner_id is not None

    def validate_text(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Write a short affirmation.")
        return value


class DailySerializer(serializers.ModelSerializer):
    affirmation = AffirmationSerializer(read_only=True)
    favorite = serializers.SerializerMethodField()

    class Meta:
        model = UserAffirmation
        fields = ["id", "date", "affirmation", "viewed_at", "acknowledged_at", "favorite"]

    def get_favorite(self, obj) -> bool:
        return AffirmationFavorite.objects.filter(user=obj.user, affirmation=obj.affirmation_id).exists()


class AffirmationViewSet(viewsets.ModelViewSet):
    """Library (read-only) + the user's custom affirmations (full CRUD)."""

    serializer_class = AffirmationSerializer
    filterset_fields = ["category"]
    search_fields = ["text"]

    def get_queryset(self):
        user = self.request.user
        fav = AffirmationFavorite.objects.filter(user=user, affirmation=OuterRef("pk"))
        qs = Affirmation.objects.filter(Q(owner__isnull=True) | Q(owner=user)).annotate(favorite=Exists(fav))
        if self.request.query_params.get("favorites") == "true":
            qs = qs.filter(favorite=True)
        if self.request.query_params.get("custom") == "true":
            qs = qs.filter(owner=user)
        return qs

    def perform_create(self, serializer):
        require_module(self.request.user, "affirmations")
        serializer.save(owner=self.request.user)

    def _own(self, obj):
        if obj.owner_id != self.request.user.id:
            raise PermissionDenied("Library affirmations can't be changed. Add your own instead.")

    def perform_update(self, serializer):
        self._own(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._own(instance)
        instance.delete()

    @action(detail=True, methods=["post", "delete"])
    def favorite(self, request, pk=None):
        aff = self.get_object()
        if request.method == "DELETE":
            AffirmationFavorite.objects.filter(user=request.user, affirmation=aff).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        AffirmationFavorite.objects.get_or_create(user=request.user, affirmation=aff)
        return Response({"favorite": True})

    @action(detail=False, methods=["get"])
    def categories(self, request):
        return Response([{"key": k, "label": label} for k, label in AffirmationCategory.choices])


class TodayAffirmationView(APIView):
    def get(self, request):
        require_module(request.user, "affirmations")
        ua = services.for_day(request.user, local_today(get_zone(request.user.preferences.time_zone)))
        if ua is None:
            return Response({"affirmation": None})
        return Response(DailySerializer(ua).data)


class DailyAffirmationActionView(APIView):
    def post(self, request, pk: int, verb: str):
        ua = UserAffirmation.objects.filter(user=request.user, pk=pk).first()
        if ua is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        now = timezone.now()
        if verb == "view" and ua.viewed_at is None:
            ua.viewed_at = now
        elif verb == "acknowledge":
            ua.viewed_at = ua.viewed_at or now
            ua.acknowledged_at = ua.acknowledged_at or now
        ua.save()
        return Response(DailySerializer(ua).data)


class HistoryView(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = DailySerializer

    def get_queryset(self):
        return UserAffirmation.objects.filter(user=self.request.user).select_related("affirmation", "user")


class AffirmationReminderView(APIView):
    KEY = "affirmation"

    def get(self, request):
        return Response(module_reminder_payload(system_reminder_state(request.user, self.KEY)))

    def put(self, request):
        ser = ModuleReminderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        upsert_system_reminder(
            request.user,
            self.KEY,
            enabled=d["enabled"],
            title="Your daily affirmation",
            category="affirmations",
            at=d.get("time"),
            rrule=days_to_rrule(d.get("days", [])),
            message="Your affirmation for today is ready.",
        )
        return Response(module_reminder_payload(system_reminder_state(request.user, self.KEY)))
