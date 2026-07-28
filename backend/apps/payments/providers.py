from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.payments.exceptions import PaymentProviderRejected


class PaymentProviderStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class CreatePaymentRequest:
    amount: Decimal
    order_number: str
    idempotency_key: str
    local_payment_id: int | str | None = None


@dataclass(frozen=True)
class ProviderPayment:
    external_id: str
    status: PaymentProviderStatus
    checkout_url: str | None = None


@runtime_checkable
class PaymentProvider(Protocol):
    name: str

    def create_payment(self, request: CreatePaymentRequest) -> ProviderPayment:
        ...

    def confirm_payment(self, external_id: str) -> ProviderPayment:
        ...


class LocalConfirmation(StrEnum):
    SUCCEED = "SUCCEED"
    REJECT = "REJECT"


class LocalPaymentProvider:
    """Deterministic, credential-free payment simulation for local use."""

    name = "local"
    _reference_prefix = "local-pay-"

    def __init__(
        self,
        *,
        confirmation: LocalConfirmation = LocalConfirmation.SUCCEED,
    ) -> None:
        if not isinstance(confirmation, LocalConfirmation):
            raise PaymentProviderRejected("Invalid local payment simulation")
        self._confirmation = confirmation

    def create_payment(self, request: CreatePaymentRequest) -> ProviderPayment:
        if request.amount < 0:
            raise PaymentProviderRejected("Invalid payment amount")
        if not request.order_number or not request.idempotency_key:
            raise PaymentProviderRejected("Invalid payment request")

        safe_key = "".join(
            character
            for character in request.idempotency_key.lower()
            if character.isascii() and (character.isalnum() or character == "-")
        )
        if not safe_key:
            raise PaymentProviderRejected("Invalid payment request")

        return ProviderPayment(
            external_id=f"{self._reference_prefix}{safe_key}"[:255],
            status=PaymentProviderStatus.PENDING,
        )

    def confirm_payment(self, external_id: str) -> ProviderPayment:
        if not external_id.startswith(self._reference_prefix):
            raise PaymentProviderRejected("Invalid local payment reference")

        status = (
            PaymentProviderStatus.SUCCEEDED
            if self._confirmation is LocalConfirmation.SUCCEED
            else PaymentProviderStatus.FAILED
        )
        return ProviderPayment(external_id=external_id, status=status)


class StripeProvider:
    """Stripe Checkout provider."""

    name = "stripe"

    def __init__(self) -> None:
        self.secret_key = self._required_setting("STRIPE_SECRET_KEY")
        self.webhook_secret = self._required_setting(
            "STRIPE_WEBHOOK_SECRET"
        )
        self.currency = self._required_setting("STRIPE_CURRENCY").lower()
        self.success_url = self._required_setting("STRIPE_SUCCESS_URL")
        self.cancel_url = self._required_setting("STRIPE_CANCEL_URL")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ImproperlyConfigured(
                "STRIPE_CURRENCY must be a three-letter currency code"
            )

        self.client = stripe.StripeClient(self.secret_key)

    @staticmethod
    def _required_setting(name: str) -> str:
        value = getattr(settings, name, "")
        if not isinstance(value, str) or not value.strip():
            raise ImproperlyConfigured(
                f"{name} must be configured when using Stripe"
            )
        return value.strip()

    def create_payment(self, request: CreatePaymentRequest) -> ProviderPayment:
        if request.amount < 0:
            raise PaymentProviderRejected("Invalid payment amount")
        if not request.order_number or not request.idempotency_key:
            raise PaymentProviderRejected("Invalid payment request")

        minor_units = request.amount * 100
        if minor_units != minor_units.to_integral_value():
            raise PaymentProviderRejected(
                "Payment amount has unsupported precision"
            )

        metadata = {"order_number": request.order_number}
        if request.local_payment_id is not None:
            metadata["local_payment_id"] = str(request.local_payment_id)

        try:
            session = self.client.v1.checkout.sessions.create(
                {
                    "mode": "payment",
                    "success_url": self.success_url,
                    "cancel_url": self.cancel_url,
                    "client_reference_id": request.order_number,
                    "line_items": [
                        {
                            "price_data": {
                                "currency": self.currency,
                                "product_data": {
                                    "name": f"Order {request.order_number}",
                                },
                                "unit_amount": int(minor_units),
                            },
                            "quantity": 1,
                        }
                    ],
                    "metadata": metadata,
                },
                {"idempotency_key": request.idempotency_key},
            )
        except stripe.StripeError as exc:
            raise PaymentProviderRejected(
                "Stripe could not create Checkout Session"
            ) from exc

        return ProviderPayment(
            external_id=session.id,
            status=PaymentProviderStatus.PENDING,
            checkout_url=getattr(session, "url", None),
        )

    def confirm_payment(self, external_id: str) -> ProviderPayment:
        raise NotImplementedError(
            "Stripe payment confirmation is not implemented"
        )


def get_payment_provider(
    provider_name: str | None = None,
) -> PaymentProvider:
    selected_name = (
        getattr(settings, "PAYMENT_PROVIDER", "local")
        if provider_name is None
        else provider_name
    )
    if selected_name == "local":
        return LocalPaymentProvider()
    if selected_name == "stripe":
        return StripeProvider()
    raise ImproperlyConfigured(
        f"Unsupported payment provider: {selected_name!r}"
    )
