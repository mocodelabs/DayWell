from django.conf import settings
from django.contrib.auth import authenticate, login, logout, password_validation, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.preferences.serializers import UserPreferenceSerializer

from . import services
from .models import AuditEvent, User, UserSession
from .serializers import (
    AccountDeleteSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    UserSessionSerializer,
)


def me_payload(request) -> dict:
    user = request.user
    return {"user": UserSerializer(user).data, "preferences": UserPreferenceSerializer(user.preferences, context={"request": request}).data}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the CSRF cookie. The SPA calls this once on boot."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"ok": True})


@method_decorator(csrf_protect, name="dispatch")  # DRF skips CSRF for anonymous requests; login CSRF must be blocked
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        with transaction.atomic():
            user = User.objects.create_user(email=data["email"], password=data["password"], display_name=data.get("display_name", "").strip())
            if data.get("time_zone"):
                user.preferences.time_zone = data["time_zone"]
                user.preferences.save(update_fields=["time_zone", "updated_at"])
            services.audit(AuditEvent.Kind.REGISTER, request, user=user)
        services.send_verification_email(user)
        if not settings.REQUIRE_EMAIL_VERIFICATION:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            services.track_session(request, user)
            return Response(me_payload(request), status=status.HTTP_201_CREATED)
        return Response({"verification_required": True, "email": user.email}, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")  # DRF skips CSRF for anonymous requests; login CSRF must be blocked
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].strip().lower()
        if services.is_locked_out(email):
            return Response(
                {"error": {"code": "locked_out", "message": "Too many failed attempts. Please wait 15 minutes or reset your password.", "fields": {}}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        user = authenticate(request, email=email, password=ser.validated_data["password"])
        if user is None:
            services.record_failure(email)
            services.audit(AuditEvent.Kind.LOGIN_FAILED, request, user=None, email_domain=email.rsplit("@", 1)[-1])
            raise serializers.ValidationError({"non_field_errors": ["That email and password don't match."]})
        if settings.REQUIRE_EMAIL_VERIFICATION and user.email_verified_at is None:
            raise serializers.ValidationError({"non_field_errors": ["Please confirm your email address first. We've sent you a link."]})
        services.clear_failures(email)
        login(request, user)
        services.track_session(request, user)
        services.audit(AuditEvent.Kind.LOGIN, request, user=user)
        return Response(me_payload(request))


class LogoutView(APIView):
    def post(self, request):
        key = request.session.session_key
        services.audit(AuditEvent.Kind.LOGOUT, request)
        if key:
            UserSession.objects.filter(session_key=key).delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        key = request.session.session_key
        if key:
            UserSession.objects.filter(session_key=key, last_seen_at__lt=timezone.now() - timezone.timedelta(minutes=10)).update(last_seen_at=timezone.now())
        return Response(me_payload(request))

    def patch(self, request):
        ser = UserSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(me_payload(request))


class PasswordChangeView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    def post(self, request):
        ser = PasswordChangeSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)  # keep this session, invalidate others
        for key in UserSession.objects.filter(user=request.user).exclude(session_key=request.session.session_key).values_list("session_key", flat=True):
            services.revoke_session(request.user, key)
        services.audit(AuditEvent.Kind.PASSWORD_CHANGED, request)
        return Response({"ok": True})


@method_decorator(csrf_protect, name="dispatch")  # DRF skips CSRF for anonymous requests; login CSRF must be blocked
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        ser = PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=ser.validated_data["email"].strip(), is_active=True).first()
        if user is not None:
            services.send_password_reset_email(user)
            services.audit(AuditEvent.Kind.PASSWORD_RESET_REQUESTED, request, user=user)
        # Same answer whether or not the account exists (no account enumeration).
        return Response({"ok": True, "message": "If an account exists for that email, a reset link is on its way."})


@method_decorator(csrf_protect, name="dispatch")  # DRF skips CSRF for anonymous requests; login CSRF must be blocked
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = services.user_from_uid(ser.validated_data["uid"])
        if user is None or not default_token_generator.check_token(user, ser.validated_data["token"]):
            raise serializers.ValidationError({"non_field_errors": ["This reset link is invalid or has expired. Please request a new one."]})
        try:
            password_validation.validate_password(ser.validated_data["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        user.set_password(ser.validated_data["new_password"])
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()  # they proved control of the mailbox
        user.save(update_fields=["password", "email_verified_at"])
        for key in list(UserSession.objects.filter(user=user).values_list("session_key", flat=True)):
            services.revoke_session(user, key)
        services.clear_failures(user.email)
        services.audit(AuditEvent.Kind.PASSWORD_RESET, request, user=user)
        return Response({"ok": True})


@method_decorator(csrf_protect, name="dispatch")  # DRF skips CSRF for anonymous requests; login CSRF must be blocked
class EmailVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = EmailVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = services.user_from_uid(ser.validated_data["uid"])
        if user is None or not services.email_verification_token.check_token(user, ser.validated_data["token"]):
            raise serializers.ValidationError({"non_field_errors": ["This verification link is invalid or has expired."]})
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
            services.audit(AuditEvent.Kind.EMAIL_VERIFIED, request, user=user)
        return Response({"ok": True})


class EmailVerifyResendView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        if request.user.email_verified_at is None:
            services.send_verification_email(request.user)
        return Response({"ok": True})


class SessionListView(APIView):
    def get(self, request):
        qs = UserSession.objects.filter(user=request.user, expires_at__gt=timezone.now())
        return Response(UserSessionSerializer(qs, many=True, context={"request": request}).data)


class SessionRevokeView(APIView):
    def delete(self, request, session_key: str):
        if session_key == request.session.session_key:
            raise serializers.ValidationError({"non_field_errors": ["Use sign out to end the current session."]})
        if not services.revoke_session(request.user, session_key):
            return Response(status=status.HTTP_404_NOT_FOUND)
        services.audit(AuditEvent.Kind.SESSION_REVOKED, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExportView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    def get(self, request):
        payload = services.export_user_data(request.user)
        services.audit(AuditEvent.Kind.DATA_EXPORTED, request)
        response = Response(payload)
        response["Content-Disposition"] = f'attachment; filename="daywell-export-{timezone.now():%Y%m%d}.json"'
        return response


class AccountDeleteView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    def post(self, request):
        ser = AccountDeleteSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        user = request.user
        logout(request)
        services.delete_account(user, request)
        return Response(status=status.HTTP_204_NO_CONTENT)
