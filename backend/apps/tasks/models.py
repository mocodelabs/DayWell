"""Tasks, subtasks, categories and recurring task series.

A recurring task is a ``TaskSeries`` (the definition) that materialises concrete ``Task`` rows for a rolling window
(``settings.TASK_SERIES_HORIZON_DAYS``). ``UniqueConstraint(series, occurrence_date)`` makes materialisation idempotent
under retries and concurrent runs. Editing "this occurrence" detaches the instance; editing "the series" updates the
definition and every future, still-open, non-detached instance.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import OwnedModel, TimeStampedModel

PALETTE = ["forest", "sage", "terracotta", "amber", "sky", "plum", "slate", "rose"]


class Category(OwnedModel):
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=12, default="forest")
    icon = models.CharField(max_length=32, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint("owner", Lower("name"), name="category_owner_name_ci_unique")]

    def __str__(self) -> str:
        return self.name


class Priority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class TaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    POSTPONED = "postponed", "Postponed"
    CANCELLED = "cancelled", "Cancelled"


OPEN_STATUSES = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.POSTPONED)


class TaskSeries(OwnedModel):
    """Definition of a recurring task. Instances are ``Task`` rows with ``series`` set."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    important = models.BooleanField(default=False)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tags = models.JSONField(default=list, blank=True)
    scheduled_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    link_url = models.URLField(max_length=500, blank=True)
    checklist = models.JSONField(default=list, blank=True)  # subtask titles copied to every new instance
    rrule = models.CharField(max_length=300)
    dtstart = models.DateField()
    time_zone = models.CharField(max_length=64)
    generated_until = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["active", "generated_until"])]


class Task(OwnedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    important = models.BooleanField(default=False)  # Eisenhower "important" axis; "urgent" is derived
    status = models.CharField(max_length=12, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    tags = models.JSONField(default=list, blank=True)
    # Scheduling: a local date (+ optional local time) in ``time_zone``; ``scheduled_at`` is the UTC instant when timed.
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_time = models.TimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    time_zone = models.CharField(max_length=64)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    link_url = models.URLField(max_length=500, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    postponed_count = models.PositiveSmallIntegerField(default=0)
    # Recurrence
    series = models.ForeignKey(TaskSeries, null=True, blank=True, on_delete=models.SET_NULL, related_name="instances")
    occurrence_date = models.DateField(null=True, blank=True)
    detached = models.BooleanField(default=False)
    # Soft delete is only used for series instances, so a deleted occurrence is not re-materialised.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_date", "scheduled_time", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["series", "occurrence_date"], condition=Q(series__isnull=False), name="task_series_occurrence_unique"),
        ]
        indexes = [
            models.Index(fields=["owner", "status", "scheduled_date"]),
            models.Index(fields=["owner", "deadline"]),
            models.Index(fields=["owner", "completed_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class TaskSubtask(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField(default=0)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]


class TaskActivity(models.Model):
    """Append-only history used by insights (completions, postponements, reschedules are counted from here)."""

    class Kind(models.TextChoices):
        CREATED = "created"
        STARTED = "started"
        COMPLETED = "completed"
        REOPENED = "reopened"
        POSTPONED = "postponed"
        RESCHEDULED = "rescheduled"
        CANCELLED = "cancelled"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="activity")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    at = models.DateTimeField()
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["at"]
        indexes = [models.Index(fields=["kind", "at"])]
