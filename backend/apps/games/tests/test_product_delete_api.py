from decimal import Decimal

from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product


class ProductDeleteAPIViewTests(APITestCase):

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

    def test_anonymous_user_cannot_delete_product(self):
        url = reverse(
            "games:product-delete",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertTrue(
            Product.objects.filter(
                id=self.product.id
            ).exists()
        )
    
    def test_admin_can_delete_product(self):
        admin = User.objects.create_superuser(
            username="admin",
            password="password123",
        )

        self.client.force_authenticate(
            user=admin,
        )

        url = reverse(
            "games:product-delete",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.product.refresh_from_db()

        self.assertFalse(
            self.product.is_active
        )

    def test_deleted_product_not_visible_in_catalog(self):
        from django.contrib.auth.models import User

        admin = User.objects.create_superuser(
            username="admin",
            password="password123",
        )

        self.client.force_authenticate(
            user=admin,
        )

        delete_url = reverse(
            "games:product-delete",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.delete(
            delete_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        list_url = reverse(
            "games:product-list"
        )

        response = self.client.get(
            list_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            0,
        )