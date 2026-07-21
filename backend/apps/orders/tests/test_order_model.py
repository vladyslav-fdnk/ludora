from django.test import TestCase

from apps.games.models import Platform, Product
from apps.orders.models import Order


class OrderModelTests(TestCase):

    def setUp(self):
        platform = Platform.objects.create(
            name="Steam",
            slug="steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            price="29.99",
            product_type="GAME",
            platform=platform,
        )


    def test_order_number_generated_automatically(self):
        order = Order.objects.create(
            product=self.product,
            email="test@example.com",
        )

        self.assertIsNotNone(
            order.order_number
        )

        self.assertTrue(
            order.order_number.startswith("LUD-")
        )