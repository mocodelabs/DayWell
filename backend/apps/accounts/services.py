"""Account business logic: audit trail, session tracking, lockout, verification and reset tokens, export, deletion."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.html import escape
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


def _send_email(user: User, *, kind: str, subject: str, intro: str, button: str, link: str, footer: str) -> bool:
    """Send a plain-text + HTML email. Never raises: a mail outage must not break the request or reveal anything.

    Logs contain the kind and user id only — never the address, the link or its token.
    """
    name = user.display_name or "there"
    text = f"Hi {name},\n\n{intro}\n\n{button}: {link}\n\n{footer}\n\n— DayWell"
    html = f"""<!doctype html><html><body style="margin:0;background:#f7f4ee;font-family:Arial,Helvetica,sans-serif;color:#2b2f2a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border-radius:16px;padding:28px">
<tr><td style="font-size:20px;font-weight:bold;color:#3f6b4f;padding-bottom:16px">DayWell</td></tr>
<tr><td style="font-size:15px;line-height:1.5;padding-bottom:20px">Hi {escape(name)},<br><br>{escape(intro)}</td></tr>
<tr><td style="padding-bottom:20px"><a href="{escape(link)}"
 style="display:inline-block;background:#3f6b4f;color:#ffffff;text-decoration:none;font-weight:bold;padding:12px 20px;border-radius:10px">
{escape(button)}</a></td></tr>
<tr><td style="font-size:13px;line-height:1.5;color:#5f655c">{escape(footer)}<br><br>
If the button doesn't work, copy this link into your browser:<br><span style="word-break:break-all">{escape(link)}</span></td></tr>
</table></td></tr></table></body></html>"""
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [user.email])
    message.attach_alternative(html, "text/html")
    try:
        message.send()
    except Exception as exc:  # SMTP down, bad credentials, timeout…
        logger.error("email not sent", extra={"kind": kind, "user_id": user.pk, "error": exc.__class__.__name__})
        return False
    logger.info("email sent", extra={"kind": kind, "user_id": user.pk})
    return True


def send_verification_email(user: User) -> bool:
    link = f"{settings.FRONTEND_URL}/verify-email?uid={uid_for(user)}&token={email_verification_token.make_token(user)}"
    return _send_email(
        user,
        kind="verify_email",
        subject="Confirm your DayWell email",
        intro="Please confirm the email address for your DayWell account.",
        button="Confirm my email",
        link=link,
        footer="If you didn't create a DayWell account, you can ignore this message.",
    )


def send_password_reset_email(user: User) -> bool:
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid_for(user)}&token={default_token_generator.make_token(user)}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    lifetime = f"{minutes // 60} hour{'s' if minutes >= 120 else ''}" if minutes >= 60 else f"{minutes} minutes"
    return _send_email(
        user,
        kind="password_reset",
        subject="Reset your DayWell password",
        intro="Someone (hopefully you) asked to reset your DayWell password. Choose a new one with the button below.",
        button="Choose a new password",
        link=link,
        footer=f"This link works once and expires in {lifetime}. If you didn't ask for it, ignore this email — your password won't change.",
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
