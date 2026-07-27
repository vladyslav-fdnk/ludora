from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.games.admin import LicenseKeyAdmin, ProductAdmin, mask_license_key
from apps.games.models import Category, LicenseKey, Platform, Product

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
        self.superuser = User.objects.create_superuser(
            email="product-admin@example.com",
            password="password123",
        )
        self.import_url = reverse(
            "admin:games_product_import_license_keys",
            args=(self.product.pk,),
        )

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
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("admin:games_product_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_changelist_displays_annotated_inventory_counts(self):
        categories = [
            Category.objects.create(name="Action", slug="action"),
            Category.objects.create(name="Indie", slug="indie"),
        ]
        self.product.categories.add(*categories)
        for status in (
            LicenseKey.Status.AVAILABLE,
            LicenseKey.Status.RESERVED,
            LicenseKey.Status.SOLD,
        ):
            LicenseKey.objects.create(
                product=self.product,
                value=f"{status}-KEY-1234",
                status=status,
            )
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("admin:games_product_changelist"))

        self.assertContains(response, "Available keys")
        self.assertContains(response, "Sold keys")
        self.assertContains(response, "Total keys")
        row = response.context["cl"].result_list.get(pk=self.product.pk)
        self.assertEqual(row._available_keys_count, 1)
        self.assertEqual(row._sold_keys_count, 1)
        self.assertEqual(row._total_keys_count, 3)

    def test_change_page_has_masked_read_only_license_key_inline(self):
        key = LicenseKey.objects.create(
            product=self.product,
            value="ABCD-PRIVATE-WXYZ",
        )
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("admin:games_product_change", args=(self.product.pk,))
        )

        self.assertContains(response, "License keys")
        self.assertContains(response, mask_license_key(key.value))
        self.assertNotContains(response, key.value)
        self.assertNotContains(response, 'name="license_keys-0-value"')
        self.assertContains(
            response,
            'name="license_keys-MAX_NUM_FORMS" value="0"',
            html=False,
        )
        self.assertNotContains(response, 'class="add-row"')

    def test_change_page_has_import_license_keys_object_tool(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("admin:games_product_change", args=(self.product.pk,))
        )

        self.assertContains(response, "Import License Keys")
        self.assertContains(response, self.import_url)

    def test_successful_csv_import_creates_available_keys_for_product(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {
                "csv_file": self.csv_file(
                    "value,notes\n AAAA-BBBB-CCCC ,first\nDDDD-EEEE-FFFF,second\n"
                )
            },
            follow=True,
        )

        self.assertRedirects(
            response,
            reverse("admin:games_product_change", args=(self.product.pk,)),
        )
        keys = LicenseKey.objects.filter(product=self.product).order_by("value")
        self.assertEqual(keys.count(), 2)
        self.assertEqual(
            list(keys.values_list("value", flat=True)),
            ["AAAA-BBBB-CCCC", "DDDD-EEEE-FFFF"],
        )
        self.assertTrue(
            all(key.status == LicenseKey.Status.AVAILABLE for key in keys)
        )
        self.assertContains(response, "Imported: 2")
        self.assertContains(response, "Skipped duplicates: 0")
        self.assertContains(response, "Skipped empty rows: 0")

    def test_csv_import_skips_database_and_file_duplicates(self):
        LicenseKey.objects.create(
            product=self.product,
            value="EXISTING-KEY",
            status=LicenseKey.Status.RESERVED,
        )
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {
                "csv_file": self.csv_file(
                    "value\nEXISTING-KEY\nNEW-KEY\nNEW-KEY\nEXISTING-KEY\n"
                )
            },
            follow=True,
        )

        self.assertEqual(
            LicenseKey.objects.filter(product=self.product).count(),
            2,
        )
        self.assertEqual(
            LicenseKey.objects.get(
                product=self.product,
                value="EXISTING-KEY",
            ).status,
            LicenseKey.Status.RESERVED,
        )
        self.assertContains(response, "Imported: 1")
        self.assertContains(response, "Skipped duplicates: 3")

    def test_csv_import_ignores_empty_rows(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {"csv_file": self.csv_file("value\n\n   \nVALID-KEY\n,\n")},
            follow=True,
        )

        self.assertEqual(
            list(
                LicenseKey.objects.filter(product=self.product).values_list(
                    "value",
                    flat=True,
                )
            ),
            ["VALID-KEY"],
        )
        self.assertContains(response, "Skipped empty rows: 3")

    def test_csv_import_accepts_utf8_bom(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {"csv_file": self.csv_file("\ufeffvalue\nBOM-KEY\n")},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            LicenseKey.objects.filter(
                product=self.product,
                value="BOM-KEY",
                status=LicenseKey.Status.AVAILABLE,
            ).exists()
        )

    def test_csv_import_with_only_duplicates_reports_all_counters_as_warning(self):
        LicenseKey.objects.create(product=self.product, value="EXISTING-KEY")
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {
                "csv_file": self.csv_file(
                    "value\nEXISTING-KEY\nEXISTING-KEY\n\n"
                )
            },
            follow=True,
        )

        self.assertContains(
            response,
            "Imported: 0 Skipped duplicates: 2 Skipped empty rows: 1",
        )
        self.assertContains(response, '<li class="warning">', html=False)
        self.assertEqual(LicenseKey.objects.filter(product=self.product).count(), 1)

    def test_missing_value_column_displays_form_validation_error(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {"csv_file": self.csv_file("key,notes\nA-B-C,test\n")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'must include a header with a "value" column',
            response.context["form"].errors["csv_file"][0],
        )
        self.assertFalse(LicenseKey.objects.filter(product=self.product).exists())

    def test_non_staff_user_cannot_access_import_page(self):
        user = User.objects.create_user(
            email="import-user@example.com",
            password="password123",
        )
        self.client.force_login(user)

        response = self.client.get(self.import_url)

        self.assertEqual(response.status_code, 302)

    def test_staff_without_product_change_permission_cannot_access_import_page(self):
        user = User.objects.create_user(
            email="staff-import-user@example.com",
            password="password123",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(self.import_url)

        self.assertEqual(response.status_code, 403)

    def test_non_csv_file_extension_displays_validation_error_and_creates_no_keys(
        self,
    ):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {
                "csv_file": self.csv_file(
                    "value\nVALID-KEY\n",
                    filename="license-keys.txt",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "File extension “txt” is not allowed",
            response.context["form"].errors["csv_file"][0],
        )
        self.assertFalse(LicenseKey.objects.filter(product=self.product).exists())

    def test_malformed_csv_does_not_create_any_keys(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            self.import_url,
            {"csv_file": self.csv_file('value\nVALID-KEY\n"unclosed')},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid CSV file")
        self.assertFalse(LicenseKey.objects.filter(product=self.product).exists())

    def test_regular_user_cannot_access_admin(self):
        user = User.objects.create_user(
            email="user@example.com",
            password="password123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)

    @staticmethod
    def csv_file(content, filename="license-keys.csv"):
        return SimpleUploadedFile(
            filename,
            content.encode(),
            content_type="text/csv",
        )


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
        self.assertEqual(mask_license_key("12345678"), "••••••••")
        self.assertEqual(mask_license_key(""), "")

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

    def test_bulk_delete_preserves_sold_keys_and_deletes_available_keys(self):
        sold_key = LicenseKey.objects.create(
            product=self.product,
            value="SOLD-BULK-KEY",
            status=LicenseKey.Status.SOLD,
        )
        available_key = LicenseKey.objects.create(
            product=self.product,
            value="AVAILABLE-BULK-KEY",
        )

        response = self.client.post(
            reverse("admin:games_licensekey_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [sold_key.pk, available_key.pk],
                "post": "yes",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(LicenseKey.objects.filter(pk=sold_key.pk).exists())
        self.assertFalse(LicenseKey.objects.filter(pk=available_key.pk).exists())

    def test_available_key_can_be_deleted_from_admin(self):
        available_key = LicenseKey.objects.create(
            product=self.product,
            value="AVAILABLE-DELETE-KEY",
        )

        response = self.client.post(
            reverse(
                "admin:games_licensekey_delete",
                args=(available_key.pk,),
            ),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(LicenseKey.objects.filter(pk=available_key.pk).exists())

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
