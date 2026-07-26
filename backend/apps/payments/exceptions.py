class PaymentProviderError(Exception):
    """Base error raised by a payment provider implementation."""


class PaymentProviderRejected(PaymentProviderError):
    """Raised when provider input or a provider operation is rejected."""
