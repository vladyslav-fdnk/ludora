from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import stripe
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.payments.exceptions import PaymentProviderRejected
from apps.payments.providers import (
    CreatePaymentRequest,
    LocalConfirmation,
    LocalPaymentProvider,
    PaymentProvider,
    PaymentProviderStatus,
    StripeProvider,
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

    @override_settings(
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_example",
        STRIPE_WEBHOOK_SECRET="whsec_example",
        STRIPE_CURRENCY="usd",
        STRIPE_SUCCESS_URL="https://example.com/payments/success",
        STRIPE_CANCEL_URL="https://example.com/payments/cancel",
    )
    def test_stripe_selection_returns_stripe_provider(self):
        self.assertIsInstance(get_payment_provider(), StripeProvider)


class StripeProviderTests(SimpleTestCase):
    valid_settings = {
        "STRIPE_SECRET_KEY": "sk_test_example",
        "STRIPE_WEBHOOK_SECRET": "whsec_example",
        "STRIPE_CURRENCY": "EUR",
        "STRIPE_SUCCESS_URL": "https://example.com/payments/success",
        "STRIPE_CANCEL_URL": "https://example.com/payments/cancel",
    }

    @override_settings(**valid_settings)
    def test_initializes_and_implements_provider_contract(self):
        provider = StripeProvider()

        self.assertIsInstance(provider, PaymentProvider)
        self.assertEqual(provider.name, "stripe")
        self.assertEqual(provider.currency, "eur")
        self.assertEqual(provider.secret_key, "sk_test_example")
        self.assertEqual(
            provider.success_url,
            "https://example.com/payments/success",
        )
        self.assertEqual(
            provider.cancel_url,
            "https://example.com/payments/cancel",
        )
        self.assertIsInstance(provider.client, stripe.StripeClient)

    def test_invalid_configuration_fails_clearly(self):
        invalid_settings = (
            {**self.valid_settings, "STRIPE_SECRET_KEY": ""},
            {**self.valid_settings, "STRIPE_WEBHOOK_SECRET": " "},
            {**self.valid_settings, "STRIPE_CURRENCY": "US"},
            {**self.valid_settings, "STRIPE_SUCCESS_URL": ""},
            {**self.valid_settings, "STRIPE_CANCEL_URL": " "},
        )

        for configured_settings in invalid_settings:
            with self.subTest(settings=configured_settings):
                with override_settings(**configured_settings):
                    with self.assertRaises(ImproperlyConfigured):
                        StripeProvider()

    @override_settings(**valid_settings)
    def test_creates_checkout_session_with_amount_metadata_and_idempotency(self):
        provider = StripeProvider()
        create = Mock(
            return_value=SimpleNamespace(
                id="cs_test_example",
                url="https://checkout.stripe.com/c/pay/cs_test_example",
            )
        )
        provider.client = SimpleNamespace(
            v1=SimpleNamespace(
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(create=create)
                )
            )
        )
        request = CreatePaymentRequest(
            amount=Decimal("19.99"),
            order_number="LUD-TESTORDER",
            idempotency_key="payment-42",
            local_payment_id=42,
        )

        result = provider.create_payment(request)

        self.assertEqual(result.external_id, "cs_test_example")
        self.assertEqual(result.status, PaymentProviderStatus.PENDING)
        self.assertEqual(
            result.checkout_url,
            "https://checkout.stripe.com/c/pay/cs_test_example",
        )
        create.assert_called_once()
        params, options = create.call_args.args
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(
            params["success_url"],
            "https://example.com/payments/success",
        )
        self.assertEqual(
            params["cancel_url"],
            "https://example.com/payments/cancel",
        )
        self.assertEqual(
            params["client_reference_id"], "LUD-TESTORDER"
        )
        self.assertEqual(
            params["line_items"][0]["price_data"]["unit_amount"], 1999
        )
        self.assertEqual(
            params["line_items"][0]["price_data"]["currency"], "eur"
        )
        self.assertEqual(
            params["metadata"],
            {
                "local_payment_id": "42",
                "order_number": "LUD-TESTORDER",
            },
        )
        self.assertEqual(options, {"idempotency_key": "payment-42"})

    @override_settings(**valid_settings)
    def test_omits_unavailable_local_payment_id_from_metadata(self):
        provider = StripeProvider()
        create = Mock(
            return_value=SimpleNamespace(id="cs_test_example", url=None)
        )
        provider.client = SimpleNamespace(
            v1=SimpleNamespace(
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(create=create)
                )
            )
        )

        provider.create_payment(
            CreatePaymentRequest(
                amount=Decimal("1.00"),
                order_number="LUD-TESTORDER",
                idempotency_key="payment-external",
            )
        )

        params = create.call_args.args[0]
        self.assertEqual(
            params["metadata"], {"order_number": "LUD-TESTORDER"}
        )

    @override_settings(**valid_settings)
    def test_wraps_stripe_sdk_errors(self):
        provider = StripeProvider()
        create = Mock(
            side_effect=stripe.APIConnectionError("Stripe unavailable")
        )
        provider.client = SimpleNamespace(
            v1=SimpleNamespace(
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(create=create)
                )
            )
        )

        with self.assertRaises(PaymentProviderRejected) as raised:
            provider.create_payment(
                CreatePaymentRequest(
                    amount=Decimal("19.99"),
                    order_number="LUD-TESTORDER",
                    idempotency_key="payment-42",
                )
            )

        self.assertIsInstance(raised.exception.__cause__, stripe.StripeError)

    @override_settings(**valid_settings)
    def test_rejects_amount_with_more_than_two_decimal_places(self):
        provider = StripeProvider()

        with self.assertRaises(PaymentProviderRejected):
            provider.create_payment(
                CreatePaymentRequest(
                    amount=Decimal("19.999"),
                    order_number="LUD-TESTORDER",
                    idempotency_key="payment-42",
                )
            )

        with self.assertRaises(NotImplementedError):
            provider.confirm_payment("pi_example")
