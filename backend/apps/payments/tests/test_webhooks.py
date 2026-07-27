import hashlib
import hmac
import json
import time

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

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


def event_payload(event_type: str) -> bytes:
    return json.dumps(
        {
            "id": "evt_test_webhook",
            "object": "event",
            "type": event_type,
            "data": {
                "object": {
                    "id": "cs_test_webhook",
                    "object": "checkout.session",
                    "metadata": {"local_payment_id": "42"},
                }
            },
        },
        separators=(",", ":"),
    ).encode()


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class StripeWebhookAPITests(SimpleTestCase):
    def setUp(self):
        self.url = reverse("payments:stripe-webhook")

    def post(self, payload: bytes, signature: str):
        return self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    def test_accepts_valid_signature_without_authentication(self):
        payload = event_payload("checkout.session.completed")

        response = self.post(payload, stripe_signature(payload))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True})

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
