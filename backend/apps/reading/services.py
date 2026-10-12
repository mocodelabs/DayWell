"""Reading sessions and statistics. Every minute and page comes from recorded sessions — nothing is estimated."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.timeutils import get_zone, local_today, week_start

from .models import Book, BookStatus, ReadingSession

MAX_SESSION_MINUTES = 12 * 60


def _apply_pages(book: Book, session: ReadingSession) -> None:
    if session.end_page is not None:
        if book.total_pages and session.end_page > book.total_pages:
            raise BusinessRuleError(f"This book has {book.total_pages} pages.", code="invalid", status_code=400)
        if session.pages_read is None and session.start_page is not None:
            session.pages_read = max(0, session.end_page - session.start_page)
        if session.end_page > book.current_page:
            book.current_page = session.end_page
    if book.status in (BookStatus.WANT, BookStatus.PAUSED):
        book.status = BookStatus.READING
        book.start_date = book.start_date or session.date
    book.save()


@transaction.atomic
def start_timer(owner, book: Book) -> ReadingSession:
    zone = get_zone(owner.preferences.time_zone)
    now = timezone.now()
    try:
        with transaction.atomic():
            return ReadingSession.objects.create(
                owner=owner, book=book, date=local_today(zone, now), started_at=now, source=ReadingSession.Source.TIMER, start_page=book.current_page or None
            )
    except IntegrityError:
        raise BusinessRuleError("A reading timer is already running. Stop it before starting another.") from None


@transaction.atomic
def stop_timer(session: ReadingSession, *, end_page: int | None = None, pages_read: int | None = None, notes: str = "") -> ReadingSession:
    session = ReadingSession.objects.select_for_update(of=("self",)).get(pk=session.pk)
    if session.ended_at is not None:
        return session
    session.ended_at = timezone.now()
    minutes = round((session.ended_at - session.started_at).total_seconds() / 60)
    session.duration_minutes = min(max(minutes, 0), MAX_SESSION_MINUTES)
    session.end_page = end_page
    session.pages_read = pages_read
    session.notes = notes or session.notes
    _apply_pages(session.book, session)
    session.save()
    return session


@transaction.atomic
def log_manual(owner, book: Book, *, day: date, minutes: int, start_time=None, start_page=None, end_page=None, pages_read=None, notes="") -> ReadingSession:
    zone = get_zone(owner.preferences.time_zone)
    if day > local_today(zone):
        raise BusinessRuleError("You can't log reading for a future day.", code="invalid", status_code=400)
    if not 1 <= minutes <= MAX_SESSION_MINUTES:
        raise BusinessRuleError("A session is between 1 minute and 12 hours.", code="invalid", status_code=400)
    from apps.core.timeutils import combine

    started = combine(day, start_time, zone) if start_time else combine(day, datetime.min.time(), zone) + timedelta(hours=12)
    session = ReadingSession(
        owner=owner,
        book=book,
        date=day,
        started_at=started,
        ended_at=started + timedelta(minutes=minutes),
        duration_minutes=minutes,
        start_page=start_page,
        end_page=end_page,
        pages_read=pages_read,
        notes=notes,
    )
    _apply_pages(book, session)
    session.save()
    return session


def complete_book(book: Book, day: date) -> Book:
    book.status = BookStatus.COMPLETED
    book.completed_date = day
    if book.total_pages:
        book.current_page = book.total_pages
    book.save()
    return book


def _totals(qs) -> dict:
    agg = qs.filter(ended_at__isnull=False).aggregate(minutes=Sum("duration_minutes"), pages=Sum("pages_read"), sessions=Count("id"))
    return {"minutes": agg["minutes"] or 0, "pages": agg["pages"] or 0, "sessions": agg["sessions"]}


def reading_streak(owner, today: date) -> dict:
    """Consecutive days with at least one finished session, ending today (or yesterday if today has none yet)."""
    days = set(ReadingSession.objects.filter(owner=owner, ended_at__isnull=False, date__gte=today - timedelta(days=400)).values_list("date", flat=True))
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    return {"current": current, "read_today": today in days}


def stats(owner) -> dict:
    prefs = owner.preferences
    zone = get_zone(prefs.time_zone)
    today = local_today(zone)
    wk = week_start(today, prefs.week_start)
    month = today.replace(day=1)
    sessions = ReadingSession.objects.filter(owner=owner)
    books = Book.objects.filter(owner=owner)
    completed_this_year = books.filter(status=BookStatus.COMPLETED, completed_date__year=today.year).count()
    return {
        "books_completed": books.filter(status=BookStatus.COMPLETED).count(),
        "books_completed_this_year": completed_this_year,
        "active_books": books.filter(status=BookStatus.READING).count(),
        "week": _totals(sessions.filter(date__gte=wk, date__lte=today)),
        "month": _totals(sessions.filter(date__gte=month, date__lte=today)),
        "streak": reading_streak(owner, today),
        "yearly_goal": {
            "target": prefs.reading_yearly_goal or None,
            "completed": completed_this_year,
            "rate": (completed_this_year / prefs.reading_yearly_goal) if prefs.reading_yearly_goal else None,
        },
        "definitions": {
            "minutes": "Sum of durations of finished sessions (timer or logged) by the session's local date.",
            "pages": "Sum of pages read entered or derived from start/end page; sessions without pages are not estimated.",
            "streak": "Consecutive days with at least one finished session. Rest days simply end the count — no penalty.",
        },
    }
