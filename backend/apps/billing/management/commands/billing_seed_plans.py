from django.core.management.base import BaseCommand

from apps.billing.models import Plan

# Current price list (keep in step with the latest price migration, billing/0003).
PLANS = [
    ("monthly-kes", "Monthly (KES)", "monthly", "KES", 34_900, 1),
    ("annual-kes", "Annual (KES)", "annually", "KES", 349_000, 2),
    ("monthly-usd", "Monthly (USD)", "monthly", "USD", 499, 3),
    ("annual-usd", "Annual (USD)", "annually", "USD", 3_999, 4),
]


class Command(BaseCommand):
    help = "Create any missing plans from the current price list (e.g. after `flush`). Never changes existing plans."

    def handle(self, *args, **opts):
        created = 0
        for code, name, interval, currency, amount, sort in PLANS:
            _, made = Plan.objects.get_or_create(code=code, defaults={"name": name, "interval": interval, "currency": currency, "amount_minor": amount, "sort": sort})
            created += made
        self.stdout.write(f"{created} plan(s) created, {len(PLANS) - created} already present.")
