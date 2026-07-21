from decimal import Decimal

from django.test import TestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import Order
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

        with self.assertRaises(ValueError) as error:
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

        order.refresh_from_db()

        self.assertEqual(
            order.price_paid,
            Decimal("59.99"),
        )

        self.assertIsNotNone(
            order.paid_at,
        )