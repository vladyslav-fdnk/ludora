from django.db import migrations, models


def validate_existing_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Payment = apps.get_model("orders", "Payment")

    if Order.objects.filter(source="CART", product__isnull=False).exists():
        raise RuntimeError(
            "Cannot constrain orders: a CART order has a legacy product reference."
        )
    if Order.objects.filter(total_price__lt=0).exists():
        raise RuntimeError("Cannot constrain orders: a negative total_price exists.")
    if Order.objects.filter(price_paid__lt=0).exists():
        raise RuntimeError("Cannot constrain orders: a negative price_paid exists.")
    if Payment.objects.filter(amount__lt=0).exists():
        raise RuntimeError("Cannot constrain payments: a negative amount exists.")


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_backfill_direct_order_items"),
    ]

    operations = [
        migrations.RunPython(validate_existing_orders, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source", "DIRECT"),
                    ("product__isnull", True),
                    _connector="OR",
                ),
                name="cart_order_has_no_legacy_product",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("total_price__gte", 0),
                    ("total_price__isnull", True),
                    _connector="OR",
                ),
                name="order_total_price_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("price_paid__gte", 0),
                    ("price_paid__isnull", True),
                    _connector="OR",
                ),
                name="order_price_paid_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gte", 0)),
                name="payment_amount_nonnegative",
            ),
        ),
    ]
