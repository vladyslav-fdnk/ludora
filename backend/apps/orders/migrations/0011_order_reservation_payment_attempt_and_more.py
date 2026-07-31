import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0010_alter_payment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="reservation_payment_attempt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="authorized_reservations",
                to="orders.payment",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=("CREATED", "PENDING")),
                fields=("order",),
                name="unique_active_payment_per_order",
            ),
        ),
    ]
