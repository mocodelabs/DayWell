from django.contrib import admin

from .models import BillingAccount, Payment, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "interval", "currency", "amount_minor", "paystack_plan_code", "active"]


@admin.register(BillingAccount)
class BillingAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "trial_ends_at", "paid_until", "renewal", "complimentary"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    exclude = ["paystack_email_token"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "user", "plan", "status", "channel", "amount_minor", "currency", "paid_at"]
    list_filter = ["status", "currency", "kind"]
    search_fields = ["reference", "user__email"]
    raw_id_fields = ["user"]
