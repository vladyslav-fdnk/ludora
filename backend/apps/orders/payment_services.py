from decimal import Decimal

from django.db import transaction

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment


@transaction.atomic
def create_payment(order: Order) -> Payment:
    order = (
        Order.objects.select_for_update()
        .select_related("product")
        .get(pk=order.pk)
    )

    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Order already paid")

    if order.payments.filter(
        status__in=[
            Payment.Status.CREATED,
            Payment.Status.PENDING,
        ]
    ).exists():
        raise OrderPaymentError("Payment already in progress")

    payment = Payment.objects.create(
        order=order,
        status=Payment.Status.CREATED,
        amount=Decimal(order.product.price),
    )

    return payment
