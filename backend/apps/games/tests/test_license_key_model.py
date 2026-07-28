from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.games.models import LicenseKey, Platform, Product


class LicenseKeyModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        platform = Platform.objects.create(name="Steam", slug="steam")
        cls.product = Product.objects.create(
            title="Game",
            slug="game",
            product_type=Product.ProductType.GAME,
            platform=platform,
            price="10.00",
        )
        cls.other_product = Product.objects.create(
            title="Other Game",
            slug="other-game",
            product_type=Product.ProductType.GAME,
            platform=platform,
            price="20.00",
        )

    def test_duplicate_key_for_same_product_cannot_be_created(self):
        LicenseKey.objects.create(product=self.product, value="DUPLICATE-KEY")

        with self.assertRaises(IntegrityError), transaction.atomic():
            LicenseKey.objects.create(product=self.product, value="DUPLICATE-KEY")

    def test_valid_keys_are_accepted(self):
        first_key = LicenseKey.objects.create(product=self.product, value="FIRST-KEY")
        second_key = LicenseKey.objects.create(product=self.product, value="SECOND-KEY")
        same_value_other_product = LicenseKey.objects.create(
            product=self.other_product,
            value="FIRST-KEY",
        )

        self.assertEqual(
            {first_key.value, second_key.value},
            {"FIRST-KEY", "SECOND-KEY"},
        )
        self.assertEqual(same_value_other_product.value, first_key.value)
