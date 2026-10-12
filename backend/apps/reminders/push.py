"""Web Push (RFC 8030/8291/8292) via pywebpush. A 201 from the push service means *accepted*, not displayed."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core import signing

from apps.core.crypto import decrypt, encrypt, sha256_hex

from .models import DeviceSubscription

logger = logging.getLogger("daywell.push")
RECEIPT_SALT = "daywell.push-receipt"
RECEIPT_MAX_AGE = 60 * 60 * 48


def push_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


@dataclass
class PushResult:
    ok: bool
    status: int | None = None
    transient: bool = False
    expired: bool = False
    error: str = ""
    ref: str = ""


def store_subscription(owner, endpoint: str, p256dh: str, auth: str, *, label: str = "", user_agent: str = "") -> DeviceSubscription:
    digest = sha256_hex(endpoint)
    sub = DeviceSubscription.objects.filter(endpoint_hash=digest).first()
    keys = encrypt(json.dumps({"p256dh": p256dh, "auth": auth}))
    if sub is None:
        return DeviceSubscription.objects.create(
            owner=owner,
            endpoint_hash=digest,
            endpoint_encrypted=encrypt(endpoint),
            keys_encrypted=keys,
            device_label=label[:120],
            user_agent=user_agent[:300],
        )
    # Same browser endpoint re-subscribed (possibly by a different account on a shared device): it now belongs to `owner`.
    sub.owner = owner
    sub.keys_encrypted = keys
    sub.active = True
    sub.failure_count = 0
    sub.device_label = label[:120] or sub.device_label
    sub.user_agent = user_agent[:300] or sub.user_agent
    sub.save()
    return sub


def subscription_info(sub: DeviceSubscription) -> dict:
    return {"endpoint": decrypt(sub.endpoint_encrypted), "keys": json.loads(decrypt(sub.keys_encrypted))}


def receipt_token(occurrence_id: int, delivery_id: int) -> str:
    return signing.dumps({"o": occurrence_id, "d": delivery_id}, salt=RECEIPT_SALT, compress=True)


def read_receipt_token(token: str) -> tuple[int, int] | None:
    try:
        data = signing.loads(token, salt=RECEIPT_SALT, max_age=RECEIPT_MAX_AGE)
        return int(data["o"]), int(data["d"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def send(sub: DeviceSubscription, payload: dict) -> PushResult:
    """Send one push message. Never raises for delivery problems — they are classified and returned."""
    from pywebpush import WebPushException, webpush

    if not push_configured():
        return PushResult(ok=False, error="Web Push is not configured on the server (VAPID keys missing).")
    try:
        info = subscription_info(sub)
    except ValueError as exc:
        return PushResult(ok=False, expired=True, error=str(exc))
    try:
        response = webpush(
            subscription_info=info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=settings.WEB_PUSH_TTL,
            timeout=10,
            headers={"Urgency": "high"},
        )
        status = getattr(response, "status_code", 201)
        return PushResult(ok=200 <= status < 300, status=status, ref=(getattr(response, "headers", {}) or {}).get("Location", "")[:300])
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None) if exc.response is not None else None
        expired = status in (404, 410)
        transient = status is None or status == 429 or status >= 500
        logger.warning("push failed", extra={"status": status, "subscription_id": sub.id, "expired": expired})
        return PushResult(ok=False, status=status, transient=transient, expired=expired, error=f"Push service responded {status}" if status else "Network error")
    except Exception as exc:  # network errors from requests, TLS, etc.
        logger.warning("push transport error", extra={"subscription_id": sub.id, "error": exc.__class__.__name__})
        return PushResult(ok=False, transient=True, error=f"Transport error: {exc.__class__.__name__}")
