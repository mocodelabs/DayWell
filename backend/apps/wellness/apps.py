from django.apps import AppConfig


class WellnessConfig(AppConfig):
    name = "apps.wellness"
    label = "wellness"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import JournalEntry, MindfulnessSession, SleepLog, WaterIntake

        register_export("water_intake", lambda u: rows(WaterIntake.objects.filter(owner=u), "date", "at", "amount_ml"))
        register_export("sleep_logs", lambda u: rows(SleepLog.objects.filter(owner=u), "date", "bedtime_at", "wake_at", "duration_minutes", "quality", "notes"))
        register_export("journal_entries", lambda u: rows(JournalEntry.objects.filter(owner=u), "date", "title", "body", "gratitude", "mood", "prompt", "tags", "created_at"))
        register_export("mindfulness_sessions", lambda u: rows(MindfulnessSession.objects.filter(owner=u), "date", "kind", "planned_seconds", "completed_seconds", "notes"))
