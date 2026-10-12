"""Task business logic shared by the API and background jobs. All state changes are transactional and logged."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.recurrence import occurrence_dates_between
from apps.core.timeutils import combine, get_zone, local_today

from .models import OPEN_STATUSES, Task, TaskActivity, TaskSeries, TaskStatus, TaskSubtask

SERIES_FIELDS = ["title", "description", "notes", "priority", "important", "category", "tags", "scheduled_time", "duration_minutes", "link_url"]


def _after_commit_resync(task_ids: list[int]) -> None:
    """Re-derive reminder occurrences for changed tasks inside the same transaction (atomic with the change)."""
    from apps.reminders.services import resync_for_tasks

    resync_for_tasks(task_ids)


def log(task: Task, kind: str, *, from_date: date | None = None, to_date: date | None = None, at: datetime | None = None) -> None:
    TaskActivity.objects.create(task=task, kind=kind, at=at or timezone.now(), from_date=from_date, to_date=to_date)


def refresh_schedule(task: Task) -> None:
    """Recompute the UTC instant from local date+time in the task's zone."""
    if task.scheduled_date and task.scheduled_time:
        task.scheduled_at = combine(task.scheduled_date, task.scheduled_time, get_zone(task.time_zone))
    else:
        task.scheduled_at = None


@transaction.atomic
def create_task(owner, data: dict, *, subtasks: list[str] | None = None, rrule: str = "") -> Task:
    data = dict(data)
    data.setdefault("time_zone", owner.preferences.time_zone)
    if rrule:
        if not data.get("scheduled_date"):
            raise BusinessRuleError("A repeating task needs a start date.", code="invalid", status_code=400)
        series = TaskSeries.objects.create(
            owner=owner,
            rrule=rrule,
            dtstart=data["scheduled_date"],
            time_zone=data["time_zone"],
            checklist=[t.strip() for t in (subtasks or []) if t.strip()],
            **{f: data[f] for f in SERIES_FIELDS if f in data},
        )
        materialize_series(series)
        first = series.instances.filter(deleted_at__isnull=True).order_by("occurrence_date").first()
        if first is None:
            raise BusinessRuleError("That repeat rule produces no dates in the coming weeks.", code="invalid", status_code=400)
        return first
    task = Task(owner=owner, **data)
    refresh_schedule(task)
    task.save()
    if subtasks:
        _replace_subtasks(task, subtasks)
    log(task, TaskActivity.Kind.CREATED)
    return task


def _replace_subtasks(task: Task, titles: list[str]) -> None:
    task.subtasks.all().delete()
    TaskSubtask.objects.bulk_create([TaskSubtask(task=task, title=t.strip(), position=i) for i, t in enumerate(titles) if t.strip()])


@transaction.atomic
def update_task(task: Task, data: dict, *, scope: str = "this") -> Task:
    """Update a task. For series instances, ``scope='series'`` also updates the definition and future open instances."""
    old_date = task.scheduled_date
    for field, value in data.items():
        setattr(task, field, value)
    refresh_schedule(task)
    if task.series_id and scope == "this":
        task.detached = True
    task.save()
    if old_date != task.scheduled_date and old_date is not None:
        log(task, TaskActivity.Kind.RESCHEDULED, from_date=old_date, to_date=task.scheduled_date)
    ids = [task.id]
    if task.series_id and scope == "series":
        series = task.series
        series_changes = {f: v for f, v in data.items() if f in SERIES_FIELDS}
        for field, value in series_changes.items():
            setattr(series, field, value)
        series.save()
        future = series.instances.filter(status__in=OPEN_STATUSES, detached=False, deleted_at__isnull=True, occurrence_date__gte=task.occurrence_date).exclude(pk=task.pk)
        for inst in future:
            for field, value in series_changes.items():
                setattr(inst, field, value)
            refresh_schedule(inst)
            inst.save()
            ids.append(inst.id)
    _after_commit_resync(ids)
    return task


def _lock(task: Task) -> Task:
    return Task.objects.select_for_update(of=("self",)).get(pk=task.pk)


@transaction.atomic
def complete(task: Task, *, at: datetime | None = None) -> Task:
    task = _lock(task)
    if task.status == TaskStatus.COMPLETED:
        return task  # idempotent
    if task.status == TaskStatus.CANCELLED:
        raise BusinessRuleError("This task was cancelled. Reopen it first if you'd like to complete it.")
    task.status = TaskStatus.COMPLETED
    task.completed_at = at or timezone.now()
    task.save(update_fields=["status", "completed_at", "updated_at"])
    log(task, TaskActivity.Kind.COMPLETED, at=task.completed_at)
    _after_commit_resync([task.id])
    return task


@transaction.atomic
def start(task: Task) -> Task:
    task = _lock(task)
    if task.status not in OPEN_STATUSES:
        raise BusinessRuleError("Only open tasks can be started.")
    if task.status != TaskStatus.IN_PROGRESS:
        task.status = TaskStatus.IN_PROGRESS
        task.save(update_fields=["status", "updated_at"])
        log(task, TaskActivity.Kind.STARTED)
    return task


@transaction.atomic
def reopen(task: Task) -> Task:
    task = _lock(task)
    if task.status in OPEN_STATUSES:
        return task
    task.status = TaskStatus.PENDING
    task.completed_at = None
    task.save(update_fields=["status", "completed_at", "updated_at"])
    log(task, TaskActivity.Kind.REOPENED)
    _after_commit_resync([task.id])
    return task


@transaction.atomic
def postpone(task: Task, *, to_date: date, to_time=None, keep_time: bool = True) -> Task:
    task = _lock(task)
    if task.status not in OPEN_STATUSES:
        raise BusinessRuleError("Only open tasks can be postponed.")
    old = task.scheduled_date
    if to_date < local_today(get_zone(task.time_zone)):
        raise BusinessRuleError("Choose today or a later date.", code="invalid", status_code=400)
    task.scheduled_date = to_date
    if not keep_time or to_time is not None:
        task.scheduled_time = to_time
    refresh_schedule(task)
    task.status = TaskStatus.POSTPONED
    task.postponed_count += 1
    if task.series_id:
        task.detached = True
    task.save()
    log(task, TaskActivity.Kind.POSTPONED, from_date=old, to_date=to_date)
    _after_commit_resync([task.id])
    return task


@transaction.atomic
def cancel(task: Task) -> Task:
    task = _lock(task)
    if task.status == TaskStatus.CANCELLED:
        return task
    task.status = TaskStatus.CANCELLED
    task.save(update_fields=["status", "updated_at"])
    log(task, TaskActivity.Kind.CANCELLED)
    _after_commit_resync([task.id])
    return task


@transaction.atomic
def delete(task: Task, *, scope: str = "this") -> None:
    if task.series_id is None:
        task.delete()  # reminders linked to it cascade
        return
    series = task.series
    if scope == "series":
        series.active = False
        series.save(update_fields=["active", "updated_at"])
        future = series.instances.filter(occurrence_date__gte=task.occurrence_date).exclude(status=TaskStatus.COMPLETED)
        ids = list(future.values_list("id", flat=True))
        future.update(deleted_at=timezone.now(), status=TaskStatus.CANCELLED)
        _after_commit_resync(ids)
    else:
        task.deleted_at = timezone.now()
        task.status = TaskStatus.CANCELLED
        task.save(update_fields=["deleted_at", "status", "updated_at"])
        _after_commit_resync([task.id])


def materialize_series(series: TaskSeries, until: date | None = None) -> int:
    """Create instances up to ``until`` (default: today + horizon). Idempotent: existing dates are skipped by the DB."""
    if not series.active:
        return 0
    zone = get_zone(series.time_zone)
    horizon = until or (local_today(zone) + timedelta(days=settings.TASK_SERIES_HORIZON_DAYS))
    start = series.generated_until + timedelta(days=1) if series.generated_until else series.dtstart
    if start > horizon:
        return 0
    dates = occurrence_dates_between(series.rrule, series.dtstart, start, horizon)
    instances = []
    for d in dates:
        t = Task(
            owner_id=series.owner_id,
            series=series,
            occurrence_date=d,
            scheduled_date=d,
            time_zone=series.time_zone,
            **{f: getattr(series, f) for f in SERIES_FIELDS},
        )
        refresh_schedule(t)
        instances.append(t)
    created = Task.objects.bulk_create(instances, ignore_conflicts=True)
    TaskSeries.objects.filter(pk=series.pk).update(generated_until=horizon)
    series.generated_until = horizon
    new_ids = list(series.instances.filter(occurrence_date__gte=start, occurrence_date__lte=horizon).values_list("id", flat=True))
    if series.checklist:
        bare = Task.objects.filter(id__in=new_ids, subtasks__isnull=True)
        TaskSubtask.objects.bulk_create([TaskSubtask(task=t, title=title, position=i) for t in bare for i, title in enumerate(series.checklist)])
    if new_ids:
        _after_commit_resync(new_ids)
    return len(created)


def extend_all_series() -> int:
    total = 0
    for series in TaskSeries.objects.filter(active=True).iterator():
        with transaction.atomic():
            total += materialize_series(series)
    return total


ADMIN_CATEGORIES = [("Home & chores", "sage"), ("Errands", "sky"), ("Bills & renewals", "terracotta"), ("Shopping", "amber")]


def ensure_admin_categories(owner) -> None:
    """Personal-admin module: make sure its categories exist (idempotent; never renames or deletes the user's own)."""
    from .models import Category

    existing = {n.lower() for n in Category.objects.filter(owner=owner).values_list("name", flat=True)}
    Category.objects.bulk_create(
        [Category(owner=owner, name=n, color=c) for n, c in ADMIN_CATEGORIES if n.lower() not in existing], ignore_conflicts=True
    )
