"""Seed the four price points and give every existing user a fresh 14-day trial (so nobody is locked out on release)."""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

PLANS = [
    ("monthly-kes", "Monthly (KES)", "monthly", "KES", 49_900, 1),
    ("annual-kes", "Annual (KES)", "annually", "KES", 499_900, 2),
    ("monthly-usd", "Monthly (USD)", "monthly", "USD", 400, 3),
    ("annual-usd", "Annual (USD)", "annually", "USD", 4_500, 4),
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    BillingAccount = apps.get_model("billing", "BillingAccount")
    User = apps.get_model("accounts", "User")
    for code, name, interval, currency, amount, sort in PLANS:
        Plan.objects.update_or_create(code=code, defaults={"name": name, "interval": interval, "currency": currency, "amount_minor": amount, "sort": sort})
    now = timezone.now()
    for user in User.objects.filter(billing__isnull=True).only("id", "date_joined"):
        BillingAccount.objects.create(user=user, trial_ends_at=max(user.date_joined + timedelta(days=14), now + timedelta(days=14)))


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial"), ("accounts", "0002_alter_auditevent_kind")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
