from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse

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
    
    def test_pay_order_assigns_license_key(self):

        order = Order.objects.create(
            product=self.product,
            email="buyer@test.com",
        )

        response = self.client.post(
            f"/api/orders/{order.id}/pay/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        order.refresh_from_db()
        self.license_key.refresh_from_db()

        self.assertEqual(
            order.status,
            Order.Status.PAID
        )

        self.assertEqual(
            order.license_key,
            self.license_key
        )

        self.assertEqual(
            self.license_key.status,
            LicenseKey.Status.SOLD
        )


    def test_pay_order_without_keys(self):

        self.license_key.status = LicenseKey.Status.SOLD
        self.license_key.save()

        order = Order.objects.create(
            product=self.product,
            email="buyer@test.com",
        )

        response = self.client.post(
            f"/api/orders/{order.id}/pay/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["error"],
            "No keys available"
        )

    def test_pay_already_paid_order_returns_400(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            status=Order.Status.PAID,
        )

        response = self.client.post(
            reverse(
                "orders:order-pay",
                kwargs={
                    "pk": order.id,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data,
            {
                "error": "Already paid",
            },
        )