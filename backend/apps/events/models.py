"""Calendar events with RFC 5545 recurrence and per-occurrence exceptions.

Wall-clock fields (``start_date``/``start_time``/``end_date``/``end_time``) in ``time_zone`` are the source of truth;
``start``/``end`` are the UTC instants of the first occurrence and ``series_end`` the UTC end of the last occurrence
(NULL = repeats forever). Occurrences are identified by their *original* local start (``occurrence key``):
``YYYY-MM-DDTHH:MM`` for timed events, ``YYYY-MM-DD`` for all-day events.
"""

from django.db import models

from apps.core.models import OwnedModel, TimeStampedModel
from apps.tasks.models import Category


class EventStatus(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    TENTATIVE = "tentative", "Tentative"
    CANCELLED = "cancelled", "Cancelled"


class Attendance(models.TextChoices):
    NONE = "", "Not recorded"
    ATTENDED = "attended", "Attended"
    COMPLETED = "completed", "Completed"
    MISSED = "missed", "Missed"
    SKIPPED = "skipped", "Skipped"


class CalendarEvent(OwnedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=300, blank=True)
    meeting_url = models.URLField(max_length=500, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    all_day = models.BooleanField(default=False)
    time_zone = models.CharField(max_length=64)
    start_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_date = models.DateField()
    end_time = models.TimeField(null=True, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    rrule = models.CharField(max_length=300, blank=True)
    series_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=EventStatus.choices, default=EventStatus.CONFIRMED)
    attendance = models.CharField(max_length=10, choices=Attendance.choices, blank=True, default="")
    ical_uid = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["start"]
        indexes = [
            models.Index(fields=["owner", "start"]),
            models.Index(fields=["owner", "end"]),
            models.Index(fields=["owner", "series_end"]),
        ]

    def __str__(self) -> str:
        return self.title


class EventException(TimeStampedModel):
    """A change to one occurrence of a recurring event: cancellation, moved time, edited details, or attendance."""

    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name="exceptions")
    original_key = models.CharField(max_length=16)
    cancelled = models.BooleanField(default=False)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=300, blank=True)
    start_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    # UTC instants of the moved occurrence (NULL when not moved), so moved occurrences can be found by range queries.
    override_start = models.DateTimeField(null=True, blank=True)
    override_end = models.DateTimeField(null=True, blank=True)
    attendance = models.CharField(max_length=10, choices=Attendance.choices, blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "original_key"], name="event_exception_unique_occurrence")]
        indexes = [models.Index(fields=["override_start"])]
