import uuid

from django.conf import settings
from django.db import models

from apps.games.models import Product


class Order(models.Model):
    class Source(models.TextChoices):
        DIRECT = "DIRECT", "Direct"
        CART = "CART", "Cart"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    order_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )
    email = models.EmailField()

    price_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.DIRECT,
    )

    license_key = models.OneToOneField(
        "games.LicenseKey",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    reservation_payment_attempt = models.ForeignKey(
        "Payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="authorized_reservations",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source="DIRECT")
                | models.Q(product__isnull=True),
                name="cart_order_has_no_legacy_product",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0)
                | models.Q(total_price__isnull=True),
                name="order_total_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(price_paid__gte=0)
                | models.Q(price_paid__isnull=True),
                name="order_price_paid_nonnegative",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"LUD-{uuid.uuid4().hex[:10].upper()}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.order_number or self.id}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    product_title = models.CharField(max_length=200)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "product"),
                name="unique_product_per_order",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="order_item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="order_item_unit_price_nonnegative",
            ),
        ]

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_title} × {self.quantity}"


class LicenseAssignment(models.Model):
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="license_assignments",
    )
    license_key = models.OneToOneField(
        "games.LicenseKey",
        on_delete=models.PROTECT,
        related_name="license_assignment",
    )

    def __str__(self):
        return f"License assignment #{self.pk}"


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    provider = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="payment_amount_nonnegative",
            ),
            models.UniqueConstraint(
                fields=("order",),
                condition=models.Q(
                    status__in=("CREATED", "PENDING"),
                ),
                name="unique_active_payment_per_order",
            ),
        ]

    def __str__(self):
        return f"Payment #{self.id} - {self.status}"
