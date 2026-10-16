import logging

from . import paystack
from .models import Plan

logger = logging.getLogger("daywell.billing")


def sync_plans() -> dict:
    """Create missing Paystack plans (needed for automatic card renewal). Idempotent; a no-op without a secret key."""
    if not paystack.configured():
        return {"skipped": "payments not configured"}
    result: dict[str, str] = {}
    for plan in Plan.objects.filter(active=True, paystack_plan_code=""):
        try:
            data = paystack.create_plan(name=f"DayWell {plan.name}", interval=plan.interval, amount_minor=plan.amount_minor, currency=plan.currency)
        except paystack.PaystackError as exc:
            # Typically a currency not enabled on the Paystack account (USD needs approval for Kenyan merchants).
            result[plan.code] = f"not created: {exc.detail}"
            continue
        plan.paystack_plan_code = data["plan_code"]
        plan.save(update_fields=["paystack_plan_code"])
        result[plan.code] = plan.paystack_plan_code
    if result:
        logger.info("paystack plans synced", extra={"result": result})
    return result


try:  # Celery deployments run the same job from beat
    from celery import shared_task

    sync_plans_task = shared_task(name="billing.sync_plans", ignore_result=True)(sync_plans)
except ImportError:  # pragma: no cover
    pass
