from decimal import Decimal

from django.contrib import admin
from django.test import TestCase

from apps.games.models import Platform, Product
from apps.orders.admin import OrderAdmin, PaymentAdmin
from apps.orders.models import Order, Payment


class TransactionAdminTests(TestCase):
    def setUp(self):
        platform = Platform.objects.create(name="Steam", slug="steam")
        self.product = Product.objects.create(
            title="Order Admin Game",
            slug="order-admin-game",
            product_type=Product.ProductType.GAME,
            platform=platform,
            price=Decimal("29.99"),
        )

    def test_order_is_registered_and_business_fields_are_read_only(self):
        model_admin = admin.site._registry[Order]

        self.assertIsInstance(model_admin, OrderAdmin)
        for field in ("status", "price_paid", "license_key", "paid_at"):
            self.assertIn(field, model_admin.readonly_fields)

    def test_payment_is_registered_and_business_data_is_read_only(self):
        model_admin = admin.site._registry[Payment]

        self.assertIsInstance(model_admin, PaymentAdmin)
        for field in ("order", "status", "amount", "transaction_id", "paid_at"):
            self.assertIn(field, model_admin.readonly_fields)

    def test_transaction_admins_have_no_unsafe_custom_actions(self):
        order_admin = admin.site._registry[Order]
        payment_admin = admin.site._registry[Payment]

        self.assertFalse(order_admin.actions)
        self.assertFalse(payment_admin.actions)
