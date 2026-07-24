from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

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

    def test_pay_order_persists_completed_sale_fields(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )
        paid_at = timezone.now()

        with patch(
            "apps.orders.services.timezone.now",
            return_value=paid_at,
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        payment = Payment.objects.get(
            order=order,
        )

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.price_paid, Decimal("59.99"))
        self.assertEqual(order.paid_at, paid_at)
        self.assertEqual(order.license_key, self.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        self.assertEqual(self.license_key.sold_at, paid_at)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.amount, Decimal("59.99"))
        self.assertEqual(payment.paid_at, paid_at)

    def test_price_paid_remains_unchanged_after_product_price_changes(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        pay_order(order.id)
        order.refresh_from_db()
        paid_price = order.price_paid

        self.product.price = Decimal("79.99")
        self.product.save()
        order.refresh_from_db()

        self.assertEqual(paid_price, Decimal("59.99"))
        self.assertEqual(order.price_paid, Decimal("59.99"))
        self.assertEqual(order.product.price, Decimal("79.99"))
