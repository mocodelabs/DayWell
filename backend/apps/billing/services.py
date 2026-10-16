"""Billing rules: trials, checkout, applying charges (idempotent), renewals and cancellation."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AuditEvent
from apps.accounts.services import audit
from apps.core.exceptions import BusinessRuleError

from . import paystack
from .models import BillingAccount, Payment, Plan

logger = logging.getLogger("daywell.billing")


def account_for(user) -> BillingAccount:
    """Every user has one billing account; the trial starts when the account was created."""
    try:
        return user.billing
    except BillingAccount.DoesNotExist:
        pass
    acct, _ = BillingAccount.objects.get_or_create(user=user, defaults={"trial_ends_at": user.date_joined + timedelta(days=settings.BILLING_TRIAL_DAYS)})
    return acct


def _period_delta(plan: Plan) -> relativedelta:
    return relativedelta(years=1) if plan.interval == Plan.Interval.ANNUALLY else relativedelta(months=1)


def channels_for(plan: Plan, auto_renew: bool) -> list[str]:
    if auto_renew:
        return ["card"]  # Paystack subscriptions charge cards only
    return ["card", "mobile_money"] if plan.currency == "KES" else ["card"]  # M-Pesa is KES only


def start_checkout(user, plan: Plan, *, auto_renew: bool) -> dict:
    if not plan.active:
        raise BusinessRuleError("That plan is no longer available.", code="plan_unavailable")
    acct = account_for(user)
    if auto_renew and acct.renewal == BillingAccount.Renewal.ACTIVE:
        raise BusinessRuleError("You already have a subscription that renews automatically.", code="already_subscribed")
    if auto_renew and not plan.paystack_plan_code:
        raise BusinessRuleError("Automatic renewal isn't available for this plan yet. Choose 'Pay once' instead.", code="plan_not_synced")
    reference = f"dw_{uuid.uuid4().hex}"
    Payment.objects.create(user=user, plan=plan, reference=reference, auto_renew=auto_renew, amount_minor=plan.amount_minor, currency=plan.currency)
    data = paystack.initialize(
        email=user.email,
        amount_minor=plan.amount_minor,
        currency=plan.currency,
        reference=reference,
        callback_url=f"{settings.FRONTEND_URL.rstrip('/')}/settings/billing",
        channels=channels_for(plan, auto_renew),
        plan_code=plan.paystack_plan_code if auto_renew else "",
        metadata={"user_id": user.pk, "plan": plan.code, "auto_renew": auto_renew},
    )
    return {"authorization_url": data["authorization_url"], "reference": reference}


@transaction.atomic
def apply_charge(payment: Payment, data: dict) -> Payment:
    """Record a provider-confirmed charge exactly once and extend access. ``data`` is Paystack's transaction object."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCESS:
        return payment  # verify + webhook (or a retried webhook) both arrive; only the first counts
    status = data.get("status")
    if status != "success":
        if status in ("failed", "abandoned"):
            payment.status = status
            payment.save(update_fields=["status"])
        return payment
    # Never trust the browser: the confirmed amount and currency must match what we asked for.
    if int(data.get("amount", -1)) != payment.amount_minor or str(data.get("currency", "")).upper() != payment.currency:
        logger.error("paystack charge does not match payment", extra={"reference": payment.reference})
        raise BusinessRuleError("This payment doesn't match the selected plan. Contact support; you won't be charged twice.", code="payment_mismatch")

    acct = BillingAccount.objects.select_for_update().get(pk=account_for(payment.user).pk)
    now = timezone.now()
    start = max(now, acct.paid_until) if acct.paid_until else now
    end = start + _period_delta(payment.plan)
    payment.status = Payment.Status.SUCCESS
    payment.channel = str(data.get("channel") or "")[:30]
    payment.paid_at = now
    payment.period_start, payment.period_end = start, end
    payment.save()

    acct.paid_until = end
    acct.plan = payment.plan
    customer = (data.get("customer") or {}).get("customer_code")
    if customer:
        acct.paystack_customer_code = customer
    if payment.auto_renew and acct.renewal != BillingAccount.Renewal.ACTIVE:
        acct.renewal = BillingAccount.Renewal.ACTIVE
    acct.save()
    audit(AuditEvent.Kind.BILLING_PAYMENT, user=payment.user, plan=payment.plan.code, payment_kind=payment.kind, channel=payment.channel)
    return payment


def verify_reference(user, reference: str) -> Payment:
    payment = Payment.objects.filter(user=user, reference=reference).select_related("plan").first()
    if payment is None:
        raise BusinessRuleError("We couldn't find that payment.", code="not_found", status_code=404)
    if payment.status == Payment.Status.SUCCESS:
        return payment
    return apply_charge(payment, paystack.verify(reference))


# --- Webhooks -------------------------------------------------------------------------------------------------------


def _account_from_event(data: dict) -> BillingAccount | None:
    sub = data.get("subscription_code") or (data.get("subscription") or {}).get("subscription_code") or ""
    if sub:
        acct = BillingAccount.objects.filter(paystack_subscription_code=sub).first()
        if acct:
            return acct
    customer = data.get("customer") or {}
    if customer.get("customer_code"):
        acct = BillingAccount.objects.filter(paystack_customer_code=customer["customer_code"]).first()
        if acct:
            return acct
    if customer.get("email"):
        return BillingAccount.objects.filter(user__email__iexact=customer["email"]).first()
    return None


def handle_event(event: str, data: dict) -> str:
    """Process a verified Paystack webhook. Returns a short outcome label (logged, never shown to users)."""
    if event == "charge.success":
        reference = data.get("reference") or ""
        payment = Payment.objects.filter(reference=reference).first()
        if payment is None:
            # A renewal Paystack charged on its own: create the payment record, then apply it once.
            plan_code = (data.get("plan") or {}).get("plan_code") if isinstance(data.get("plan"), dict) else None
            plan = Plan.objects.filter(paystack_plan_code=plan_code).first() if plan_code else None
            acct = _account_from_event(data)
            if not (plan and acct):
                return "ignored: unknown charge"
            payment, _ = Payment.objects.get_or_create(
                reference=reference,
                defaults={"user": acct.user, "plan": plan, "kind": Payment.Kind.RENEWAL, "auto_renew": True, "amount_minor": plan.amount_minor, "currency": plan.currency},
            )
        apply_charge(payment, data)
        return "charge applied"

    if event == "subscription.create":
        acct = _account_from_event(data)
        if not acct:
            return "ignored: unknown customer"
        acct.paystack_subscription_code = data.get("subscription_code") or acct.paystack_subscription_code
        acct.paystack_email_token = data.get("email_token") or acct.paystack_email_token
        acct.renewal = BillingAccount.Renewal.ACTIVE
        acct.save(update_fields=["paystack_subscription_code", "paystack_email_token", "renewal", "updated_at"])
        return "subscription linked"

    if event in ("subscription.not_renew", "subscription.disable"):
        acct = _account_from_event(data)
        if not acct:
            return "ignored: unknown subscription"
        acct.renewal = BillingAccount.Renewal.NON_RENEWING if event == "subscription.not_renew" else BillingAccount.Renewal.NONE
        acct.save(update_fields=["renewal", "updated_at"])
        return "renewal stopped"

    if event == "invoice.payment_failed":
        acct = _account_from_event(data)
        if acct:
            acct.renewal = BillingAccount.Renewal.ATTENTION
            acct.save(update_fields=["renewal", "updated_at"])
        return "renewal failed"
    return "ignored"


def cancel_renewal(user) -> BillingAccount:
    acct = account_for(user)
    if acct.renewal not in (BillingAccount.Renewal.ACTIVE, BillingAccount.Renewal.ATTENTION) or not acct.paystack_subscription_code:
        raise BusinessRuleError("There's no automatic renewal to cancel.", code="no_subscription")
    paystack.disable_subscription(code=acct.paystack_subscription_code, email_token=acct.paystack_email_token)
    acct.renewal = BillingAccount.Renewal.NON_RENEWING
    acct.save(update_fields=["renewal", "updated_at"])
    audit(AuditEvent.Kind.BILLING_RENEWAL_CANCELLED, user=user)
    return acct
