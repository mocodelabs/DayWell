from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    label = "events"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import CalendarEvent, EventException

        register_export(
            "calendar_events",
            lambda u: rows(
                CalendarEvent.objects.filter(owner=u),
                "id",
                "title",
                "description",
                "location",
                "meeting_url",
                "category_id",
                "all_day",
                "time_zone",
                "start_date",
                "start_time",
                "end_date",
                "end_time",
                "rrule",
                "status",
                "attendance",
                "created_at",
            ),
        )
        register_export(
            "calendar_event_exceptions",
            lambda u: rows(
                EventException.objects.filter(event__owner=u),
                "event_id",
                "original_key",
                "cancelled",
                "title",
                "start_date",
                "start_time",
                "end_date",
                "end_time",
                "attendance",
            ),
        )
