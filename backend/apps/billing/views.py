import json
import logging

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import paystack, services
from .models import Payment, Plan

logger = logging.getLogger("daywell.billing")


class PlanSerializer(serializers.ModelSerializer):
    auto_renew_available = serializers.SerializerMethodField()
    mpesa_available = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ["code", "name", "interval", "currency", "amount_minor", "auto_renew_available", "mpesa_available"]

    def get_auto_renew_available(self, plan) -> bool:
        return bool(plan.paystack_plan_code)

    def get_mpesa_available(self, plan) -> bool:
        return plan.currency == "KES"


class PaymentSerializer(serializers.ModelSerializer):
    plan = serializers.CharField(source="plan.code")

    class Meta:
        model = Payment
        fields = ["reference", "plan", "kind", "auto_renew", "amount_minor", "currency", "status", "channel", "period_start", "period_end", "paid_at", "created_at"]


def billing_status(user) -> dict:
    acct = services.account_for(user)
    now = timezone.now()
    state = acct.state(now)
    return {
        "state": state,
        "has_premium": state != "read_only",
        "trial_ends_at": acct.trial_ends_at,
        "paid_until": acct.paid_until,
        "renewal": acct.renewal,
        "plan": acct.plan.code if acct.plan else None,
        "payments_enabled": paystack.configured(),
        "plans": PlanSerializer(Plan.objects.filter(active=True), many=True).data,
        "payments": PaymentSerializer(user.payments.exclude(status=Payment.Status.PENDING).select_related("plan")[:20], many=True).data,
    }


class BillingView(APIView):
    def get(self, request):
        return Response(billing_status(request.user))


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="code", queryset=Plan.objects.filter(active=True))
    auto_renew = serializers.BooleanField(default=False)


class CheckoutView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive"

    def post(self, request):
        s = CheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(services.start_checkout(request.user, s.validated_data["plan"], auto_renew=s.validated_data["auto_renew"]))


class VerifySerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100)


class VerifyView(APIView):
    def post(self, request):
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payment = services.verify_reference(request.user, s.validated_data["reference"])
        return Response({"payment": PaymentSerializer(payment).data, "billing": billing_status(request.user)})


class CancelRenewalView(APIView):
    def post(self, request):
        services.cancel_renewal(request.user)
        return Response(billing_status(request.user))


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
@throttle_classes([])
def webhook(request):
    """Paystack → DayWell events. Authenticated by the HMAC signature only; always 200 once verified (Paystack retries otherwise)."""
    raw = request.body
    if not paystack.valid_signature(raw, request.headers.get("x-paystack-signature", "")):
        return Response({"detail": "invalid signature"}, status=401)
    try:
        payload = json.loads(raw)
        outcome = services.handle_event(str(payload.get("event", "")), payload.get("data") or {})
    except Exception:
        logger.exception("paystack webhook failed")
        return Response({"detail": "error"}, status=500)  # Paystack retries; processing is idempotent
    logger.info("paystack webhook", extra={"event": payload.get("event"), "outcome": outcome})
    return Response({"ok": True})
