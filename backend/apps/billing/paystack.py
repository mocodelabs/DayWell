"""Minimal Paystack REST client (https://paystack.com/docs/api/). The secret key never leaves the server or the logs."""

from __future__ import annotations

import hashlib
import hmac
import logging

import requests
from django.conf import settings

from apps.core.exceptions import BusinessRuleError

logger = logging.getLogger("daywell.billing")

BASE_URL = "https://api.paystack.co"


class PaystackError(BusinessRuleError):
    status_code = 502
    default_code = "payment_provider_error"
    default_detail = "We couldn't reach the payment provider. You haven't been charged — please try again."


def configured() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


def _call(method: str, path: str, payload: dict | None = None) -> dict:
    if not configured():
        raise BusinessRuleError("Payments aren't set up yet.", code="payments_not_configured", status_code=503)
    try:
        res = requests.request(
            method,
            BASE_URL + path,
            json=payload,
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
            timeout=15,
        )
        body = res.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("paystack request failed", extra={"path": path, "error": exc.__class__.__name__})
        raise PaystackError() from exc
    if res.status_code >= 400 or not body.get("status"):
        # Paystack's message is safe to log (no secrets); it often explains config problems (e.g. currency not enabled).
        logger.warning("paystack rejected request", extra={"path": path, "http_status": res.status_code, "provider_message": body.get("message")})
        raise PaystackError(body.get("message") or None)
    return body["data"]


def initialize(*, email: str, amount_minor: int, currency: str, reference: str, callback_url: str, channels: list[str], plan_code: str = "", metadata: dict | None = None) -> dict:
    payload = {"email": email, "amount": amount_minor, "currency": currency, "reference": reference, "callback_url": callback_url, "channels": channels, "metadata": metadata or {}}
    if plan_code:
        payload["plan"] = plan_code  # Paystack creates the subscription on success (cards only)
    return _call("POST", "/transaction/initialize", payload)


def verify(reference: str) -> dict:
    return _call("GET", f"/transaction/verify/{requests.utils.quote(reference, safe='')}")


def create_plan(*, name: str, interval: str, amount_minor: int, currency: str) -> dict:
    return _call("POST", "/plan", {"name": name, "interval": interval, "amount": amount_minor, "currency": currency})


def disable_subscription(*, code: str, email_token: str) -> dict:
    return _call("POST", "/subscription/disable", {"code": code, "token": email_token})


def valid_signature(raw_body: bytes, signature: str) -> bool:
    """Webhooks are signed with HMAC-SHA512 of the raw body using the secret key (header ``x-paystack-signature``)."""
    if not configured() or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
