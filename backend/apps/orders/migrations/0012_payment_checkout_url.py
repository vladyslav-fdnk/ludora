from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0011_order_reservation_payment_attempt_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="checkout_url",
            field=models.URLField(
                blank=True,
                max_length=2048,
                null=True,
            ),
        ),
    ]
