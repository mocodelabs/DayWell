"""Read-only mode: once the trial and any paid period are over, the account can read but not change its data."""

from rest_framework import exceptions, permissions, status

# Changes that stay possible without Premium: signing in/out, profile and password, data export and account deletion
# (data rights), subscribing, preferences, push registration, and acting on alarms that are already ringing.
ALWAYS_ALLOWED_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/account/",
    "/api/v1/billing/",
    "/api/v1/preferences/",
    "/api/v1/push/",
    "/api/v1/alarms/",
    "/api/v1/notifications/",
)


class SubscriptionRequired(exceptions.APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "subscription_required"
    default_detail = "Your free trial has ended, so DayWell is read-only. Subscribe to add or change things — everything you've saved is still here."


class PremiumOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS or not request.user.is_authenticated:
            return True
        if request.path.startswith(ALWAYS_ALLOWED_PREFIXES):
            return True
        from .services import account_for

        if account_for(request.user).has_premium():
            return True
        raise SubscriptionRequired()
