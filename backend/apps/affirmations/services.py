from __future__ import annotations

import hashlib
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q

from .library import LIBRARY
from .models import Affirmation, UserAffirmation

NO_REPEAT_DAYS = 30


def seed_library() -> int:
    existing = set(Affirmation.objects.filter(owner__isnull=True).values_list("text", flat=True))
    new = [Affirmation(text=t, category=c) for c, items in LIBRARY.items() for t in items if t not in existing]
    Affirmation.objects.bulk_create(new, ignore_conflicts=True)
    return len(new)


def pool(user):
    qs = Affirmation.objects.filter(Q(owner__isnull=True) | Q(owner=user), active=True)
    cats = user.preferences.affirmation_categories
    if cats:
        filtered = qs.filter(category__in=cats)
        if filtered.exists():
            return filtered
    return qs


def for_day(user, day: date) -> UserAffirmation | None:
    """The day's affirmation: stable once chosen; avoids repeats from the last 30 days when possible."""
    existing = UserAffirmation.objects.filter(user=user, date=day).select_related("affirmation").first()
    if existing:
        return existing
    candidates = list(pool(user).values_list("id", flat=True))
    if not candidates:
        return None
    recent = set(UserAffirmation.objects.filter(user=user, date__gte=day - timedelta(days=NO_REPEAT_DAYS)).values_list("affirmation_id", flat=True))
    fresh = [c for c in candidates if c not in recent] or candidates
    idx = int(hashlib.sha256(f"{user.pk}:{day.isoformat()}".encode()).hexdigest()[:8], 16) % len(fresh)
    try:
        with transaction.atomic():
            return UserAffirmation.objects.create(user=user, date=day, affirmation_id=sorted(fresh)[idx])
    except IntegrityError:  # a concurrent request chose it first — use theirs
        return UserAffirmation.objects.select_related("affirmation").get(user=user, date=day)
