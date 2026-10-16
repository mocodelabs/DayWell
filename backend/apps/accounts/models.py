from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email: str):
        return self.get(email__iexact=email)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]

    def __str__(self) -> str:
        return self.email

    @property
    def greeting_name(self) -> str:
        return self.display_name.strip() or ""


class UserSession(models.Model):
    """Tracks a login so the user can see and revoke their active sessions."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    user_agent = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_seen_at"]


class AuditEvent(models.Model):
    """Security-relevant account events. Never stores passwords, tokens or private content."""

    class Kind(models.TextChoices):
        REGISTER = "register"
        LOGIN = "login"
        LOGIN_FAILED = "login_failed"
        LOGOUT = "logout"
        PASSWORD_CHANGED = "password_changed"
        PASSWORD_RESET_REQUESTED = "password_reset_requested"
        PASSWORD_RESET = "password_reset"
        EMAIL_VERIFIED = "email_verified"
        SESSION_REVOKED = "session_revoked"
        DATA_EXPORTED = "data_exported"
        ACCOUNT_DELETED = "account_deleted"
        PUSH_SUBSCRIBED = "push_subscribed"
        PUSH_UNSUBSCRIBED = "push_unsubscribed"
        BILLING_PAYMENT = "billing_payment"
        BILLING_RENEWAL_CANCELLED = "billing_renewal_cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    kind = models.CharField(max_length=40, choices=Kind.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
