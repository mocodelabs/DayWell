from django.db import models

from apps.core.models import OwnedModel


def default_days() -> list:
    return [0, 2, 4]


class WorkoutRoutine(OwnedModel):
    name = models.CharField(max_length=100)
    workout_type = models.CharField(max_length=40, default="Gym")
    days = models.JSONField(default=default_days)  # 0=Monday … 6=Sunday; other days are rest days
    time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    location = models.CharField(max_length=200, blank=True)
    prep_buffer_minutes = models.PositiveSmallIntegerField(default=0)  # reminder fires this long before (travel/prep)
    reminder_enabled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SessionStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    PARTIAL = "partial", "Partly done"
    SKIPPED = "skipped", "Skipped"


class WorkoutSession(OwnedModel):
    routine = models.ForeignKey(WorkoutRoutine, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions")
    date = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    workout_type = models.CharField(max_length=40, default="Gym")
    planned_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=SessionStatus.choices, default=SessionStatus.COMPLETED)
    # Optional, user-chosen measurements only. Body weight or other sensitive metrics are never required.
    distance = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    distance_unit = models.CharField(max_length=4, default="km")
    exercises = models.JSONField(default=list, blank=True)  # [{name, sets, reps, weight, notes}]
    effort = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–10, optional
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["owner", "date"])]
