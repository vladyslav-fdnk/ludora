from django.db import models


class Platform(models.Model):
    """A digital store platform a product is sold on (Steam, Epic, GOG, ...)."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    logo = models.ImageField(upload_to="platforms/", blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    """A product category (RPG, Action, Indie, ...)."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """A product that customers can buy."""

    class ProductType(models.TextChoices):
        GAME = "GAME", "Game"
        DLC = "DLC", "DLC"
        SUBSCRIPTION = "SUBSCRIPTION", "Subscription"
        GIFT_CARD = "GIFT_CARD", "Gift card"
        SOFTWARE = "SOFTWARE", "Software"

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
    )
    platform = models.ForeignKey(
        Platform,
        on_delete=models.PROTECT,
        related_name="products",
    )
    categories = models.ManyToManyField(
        Category,
        related_name="products",
        blank=True,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class LicenseKey(models.Model):
    """A digital license/key delivered to the customer after purchase."""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        RESERVED = "RESERVED", "Reserved"
        SOLD = "SOLD", "Sold"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="license_keys",
    )
    value = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.product.title} ({self.status})"
