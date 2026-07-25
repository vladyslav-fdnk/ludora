from decimal import Decimal

from django.db import migrations
from django.db.models import Prefetch


def backfill_direct_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Payment = apps.get_model("orders", "Payment")

    orders = (
        Order.objects.filter(source="DIRECT")
        .select_related("product")
        .prefetch_related(
            "items",
            Prefetch(
                "payments",
                queryset=Payment.objects.filter(status="PAID").order_by(
                    "-paid_at", "-created_at", "-pk"
                ),
                to_attr="paid_payments",
            ),
        )
        .iterator(chunk_size=500)
    )
    for order in orders:
        items = list(order.items.all())

        # Financial fallback rules, in descending reliability:
        # 1. retain an existing authoritative order total;
        # 2. use the amount recorded as paid on the order;
        # 3. use a completed payment record;
        # 4. use an existing immutable OrderItem snapshot;
        # 5. only for an unpaid legacy order, snapshot the current catalogue price.
        # If the product and every historical amount are missing, leave the total
        # unresolved. Inventing a zero or title would conceal missing financial data.
        total = order.total_price
        if total is None:
            total = order.price_paid
        if total is None:
            total = order.paid_payments[0].amount if order.paid_payments else None
        if total is None and items:
            total = sum(
                (item.unit_price * item.quantity for item in items),
                start=Decimal("0.00"),
            )
        if (
            total is None
            and order.status != "PAID"
            and not order.paid_payments
            and order.product_id is not None
        ):
            total = order.product.price

        if order.total_price is None and total is not None:
            Order.objects.filter(pk=order.pk, total_price__isnull=True).update(
                total_price=total
            )

        product_title = order.product.title.strip() if order.product_id else ""
        if (
            not items
            and order.product_id is not None
            and product_title
            and total is not None
        ):
            OrderItem.objects.create(
                order_id=order.pk,
                product_id=order.product_id,
                product_title=product_title,
                quantity=1,
                unit_price=total,
            )


def preserve_normalized_data(apps, schema_editor):
    # The pre-normalization schema can store OrderItem rows and total_price, so
    # retaining the backfill is safer than deleting rows that may have been
    # created by application traffic after the forward migration.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_order_source_order_total_price_alter_order_product_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_direct_orders, preserve_normalized_data),
    ]
