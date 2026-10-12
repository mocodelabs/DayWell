from django.apps import AppConfig


class AffirmationsConfig(AppConfig):
    name = "apps.affirmations"
    label = "affirmations"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import Affirmation, AffirmationFavorite, UserAffirmation

        register_export("custom_affirmations", lambda u: rows(Affirmation.objects.filter(owner=u), "id", "text", "category", "active"))
        register_export("affirmation_history", lambda u: rows(UserAffirmation.objects.filter(user=u), "date", "affirmation__text", "viewed_at", "acknowledged_at"))
        register_export("favorite_affirmations", lambda u: rows(AffirmationFavorite.objects.filter(user=u), "affirmation__text"))
