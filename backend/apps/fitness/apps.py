from django.apps import AppConfig


class FitnessConfig(AppConfig):
    name = "apps.fitness"
    label = "fitness"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import WorkoutRoutine, WorkoutSession

        register_export(
            "workout_routines", lambda u: rows(WorkoutRoutine.objects.filter(owner=u), "id", "name", "workout_type", "days", "time", "duration_minutes", "location", "active", "notes")
        )
        register_export(
            "workout_sessions",
            lambda u: rows(
                WorkoutSession.objects.filter(owner=u),
                "routine_id",
                "date",
                "started_at",
                "ended_at",
                "workout_type",
                "planned_minutes",
                "duration_minutes",
                "status",
                "distance",
                "distance_unit",
                "exercises",
                "effort",
                "notes",
            ),
        )
