from django.apps import AppConfig


class HabitsConfig(AppConfig):
    name = "apps.habits"
    label = "habits"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import Habit, HabitCompletion

        register_export(
            "habits",
            lambda u: rows(
                Habit.objects.filter(owner=u),
                "id",
                "name",
                "description",
                "category",
                "icon",
                "target_type",
                "target_value",
                "unit",
                "schedule_rule",
                "times_per_week",
                "start_date",
                "time_zone",
                "reminder_time",
                "status",
                "paused_at",
                "created_at",
            ),
        )
        register_export("habit_completions", lambda u: rows(HabitCompletion.objects.filter(habit__owner=u), "habit_id", "date", "status", "value", "notes", "completed_at"))
