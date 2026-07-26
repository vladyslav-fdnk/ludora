from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

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


@dataclass(frozen=True)
class ProviderPayment:
    external_id: str
    status: PaymentProviderStatus


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
    raise ImproperlyConfigured(
        f"Unsupported payment provider: {selected_name!r}"
    )
