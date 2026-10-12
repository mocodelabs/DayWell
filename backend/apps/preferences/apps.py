from django.apps import AppConfig


class PreferencesConfig(AppConfig):
    name = "apps.preferences"
    label = "preferences"

    def ready(self) -> None:
        from django.conf import settings
        from django.db.models.signals import post_save

        from apps.core.registry import register_export, rows

        from .models import NotificationPreference, UserPreference
        from .services import ensure_defaults

        def on_user_created(sender, instance, created, **kwargs):
            if created:
                ensure_defaults(instance)

        post_save.connect(on_user_created, sender=settings.AUTH_USER_MODEL, weak=False, dispatch_uid="preferences_defaults")
        pref_fields = [f.name for f in UserPreference._meta.fields if f.name not in ("id", "user")]
        register_export("preferences", lambda u: rows(UserPreference.objects.filter(user=u), *pref_fields))
        register_export(
            "notification_preferences",
            lambda u: rows(
                NotificationPreference.objects.filter(user=u),
                "category",
                "enabled",
                "channels",
                "sound",
                "snooze_minutes",
                "bypass_quiet_hours",
                "min_gap_minutes",
            ),
        )
