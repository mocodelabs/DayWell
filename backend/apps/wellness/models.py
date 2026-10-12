"""Optional wellness modules: hydration, sleep, journal & gratitude, mindfulness sessions."""

from django.db import models

from apps.core.models import OwnedModel


class WaterIntake(OwnedModel):
    date = models.DateField()  # owner's local date
    at = models.DateTimeField()
    amount_ml = models.PositiveIntegerField()  # always stored in ml; converted for display

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["owner", "date"])]


class SleepLog(OwnedModel):
    """Manual sleep log. Not a clinical measurement — no analysis beyond simple averages and consistency."""

    date = models.DateField()  # the local date you woke up
    bedtime_at = models.DateTimeField()
    wake_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    quality = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–5, optional self-rating
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["owner", "date"], name="sleep_log_one_per_day")]


class JournalEntry(OwnedModel):
    """Private by default. Never logged, never sent to third parties (including AI) without explicit consent."""

    date = models.DateField()
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True, max_length=20000)
    gratitude = models.JSONField(default=list, blank=True)  # up to 3 short lines
    mood = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–5 optional check-in
    prompt = models.CharField(max_length=300, blank=True)
    tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["owner", "date"])]


class MindfulnessSession(OwnedModel):
    class Kind(models.TextChoices):
        BREATHING = "breathing", "Breathing"
        MEDITATION = "meditation", "Meditation"
        REFLECTION = "reflection", "Reflection"
        STRETCH = "stretch", "Stretch break"

    date = models.DateField()
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.BREATHING)
    planned_seconds = models.PositiveIntegerField()
    completed_seconds = models.PositiveIntegerField()
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
