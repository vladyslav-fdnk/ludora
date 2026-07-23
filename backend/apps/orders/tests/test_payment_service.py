from decimal import Decimal

from django.test import TestCase

from apps.games.models import Platform, Product
from apps.orders.models import (
    Order,
    Payment,
)
from apps.orders.services import create_payment


class PaymentServiceTests(TestCase):
    def setUp(self):

        self.platform = Platform.objects.create(name="Steam")

        self.product = Product.objects.create(
            title="Cyber Game",
            price=Decimal("59.99"),
            platform=self.platform,
        )

    def test_create_payment_for_order(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        payment = create_payment(order)

        self.assertEqual(
            payment.order,
            order,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.CREATED,
        )

        self.assertEqual(
            payment.amount,
            Decimal("59.99"),
        )
