import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import LicenseAssignment, Order, Payment
from apps.payments.webhooks import (
    StripeCheckoutEventType,
    parse_stripe_webhook,
)

WEBHOOK_SECRET = "whsec_test_webhook"


def stripe_signature(payload: bytes) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def event_payload(
    event_type: str,
    *,
    payment_id: str | None = "42",
    session_id: str = "cs_test_webhook",
) -> bytes:
    metadata = (
        {}
        if payment_id is None
        else {"local_payment_id": payment_id}
    )
    return json.dumps(
        {
            "id": "evt_test_webhook",
            "object": "event",
            "type": event_type,
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "metadata": metadata,
                }
            },
        },
        separators=(",", ":"),
    ).encode()


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class StripeWebhookAPITests(TestCase):
    def setUp(self):
        self.url = reverse("payments:stripe-webhook")
        self.platform = Platform.objects.create(name="Steam")
        self.product = Product.objects.create(
            title="Webhook Game",
            slug="webhook-game",
            price=Decimal("19.99"),
            product_type="GAME",
            platform=self.platform,
        )
        self.order = Order.objects.create(
            product=self.product,
            email="buyer@example.com",
            total_price=Decimal("19.99"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            status=Payment.Status.PENDING,
            amount=Decimal("19.99"),
            provider="stripe",
            transaction_id="cs_test_webhook",
        )
        self.license_key = LicenseKey.objects.create(
            product=self.product,
            value="WEBHOOK-KEY",
        )

    def post(self, payload: bytes, signature: str):
        return self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    def test_accepts_valid_signature_without_authentication(self):
        payload = event_payload(
            "checkout.session.completed",
            payment_id=str(self.payment.id),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True})
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        self.assertEqual(
            LicenseAssignment.objects.filter(
                order_item__order=self.order
            ).count(),
            1,
        )
        dispatch_email.assert_called_once_with(self.order.id)

    def test_duplicate_successful_delivery_is_idempotent(self):
        payload = event_payload(
            "checkout.session.async_payment_succeeded",
            payment_id=str(self.payment.id),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            first = self.post(payload, stripe_signature(payload))
        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as duplicate_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            second = self.post(payload, stripe_signature(payload))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            LicenseAssignment.objects.filter(
                order_item__order=self.order
            ).count(),
            1,
        )
        dispatch_email.assert_called_once_with(self.order.id)
        duplicate_email.assert_not_called()

    def test_async_payment_failed_marks_payment_failed(self):
        payload = event_payload(
            "checkout.session.async_payment_failed",
            payment_id=str(self.payment.id),
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_expired_session_marks_payment_failed(self):
        payload = event_payload(
            "checkout.session.expired",
            payment_id=str(self.payment.id),
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_rejects_missing_payment(self):
        payload = event_payload(
            "checkout.session.completed",
            payment_id="999999",
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_rejects_invalid_metadata(self):
        payload = event_payload(
            "checkout.session.completed",
            payment_id=None,
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_rejects_non_stripe_payment(self):
        self.payment.provider = "local"
        self.payment.save(update_fields=("provider",))
        payload = event_payload(
            "checkout.session.completed",
            payment_id=str(self.payment.id),
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_rejects_checkout_session_from_another_payment(self):
        payload = event_payload(
            "checkout.session.completed",
            payment_id=str(self.payment.id),
            session_id="cs_test_different",
        )

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(LicenseAssignment.objects.exists())

    def test_rejects_invalid_signature(self):
        payload = event_payload("checkout.session.completed")

        response = self.post(payload, "t=1,v1=invalid")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid Stripe webhook"})

    def test_rejects_malformed_payload_with_valid_signature(self):
        payload = b'{"not valid JSON"'

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 400)

    def test_acknowledges_unsupported_event(self):
        payload = event_payload("customer.created")

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 200)

    def test_rejects_non_post_requests(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)


class StripeWebhookParserTests(SimpleTestCase):
    def test_parses_each_supported_checkout_session_event(self):
        for event_type in StripeCheckoutEventType:
            with self.subTest(event_type=event_type):
                payload = event_payload(event_type.value)

                result = parse_stripe_webhook(
                    payload=payload,
                    signature=stripe_signature(payload),
                    secret=WEBHOOK_SECRET,
                )

                self.assertTrue(result.is_supported)
                self.assertEqual(result.event_id, "evt_test_webhook")
                self.assertEqual(result.event_type, event_type.value)
                self.assertEqual(
                    result.checkout_session.id,
                    "cs_test_webhook",
                )
                self.assertEqual(
                    result.checkout_session.local_payment_id,
                    "42",
                )

    def test_returns_structured_noop_for_unsupported_event(self):
        payload = event_payload("customer.created")

        result = parse_stripe_webhook(
            payload=payload,
            signature=stripe_signature(payload),
            secret=WEBHOOK_SECRET,
        )

        self.assertFalse(result.is_supported)
        self.assertEqual(result.event_type, "customer.created")
        self.assertIsNone(result.checkout_session)
