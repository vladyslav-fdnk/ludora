from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product


class ProductCreateAPIViewTests(APITestCase):

    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
            slug="steam",
        )

        self.admin = User.objects.create_superuser(
            username="admin",
            password="password123",
        )

    def test_anonymous_user_cannot_create_product(self):
        url = reverse(
            "games:product-create"
        )

        response = self.client.post(
            url,
            {
                "title": "New Game",
                "slug": "new-game",
                "description": "Test",
                "product_type": "GAME",
                "platform": self.platform.id,
                "price": "50.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_can_create_product(self):
        self.client.force_authenticate(
            user=self.admin,
        )

        url = reverse(
            "games:product-create"
        )

        response = self.client.post(
            url,
            {
                "title": "Elden Ring",
                "slug": "elden-ring",
                "description": "Action RPG",
                "product_type": "GAME",
                "platform": self.platform.id,
                "price": "49.99",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["title"],
            "Elden Ring",
        )

        self.assertTrue(
            Product.objects.filter(
                slug="elden-ring"
            ).exists()
        )

    def test_admin_cannot_create_product_without_price(self):
        self.client.force_authenticate(
            user=self.admin,
        )

        url = reverse(
            "games:product-create"
        )

        response = self.client.post(
            url,
            {
                "title": "No Price Game",
                "slug": "no-price-game",
                "description": "Test",
                "product_type": "GAME",
                "platform": self.platform.id,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "price",
            response.data,
        )
    
    def test_admin_cannot_create_product_with_existing_slug(self):
        Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            product_type="GAME",
            platform=self.platform,
            price="59.99",
        )

        self.client.force_authenticate(
            user=self.admin,
        )

        url = reverse(
            "games:product-create"
        )

        response = self.client.post(
            url,
            {
                "title": "Another Cyberpunk",
                "slug": "cyberpunk-2077",
                "product_type": "GAME",
                "platform": self.platform.id,
                "price": "40.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "slug",
            response.data,
        )