from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import Order, OrderItem

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
            is_active=True,
        )

        self.license_key = LicenseKey.objects.create(
            product=self.product,
            value="TEST-KEY-123",
        )

        self.user = User.objects.create_user(
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

        self.assertEqual(order.product, self.product)
        self.assertEqual(order.source, Order.Source.DIRECT)
        self.assertEqual(order.total_price, Decimal("59.99"))
        item = order.items.get()
        self.assertEqual(item.product_title, "Cyberpunk 2077")
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.unit_price, Decimal("59.99"))
        self.assertIsNone(order.license_key)
        self.assertIsNone(response.data["license_key"])
        self.assertNotIn(self.license_key.value, str(response.data))

    def test_cannot_create_order_for_inactive_product(self):
        inactive_product = Product.objects.create(
            title="Inactive Game",
            slug="inactive-game",
            price=29.99,
            product_type="GAME",
            platform=self.platform,
            is_active=False,
        )

        response = self.client.post(
            "/api/orders/",
            {
                "email": "buyer@test.com",
                "product": inactive_product.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product", response.data)
        self.assertEqual(Order.objects.count(), 0)

    @patch("apps.orders.services.OrderItem.objects.create")
    def test_order_item_failure_rolls_back_direct_order(self, create_item):
        create_item.side_effect = RuntimeError("database failure")

        with self.assertRaisesMessage(RuntimeError, "database failure"):
            self.client.post(
                "/api/orders/",
                {"email": self.user.email, "product": self.product.pk},
                format="json",
            )

        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())

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
