from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product
from apps.orders.models import Order, Payment

User = get_user_model()


@override_settings(PAYMENT_PROVIDER="stripe")
class PaymentCreateAPIViewTests(APITestCase):
    checkout_session_id = "cs_test_payment_create"
    checkout_url = (
        "https://checkout.stripe.com/c/pay/cs_test_payment_create"
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
        self.user = User.objects.create_user(
            email="user1@test.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            email="user2@test.com",
            password="password123",
        )
        self.order = Order.objects.create(
            product=self.product,
            user=self.user,
            email=self.user.email,
            total_price=self.product.price,
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

    def test_anonymous_user_cannot_create_payment(self):
        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertFalse(Payment.objects.exists())
        self.create_checkout_session.assert_not_called()

    def test_user_cannot_create_payment_for_another_users_order(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(Payment.objects.exists())
        self.create_checkout_session.assert_not_called()

    def test_owner_can_create_payment(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        payment = Payment.objects.get(
            id=response.data["id"],
            order=self.order,
        )
        self.assertEqual(payment.provider, "stripe")
        self.assertEqual(payment.transaction_id, self.checkout_session_id)
        self.assertEqual(response.data["checkout_url"], self.checkout_url)
        self.create_checkout_session.assert_called_once()

    def test_checkout_url_is_returned_to_client(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["checkout_url"], self.checkout_url)
        payment = Payment.objects.get(id=response.data["id"])
        params, options = self.create_checkout_session.call_args.args
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(
            params["client_reference_id"],
            self.order.order_number,
        )
        self.assertEqual(
            params["metadata"],
            {
                "order_number": self.order.order_number,
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

    def test_second_payment_is_rejected_when_created_payment_exists(self):
        Payment.objects.create(
            order=self.order,
            status=Payment.Status.CREATED,
            amount=self.product.price,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"error": "Payment already in progress"},
        )
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)
        self.create_checkout_session.assert_not_called()

    def test_second_payment_is_rejected_when_pending_payment_exists(self):
        Payment.objects.create(
            order=self.order,
            status=Payment.Status.PENDING,
            amount=self.product.price,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"error": "Payment already in progress"},
        )
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)
        self.create_checkout_session.assert_not_called()

    def test_payment_is_rejected_when_order_is_already_paid(self):
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=["status"])
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {"error": "Order already paid"},
        )
        self.assertFalse(Payment.objects.filter(order=self.order).exists())
        self.create_checkout_session.assert_not_called()

    def test_payment_retry_is_allowed_after_failed_payment(self):
        failed_payment = Payment.objects.create(
            order=self.order,
            status=Payment.Status.FAILED,
            amount=self.product.price,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"order": self.order.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 2)
        self.assertNotEqual(response.data["id"], failed_payment.id)
        self.assertEqual(response.data["status"], Payment.Status.CREATED)
        self.assertEqual(response.data["checkout_url"], self.checkout_url)
        self.create_checkout_session.assert_called_once()
