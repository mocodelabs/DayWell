"""Abstract base models shared by every DayWell app."""

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimeStampedModel):
    """A record that belongs to exactly one user. Ownership is enforced by OwnedQuerysetMixin and owner-scoped FKs."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True
