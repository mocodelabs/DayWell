from django.apps import AppConfig


class InsightsConfig(AppConfig):
    name = "apps.insights"
    label = "insights"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import Goal, GoalCheckIn, WeeklyReview

        register_export(
            "goals",
            lambda u: rows(
                Goal.objects.filter(owner=u), "id", "title", "description", "metric", "habit_id", "target_value", "unit", "current_value", "start_date", "due_date", "status", "completed_at"
            ),
        )
        register_export("goal_check_ins", lambda u: rows(GoalCheckIn.objects.filter(goal__owner=u), "goal_id", "date", "value", "note"))
        register_export(
            "weekly_reviews",
            lambda u: rows(WeeklyReview.objects.filter(owner=u), "week_start", "went_well", "challenges", "next_focus", "wins", "adjustments", "stats_snapshot", "completed_at"),
        )
