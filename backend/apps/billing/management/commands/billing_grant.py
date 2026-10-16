from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.services import account_for


class Command(BaseCommand):
    help = "Give an account complimentary Premium (demo/staff), extend its trial, or revoke complimentary access."

    def add_arguments(self, parser):
        parser.add_argument("email")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--complimentary", action="store_true")
        group.add_argument("--revoke", action="store_true")
        group.add_argument("--trial-days", type=int)

    def handle(self, *args, email, complimentary, revoke, trial_days, **opts):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No user {email}")
        acct = account_for(user)
        if trial_days is not None:
            acct.trial_ends_at = timezone.now() + timedelta(days=trial_days)
        else:
            acct.complimentary = complimentary
        acct.save()
        self.stdout.write(f"{email}: {acct.state()}")
