import logging

from celery import shared_task

logger = logging.getLogger("daywell.tasks")


@shared_task(name="tasks.extend_series")
def extend_series() -> int:
    """Keep recurring task series materialised for the rolling horizon. Idempotent (unique series+date)."""
    from .services import extend_all_series

    created = extend_all_series()
    if created:
        logger.info("materialised recurring task instances", extra={"created": created})
    return created
