from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import NotificationCategory, NotificationPreference, UserPreference

DEFAULT_CHANNELS = ["in_app", "push"]


def ensure_defaults(user) -> UserPreference:
    prefs, _ = UserPreference.objects.get_or_create(user=user)
    existing = set(NotificationPreference.objects.filter(user=user).values_list("category", flat=True))
    NotificationPreference.objects.bulk_create([NotificationPreference(user=user, category=c, channels=list(DEFAULT_CHANNELS)) for c in NotificationCategory.values if c not in existing])
    return prefs


def notification_pref(user, category: str) -> NotificationPreference:
    pref = NotificationPreference.objects.filter(user=user, category=category).first()
    if pref is None:
        pref, _ = NotificationPreference.objects.get_or_create(user=user, category=category, defaults={"channels": list(DEFAULT_CHANNELS)})
    return pref


def in_quiet_hours(prefs: UserPreference, local_dt: datetime) -> bool:
    """Is a local wall time inside the user's quiet hours? Windows may cross midnight (22:00→07:00).

    For a window crossing midnight, the *start day* decides: Friday 22:00 → Saturday 07:00 is "Friday's" quiet period.
    """
    if not prefs.quiet_enabled:
        return False
    start, end, t = prefs.quiet_start, prefs.quiet_end, local_dt.time()
    days = set(prefs.quiet_days or [])
    if start == end:
        return False
    if start < end:
        return start <= t < end and local_dt.weekday() in days
    if t >= start:
        return local_dt.weekday() in days
    if t < end:
        return (local_dt - timedelta(days=1)).weekday() in days
    return False


def quiet_hours_end(prefs: UserPreference, local_dt: datetime, zone: ZoneInfo) -> datetime:
    """The local wall time when the current quiet period ends (assumes in_quiet_hours is True)."""
    end: time = prefs.quiet_end
    candidate = datetime.combine(local_dt.date(), end)
    if candidate <= local_dt.replace(tzinfo=None):
        candidate += timedelta(days=1)
    return candidate
