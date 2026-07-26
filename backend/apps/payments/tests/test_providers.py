from dataclasses import asdict
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.payments.exceptions import PaymentProviderRejected
from apps.payments.providers import (
    CreatePaymentRequest,
    LocalConfirmation,
    LocalPaymentProvider,
    PaymentProvider,
    PaymentProviderStatus,
    get_payment_provider,
)


class LocalPaymentProviderTests(SimpleTestCase):
    def setUp(self):
        self.request = CreatePaymentRequest(
            amount=Decimal("19.99"),
            order_number="LUD-TESTORDER",
            idempotency_key="payment-42",
        )

    def test_implements_provider_contract_and_creates_safe_reference(self):
        provider = LocalPaymentProvider()

        result = provider.create_payment(self.request)

        self.assertIsInstance(provider, PaymentProvider)
        self.assertEqual(result.external_id, "local-pay-payment-42")
        self.assertEqual(result.status, PaymentProviderStatus.PENDING)
        self.assertNotIn("LUD-TESTORDER", result.external_id)
        self.assertNotIn("model", repr(asdict(result)).lower())

    def test_confirmation_succeeds_deterministically(self):
        provider = LocalPaymentProvider()
        created = provider.create_payment(self.request)

        first = provider.confirm_payment(created.external_id)
        second = provider.confirm_payment(created.external_id)

        self.assertEqual(first, second)
        self.assertEqual(first.status, PaymentProviderStatus.SUCCEEDED)

    def test_configured_rejection_returns_normalized_failure(self):
        provider = LocalPaymentProvider(
            confirmation=LocalConfirmation.REJECT
        )
        created = provider.create_payment(self.request)

        result = provider.confirm_payment(created.external_id)

        self.assertEqual(result.status, PaymentProviderStatus.FAILED)

    def test_invalid_simulation_and_reference_are_rejected(self):
        with self.assertRaises(PaymentProviderRejected):
            LocalPaymentProvider(confirmation="SUCCEED")

        with self.assertRaises(PaymentProviderRejected):
            LocalPaymentProvider().confirm_payment("other-pay-1")

    def test_invalid_creation_input_is_rejected(self):
        invalid_requests = (
            CreatePaymentRequest(
                amount=Decimal("-0.01"),
                order_number="LUD-TEST",
                idempotency_key="payment-1",
            ),
            CreatePaymentRequest(
                amount=Decimal("1.00"),
                order_number="",
                idempotency_key="payment-1",
            ),
            CreatePaymentRequest(
                amount=Decimal("1.00"),
                order_number="LUD-TEST",
                idempotency_key="***",
            ),
        )

        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaises(PaymentProviderRejected):
                    LocalPaymentProvider().create_payment(request)


class PaymentProviderSelectionTests(SimpleTestCase):
    @override_settings(PAYMENT_PROVIDER="local")
    def test_default_selection_returns_configured_provider(self):
        self.assertIsInstance(get_payment_provider(), LocalPaymentProvider)

    @override_settings(PAYMENT_PROVIDER="unsupported-default")
    def test_explicit_selection_ignores_default(self):
        self.assertIsInstance(
            get_payment_provider("local"),
            LocalPaymentProvider,
        )

    def test_unsupported_explicit_provider_fails_clearly(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Unsupported payment provider",
        ):
            get_payment_provider("unknown")

    def test_empty_explicit_provider_does_not_fall_back(self):
        with self.assertRaises(ImproperlyConfigured):
            get_payment_provider("")
