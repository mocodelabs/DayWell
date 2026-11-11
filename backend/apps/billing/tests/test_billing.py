"""Billing: trial → read-only, checkout, verify, webhooks (signature, idempotency, renewals), cancellation.

Paystack is never called: ``apps.billing.paystack._call`` is replaced per test.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.billing import paystack
from apps.billing.models import BillingAccount, Payment, Plan
from apps.billing.services import account_for

pytestmark = pytest.mark.django_db

SECRET = "sk_test_" + "x" * 40


@pytest.fixture(autouse=True)
def _paystack_key(settings):
    settings.PAYSTACK_SECRET_KEY = SECRET
    settings.FRONTEND_URL = "https://daywell.example"


def expire_trial(user):
    acct = account_for(user)
    acct.trial_ends_at = timezone.now() - timedelta(minutes=1)
    acct.save()
    return acct


def charge(payment, **over):
    data = {
        "status": "success",
        "reference": payment.reference,
        "amount": payment.amount_minor,
        "currency": payment.currency,
        "channel": "card",
        "customer": {"customer_code": "CUS_1", "email": payment.user.email},
    }
    data.update(over)
    return data


def signed_post(anon, body: dict, secret=SECRET):
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    return anon.post("/api/v1/billing/webhook/paystack/", data=raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig)


class TestTrialAndReadOnly:
    def test_new_user_gets_a_14_day_trial(self, api, user):
        res = api.get("/api/v1/billing/").json()
        assert res["state"] == "trial" and res["has_premium"] is True
        assert {p["code"] for p in res["plans"]} == {"monthly-kes", "annual-kes", "monthly-usd", "annual-usd"}
        acct = account_for(user)
        assert abs((acct.trial_ends_at - user.date_joined) - timedelta(days=14)) < timedelta(seconds=1)

    def test_prices_match_the_agreed_price_list(self):
        prices = {p.code: (p.currency, p.amount_minor) for p in Plan.objects.all()}
        assert prices == {"monthly-kes": ("KES", 34_900), "annual-kes": ("KES", 349_000), "monthly-usd": ("USD", 499), "annual-usd": ("USD", 3_999)}

    def test_after_trial_reads_work_but_writes_get_402(self, api, user):
        expire_trial(user)
        assert api.get("/api/v1/tasks/").status_code == 200
        res = api.post("/api/v1/tasks/", {"title": "Buy milk"})
        assert res.status_code == 402
        assert res.json()["error"]["code"] == "subscription_required"

    def test_read_only_still_allows_account_rights_and_settings(self, api, user):
        expire_trial(user)
        assert api.patch("/api/v1/preferences/", {"theme": "dark"}).status_code == 200
        assert api.get("/api/v1/account/export/").status_code == 200
        assert api.post("/api/v1/auth/logout/").status_code in (200, 204)

    def test_complimentary_and_paid_accounts_can_write(self, api, user):
        acct = expire_trial(user)
        acct.paid_until = timezone.now() + timedelta(days=3)
        acct.save()
        assert api.post("/api/v1/tasks/", {"title": "Paid"}).status_code == 201
        acct.paid_until = None
        acct.complimentary = True
        acct.save()
        assert api.post("/api/v1/tasks/", {"title": "Comp"}).status_code == 201

    def test_auto_renewing_subscription_gets_grace_while_renewal_settles(self, user):
        acct = expire_trial(user)
        acct.paid_until = timezone.now() - timedelta(days=1)
        acct.renewal = BillingAccount.Renewal.ACTIVE
        assert acct.state() == "active"
        acct.renewal = BillingAccount.Renewal.NONE
        assert acct.state() == "read_only"


class TestCheckout:
    def test_pay_once_in_kes_offers_card_and_mpesa(self, api, user):
        with mock.patch.object(paystack, "_call", return_value={"authorization_url": "https://checkout.paystack.com/abc"}) as call:
            res = api.post("/api/v1/billing/checkout/", {"plan": "monthly-kes", "auto_renew": False})
        assert res.status_code == 200 and res.json()["authorization_url"] == "https://checkout.paystack.com/abc"
        method, path, payload = call.call_args.args
        assert (method, path) == ("POST", "/transaction/initialize")
        assert payload["channels"] == ["card", "mobile_money"] and payload["currency"] == "KES" and payload["amount"] == 34_900
        assert "plan" not in payload
        assert payload["callback_url"] == "https://daywell.example/settings/billing"
        assert Payment.objects.get(reference=payload["reference"]).status == "pending"

    def test_usd_is_card_only(self, api):
        with mock.patch.object(paystack, "_call", return_value={"authorization_url": "u"}) as call:
            api.post("/api/v1/billing/checkout/", {"plan": "annual-usd"})
        assert call.call_args.args[2]["channels"] == ["card"]

    def test_auto_renew_passes_the_paystack_plan_and_cards_only(self, api):
        Plan.objects.filter(code="monthly-usd").update(paystack_plan_code="PLN_usd_m")
        with mock.patch.object(paystack, "_call", return_value={"authorization_url": "u"}) as call:
            api.post("/api/v1/billing/checkout/", {"plan": "monthly-usd", "auto_renew": True})
        payload = call.call_args.args[2]
        assert payload["plan"] == "PLN_usd_m" and payload["channels"] == ["card"]

    def test_auto_renew_needs_a_synced_plan(self, api):
        res = api.post("/api/v1/billing/checkout/", {"plan": "monthly-kes", "auto_renew": True})
        assert res.status_code == 409 and res.json()["error"]["code"] == "plan_not_synced"

    def test_checkout_without_keys_is_a_clear_503(self, api, settings):
        settings.PAYSTACK_SECRET_KEY = ""
        res = api.post("/api/v1/billing/checkout/", {"plan": "monthly-kes"})
        assert res.status_code == 503 and res.json()["error"]["code"] == "payments_not_configured"

    def test_checkout_works_in_read_only_mode(self, api, user):
        expire_trial(user)
        with mock.patch.object(paystack, "_call", return_value={"authorization_url": "u"}):
            assert api.post("/api/v1/billing/checkout/", {"plan": "monthly-kes"}).status_code == 200


def pending(user, code="monthly-kes", **kw):
    plan = Plan.objects.get(code=code)
    return Payment.objects.create(user=user, plan=plan, reference=kw.pop("reference", "dw_ref1"), amount_minor=plan.amount_minor, currency=plan.currency, **kw)


class TestVerify:
    def test_verified_payment_unlocks_one_period(self, api, user):
        expire_trial(user)
        p = pending(user)
        with mock.patch.object(paystack, "_call", return_value=charge(p, channel="mobile_money")):
            res = api.post("/api/v1/billing/verify/", {"reference": p.reference})
        assert res.status_code == 200
        body = res.json()
        assert body["payment"]["status"] == "success" and body["payment"]["channel"] == "mobile_money"
        assert body["billing"]["state"] == "active"
        acct = account_for(user)
        acct.refresh_from_db()
        assert timedelta(days=27) < acct.paid_until - timezone.now() < timedelta(days=32)
        assert acct.renewal == "none"  # M-Pesa / pay-once never auto-renews

    def test_verify_is_idempotent(self, api, user):
        p = pending(user)
        with mock.patch.object(paystack, "_call", return_value=charge(p)):
            api.post("/api/v1/billing/verify/", {"reference": p.reference})
            first = account_for(user).paid_until
            api.post("/api/v1/billing/verify/", {"reference": p.reference})
        acct = BillingAccount.objects.get(user=user)
        assert acct.paid_until == first

    def test_paying_early_stacks_onto_the_remaining_period(self, user):
        from apps.billing.services import apply_charge

        acct = account_for(user)
        acct.paid_until = timezone.now() + timedelta(days=10)
        acct.save()
        p = pending(user, "annual-kes")
        apply_charge(p, charge(p))
        acct.refresh_from_db()
        assert timedelta(days=374) < acct.paid_until - timezone.now() < timedelta(days=377)

    def test_amount_mismatch_is_rejected(self, api, user):
        p = pending(user)
        with mock.patch.object(paystack, "_call", return_value=charge(p, amount=100)):
            res = api.post("/api/v1/billing/verify/", {"reference": p.reference})
        assert res.status_code == 409 and res.json()["error"]["code"] == "payment_mismatch"
        p.refresh_from_db()
        assert p.status == "pending"

    def test_cannot_verify_someone_elses_payment(self, other_api, user):
        p = pending(user)
        assert other_api.post("/api/v1/billing/verify/", {"reference": p.reference}).status_code == 404

    def test_failed_payment_is_recorded_without_access(self, api, user):
        expire_trial(user)
        p = pending(user)
        with mock.patch.object(paystack, "_call", return_value=charge(p, status="failed")):
            res = api.post("/api/v1/billing/verify/", {"reference": p.reference})
        assert res.json()["payment"]["status"] == "failed" and res.json()["billing"]["state"] == "read_only"


class TestWebhook:
    def test_rejects_bad_signature(self, anon, user):
        p = pending(user)
        res = signed_post(anon, {"event": "charge.success", "data": charge(p)}, secret="wrong")
        assert res.status_code == 401
        p.refresh_from_db()
        assert p.status == "pending"

    def test_charge_success_applies_once_even_if_retried(self, anon, user):
        p = pending(user, auto_renew=True)
        body = {"event": "charge.success", "data": charge(p)}
        assert signed_post(anon, body).status_code == 200
        until = BillingAccount.objects.get(user=user).paid_until
        assert signed_post(anon, body).status_code == 200
        acct = BillingAccount.objects.get(user=user)
        assert acct.paid_until == until and acct.renewal == "active" and acct.paystack_customer_code == "CUS_1"

    def test_subscription_lifecycle_and_automatic_renewal(self, anon, user):
        Plan.objects.filter(code="monthly-usd").update(paystack_plan_code="PLN_usd_m")
        p = pending(user, "monthly-usd", auto_renew=True)
        signed_post(anon, {"event": "charge.success", "data": charge(p)})
        signed_post(anon, {"event": "subscription.create", "data": {"subscription_code": "SUB_1", "email_token": "tok", "customer": {"customer_code": "CUS_1"}}})
        acct = BillingAccount.objects.get(user=user)
        assert (acct.paystack_subscription_code, acct.renewal) == ("SUB_1", "active")
        first_end = acct.paid_until

        # Paystack charges the card itself a month later, with its own reference.
        renewal = {
            "status": "success",
            "reference": "T_renew_1",
            "amount": 499,
            "currency": "USD",
            "channel": "card",
            "plan": {"plan_code": "PLN_usd_m"},
            "customer": {"customer_code": "CUS_1"},
        }
        signed_post(anon, {"event": "charge.success", "data": renewal})
        acct.refresh_from_db()
        assert acct.paid_until > first_end
        assert Payment.objects.get(reference="T_renew_1").kind == "renewal"

        signed_post(anon, {"event": "subscription.not_renew", "data": {"subscription_code": "SUB_1"}})
        acct.refresh_from_db()
        assert acct.renewal == "non_renewing" and acct.state() == "active"  # keeps access to the end of the period

    def test_unknown_charge_is_acknowledged_and_ignored(self, anon):
        res = signed_post(anon, {"event": "charge.success", "data": {"status": "success", "reference": "nope", "amount": 1, "currency": "KES"}})
        assert res.status_code == 200 and not Payment.objects.filter(reference="nope").exists()


class TestCancelRenewal:
    def test_cancel_disables_the_paystack_subscription(self, api, user):
        acct = account_for(user)
        acct.renewal, acct.paystack_subscription_code, acct.paystack_email_token = "active", "SUB_1", "tok"
        acct.paid_until = timezone.now() + timedelta(days=20)
        acct.save()
        with mock.patch.object(paystack, "_call", return_value={}) as call:
            res = api.post("/api/v1/billing/cancel-renewal/")
        assert res.status_code == 200 and res.json()["renewal"] == "non_renewing" and res.json()["state"] == "active"
        assert call.call_args.args[:3] == ("POST", "/subscription/disable", {"code": "SUB_1", "token": "tok"})

    def test_nothing_to_cancel(self, api):
        assert api.post("/api/v1/billing/cancel-renewal/").status_code == 409


class TestPlanSync:
    def test_creates_missing_plans_and_reports_rejected_currencies(self):
        def fake(method, path, payload=None):
            if payload["currency"] == "USD":
                raise paystack.PaystackError("Currency not supported by merchant")
            return {"plan_code": f"PLN_{payload['interval']}"}

        from apps.billing.tasks import sync_plans

        with mock.patch.object(paystack, "_call", side_effect=fake):
            result = sync_plans()
            assert sync_plans() == {"monthly-usd": "not created: Currency not supported by merchant", "annual-usd": "not created: Currency not supported by merchant"}
        assert result["monthly-kes"] == "PLN_monthly" and result["annual-kes"] == "PLN_annually"
        assert Plan.objects.get(code="annual-kes").paystack_plan_code == "PLN_annually"

    def test_noop_without_keys(self, settings):
        from apps.billing.tasks import sync_plans

        settings.PAYSTACK_SECRET_KEY = ""
        assert sync_plans() == {"skipped": "payments not configured"}
