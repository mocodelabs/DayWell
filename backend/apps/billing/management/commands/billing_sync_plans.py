from django.core.management.base import BaseCommand

from apps.billing.tasks import sync_plans


class Command(BaseCommand):
    help = "Create DayWell's plans in Paystack (needed for automatic card renewal) and store their plan codes. Idempotent."

    def handle(self, *args, **opts):
        result = sync_plans()
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")
        self.stdout.write("Done.")
