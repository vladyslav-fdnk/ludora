import logging
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.games.models import LicenseKey, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import LicenseAssignment, Order, OrderItem, Payment
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import (
    CreatePaymentRequest,
    PaymentProvider,
    PaymentProviderStatus,
    get_payment_provider,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompletePaymentResult:
    order: Order
    already_completed: bool


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


def get_or_create_order_items_for_fulfilment(
    order: Order,
    *,
    legacy_unit_price: Decimal,
) -> list[OrderItem]:
    """Return the normalized items used to fulfil an order.

    Pre-OrderItem orders are normalized lazily here so payment and fulfilment
    code can operate exclusively on item collections.
    """
    order_items = list(
        order.items.select_related("product").order_by("product_id", "id")
    )
    if order_items or order.source == Order.Source.CART:
        return order_items

    if order.product_id is not None:
        return [
            OrderItem.objects.create(
                order=order,
                product=order.product,
                product_title=order.product.title,
                quantity=1,
                unit_price=legacy_unit_price,
            )
        ]

    raise OrderPaymentError(
        "Order has no product reference and requires manual review"
    )


def _fulfil_order(
    order_items: list[OrderItem],
    *,
    paid_at,
) -> list[LicenseKey]:
    if not order_items:
        raise OrderPaymentError(
            "Order has no product reference and requires manual review"
        )

    assignments = []
    license_keys = []
    for order_item in order_items:
        item_keys = list(
            LicenseKey.objects.select_for_update()
            .filter(
                product_id=order_item.product_id,
                status=LicenseKey.Status.AVAILABLE,
            )
            .order_by("id")[: order_item.quantity]
        )
        if len(item_keys) != order_item.quantity:
            raise OrderPaymentError("No keys available")
        for license_key in item_keys:
            license_key.status = LicenseKey.Status.SOLD
            license_key.sold_at = paid_at
            assignments.append(
                LicenseAssignment(
                    order_item=order_item,
                    license_key=license_key,
                )
            )
        license_keys.extend(item_keys)

    LicenseKey.objects.bulk_update(license_keys, ("status", "sold_at"))
    LicenseAssignment.objects.bulk_create(assignments)
    return license_keys


@transaction.atomic
def complete_payment(payment_id: int) -> CompletePaymentResult:
    """Complete provider-neutral order fulfilment for a confirmed payment."""
    payment_reference = Payment.objects.only("order_id").get(id=payment_id)
    order = (
        Order.objects.select_for_update(of=("self",))
        .select_related("product")
        .get(id=payment_reference.order_id)
    )
    payment = Payment.objects.select_for_update().get(
        id=payment_id,
        order=order,
    )

    if (
        order.status == Order.Status.PAID
        and payment.status == Payment.Status.PAID
    ):
        return CompletePaymentResult(
            order=order,
            already_completed=True,
        )
    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Order payment state is inconsistent")
    if payment.status not in (Payment.Status.CREATED, Payment.Status.PENDING):
        raise OrderPaymentError("Payment cannot be completed")

    price_paid = payable_total(order)
    if payment.amount != price_paid:
        raise OrderPaymentError("Payment amount does not match order total")

    order_items = get_or_create_order_items_for_fulfilment(
        order,
        legacy_unit_price=price_paid,
    )
    paid_at = timezone.now()
    license_keys = _fulfil_order(order_items, paid_at=paid_at)
    if order.source == Order.Source.DIRECT:
        order.license_key = license_keys[0]
    order.status = Order.Status.PAID
    order.price_paid = price_paid
    order.paid_at = paid_at
    order.save(
        update_fields=(
            "license_key",
            "status",
            "price_paid",
            "paid_at",
            "updated_at",
        )
    )

    payment.status = Payment.Status.PAID
    payment.paid_at = paid_at
    payment.save(update_fields=("status", "paid_at"))

    committed_order_id = order.pk

    def dispatch_confirmation_email(order_id=committed_order_id):
        from apps.orders.tasks import send_order_confirmation_email

        try:
            send_order_confirmation_email.delay(order_id)
        except OperationalError:
            logger.exception(
                "Order confirmation email could not be queued; order_id=%s",
                order_id,
                extra={"order_id": order_id},
            )

    transaction.on_commit(dispatch_confirmation_email)
    return CompletePaymentResult(
        order=order,
        already_completed=False,
    )


@contextmanager
def _pay_order_lock(order_id: int):
    lock_name = f"orders.pay_order:{order_id}"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
            [lock_name],
        )
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                [lock_name],
            )


def pay_order(
    order_id: int,
    *,
    provider: PaymentProvider | None = None,
) -> Order:
    with _pay_order_lock(order_id):
        return _pay_order(order_id, provider=provider)


def _pay_order(
    order_id: int,
    *,
    provider: PaymentProvider | None = None,
) -> Order:
    created_payment = False
    created_provider_payment = False
    with transaction.atomic():
        order = (
            Order.objects.select_for_update(of=("self",))
            .select_related("product")
            .get(id=order_id)
        )

        if order.status == Order.Status.PAID:
            raise OrderPaymentError("Already paid")
        price_paid = payable_total(order)
        payment = (
            Payment.objects.select_for_update()
            .filter(
                order=order,
                status__in=(Payment.Status.CREATED, Payment.Status.PENDING),
            )
            .order_by("created_at", "id")
            .first()
        )

        if payment is None:
            payment = Payment.objects.create(
                order=order,
                status=Payment.Status.CREATED,
                amount=price_paid,
            )
            created_payment = True

        if not payment.transaction_id:
            if provider is not None:
                selected_provider = provider
            else:
                try:
                    selected_provider = get_payment_provider()
                except ImproperlyConfigured as exc:
                    raise OrderPaymentError(
                        "Payment provider configuration is invalid"
                    ) from exc
        else:
            if not payment.provider:
                raise OrderPaymentError(
                    "Payment provider configuration is invalid"
                )
            if provider is not None:
                if provider.name != payment.provider:
                    raise OrderPaymentError(
                        "Payment provider configuration is invalid"
                    )
                selected_provider = provider
            else:
                try:
                    selected_provider = get_payment_provider(
                        payment.provider
                    )
                except ImproperlyConfigured as exc:
                    raise OrderPaymentError(
                        "Payment provider configuration is invalid"
                    ) from exc

    try:
        if not payment.transaction_id:
            provider_payment = selected_provider.create_payment(
                CreatePaymentRequest(
                    amount=payment.amount,
                    order_number=order.order_number,
                    idempotency_key=f"payment-{payment.pk}",
                    local_payment_id=payment.pk,
                )
            )
            created_provider_payment = True
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(pk=payment.pk)
                payment.provider = selected_provider.name
                payment.transaction_id = provider_payment.external_id
                payment.save(update_fields=("provider", "transaction_id"))

        provider_result = selected_provider.confirm_payment(
            payment.transaction_id
        )
    except ImproperlyConfigured as exc:
        raise OrderPaymentError(
            "Payment provider configuration is invalid"
        ) from exc
    except PaymentProviderError as exc:
        with transaction.atomic():
            if created_payment:
                Payment.objects.filter(pk=payment.pk).delete()
            elif created_provider_payment:
                Payment.objects.filter(pk=payment.pk).update(
                    provider=None,
                    transaction_id=None,
                )
        raise OrderPaymentError(
            "Payment provider could not confirm payment"
        ) from exc
    except Exception:
        with transaction.atomic():
            if created_payment:
                Payment.objects.filter(pk=payment.pk).delete()
            elif created_provider_payment:
                Payment.objects.filter(pk=payment.pk).update(
                    provider=None,
                    transaction_id=None,
                )
        raise

    provider_outcome_error = None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
        if provider_result.status is PaymentProviderStatus.FAILED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=("status",))
            provider_outcome_error = "Payment was rejected"
        elif provider_result.status is not PaymentProviderStatus.SUCCEEDED:
            payment.status = Payment.Status.PENDING
            payment.save(update_fields=("status",))
            provider_outcome_error = "Payment is still pending"

        if provider_outcome_error:
            return_order = order
        else:
            return_order = complete_payment(payment.id).order

    if provider_outcome_error:
        raise OrderPaymentError(provider_outcome_error)

    return return_order
