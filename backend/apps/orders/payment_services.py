from django.db import transaction

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, OrderItem, Payment
from apps.orders.services import (
    get_or_create_order_items_for_fulfilment,
    payable_total,
    release_order_license_reservation,
    reserve_order_licenses,
)
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import (
    CreatePaymentRequest,
    PaymentProvider,
    get_payment_provider,
)


def create_payment(
    order: Order,
    *,
    provider: PaymentProvider | None = None,
) -> Payment:
    with transaction.atomic():
        order = (
            Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
        )

        if order.status == Order.Status.PAID:
            raise OrderPaymentError("Order already paid")
        amount = payable_total(order)
        had_order_items = order.items.exists()
        order_items = get_or_create_order_items_for_fulfilment(
            order,
            legacy_unit_price=amount,
        )
        created_order_item_id = (
            order_items[0].pk if order_items and not had_order_items else None
        )

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
        reserve_order_licenses(order.id)

    try:
        selected_provider = provider or get_payment_provider()
        provider_payment = selected_provider.create_payment(
            CreatePaymentRequest(
                amount=amount,
                order_number=order.order_number,
                idempotency_key=f"payment-{payment.pk}",
                local_payment_id=payment.pk,
            )
        )
    except PaymentProviderError as exc:
        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).delete()
            release_order_license_reservation(order.id)
            OrderItem.objects.filter(pk=created_order_item_id).delete()
        raise OrderPaymentError("Payment provider could not create payment") from exc
    except Exception:
        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).delete()
            release_order_license_reservation(order.id)
            OrderItem.objects.filter(pk=created_order_item_id).delete()
        raise

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        payment.provider = selected_provider.name
        payment.transaction_id = provider_payment.external_id
        payment.save(update_fields=("provider", "transaction_id"))
    payment.checkout_url = provider_payment.checkout_url

    return payment
