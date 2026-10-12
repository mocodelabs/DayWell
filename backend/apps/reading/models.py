from django.db import models
from django.db.models import Q

from apps.core.models import OwnedModel, TimeStampedModel


class BookStatus(models.TextChoices):
    WANT = "want", "Want to read"
    READING = "reading", "Reading"
    COMPLETED = "completed", "Completed"
    PAUSED = "paused", "Paused"


class Book(OwnedModel):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=200, blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    category = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=BookStatus.choices, default=BookStatus.WANT)
    total_pages = models.PositiveIntegerField(null=True, blank=True)
    current_page = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    daily_goal_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    review = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return self.title


class BookNote(TimeStampedModel):
    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        HIGHLIGHT = "highlight", "Highlight"
        QUOTE = "quote", "Favourite quote"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="book_notes")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField(max_length=4000)
    page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["page", "created_at"]


class ReadingSession(OwnedModel):
    """A timed or manually logged reading session. Durations always come from recorded times or user input."""

    class Source(models.TextChoices):
        TIMER = "timer", "Timer"
        MANUAL = "manual", "Logged manually"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField()  # local date of the session (owner's zone)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)  # NULL while the timer is running
    duration_minutes = models.PositiveIntegerField(default=0)
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page = models.PositiveIntegerField(null=True, blank=True)
    pages_read = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["owner", "date"])]
        constraints = [
            models.UniqueConstraint(fields=["owner"], condition=Q(ended_at__isnull=True), name="reading_one_running_timer"),
        ]
