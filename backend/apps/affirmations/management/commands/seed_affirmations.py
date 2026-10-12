from django.core.management.base import BaseCommand

from apps.affirmations.services import seed_library


class Command(BaseCommand):
    help = "Load the built-in affirmation library (idempotent)."

    def handle(self, *args, **options):
        self.stdout.write(f"Added {seed_library()} affirmations.")
