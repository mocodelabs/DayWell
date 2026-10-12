from django.apps import AppConfig


class TasksConfig(AppConfig):
    name = "apps.tasks"
    label = "tasks"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import Category, Task, TaskActivity, TaskSeries, TaskSubtask

        register_export("categories", lambda u: rows(Category.objects.filter(owner=u), "id", "name", "color", "icon", "archived"))
        register_export(
            "tasks",
            lambda u: rows(
                Task.objects.filter(owner=u),
                "id",
                "title",
                "description",
                "notes",
                "priority",
                "important",
                "status",
                "category_id",
                "tags",
                "scheduled_date",
                "scheduled_time",
                "time_zone",
                "duration_minutes",
                "deadline",
                "link_url",
                "completed_at",
                "postponed_count",
                "series_id",
                "occurrence_date",
                "deleted_at",
                "created_at",
                "updated_at",
            ),
        )
        register_export("task_subtasks", lambda u: rows(TaskSubtask.objects.filter(task__owner=u), "task_id", "title", "position", "done", "done_at"))
        register_export("task_series", lambda u: rows(TaskSeries.objects.filter(owner=u), "id", "title", "rrule", "dtstart", "time_zone", "active", "checklist"))
        register_export("task_activity", lambda u: rows(TaskActivity.objects.filter(task__owner=u), "task_id", "kind", "at", "from_date", "to_date"))
