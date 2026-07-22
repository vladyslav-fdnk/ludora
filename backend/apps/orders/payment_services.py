from decimal import Decimal

from apps.orders.models import Order, Payment


def create_payment(order: Order) -> Payment:
    return Payment.objects.create(
        order=order,
        status=Payment.Status.CREATED,
        amount=Decimal(order.product.price),
    )