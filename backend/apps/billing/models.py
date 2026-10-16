"""Subscriptions: plans, one billing account per user (trial + paid access window), and an append-only payment log.

Access is a single window: Premium while ``now < max(trial_ends_at, paid_until)`` (or ``complimentary``). Every successful
charge extends ``paid_until`` by one plan interval from ``max(now, paid_until)`` so paying early never loses days.
Card payments can auto-renew through a Paystack subscription; M-Pesa (and any "pay once") payments simply buy a period.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    class Interval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        ANNUALLY = "annually", "Annual"

    code = models.SlugField(max_length=40, unique=True)  # e.g. "monthly-kes"
    name = models.CharField(max_length=80)
    interval = models.CharField(max_length=10, choices=Interval.choices)
    currency = models.CharField(max_length=3)  # ISO 4217, as Paystack expects (KES, USD)
    amount_minor = models.PositiveIntegerField(help_text="Price in the currency's subunit (cents).")
    paystack_plan_code = models.CharField(max_length=40, blank=True, help_text="Set by `manage.py billing_sync_plans`.")
    active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self) -> str:
        return self.code


class BillingAccount(models.Model):
    class Renewal(models.TextChoices):
        NONE = "none", "Pays per period"
        ACTIVE = "active", "Renews automatically"
        NON_RENEWING = "non_renewing", "Cancelled; access runs to the end of the period"
        ATTENTION = "attention", "Renewal payment failed"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="billing")
    trial_ends_at = models.DateTimeField()
    paid_until = models.DateTimeField(null=True, blank=True)
    complimentary = models.BooleanField(default=False, help_text="Premium without payment (demo/staff accounts).")
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    renewal = models.CharField(max_length=14, choices=Renewal.choices, default=Renewal.NONE)
    paystack_customer_code = models.CharField(max_length=40, blank=True, db_index=True)
    paystack_subscription_code = models.CharField(max_length=40, blank=True, db_index=True)
    paystack_email_token = models.CharField(max_length=60, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def access_until(self):
        return max(filter(None, [self.trial_ends_at, self.paid_until]))

    def state(self, now=None) -> str:
        now = now or timezone.now()
        if self.complimentary:
            return "complimentary"
        if self.paid_until and now < self.paid_until + self.grace():
            return "active"
        if now < self.trial_ends_at:
            return "trial"
        return "read_only"

    def grace(self) -> timedelta:
        # A card renewal is charged on the period's last day and confirmed by webhook; don't lock anyone out meanwhile.
        return timedelta(days=settings.BILLING_RENEWAL_GRACE_DAYS) if self.renewal == self.Renewal.ACTIVE else timedelta(0)

    def has_premium(self, now=None) -> bool:
        return self.state(now) != "read_only"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Paid"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"

    class Kind(models.TextChoices):
        CHECKOUT = "checkout", "Checkout"
        RENEWAL = "renewal", "Automatic renewal"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=20, default="paystack")
    reference = models.CharField(max_length=100, unique=True)  # idempotency key for verify + webhooks
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHECKOUT)
    auto_renew = models.BooleanField(default=False)
    amount_minor = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    channel = models.CharField(max_length=30, blank=True)  # card, mobile_money, ...
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
