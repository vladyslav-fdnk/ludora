from django.db import transaction

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment
from apps.orders.services import (
    get_or_create_order_items_for_fulfilment,
    payable_total,
)
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import (
    CreatePaymentRequest,
    PaymentProvider,
    get_payment_provider,
)


@transaction.atomic
def create_payment(
    order: Order,
    *,
    provider: PaymentProvider | None = None,
) -> Payment:
    order = (
        Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    )

    if order.status == Order.Status.PAID:
        raise OrderPaymentError("Order already paid")
    amount = payable_total(order)
    get_or_create_order_items_for_fulfilment(
        order,
        legacy_unit_price=amount,
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

    selected_provider = provider or get_payment_provider()
    try:
        provider_payment = selected_provider.create_payment(
            CreatePaymentRequest(
                amount=amount,
                order_number=order.order_number,
                idempotency_key=f"payment-{payment.pk}",
            )
        )
    except PaymentProviderError as exc:
        raise OrderPaymentError("Payment provider could not create payment") from exc

    payment.provider = selected_provider.name
    payment.transaction_id = provider_payment.external_id
    payment.save(update_fields=("provider", "transaction_id"))

    return payment
