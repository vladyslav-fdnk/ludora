from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.games.models import LicenseKey, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, OrderItem, Payment


@transaction.atomic
def create_direct_order(*, user, product: Product, email: str) -> Order:
    """Create a direct order from a product already authorized by the caller.

    Public endpoints must validate catalogue availability before calling this
    trusted domain service.
    """
    total_price = product.price
    order = Order.objects.create(
        user=user,
        product=product,
        email=email,
        source=Order.Source.DIRECT,
        total_price=total_price,
    )
    item = OrderItem.objects.create(
        order=order,
        product=product,
        product_title=product.title,
        quantity=1,
        unit_price=total_price,
    )
    order._prefetched_objects_cache = {"items": [item]}
    return order


def payable_total(order: Order) -> Decimal:
    if order.total_price is None:
        raise OrderPaymentError(
            "Order has no authoritative total and requires manual review"
        )
    return order.total_price


@transaction.atomic
def pay_order(order_id: int) -> Order:

    order = Order.objects.select_for_update().get(id=order_id)

    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Already paid")
    if order.source == Order.Source.CART:
        raise OrderPaymentError("Cart orders are not payable in this stage")

    if order.product_id is None:
        raise OrderPaymentError(
            "Order has no product reference and requires manual review"
        )
    price_paid = payable_total(order)
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
