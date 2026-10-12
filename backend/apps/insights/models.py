from django.db import models

from apps.core.models import OwnedModel, TimeStampedModel
from apps.habits.models import Habit


class GoalMetric(models.TextChoices):
    MANUAL = "manual", "I'll update it myself"
    BOOKS_COMPLETED = "books_completed", "Books completed"
    READING_MINUTES = "reading_minutes", "Reading minutes"
    WORKOUT_SESSIONS = "workout_sessions", "Workout sessions"
    WORKOUT_MINUTES = "workout_minutes", "Workout minutes"
    HABIT_COMPLETIONS = "habit_completions", "Habit completions"
    TASKS_COMPLETED = "tasks_completed", "Tasks completed"


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class Goal(OwnedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric = models.CharField(max_length=20, choices=GoalMetric.choices, default=GoalMetric.MANUAL)
    habit = models.ForeignKey(Habit, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    target_value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=30, blank=True)
    current_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # used by manual goals only
    start_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=GoalStatus.choices, default=GoalStatus.ACTIVE)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]


class GoalCheckIn(TimeStampedModel):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="check_ins")
    date = models.DateField()
    value = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]


class WeeklyReview(OwnedModel):
    """A user's reflection on a week, with a snapshot of the statistics as they were when saved (reproducible)."""

    week_start = models.DateField()
    went_well = models.TextField(blank=True)
    challenges = models.TextField(blank=True)
    next_focus = models.TextField(blank=True)
    wins = models.TextField(blank=True)
    adjustments = models.TextField(blank=True)
    stats_snapshot = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-week_start"]
        constraints = [models.UniqueConstraint(fields=["owner", "week_start"], name="weekly_review_one_per_week")]
