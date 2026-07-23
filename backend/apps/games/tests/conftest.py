import pytest
from django.contrib.auth import get_user_model

from apps.games.models import Platform, Product

User = get_user_model()


@pytest.fixture
def platform():
    return Platform.objects.create(
        name="Steam",
        slug="steam",
    )


@pytest.fixture
def product(platform):
    return Product.objects.create(
        title="Cyberpunk 2077",
        slug="cyberpunk-2077",
        product_type="GAME",
        platform=platform,
        price="59.99",
        is_active=True,
    )


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(
        username="admin",
        password="password123",
    )
