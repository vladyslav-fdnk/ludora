from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product

"""
Product API
 ├── active products
 ├── inactive products
 ├── platform filter
 ├── search
 └── ordering
"""


class ProductListAPIViewTests(APITestCase):
    """
    Tests for the products list API.
    """

    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
            slug="steam",
        )

        self.epic_platform = Platform.objects.create(
            name="Epic Games",
            slug="epic-games",
        )

        self.active_product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            description="Futuristic action RPG game",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("59.99"),
            is_active=True,
        )

        self.inactive_product = Product.objects.create(
            title="GTA VI",
            slug="gta-vi",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("69.99"),
            is_active=False,
        )

        self.epic_product = Product.objects.create(
            title="Fortnite",
            slug="fortnite",
            description="Battle royale game",
            product_type=Product.ProductType.GAME,
            platform=self.epic_platform,
            price=Decimal("0.00"),
            is_active=True,
        )

    def test_returns_only_active_products(self):
        """
        The products list should contain only active products.
        """
        url = reverse("games:product-list")

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        titles = [product["title"] for product in response.data["results"]]

        self.assertIn(
            "Cyberpunk 2077",
            titles,
        )

        self.assertIn(
            "Fortnite",
            titles,
        )

        self.assertNotIn(
            "GTA VI",
            titles,
        )

    def test_inactive_products_are_not_in_list(self):
        """
        Inactive products should not be visible in catalog.
        """
        url = reverse("games:product-list")

        response = self.client.get(url)

        titles = [product["title"] for product in response.data["results"]]

        self.assertNotIn(
            "GTA VI",
            titles,
        )

    def test_filter_products_by_platform(self):
        """
        Products can be filtered by platform.
        """
        url = reverse("games:product-list")

        response = self.client.get(
            url,
            {
                "platform": self.platform.id,
            },
        )

        titles = [product["title"] for product in response.data["results"]]

        self.assertIn(
            "Cyberpunk 2077",
            titles,
        )

        self.assertNotIn(
            "Fortnite",
            titles,
        )

    def test_search_products_by_title(self):
        """
        Products can be searched by title.
        """
        url = reverse("games:product-list")

        response = self.client.get(
            url,
            {
                "search": "Cyberpunk",
            },
        )

        titles = [product["title"] for product in response.data["results"]]

        self.assertIn(
            "Cyberpunk 2077",
            titles,
        )

        self.assertNotIn(
            "Fortnite",
            titles,
        )

    def test_order_products_by_price_desc(self):
        """
        Products can be ordered by price descending.
        """
        url = reverse("games:product-list")

        response = self.client.get(
            url,
            {
                "ordering": "-price",
            },
        )

        products = response.data["results"]

        self.assertEqual(
            products[0]["title"],
            "Cyberpunk 2077",
        )

        self.assertEqual(
            products[1]["title"],
            "Fortnite",
        )

    def test_order_products_by_price_asc(self):
        """
        Products can be ordered by price ascending.
        """
        url = reverse("games:product-list")

        response = self.client.get(
            url,
            {
                "ordering": "price",
            },
        )

        products = response.data["results"]

        self.assertEqual(
            products[0]["title"],
            "Fortnite",
        )

        self.assertEqual(
            products[1]["title"],
            "Cyberpunk 2077",
        )
