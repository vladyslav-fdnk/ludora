from django.db import transaction

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment
from apps.orders.services import payable_total


@transaction.atomic
def create_payment(order: Order) -> Payment:
    order = (
        Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    )

    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Order already paid")
    if order.source == Order.Source.CART:
        raise OrderPaymentError("Cart orders are not payable in this stage")
    if order.product_id is None:
        raise OrderPaymentError(
            "Order has no product reference and requires manual review"
        )
    amount = payable_total(order)

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
        amount=amount,
    )

    return payment
