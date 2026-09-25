from io import StringIO

import pytest
from django.core.management import call_command

from apps.games.management.commands.seed_demo import PRODUCTS
from apps.games.models import LicenseKey, Product

pytestmark = pytest.mark.django_db


def seed(**options) -> str:
    out = StringIO()
    call_command("seed_demo", stdout=out, **options)
    return out.getvalue()


def test_seed_demo_creates_active_catalogue_with_available_keys():
    seed(keys_per_product=3)

    products = Product.objects.filter(slug__in=[p[0] for p in PRODUCTS])
    assert products.count() == len(PRODUCTS)
    assert all(product.is_active for product in products)
    for product in products:
        assert product.categories.exists()
        assert product.license_keys.filter(status=LicenseKey.Status.AVAILABLE).count() == 3


def test_seed_demo_is_idempotent():
    seed(keys_per_product=3)
    output = seed(keys_per_product=3)

    assert Product.objects.count() == len(PRODUCTS)
    assert LicenseKey.objects.count() == 3 * len(PRODUCTS)
    assert "0 new license keys" in output


def test_seed_demo_tops_up_only_available_keys():
    seed(keys_per_product=2)
    product = Product.objects.get(slug=PRODUCTS[0][0])
    sold_key = product.license_keys.first()
    assert sold_key is not None
    product.license_keys.filter(pk=sold_key.pk).update(
        status=LicenseKey.Status.SOLD
    )

    seed(keys_per_product=2)

    assert product.license_keys.filter(status=LicenseKey.Status.AVAILABLE).count() == 2
    assert product.license_keys.filter(status=LicenseKey.Status.SOLD).count() == 1
