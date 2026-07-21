from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product, Category


class ProductDetailAPIViewTests(APITestCase):

    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
            slug="steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            description="Action RPG game",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("59.99"),
            is_active=True,
        )

        self.inactive_product = Product.objects.create(
            title="Hidden Game",
            slug="hidden-game",
            description="Not visible",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("10.00"),
            is_active=False,
        )
        
        self.category = Category.objects.create(
            name="RPG",
            slug="rpg",
        )

        self.product.categories.add(
            self.category
        )

    def test_get_product_detail(self):
        url = reverse(
            "games:product-detail",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["title"],
            "Cyberpunk 2077",
        )

        self.assertEqual(
            response.data["platform"],
            "Steam",
        )

    def test_inactive_product_returns_404(self):
        url = reverse(
            "games:product-detail",
            kwargs={
                "pk": self.inactive_product.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
    
    def test_product_detail_contains_categories(self):
        url = reverse(
            "games:product-detail",
            kwargs={
                "pk": self.product.id,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.data["categories"],
            ["RPG"],
        )