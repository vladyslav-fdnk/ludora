from django.db import transaction
from django.utils import timezone

from apps.games.models import LicenseKey
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment


@transaction.atomic
def pay_order(order_id: int) -> Order:

    order = Order.objects.select_for_update().get(id=order_id)

    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Already paid")

    license_key = (
        LicenseKey.objects.select_for_update()
        .filter(
            product=order.product,
            status=LicenseKey.Status.AVAILABLE,
        )
        .first()
    )

    if not license_key:
        raise OrderPaymentError("No keys available")

    paid_at = timezone.now()
    price_paid = order.product.price

    license_key.status = LicenseKey.Status.SOLD
    license_key.sold_at = paid_at
    license_key.save()

    order.license_key = license_key
    order.status = Order.Status.PAID
    order.price_paid = price_paid
    order.paid_at = paid_at
    order.save()

    Payment.objects.create(
        order=order,
        status=Payment.Status.PAID,
        amount=price_paid,
        paid_at=paid_at,
    )

    return order
