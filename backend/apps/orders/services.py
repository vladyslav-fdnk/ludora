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


def _locked_reservation_assignments(
    order_items: list[OrderItem],
) -> list[LicenseAssignment]:
    assignments = list(
        LicenseAssignment.objects.select_for_update()
        .filter(order_item__in=order_items)
        .order_by("order_item_id", "id")
    )
    if not assignments:
        return []

    license_keys = {
        license_key.id: license_key
        for license_key in LicenseKey.objects.select_for_update().filter(
            id__in=[assignment.license_key_id for assignment in assignments]
        )
    }
    assignment_counts = {order_item.id: 0 for order_item in order_items}
    order_items_by_id = {order_item.id: order_item for order_item in order_items}

    for assignment in assignments:
        order_item = order_items_by_id.get(assignment.order_item_id)
        license_key = license_keys.get(assignment.license_key_id)
        if (
            order_item is None
            or license_key is None
            or license_key.product_id != order_item.product_id
            or license_key.status != LicenseKey.Status.RESERVED
        ):
            raise OrderPaymentError("Order reservation is inconsistent")
        assignment_counts[order_item.id] += 1

    if any(assignment_counts[order_item.id] != order_item.quantity for order_item in order_items):
        raise OrderPaymentError("Order reservation is inconsistent")

    return assignments


@transaction.atomic
def reserve_order_licenses(order_id: int) -> list[LicenseAssignment]:
    """Establish or reuse the complete provider-neutral order reservation."""
    order = Order.objects.select_for_update(of=("self",)).select_related("product").get(id=order_id)
    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Paid orders cannot reserve licenses")

    order_items = get_or_create_order_items_for_fulfilment(
        order,
        legacy_unit_price=payable_total(order),
    )
    order_items = list(
        OrderItem.objects.select_for_update()
        .select_related("product")
        .filter(id__in=[order_item.id for order_item in order_items])
        .order_by("product_id", "id")
    )
    if not order_items:
        raise OrderPaymentError("Order has no product reference and requires manual review")

    existing_assignments = _locked_reservation_assignments(order_items)
    if existing_assignments:
        return existing_assignments

    assignments = []
    license_keys = []
    for order_item in order_items:
        item_keys = list(
            LicenseKey.objects.select_for_update(skip_locked=True)
            .filter(
                product_id=order_item.product_id,
                status=LicenseKey.Status.AVAILABLE,
            )
            .exclude(id__in=LicenseAssignment.objects.values("license_key_id"))
            .order_by("id")[: order_item.quantity]
        )
        if len(item_keys) != order_item.quantity:
            raise OrderPaymentError("No keys available")
        for license_key in item_keys:
            license_key.status = LicenseKey.Status.RESERVED
            assignments.append(
                LicenseAssignment(
                    order_item=order_item,
                    license_key=license_key,
                )
            )
        license_keys.extend(item_keys)

    LicenseKey.objects.bulk_update(license_keys, ("status",))
    return LicenseAssignment.objects.bulk_create(assignments)


@transaction.atomic
def release_order_license_reservation(
    order_id: int,
) -> list[LicenseKey]:
    """Release one unpaid order's complete provider-neutral reservation."""
    order = Order.objects.select_for_update(of=("self",)).get(id=order_id)
    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Paid orders cannot release licenses")

    order_items = list(
        OrderItem.objects.select_for_update().filter(order=order).order_by("product_id", "id")
    )
    if not order_items:
        return []

    assignments = _locked_reservation_assignments(order_items)
    if not assignments:
        return []

    license_keys = list(
        LicenseKey.objects.select_for_update().filter(
            id__in=[assignment.license_key_id for assignment in assignments]
        )
    )
    for license_key in license_keys:
        license_key.status = LicenseKey.Status.AVAILABLE

    LicenseKey.objects.bulk_update(license_keys, ("status",))
    LicenseAssignment.objects.filter(id__in=[assignment.id for assignment in assignments]).delete()
    return license_keys


def fail_payment(*, order: Order, payment: Payment) -> Payment:
    """Record a terminal payment failure and release its order reservation.

    This internal helper does not own transaction boundaries. It must be called
    within an existing transaction after the caller has acquired row locks for
    both the Order and Payment.
    """
    if payment.status == Payment.Status.PAID:
        return payment

    if order.status == Order.Status.PAID:
        if payment.status != Payment.Status.FAILED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=("status",))
        return payment

    payment.status = Payment.Status.FAILED
    payment.save(update_fields=("status",))
    release_order_license_reservation(order.id)
    return payment


def _fulfil_order(
    order_items: list[OrderItem],
    *,
    paid_at,
) -> list[LicenseKey]:
    if not order_items:
        raise OrderPaymentError(
            "Order has no product reference and requires manual review"
        )

    reserved_assignments = _locked_reservation_assignments(order_items)
    if reserved_assignments:
        license_keys = list(
            LicenseKey.objects.select_for_update()
            .filter(
                id__in=[
                    assignment.license_key_id
                    for assignment in reserved_assignments
                ]
            )
            .order_by("id")
        )
        for license_key in license_keys:
            license_key.status = LicenseKey.Status.SOLD
            license_key.sold_at = paid_at
        LicenseKey.objects.bulk_update(
            license_keys,
            ("status", "sold_at"),
        )
        return license_keys

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
    if payment.status not in (
        Payment.Status.CREATED,
        Payment.Status.PENDING,
        Payment.Status.FAILED,
    ):
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
    created_order_item_id = None
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
            if provider is not None:
                selected_provider = provider
            else:
                try:
                    selected_provider = get_payment_provider()
                except ImproperlyConfigured as exc:
                    raise OrderPaymentError(
                        "Payment provider configuration is invalid"
                    ) from exc
            if selected_provider.name == "stripe":
                raise OrderPaymentError(
                    "Stripe payments require checkout"
                )
            payment = Payment.objects.create(
                order=order,
                status=Payment.Status.CREATED,
                amount=price_paid,
            )
            created_payment = True

        had_order_items = order.items.exists()
        reserve_order_licenses(order.id)
        if not had_order_items:
            created_order_item_id = (
                OrderItem.objects.filter(order=order)
                .values_list("id", flat=True)
                .first()
            )

        if not payment.transaction_id:
            if not created_payment:
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

    if not payment.transaction_id:
        try:
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
        except ImproperlyConfigured as exc:
            with transaction.atomic():
                if created_payment:
                    Payment.objects.filter(pk=payment.pk).delete()
                release_order_license_reservation(order.id)
                OrderItem.objects.filter(pk=created_order_item_id).delete()
            raise OrderPaymentError(
                "Payment provider configuration is invalid"
            ) from exc
        except PaymentProviderError as exc:
            with transaction.atomic():
                if created_payment:
                    Payment.objects.filter(pk=payment.pk).delete()
                release_order_license_reservation(order.id)
                OrderItem.objects.filter(pk=created_order_item_id).delete()
            raise OrderPaymentError(
                "Payment provider could not confirm payment"
            ) from exc
        except Exception:
            with transaction.atomic():
                if created_payment:
                    Payment.objects.filter(pk=payment.pk).delete()
                release_order_license_reservation(order.id)
                OrderItem.objects.filter(pk=created_order_item_id).delete()
            raise

    try:
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
        order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if provider_result.status is PaymentProviderStatus.FAILED:
            payment = fail_payment(order=order, payment=payment)
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
