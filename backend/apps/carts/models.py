from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.games.models import Product

MAX_CART_ITEM_QUANTITY = 99


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Cart #{self.pk} for {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(MAX_CART_ITEM_QUANTITY),
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "product"),
                name="unique_product_per_cart",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1, quantity__lte=MAX_CART_ITEM_QUANTITY),
                name="cart_item_quantity_between_1_and_99",
            ),
        ]

    @property
    def line_total(self) -> Decimal:
        return self.product.price * self.quantity

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity}"
