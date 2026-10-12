from django.contrib import admin

from .models import AuditEvent, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "display_name", "is_active", "date_joined"]
    search_fields = ["email", "display_name"]
    exclude = ["password"]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "user", "ip_address"]
    list_filter = ["kind"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]
