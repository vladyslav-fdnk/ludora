from decimal import Decimal

from django.db import transaction

from apps.orders.models import Order, Payment
from apps.orders.exceptions import OrderPaymentError


@transaction.atomic
def create_payment(order: Order) -> Payment:

    if order.status == Order.Status.PAID:
        raise OrderPaymentError(
            "Order already paid"
        )

    payment = Payment.objects.create(
        order=order,
        status=Payment.Status.CREATED,
        amount=Decimal(order.product.price),
    )

    return payment