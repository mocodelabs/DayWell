from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Sum

from apps.core.timeutils import get_zone, local_today

from .models import SleepLog, WaterIntake

OZ_ML = Decimal("29.5735")

JOURNAL_PROMPTS = [
    "What went well today, even a little?",
    "What is one thing you're looking forward to?",
    "What drained your energy today, and what restored it?",
    "Who made your day better, and how?",
    "What would make tomorrow feel lighter?",
    "What did you learn about yourself this week?",
    "What are you ready to let go of?",
]


def to_ml(amount: Decimal, unit: str, glass_ml: int) -> int:
    if unit == "oz":
        return round(amount * OZ_ML)
    if unit == "glass":
        return round(amount * glass_ml)
    return round(amount)


def from_ml(ml: int, unit: str, glass_ml: int) -> float:
    if unit == "oz":
        return round(float(Decimal(ml) / OZ_ML), 1)
    if unit == "glass":
        return round(ml / glass_ml, 1) if glass_ml else 0.0
    return float(ml)


def target_ml(prefs) -> int:
    return to_ml(Decimal(prefs.hydration_target), prefs.hydration_unit, prefs.glass_size_ml)


def hydration_day(owner, day: date) -> dict:
    prefs = owner.preferences
    total = WaterIntake.objects.filter(owner=owner, date=day).aggregate(s=Sum("amount_ml"))["s"] or 0
    target = target_ml(prefs)
    return {
        "date": day.isoformat(),
        "total_ml": total,
        "target_ml": target,
        "unit": prefs.hydration_unit,
        "total": from_ml(total, prefs.hydration_unit, prefs.glass_size_ml),
        "target": prefs.hydration_target,
        "progress": round(min(total / target, 1), 3) if target else None,
        "glass_ml": prefs.glass_size_ml,
    }


def hydration_week(owner, end: date) -> list[dict]:
    start = end - timedelta(days=6)
    totals = dict(WaterIntake.objects.filter(owner=owner, date__gte=start, date__lte=end).values_list("date").annotate(s=Sum("amount_ml")))
    target = target_ml(owner.preferences)
    return [{"date": (start + timedelta(days=i)).isoformat(), "total_ml": totals.get(start + timedelta(days=i), 0), "target_ml": target} for i in range(7)]


def _minutes_of_day(dt: datetime, zone, pivot: int = 12 * 60) -> int:
    """Minutes since local midnight, with times before noon shifted +24h so bedtimes around midnight average correctly."""
    local = dt.astimezone(zone)
    m = local.hour * 60 + local.minute
    return m + 24 * 60 if m < pivot else m


def sleep_summary(owner, days: int = 14) -> dict:
    zone = get_zone(owner.preferences.time_zone)
    today = local_today(zone)
    logs = list(SleepLog.objects.filter(owner=owner, date__gt=today - timedelta(days=days), date__lte=today))
    if not logs:
        return {"nights": 0, "average_minutes": None, "bedtime_spread_minutes": None, "average_quality": None}
    beds = [_minutes_of_day(log.bedtime_at, zone) for log in logs]
    return {
        "nights": len(logs),
        "average_minutes": round(sum(log.duration_minutes for log in logs) / len(logs)),
        # Consistency = standard deviation of bedtime in minutes (lower = more consistent). Needs ≥ 2 nights.
        "bedtime_spread_minutes": round(statistics.pstdev(beds)) if len(beds) >= 2 else None,
        "average_quality": SleepLog.objects.filter(pk__in=[log.pk for log in logs], quality__isnull=False).aggregate(a=Avg("quality"))["a"],
        "definitions": {
            "bedtime_spread_minutes": "Standard deviation of logged bedtimes over the period. A self-reported consistency indicator, not a clinical measure.",
        },
    }
