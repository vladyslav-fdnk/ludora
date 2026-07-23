from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product

User = get_user_model()


class ProductUpdateAPIViewTests(APITestCase):
    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
            slug="steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            description="Action RPG",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("59.99"),
            is_active=True,
        )

    def test_anonymous_user_cannot_update_product(self):
        url = reverse(
            "games:product-update",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.patch(
            url,
            {
                "price": "10.00",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_admin_can_update_product(self):

        admin = User.objects.create_superuser(
            username="admin",
            password="password123",
        )

        self.client.force_authenticate(
            user=admin,
        )

        url = reverse(
            "games:product-update",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.patch(
            url,
            {
                "price": "39.99",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.product.refresh_from_db()

        self.assertEqual(
            str(self.product.price),
            "39.99",
        )
