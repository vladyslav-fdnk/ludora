from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import LicenseAssignment, Order, Payment
from apps.payments.webhooks import (
    StripeCheckoutEventType,
    StripeCheckoutSession,
    StripeWebhookResult,
    process_stripe_webhook,
)

User = get_user_model()


@override_settings(PAYMENT_PROVIDER="stripe")
class OrderTests(APITestCase):
    checkout_session_id = "cs_test_order_payment"
    checkout_url = (
        "https://checkout.stripe.com/c/pay/cs_test_order_payment"
    )

    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            price=59.99,
            product_type="GAME",
            platform=self.platform,
        )

        self.license_key = LicenseKey.objects.create(
            product=self.product,
            value="TEST-KEY-123",
        )

        self.user = User.objects.create_user(
            email="user1@test.com",
            password="password123",
        )

        self.other_user = User.objects.create_user(
            email="user2@test.com",
            password="password123",
        )
        self.url = reverse("orders:payment-create")

        stripe_client_patcher = patch(
            "apps.payments.providers.stripe.StripeClient"
        )
        self.addCleanup(stripe_client_patcher.stop)
        stripe_client = stripe_client_patcher.start().return_value
        self.create_checkout_session = (
            stripe_client.v1.checkout.sessions.create
        )
        self.create_checkout_session.return_value = SimpleNamespace(
            id=self.checkout_session_id,
            url=self.checkout_url,
        )

    def create_order(self, **changes):
        values = {
            "product": self.product,
            "user": self.user,
            "email": self.user.email,
            "total_price": Decimal("59.99"),
        }
        values.update(changes)
        return Order.objects.create(**values)

    def create_payment(self, order):
        return self.client.post(
            self.url,
            {"order": order.id},
            format="json",
        )

    def complete_checkout(self, payment):
        process_stripe_webhook(
            StripeWebhookResult(
                event_id="evt_test_order_payment",
                event_type=StripeCheckoutEventType.COMPLETED,
                checkout_session=StripeCheckoutSession(
                    id=self.checkout_session_id,
                    local_payment_id=str(payment.id),
                    payment_status="paid",
                ),
            )
        )

    def test_payment_creation_opens_checkout_and_webhook_assigns_license_key(
        self,
    ):
        order = self.create_order()
        self.client.force_authenticate(user=self.user)

        response = self.create_payment(order)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["checkout_url"], self.checkout_url)
        payment = Payment.objects.get(id=response.data["id"])
        self.assertEqual(payment.order, order)
        self.assertEqual(payment.provider, "stripe")
        self.assertEqual(payment.transaction_id, self.checkout_session_id)

        params, options = self.create_checkout_session.call_args.args
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(params["client_reference_id"], order.order_number)
        self.assertEqual(
            params["metadata"],
            {
                "order_number": order.order_number,
                "local_payment_id": str(payment.id),
            },
        )
        self.assertEqual(
            params["line_items"][0]["price_data"]["unit_amount"],
            5999,
        )
        self.assertEqual(
            options,
            {"idempotency_key": f"payment-{payment.id}"},
        )

        self.complete_checkout(payment)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.license_key, self.license_key)
        assignment = LicenseAssignment.objects.get(
            license_key=self.license_key,
        )
        self.assertEqual(assignment.order_item.order, order)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)

    def test_checkout_completion_without_keys_fails_fulfilment(self):
        self.license_key.status = LicenseKey.Status.SOLD
        self.license_key.save()
        order = self.create_order()
        self.client.force_authenticate(user=self.user)

        response = self.create_payment(order)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(id=response.data["id"])
        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            self.complete_checkout(payment)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(payment.status, Payment.Status.CREATED)

    def test_payment_for_already_paid_order_returns_400(self):
        order = self.create_order(status=Order.Status.PAID)
        self.client.force_authenticate(user=self.user)

        response = self.create_payment(order)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(response.data, {"error": "Order already paid"})
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.create_checkout_session.assert_not_called()

    def test_user_cannot_create_payment_for_other_users_order(self):
        order = self.create_order()
        self.client.force_authenticate(user=self.other_user)

        response = self.create_payment(order)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertNotIn(self.license_key.value, str(response.data))
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.create_checkout_session.assert_not_called()

    def test_anonymous_user_cannot_create_payment(self):
        order = self.create_order()

        response = self.create_payment(order)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.create_checkout_session.assert_not_called()
