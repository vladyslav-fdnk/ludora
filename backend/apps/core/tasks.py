import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="ludora.diagnostics.log_worker_probe")
def log_worker_probe(message: str) -> dict[str, str]:
    """Log a bounded diagnostic message to prove that a worker executed a task."""
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if not message or len(message) > 200:
        raise ValueError("message must contain between 1 and 200 characters")

    logger.info(
        "Celery diagnostic task executed: diagnostic_message=%s",
        message,
        extra={"diagnostic_message": message},
    )
    return {"message": message, "status": "processed"}
