"""Generic habit engine: binary, count, duration and numeric targets on a recurrence schedule or N-times-per-week."""

from django.db import models

from apps.core.models import OwnedModel, TimeStampedModel


class HabitCategory(models.TextChoices):
    HEALTH = "health", "Health"
    FITNESS = "fitness", "Fitness"
    HYDRATION = "hydration", "Hydration"
    READING = "reading", "Reading"
    LEARNING = "learning", "Learning"
    MINDFULNESS = "mindfulness", "Mindfulness"
    SLEEP = "sleep", "Sleep"
    SOCIAL = "social", "Relationships"
    HOME = "home", "Home"
    WORK = "work", "Work"
    OTHER = "other", "Other"


# Habit category → notification category used for its reminders (and therefore which module gates them).
REMINDER_CATEGORY = {"hydration": "hydration", "reading": "reading", "fitness": "fitness", "mindfulness": "mindfulness", "sleep": "sleep"}


class TargetType(models.TextChoices):
    BINARY = "binary", "Done / not done"
    COUNT = "count", "Count"
    DURATION = "duration", "Duration (minutes)"
    NUMERIC = "numeric", "Amount"


class HabitStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    ARCHIVED = "archived", "Archived"


class Habit(OwnedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=12, choices=HabitCategory.choices, default=HabitCategory.OTHER)
    icon = models.CharField(max_length=32, default="sparkles")
    color = models.CharField(max_length=12, default="sage")
    target_type = models.CharField(max_length=8, choices=TargetType.choices, default=TargetType.BINARY)
    target_value = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit = models.CharField(max_length=20, blank=True)
    # Schedule: an RRULE over local dates (e.g. FREQ=DAILY, FREQ=WEEKLY;BYDAY=MO,WE,FR) …
    schedule_rule = models.CharField(max_length=300, default="FREQ=DAILY")
    # … or a flexible weekly goal ("3 times a week, any days"). When set, every day is eligible.
    times_per_week = models.PositiveSmallIntegerField(null=True, blank=True)
    start_date = models.DateField()
    time_zone = models.CharField(max_length=64)
    reminder_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=HabitStatus.choices, default=HabitStatus.ACTIVE)
    paused_at = models.DateTimeField(null=True, blank=True)
    streaks_enabled = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return self.name

    @property
    def reminder_category(self) -> str:
        return REMINDER_CATEGORY.get(self.category, "habits")


class CompletionStatus(models.TextChoices):
    DONE = "done", "Done"
    PARTIAL = "partial", "Partly done"
    SKIPPED = "skipped", "Rest day / skipped"


class HabitCompletion(TimeStampedModel):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="completions")
    date = models.DateField()
    status = models.CharField(max_length=8, choices=CompletionStatus.choices, default=CompletionStatus.DONE)
    value = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    notes = models.CharField(max_length=500, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["habit", "date"], name="habit_completion_unique_day")]
        indexes = [models.Index(fields=["habit", "date"])]
