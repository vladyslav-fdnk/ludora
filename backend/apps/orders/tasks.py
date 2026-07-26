import logging
from smtplib import SMTPException

from celery import shared_task

from apps.orders.emails import build_order_confirmation_email
from apps.orders.models import Order, Payment

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(OSError, SMTPException),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    name="ludora.orders.send_order_confirmation_email",
)
def send_order_confirmation_email(self, order_id: int) -> dict[str, object]:
    """Send a confirmation for a completed order without changing its state."""
    try:
        order = (
            Order.objects.select_related("product", "license_key")
            .prefetch_related("items")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        logger.warning(
            "Order confirmation email skipped: order missing; order_id=%s",
            order_id,
            extra={"order_id": order_id},
        )
        return {"order_id": order_id, "status": "missing"}

    is_eligible = (
        order.status == Order.Status.PAID
        and order.license_key_id is not None
        and order.price_paid is not None
        and order.payments.filter(status=Payment.Status.PAID).exists()
    )
    if not is_eligible:
        logger.warning(
            "Order confirmation email skipped: order ineligible; order_id=%s",
            order_id,
            extra={"order_id": order_id},
        )
        return {"order_id": order_id, "status": "ineligible"}

    build_order_confirmation_email(order).send(fail_silently=False)
    logger.info(
        "Order confirmation email sent; order_id=%s order_number=%s",
        order_id,
        order.order_number,
        extra={"order_id": order_id, "order_number": order.order_number},
    )
    return {"order_id": order_id, "status": "sent"}
