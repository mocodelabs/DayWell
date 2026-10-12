from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class AffirmationCategory(models.TextChoices):
    CONFIDENCE = "confidence", "Confidence"
    FOCUS = "focus", "Focus"
    GRATITUDE = "gratitude", "Gratitude"
    RESILIENCE = "resilience", "Resilience"
    SELF_COMPASSION = "self_compassion", "Self-compassion"
    CONSISTENCY = "consistency", "Consistency"
    LEARNING = "learning", "Learning"
    CALMNESS = "calmness", "Calmness"
    GROWTH = "growth", "Personal growth"


class Affirmation(TimeStampedModel):
    """Library affirmations have ``owner`` NULL (shared, read-only); custom ones belong to one user."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    text = models.CharField(max_length=300)
    category = models.CharField(max_length=16, choices=AffirmationCategory.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "id"]
        constraints = [models.UniqueConstraint(fields=["text"], condition=Q(owner__isnull=True), name="affirmation_library_text_unique")]


class UserAffirmation(TimeStampedModel):
    """The affirmation shown to a user on a given local day (one per day) and whether they saw/acknowledged it."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_affirmations")
    affirmation = models.ForeignKey(Affirmation, on_delete=models.CASCADE, related_name="+")
    date = models.DateField()
    viewed_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="user_affirmation_one_per_day")]


class AffirmationFavorite(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_affirmations")
    affirmation = models.ForeignKey(Affirmation, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "affirmation"], name="affirmation_favorite_unique")]
