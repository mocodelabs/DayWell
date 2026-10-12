"""Account business logic: audit trail, session tracking, lockout, verification and reset tokens, export, deletion."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.throttling import BaseThrottle

from .models import AuditEvent, User, UserSession

logger = logging.getLogger("daywell.accounts")

LOCKOUT_FAILURES = 8
LOCKOUT_WINDOW = 15 * 60


def client_ip(request) -> str | None:
    """Client IP honouring REST_FRAMEWORK['NUM_PROXIES'] (so X-Forwarded-For cannot be spoofed past the proxy count)."""
    ident = BaseThrottle().get_ident(request)
    return ident or None


def audit(kind: str, request=None, user: User | None = None, **metadata) -> None:
    AuditEvent.objects.create(
        user=user if user is not None else (request.user if request is not None and request.user.is_authenticated else None),
        kind=kind,
        ip_address=client_ip(request) if request is not None else None,
        user_agent=(request.headers.get("User-Agent", "")[:300] if request is not None else ""),
        metadata=metadata,
    )


# --- Login lockout (per account, on top of per-IP throttling) ---


def _lock_key(email: str) -> str:
    return f"auth:fail:{email.lower()}"


def is_locked_out(email: str) -> bool:
    return (cache.get(_lock_key(email)) or 0) >= LOCKOUT_FAILURES


def record_failure(email: str) -> None:
    key = _lock_key(email)
    try:
        cache.add(key, 0, LOCKOUT_WINDOW)
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, LOCKOUT_WINDOW)


def clear_failures(email: str) -> None:
    cache.delete(_lock_key(email))


def track_session(request, user: User) -> None:
    if not request.session.session_key:
        request.session.save()
    UserSession.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={
            "user": user,
            "user_agent": request.headers.get("User-Agent", "")[:300],
            "ip_address": client_ip(request),
            "last_seen_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE),
        },
    )


def destroy_session(session_key: str) -> None:
    """Delete a session through the configured engine so cached copies (cached_db → Redis) are removed too."""
    from importlib import import_module

    import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key).delete()


def revoke_session(user: User, session_key: str) -> bool:
    deleted, _ = UserSession.objects.filter(user=user, session_key=session_key).delete()
    destroy_session(session_key)
    return bool(deleted)


# --- Email verification & password reset ---


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "daywell.accounts.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified_at}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()


def uid_for(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def user_from_uid(uid: str) -> User | None:
    try:
        return User.objects.get(pk=int(force_str(urlsafe_base64_decode(uid))))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def send_verification_email(user: User) -> None:
    link = f"{settings.FRONTEND_URL}/verify-email?uid={uid_for(user)}&token={email_verification_token.make_token(user)}"
    send_mail(
        "Confirm your DayWell email",
        f"Hi{(' ' + user.display_name) if user.display_name else ''},\n\nPlease confirm your email address:\n{link}\n\nIf you didn't create a DayWell account you can ignore this message.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def send_password_reset_email(user: User) -> None:
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid_for(user)}&token={default_token_generator.make_token(user)}"
    send_mail(
        "Reset your DayWell password",
        f"Someone (hopefully you) asked to reset your DayWell password.\n\nChoose a new password here:\n{link}\n\n"
        "This link expires in a few days. If you didn't ask for it, you can ignore this email — your password won't change.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


# --- Export & deletion ---


def export_user_data(user: User) -> dict:
    from apps.core.registry import export_all

    return {
        "format": "daywell-export",
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "account": {"email": user.email, "display_name": user.display_name, "date_joined": user.date_joined.isoformat()},
        "data": export_all(user),
    }


@transaction.atomic
def delete_account(user: User, request=None) -> None:
    """Hard-deletes the user and every owned record (FK CASCADE). Leaves a single anonymous audit row."""
    for key in UserSession.objects.filter(user=user).values_list("session_key", flat=True):
        destroy_session(key)
    user_id = user.pk
    user.delete()
    AuditEvent.objects.create(user=None, kind=AuditEvent.Kind.ACCOUNT_DELETED, metadata={"former_user_id": user_id}, ip_address=client_ip(request) if request else None)
    logger.info("account deleted", extra={"former_user_id": user_id})
