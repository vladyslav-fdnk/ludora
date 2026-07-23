from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import Order

User = get_user_model()


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

        self.user = User.objects.create_user(
            username="buyer",
            email="buyer@test.com",
            password="password123",
        )

        self.client.force_authenticate(
            user=self.user,
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

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(response.data["status"], "CREATED")

        order = Order.objects.get(id=response.data["id"])

        self.assertIsNone(order.license_key)

    def test_authenticated_user_is_assigned_to_order(self):
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
            status.HTTP_201_CREATED,
        )

        order = Order.objects.get(
            id=response.data["id"],
        )

        self.assertEqual(
            order.user,
            self.user,
        )

    def test_anonymous_user_cannot_create_order(self):

        self.client.force_authenticate(
            user=None,
        )

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
            status.HTTP_401_UNAUTHORIZED,
        )
