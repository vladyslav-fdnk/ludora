from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.games.admin import LicenseKeyAdmin, ProductAdmin
from apps.games.models import LicenseKey, Platform, Product

User = get_user_model()


class ProductAdminTests(TestCase):
    def setUp(self):
        self.platform = Platform.objects.create(name="Steam", slug="steam")
        self.product = Product.objects.create(
            title="Admin Test Game",
            slug="admin-test-game",
            description="Keep this description",
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            price=Decimal("19.99"),
            is_active=False,
        )
        self.model_admin = ProductAdmin(Product, AdminSite())
        self.request = RequestFactory().post("/")
        self.request.session = {}
        self.request._messages = FallbackStorage(self.request)

    def test_product_is_registered(self):
        self.assertIsInstance(admin.site._registry[Product], ProductAdmin)

    def test_activate_and_deactivate_actions_only_change_active_flag(self):
        original = (self.product.title, self.product.price, self.product.description)

        self.model_admin.activate_products(
            self.request,
            Product.objects.filter(pk=self.product.pk),
        )
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(
            (self.product.title, self.product.price, self.product.description),
            original,
        )

        self.model_admin.deactivate_products(
            self.request,
            Product.objects.filter(pk=self.product.pk),
        )
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(
            (self.product.title, self.product.price, self.product.description),
            original,
        )

    def test_superuser_can_access_product_changelist(self):
        superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse("admin:games_product_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_admin(self):
        user = User.objects.create_user(
            email="user@example.com",
            password="password123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)


class LicenseKeyAdminTests(TestCase):
    def setUp(self):
        platform = Platform.objects.create(name="GOG", slug="gog")
        self.product = Product.objects.create(
            title="Key Test Game",
            slug="key-test-game",
            product_type=Product.ProductType.GAME,
            platform=platform,
            price=Decimal("9.99"),
        )
        self.model_admin = LicenseKeyAdmin(LicenseKey, AdminSite())
        self.superuser = User.objects.create_superuser(
            email="license-admin@example.com",
            password="password123",
        )
        self.client.force_login(self.superuser)

    def test_license_key_is_registered(self):
        self.assertIsInstance(admin.site._registry[LicenseKey], LicenseKeyAdmin)

    def test_masking_hides_full_keys_and_handles_short_values(self):
        long_key = LicenseKey(product=self.product, value="ABCD-SECRET-WXYZ")
        short_key = LicenseKey(product=self.product, value="SHORT")

        masked = self.model_admin.masked_key(long_key)
        self.assertNotEqual(masked, long_key.value)
        self.assertNotIn(long_key.value, masked)
        self.assertTrue(masked.startswith("ABCD"))
        self.assertTrue(masked.endswith("WXYZ"))
        self.assertEqual(self.model_admin.masked_key(short_key), "•••••")

    def test_key_without_order_safely_has_no_assigned_order(self):
        key = LicenseKey.objects.create(
            product=self.product,
            value="UNASSIGNED-KEY",
        )

        self.assertIsNone(self.model_admin.assigned_order(key))

    def test_sold_key_detail_is_visible_but_cannot_be_modified(self):
        sold_key = LicenseKey.objects.create(
            product=self.product,
            value="SOLD-KEY-1234",
            status=LicenseKey.Status.SOLD,
        )
        change_url = reverse("admin:games_licensekey_change", args=(sold_key.pk,))

        response = self.client.get(change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sold_key.value)
        response = self.client.post(
            change_url,
            {
                "product": self.product.pk,
                "value": "CHANGED-KEY",
                "status": LicenseKey.Status.AVAILABLE,
                "_save": "Save",
            },
        )
        sold_key.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(sold_key.value, "SOLD-KEY-1234")
        self.assertEqual(sold_key.status, LicenseKey.Status.SOLD)

    def test_sold_key_cannot_be_deleted(self):
        sold_key = LicenseKey.objects.create(
            product=self.product,
            value="SOLD-KEY-5678",
            status=LicenseKey.Status.SOLD,
        )

        response = self.client.post(
            reverse("admin:games_licensekey_delete", args=(sold_key.pk,)),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(LicenseKey.objects.filter(pk=sold_key.pk).exists())

    def test_available_key_remains_editable(self):
        available_key = LicenseKey.objects.create(
            product=self.product,
            value="AVAILABLE-KEY",
        )

        response = self.client.post(
            reverse("admin:games_licensekey_change", args=(available_key.pk,)),
            {
                "product": self.product.pk,
                "value": "UPDATED-AVAILABLE-KEY",
                "_save": "Save",
            },
        )
        available_key.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(available_key.value, "UPDATED-AVAILABLE-KEY")
        self.assertEqual(available_key.status, LicenseKey.Status.AVAILABLE)

    def test_reserved_key_protects_product_and_value(self):
        reserved_key = LicenseKey.objects.create(
            product=self.product,
            value="RESERVED-KEY",
            status=LicenseKey.Status.RESERVED,
        )

        readonly = self.model_admin.get_readonly_fields(
            RequestFactory().get("/"),
            reserved_key,
        )

        self.assertIn("product", readonly)
        self.assertIn("value", readonly)
