from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError, loads
from typing import Any, Mapping

import stripe


class StripeCheckoutEventType(StrEnum):
    COMPLETED = "checkout.session.completed"
    ASYNC_PAYMENT_SUCCEEDED = "checkout.session.async_payment_succeeded"
    ASYNC_PAYMENT_FAILED = "checkout.session.async_payment_failed"
    EXPIRED = "checkout.session.expired"


@dataclass(frozen=True)
class StripeCheckoutSession:
    id: str
    local_payment_id: str | None


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
        ),
    )
