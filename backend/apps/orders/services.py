from django.db import transaction
from django.utils import timezone

from apps.games.models import LicenseKey
from apps.orders.models import Order


@transaction.atomic
def pay_order(order_id: int) -> Order:
    """
    Pay order and assign available license key.
    """

    order = (
        Order.objects
        .select_for_update()
        .get(id=order_id)
    )

    if order.status == Order.Status.PAID:
        raise ValueError("Already paid")

    license_key = (
        LicenseKey.objects
        .select_for_update()
        .filter(
            product=order.product,
            status=LicenseKey.Status.AVAILABLE,
        )
        .first()
    )

    if not license_key:
        raise ValueError("No keys available")

    license_key.status = LicenseKey.Status.SOLD
    license_key.save()

    order.license_key = license_key
    order.status = Order.Status.PAID
    order.price_paid = order.product.price
    order.paid_at = timezone.now()
    order.save()

    return order