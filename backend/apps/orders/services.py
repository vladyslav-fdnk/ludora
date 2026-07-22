from django.db import transaction
from django.utils import timezone

from apps.games.models import LicenseKey
from apps.orders.models import Order,Payment
from apps.orders.payment_services import create_payment
from apps.orders.exceptions import OrderPaymentError


@transaction.atomic
def pay_order(order_id: int) -> Order:

    order = (
        Order.objects
        .select_for_update()
        .get(id=order_id)
    )

    if order.status == Order.Status.PAID:
        raise OrderPaymentError(
            "Already paid"
        )

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
        raise OrderPaymentError(
            "No keys available"
        )

    license_key.status = LicenseKey.Status.SOLD
    license_key.save()

    order.license_key = license_key
    order.status = Order.Status.PAID
    order.save()

    Payment.objects.create(
        order=order,
        status=Payment.Status.PAID,
        amount=order.product.price,
        paid_at=timezone.now(),
    )

    return order