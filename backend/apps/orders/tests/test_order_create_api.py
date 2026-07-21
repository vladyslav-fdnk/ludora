from rest_framework.test import APITestCase
from rest_framework import status

from apps.games.models import Product, LicenseKey, Platform
from apps.orders.models import Order


class OrderTests(APITestCase):

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

    def test_create_order(self):
        response = self.client.post(
            "/api/orders/",
            {
                "email": "buyer@test.com",
                "product": self.product.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(
            response.data["status"],
            "CREATED"
        )

        order = Order.objects.get(
            id=response.data["id"]
        )

        self.assertIsNone(
            order.license_key
        )
