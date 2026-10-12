from django.apps import AppConfig


class RemindersConfig(AppConfig):
    name = "apps.reminders"
    label = "reminders"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import DeviceSubscription, Reminder, ReminderOccurrence

        register_export(
            "reminders",
            lambda u: rows(
                Reminder.objects.filter(owner=u, is_test=False),
                "id",
                "title",
                "message",
                "category",
                "kind",
                "priority",
                "dtstart_date",
                "dtstart_time",
                "rrule",
                "time_zone",
                "offset_minutes",
                "anchor",
                "task_id",
                "task_series_id",
                "event_id",
                "habit_id",
                "sound",
                "snooze_minutes",
                "bypass_quiet_hours",
                "repeat_until_ack",
                "enabled",
                "archived",
            ),
        )
        register_export(
            "reminder_history",
            lambda u: rows(
                ReminderOccurrence.objects.filter(owner=u).exclude(status__in=["scheduled", "cancelled"]),
                "id",
                "reminder_id",
                "title",
                "category",
                "status",
                "skip_reason",
                "scheduled_for",
                "fire_at",
                "sent_at",
                "delivered_at",
                "audio_status",
                "acted_at",
                "dismissed_at",
                "completed_at",
                "snoozed_until",
            ),
        )
        # Push endpoint/keys are deliberately excluded (device credentials, useless outside this server).
        register_export("push_devices", lambda u: rows(DeviceSubscription.objects.filter(owner=u), "device_label", "active", "created_at", "last_success_at"))
