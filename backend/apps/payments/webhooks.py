from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError, loads
from typing import Any, Mapping

import stripe
from django.db import transaction

from apps.orders.models import Payment
from apps.orders.services import complete_payment
from apps.payments.models import StripeWebhookEvent


class StripeCheckoutEventType(StrEnum):
    COMPLETED = "checkout.session.completed"
    ASYNC_PAYMENT_SUCCEEDED = "checkout.session.async_payment_succeeded"
    ASYNC_PAYMENT_FAILED = "checkout.session.async_payment_failed"
    EXPIRED = "checkout.session.expired"


SUCCESSFUL_PAYMENT_STATUSES = frozenset({"paid", "no_payment_required"})


@dataclass(frozen=True)
class StripeCheckoutSession:
    id: str
    local_payment_id: str | None
    payment_status: str


@dataclass(frozen=True)
class StripeWebhookResult:
    event_id: str
    event_type: str
    checkout_session: StripeCheckoutSession | None

    @property
    def is_supported(self) -> bool:
        return self.checkout_session is not None


class InvalidStripeWebhook(ValueError):
    """The webhook signature or payload could not be validated."""


@transaction.atomic
def process_stripe_webhook(result: StripeWebhookResult) -> None:
    """Apply a parsed Stripe Checkout event to its local payment."""
    _, created = StripeWebhookEvent.objects.get_or_create(
        event_id=result.event_id
    )
    if not created:
        return

    if not result.is_supported:
        return

    session = result.checkout_session
    assert session is not None
    local_payment_id = session.local_payment_id
    if (
        local_payment_id is None
        or not local_payment_id.isdecimal()
        or str(int(local_payment_id)) != local_payment_id
    ):
        raise InvalidStripeWebhook(
            "Stripe Checkout Session payment reference is invalid"
        )

    try:
        payment = Payment.objects.select_for_update().get(
            id=int(local_payment_id)
        )
    except Payment.DoesNotExist as exc:
        raise InvalidStripeWebhook("Stripe payment does not exist") from exc

    if payment.provider != "stripe":
        raise InvalidStripeWebhook("Payment provider is not Stripe")
    if payment.transaction_id != session.id:
        raise InvalidStripeWebhook(
            "Stripe Checkout Session does not belong to payment"
        )

    event_type = StripeCheckoutEventType(result.event_type)
    if event_type in (
        StripeCheckoutEventType.COMPLETED,
        StripeCheckoutEventType.ASYNC_PAYMENT_SUCCEEDED,
    ):
        if session.payment_status not in SUCCESSFUL_PAYMENT_STATUSES:
            return
        complete_payment(payment.id)
        return

    if payment.status != Payment.Status.PAID:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=("status",))


def parse_stripe_webhook(
    *,
    payload: bytes,
    signature: str,
    secret: str,
) -> StripeWebhookResult:
    try:
        stripe.Webhook.construct_event(payload, signature, secret)
    except (
        stripe.SignatureVerificationError,
        JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise InvalidStripeWebhook("Invalid Stripe webhook") from exc

    event = loads(payload)
    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not event_id:
        raise InvalidStripeWebhook("Stripe event has no valid id")
    if not isinstance(event_type, str) or not event_type:
        raise InvalidStripeWebhook("Stripe event has no valid type")

    try:
        supported_type = StripeCheckoutEventType(event_type)
    except ValueError:
        return StripeWebhookResult(
            event_id=event_id,
            event_type=event_type,
            checkout_session=None,
        )

    session = event.get("data", {}).get("object")
    if not isinstance(session, Mapping):
        raise InvalidStripeWebhook("Stripe event has no Checkout Session")
    if session.get("object") != "checkout.session":
        raise InvalidStripeWebhook("Stripe event object is not a Checkout Session")

    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise InvalidStripeWebhook("Stripe Checkout Session has no valid id")

    payment_status = session.get("payment_status")
    if not isinstance(payment_status, str):
        raise InvalidStripeWebhook(
            "Stripe Checkout Session has no valid payment status"
        )

    metadata: Any = session.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise InvalidStripeWebhook("Stripe Checkout Session metadata is invalid")
    local_payment_id = metadata.get("local_payment_id")
    if local_payment_id is not None and (
        not isinstance(local_payment_id, str) or not local_payment_id
    ):
        raise InvalidStripeWebhook(
            "Stripe Checkout Session payment reference is invalid"
        )

    return StripeWebhookResult(
        event_id=event_id,
        event_type=supported_type.value,
        checkout_session=StripeCheckoutSession(
            id=session_id,
            local_payment_id=local_payment_id,
            payment_status=payment_status,
        ),
    )
