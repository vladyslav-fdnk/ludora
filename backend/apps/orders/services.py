import logging
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.games.models import LicenseKey, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, OrderItem, Payment
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import (
    CreatePaymentRequest,
    PaymentProvider,
    PaymentProviderStatus,
    get_payment_provider,
)

logger = logging.getLogger(__name__)


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


def pay_order(
    order_id: int,
    *,
    provider: PaymentProvider | None = None,
) -> Order:
    provider_outcome_error = None
    with transaction.atomic():
        order = (
            Order.objects.select_for_update(of=("self",))
            .select_related("product")
            .get(id=order_id)
        )

        if order.status == Order.Status.PAID:
            raise OrderPaymentError("Already paid")
        if order.source == Order.Source.CART:
            raise OrderPaymentError("Cart orders are not payable in this stage")

        if order.product_id is None:
            raise OrderPaymentError(
                "Order has no product reference and requires manual review"
            )
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

        try:
            if not payment.transaction_id:
                selected_provider = provider or get_payment_provider()
                provider_payment = selected_provider.create_payment(
                    CreatePaymentRequest(
                        amount=payment.amount,
                        order_number=order.order_number,
                        idempotency_key=f"payment-{payment.pk}",
                    )
                )
                payment.provider = selected_provider.name
                payment.transaction_id = provider_payment.external_id
                payment.save(update_fields=("provider", "transaction_id"))
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

            provider_result = selected_provider.confirm_payment(
                payment.transaction_id
            )
        except ImproperlyConfigured as exc:
            raise OrderPaymentError(
                "Payment provider configuration is invalid"
            ) from exc
        except PaymentProviderError as exc:
            raise OrderPaymentError(
                "Payment provider could not confirm payment"
            ) from exc

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
            license_key.save(update_fields=("status", "sold_at"))

            order.license_key = license_key
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
            return_order = order

    if provider_outcome_error:
        raise OrderPaymentError(provider_outcome_error)

    return return_order
