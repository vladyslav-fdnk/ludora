from decimal import Decimal

from django.test import TestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment
from apps.orders.services import pay_order


class OrderServiceTests(TestCase):
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

    def test_pay_order_assigns_license_key(self):

        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()

        self.assertEqual(
            order.status,
            Order.Status.PAID,
        )

        self.assertEqual(
            order.license_key,
            self.license_key,
        )

        self.assertEqual(
            self.license_key.status,
            LicenseKey.Status.SOLD,
        )

    def test_cannot_pay_already_paid_order(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            status=Order.Status.PAID,
        )

        with self.assertRaises(OrderPaymentError) as error:
            pay_order(order.id)

        self.assertEqual(
            str(error.exception),
            "Already paid",
        )

    def test_pay_order_saves_payment_data(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        pay_order(order.id)

        payment = Payment.objects.get(
            order=order,
        )

        self.assertEqual(
            payment.amount,
            Decimal("59.99"),
        )

        self.assertIsNotNone(
            payment.paid_at,
        )

    def test_payment_created_after_successful_payment(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        pay_order(order.id)

        payment = Payment.objects.get(
            order=order,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.PAID,
        )

        self.assertEqual(
            payment.amount,
            Decimal(str(self.product.price)),
        )

        self.assertIsNotNone(
            payment.paid_at,
        )
