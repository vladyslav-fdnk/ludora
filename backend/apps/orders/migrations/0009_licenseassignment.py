import logging

import django.db.models.deletion
from django.db import migrations, models


logger = logging.getLogger(__name__)


def backfill_direct_order_license_assignments(apps, schema_editor):
    LicenseAssignment = apps.get_model("orders", "LicenseAssignment")
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")

    paid_direct_orders = (
        Order.objects.filter(
            source="DIRECT",
            status="PAID",
            license_key_id__isnull=False,
        )
        .order_by("pk")
        .values_list("pk", "license_key_id")
        .iterator(chunk_size=500)
    )

    assignments = []
    malformed_order_ids = []
    for order_id, license_key_id in paid_direct_orders:
        order_item_ids = list(
            OrderItem.objects.filter(order_id=order_id)
            .order_by("pk")
            .values_list("pk", flat=True)
            [:2]
        )
        if len(order_item_ids) != 1:
            malformed_order_ids.append(order_id)
            continue

        assignments.append(
            LicenseAssignment(
                order_item_id=order_item_ids[0],
                license_key_id=license_key_id,
            )
        )

    LicenseAssignment.objects.bulk_create(assignments, batch_size=500)
    if malformed_order_ids:
        logger.warning(
            "Skipped license-assignment backfill for malformed legacy direct "
            "orders without exactly one OrderItem: %s",
            ", ".join(str(order_id) for order_id in malformed_order_ids),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0002_product_price_nonnegative"),
        ("orders", "0008_order_financial_constraints"),
    ]

    operations = [
        migrations.CreateModel(
            name="LicenseAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "license_key",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="license_assignment",
                        to="games.licensekey",
                    ),
                ),
                (
                    "order_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="license_assignments",
                        to="orders.orderitem",
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            backfill_direct_order_license_assignments,
            migrations.RunPython.noop,
        ),
    ]
