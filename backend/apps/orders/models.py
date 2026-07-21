import uuid

from django.db import models

from apps.games.models import Product


class Order(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
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

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = (
                f"LUD-{uuid.uuid4().hex[:10].upper()}"
            )

        super().save(*args, **kwargs)

        
    def __str__(self):
        return f"Order #{self.order_number or self.id}"
    