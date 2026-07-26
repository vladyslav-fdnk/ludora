from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import Order, OrderItem
from apps.orders.services import create_direct_order

User = get_user_model()


class MyOrdersAPIViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user1@test.com",
            password="password123",
        )

        self.other_user = User.objects.create_user(
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

        self.order1 = create_direct_order(
            user=self.user,
            product=self.product,
            email=self.user.email,
        )

        self.order2 = create_direct_order(
            user=self.user,
            product=self.product,
            email=self.user.email,
        )

        self.order3 = create_direct_order(
            user=self.other_user,
            product=self.product,
            email=self.other_user.email,
        )

        self.url = reverse("orders:order-list")

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

        order_numbers = [order["order_number"] for order in response.data["results"]]

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

        serialized = response.data["results"][0]
        self.assertEqual(
            set(serialized),
            {
                "id",
                "order_number",
                "product",
                "status",
                "source",
                "total_price",
                "price_paid",
                "created_at",
                "updated_at",
                "paid_at",
                "items",
            },
        )
        self.assertEqual(serialized["source"], Order.Source.DIRECT)
        self.assertEqual(serialized["product"], "Cyberpunk 2077")
        self.assertEqual(serialized["total_price"], "59.99")
        self.assertEqual(serialized["items"][0]["product_title"], "Cyberpunk 2077")
        self.assertEqual(serialized["items"][0]["unit_price"], "59.99")

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

    def test_list_queries_are_bounded_and_uses_item_snapshots(self):
        self.product.title = "Renamed Product"
        self.product.price = Decimal("99.99")
        self.product.save(update_fields=("title", "price"))
        self.client.force_authenticate(user=self.user)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 4)
        for order in response.data["results"]:
            self.assertEqual(order["product"], "Cyberpunk 2077")
            self.assertEqual(order["items"][0]["product_title"], "Cyberpunk 2077")
            self.assertEqual(order["items"][0]["unit_price"], "59.99")

    def test_malformed_jwt_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer malformed-token")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_sees_owned_cart_order_but_not_guest_order(self):
        cart_order = Order.objects.create(
            user=self.user,
            email=self.user.email,
            source=Order.Source.CART,
            total_price=Decimal("119.98"),
        )
        OrderItem.objects.create(
            order=cart_order,
            product=self.product,
            product_title=self.product.title,
            quantity=2,
            unit_price=Decimal("59.99"),
        )
        guest_order = create_direct_order(
            user=None,
            product=self.product,
            email="guest@history.invalid",
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url, {"user": self.other_user.pk})

        order_numbers = {
            order["order_number"] for order in response.data["results"]
        }
        self.assertIn(cart_order.order_number, order_numbers)
        self.assertNotIn(guest_order.order_number, order_numbers)
        self.assertNotIn(self.order3.order_number, order_numbers)

    def test_list_is_paginated_with_project_page_size(self):
        for _ in range(9):
            create_direct_order(
                user=self.user,
                product=self.product,
                email=self.user.email,
            )
        self.client.force_authenticate(user=self.user)

        first_page = self.client.get(self.url)
        second_page = self.client.get(self.url, {"page": 2})

        self.assertEqual(first_page.data["count"], 11)
        self.assertEqual(len(first_page.data["results"]), 10)
        self.assertEqual(len(second_page.data["results"]), 1)

    def test_staff_sees_owned_other_user_and_guest_orders_without_keys(self):
        staff = User.objects.create_user(
            email="staff@history.invalid",
            password="password123",
            is_staff=True,
        )
        guest_order = create_direct_order(
            user=None,
            product=self.product,
            email="guest@history.invalid",
        )
        license_key = LicenseKey.objects.create(
            product=self.product,
            value="HISTORY-SECRET-KEY",
            status=LicenseKey.Status.SOLD,
        )
        guest_order.license_key = license_key
        guest_order.save(update_fields=("license_key", "updated_at"))
        self.client.force_authenticate(user=staff)

        response = self.client.get(self.url)

        order_numbers = {
            order["order_number"] for order in response.data["results"]
        }
        self.assertEqual(
            order_numbers,
            {
                self.order1.order_number,
                self.order2.order_number,
                self.order3.order_number,
                guest_order.order_number,
            },
        )
        self.assertNotIn(license_key.value, str(response.data))
        self.assertNotIn("license_key", str(response.data))
        self.assertNotIn("email", response.data["results"][0])
        self.assertNotIn("user", response.data["results"][0])


class OrderDetailAPIViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="detail-owner@history.invalid",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            email="detail-other@history.invalid",
            password="password123",
        )
        self.platform = Platform.objects.create(name="Detail Platform")
        self.product = Product.objects.create(
            title="Detail Product",
            slug="detail-product",
            product_type="GAME",
            platform=self.platform,
            price=Decimal("29.99"),
        )
        self.order1 = create_direct_order(
            user=self.user,
            product=self.product,
            email=self.user.email,
        )
        self.order3 = create_direct_order(
            user=self.other_user,
            product=self.product,
            email=self.other_user.email,
        )
        self.url = reverse("orders:order-detail", kwargs={"pk": self.order1.pk})

    def test_anonymous_user_cannot_retrieve_order(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_retrieve_safe_order_detail(self):
        license_key = LicenseKey.objects.create(
            product=self.product,
            value="OWNER-HISTORY-SECRET",
            status=LicenseKey.Status.SOLD,
        )
        self.order1.license_key = license_key
        self.order1.save(update_fields=("license_key", "updated_at"))
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.order1.pk)
        self.assertNotIn(license_key.value, str(response.data))
        self.assertNotIn("license_key", response.data)
        self.assertNotIn("email", response.data)
        self.assertNotIn("user", response.data)

    def test_other_user_receives_not_found(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_order_returns_not_found(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse("orders:order-detail", kwargs={"pk": 999999})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_another_users_order_and_guest_order(self):
        staff = User.objects.create_user(
            email="staff-detail@history.invalid",
            password="password123",
            is_staff=True,
        )
        guest_order = create_direct_order(
            user=None,
            product=self.product,
            email="guest-detail@history.invalid",
        )
        self.client.force_authenticate(user=staff)

        other_response = self.client.get(
            reverse("orders:order-detail", kwargs={"pk": self.order3.pk})
        )
        guest_response = self.client.get(
            reverse("orders:order-detail", kwargs={"pk": guest_order.pk})
        )

        self.assertEqual(other_response.status_code, status.HTTP_200_OK)
        self.assertEqual(guest_response.status_code, status.HTTP_200_OK)
