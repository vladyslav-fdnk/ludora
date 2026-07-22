from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Platform, Product
from apps.orders.models import Order


User = get_user_model()


class MyOrdersAPIViewTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="user1",
            email="user1@test.com",
            password="password123",
        )

        self.other_user = User.objects.create_user(
            username="user2",
            email="user2@test.com",
            password="password123",
        )

        self.platform = Platform.objects.create(
            name="Steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            product_type="GAME",
            platform=self.platform,
            price=59.99,
        )

        self.order1 = Order.objects.create(
            user=self.user,
            product=self.product,
            email=self.user.email,
        )

        self.order2 = Order.objects.create(
            user=self.user,
            product=self.product,
            email=self.user.email,
        )

        self.order3 = Order.objects.create(
            user=self.other_user,
            product=self.product,
            email=self.other_user.email,
        )

        self.url = reverse(
            "orders:my-orders",
        )


    def test_anonymous_user_cannot_get_orders(self):
        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


    def test_authenticated_user_can_get_only_own_orders(self):
        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["results"]),
            2,
        )

        order_numbers = [
            order["order_number"]
            for order in response.data["results"]
        ]

        self.assertIn(
            self.order1.order_number,
            order_numbers,
        )

        self.assertIn(
            self.order2.order_number,
            order_numbers,
        )

        self.assertNotIn(
            self.order3.order_number,
            order_numbers,
        )


    def test_orders_are_ordered_by_created_date_desc(self):
        self.order1.created_at = timezone.now()
        self.order1.save()

        self.order2.created_at = timezone.now() + timedelta(seconds=10)
        self.order2.save()

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(
            self.url,
        )

        orders = response.data["results"]

        self.assertEqual(
            orders[0]["order_number"],
            self.order2.order_number,
        )

        self.assertEqual(
            orders[1]["order_number"],
            self.order1.order_number,
        )