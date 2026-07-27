from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.games.models import Platform, Product
from apps.orders.admin import OrderAdmin, PaymentAdmin
from apps.orders.models import Order, OrderItem, Payment

User = get_user_model()


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
        self.superuser = User.objects.create_superuser(
            email="order-admin@example.com",
            password="password123",
        )
        self.client.force_login(self.superuser)
        self.order = Order.objects.create(
            product=self.product,
            email="customer@example.com",
            source=Order.Source.DIRECT,
            total_price=Decimal("29.99"),
            price_paid=Decimal("29.99"),
            status=Order.Status.PAID,
            paid_at=timezone.now(),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title=self.product.title,
            quantity=1,
            unit_price=self.product.price,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            status=Payment.Status.PAID,
            provider="local",
            transaction_id="txn-admin-search-123",
            amount=Decimal("29.99"),
            paid_at=timezone.now(),
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

    def test_order_change_page_has_read_only_items_and_payments(self):
        response = self.client.get(
            reverse("admin:orders_order_change", args=(self.order.pk,))
        )

        self.assertContains(response, "Order items")
        self.assertContains(response, "Payments")
        self.assertContains(response, "Payment ID")
        self.assertContains(response, self.payment.transaction_id)
        self.assertNotContains(response, 'name="items-0-DELETE"')
        self.assertNotContains(response, 'name="payments-0-DELETE"')
        self.assertContains(
            response,
            'name="items-MAX_NUM_FORMS" value="0"',
            html=False,
        )
        self.assertContains(
            response,
            'name="payments-MAX_NUM_FORMS" value="0"',
            html=False,
        )
        self.assertNotContains(response, 'class="add-row"')
        self.assertNotContains(response, 'name="payments-0-status"')

    def test_order_changelist_has_paid_at_and_status_badge(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))

        self.assertContains(response, "Paid at")
        self.assertContains(response, ">Paid</span>", html=False)

    def test_order_deletion_is_disabled(self):
        delete_response = self.client.post(
            reverse("admin:orders_order_delete", args=(self.order.pk,)),
            {"post": "yes"},
        )
        changelist_response = self.client.get(
            reverse("admin:orders_order_changelist")
        )

        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertIsNone(changelist_response.context["action_form"])

    def test_payment_changelist_displays_diagnostics_and_status_badge(self):
        response = self.client.get(reverse("admin:orders_payment_changelist"))

        self.assertContains(response, "Provider")
        self.assertContains(response, "Transaction id")
        self.assertContains(response, "Paid at")
        self.assertContains(response, self.payment.transaction_id)
        self.assertContains(response, ">Paid</span>", html=False)

    def test_payment_searches_by_transaction_id(self):
        response = self.client.get(
            reverse("admin:orders_payment_changelist"),
            {"q": self.payment.transaction_id},
        )

        self.assertContains(response, self.payment.transaction_id)
        self.assertEqual(list(response.context["cl"].result_list), [self.payment])

    def test_payment_creation_and_deletion_are_disabled(self):
        add_response = self.client.get(reverse("admin:orders_payment_add"))
        delete_response = self.client.post(
            reverse("admin:orders_payment_delete", args=(self.payment.pk,)),
            {"post": "yes"},
        )

        self.assertEqual(add_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
