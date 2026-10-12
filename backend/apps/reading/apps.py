from django.apps import AppConfig


class ReadingConfig(AppConfig):
    name = "apps.reading"
    label = "reading"

    def ready(self) -> None:
        from apps.core.registry import register_export, rows

        from .models import Book, BookNote, ReadingSession

        register_export(
            "books",
            lambda u: rows(
                Book.objects.filter(owner=u),
                "id",
                "title",
                "author",
                "cover_url",
                "category",
                "status",
                "total_pages",
                "current_page",
                "start_date",
                "target_date",
                "completed_date",
                "rating",
                "notes",
                "review",
            ),
        )
        register_export("book_notes", lambda u: rows(BookNote.objects.filter(book__owner=u), "book_id", "kind", "text", "page", "created_at"))
        register_export(
            "reading_sessions",
            lambda u: rows(
                ReadingSession.objects.filter(owner=u),
                "book_id",
                "date",
                "started_at",
                "ended_at",
                "duration_minutes",
                "start_page",
                "end_page",
                "pages_read",
                "source",
                "notes",
            ),
        )
