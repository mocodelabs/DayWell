"""Early-adopter prices: KES 349/mo, KES 3,490/yr, USD 4.99/mo, USD 39.99/yr.

Paystack plan amounts are immutable, so a changed price clears the stored plan code; the hourly `sync-billing-plans`
job then creates a new Paystack plan at the new amount. Existing auto-renewing subscribers stay on their old Paystack
plan (and price) until they cancel — Paystack does not move subscriptions between plans.
"""

from django.db import migrations

PRICES = {"monthly-kes": 34_900, "annual-kes": 349_000, "monthly-usd": 499, "annual-usd": 3_999}


def apply(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, amount in PRICES.items():
        plan = Plan.objects.filter(code=code).first()
        if plan and plan.amount_minor != amount:
            plan.amount_minor = amount
            plan.paystack_plan_code = ""
            plan.save(update_fields=["amount_minor", "paystack_plan_code"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_seed_plans_and_accounts")]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
