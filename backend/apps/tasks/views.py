from datetime import timedelta

import django_filters
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.timeutils import get_zone, local_today
from apps.core.viewsets import OwnedModelViewSet

from . import services
from .models import OPEN_STATUSES, Category, Task, TaskSubtask
from .serializers import CategorySerializer, PostponeSerializer, SubtaskSerializer, TaskSerializer


class CategoryViewSet(OwnedModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None
    search_fields = ["name"]


class TaskFilter(django_filters.FilterSet):
    status = django_filters.BaseInFilter(field_name="status")
    priority = django_filters.BaseInFilter(field_name="priority")
    date_from = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="lte")
    category = django_filters.NumberFilter(field_name="category_id")
    tag = django_filters.CharFilter(method="filter_tag")
    open = django_filters.BooleanFilter(method="filter_open")
    inbox = django_filters.BooleanFilter(method="filter_inbox")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    admin = django_filters.BooleanFilter(method="filter_admin")

    class Meta:
        model = Task
        fields = ["important", "series"]

    def filter_tag(self, qs, name, value):
        return qs.filter(tags__contains=[value])

    def filter_open(self, qs, name, value):
        return qs.filter(status__in=OPEN_STATUSES) if value else qs.exclude(status__in=OPEN_STATUSES)

    def filter_inbox(self, qs, name, value):
        return qs.filter(scheduled_date__isnull=value)

    def filter_admin(self, qs, name, value):
        names = [n for n, _ in services.ADMIN_CATEGORIES]
        return qs.filter(category__name__in=names) if value else qs.exclude(category__name__in=names)

    def filter_overdue(self, qs, name, value):
        if not value:
            return qs
        today = local_today(get_zone(self.request.user.preferences.time_zone))
        return qs.filter(status__in=OPEN_STATUSES).filter(Q(scheduled_date__lt=today) | Q(deadline__lt=timezone.now()))


PRIORITY_ORDER = Case(
    When(priority="urgent", then=Value(0)),
    When(priority="high", then=Value(1)),
    When(priority="normal", then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)


class TaskViewSet(OwnedModelViewSet):
    serializer_class = TaskSerializer
    filterset_class = TaskFilter
    search_fields = ["title", "description", "notes"]
    ordering_fields = ["scheduled_date", "deadline", "created_at", "priority_rank", "completed_at"]

    def get_queryset(self):
        return (
            Task.objects.filter(owner=self.request.user, deleted_at__isnull=True)
            .select_related("series", "category")
            .prefetch_related("subtasks", "reminders", "series__reminders")
            .annotate(priority_rank=PRIORITY_ORDER)
            .order_by("scheduled_date", "scheduled_time", "priority_rank", "created_at")
        )

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        checklist = data.pop("checklist", None)
        rrule = data.pop("recurrence", "")
        reminders = data.pop("reminders", None)
        task = services.create_task(self.request.user, data, subtasks=checklist, rrule=rrule)
        if reminders is not None:
            from apps.reminders.services import set_item_reminders

            set_item_reminders(self.request.user, reminders, task=task, series=task.series)
        serializer.instance = task

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        data.pop("checklist", None)
        data.pop("recurrence", None)
        reminders = data.pop("reminders", None)
        scope = self.request.query_params.get("scope", "this")
        if scope not in ("this", "series"):
            raise serializers.ValidationError({"scope": ["Use 'this' or 'series'."]})
        task = services.update_task(serializer.instance, data, scope=scope)
        if reminders is not None:
            from apps.reminders.services import set_item_reminders

            set_item_reminders(self.request.user, reminders, task=task, series=task.series if scope == "series" else None)
        serializer.instance = task

    def destroy(self, request, *args, **kwargs):
        scope = request.query_params.get("scope", "this")
        services.delete(self.get_object(), scope=scope if scope in ("this", "series") else "this")
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _respond(self, task):
        task = self.get_queryset().get(pk=task.pk)
        return Response(TaskSerializer(task, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._respond(services.complete(self.get_object()))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._respond(services.reopen(self.get_object()))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._respond(services.start(self.get_object()))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._respond(services.cancel(self.get_object()))

    @action(detail=True, methods=["post"])
    def postpone(self, request, pk=None):
        task = self.get_object()
        ser = PostponeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        today = local_today(get_zone(task.time_zone))
        preset = ser.validated_data.get("preset")
        if preset == "tomorrow":
            to_date = today + timedelta(days=1)
        elif preset == "next_week":
            to_date = today + timedelta(days=7 - today.weekday())
        elif preset == "weekend":
            to_date = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        else:
            to_date = ser.validated_data["to_date"]
        keep_time = "to_time" not in ser.validated_data
        return self._respond(services.postpone(task, to_date=to_date, to_time=ser.validated_data.get("to_time"), keep_time=keep_time))


class SubtaskViewSet(viewsets.ModelViewSet):
    serializer_class = SubtaskSerializer
    pagination_class = None

    def _task(self):
        return get_object_or_404(Task, pk=self.kwargs["task_pk"], owner=self.request.user, deleted_at__isnull=True)

    def get_queryset(self):
        return TaskSubtask.objects.filter(task=self._task())

    def perform_create(self, serializer):
        task = self._task()
        serializer.save(task=task, position=task.subtasks.count())
