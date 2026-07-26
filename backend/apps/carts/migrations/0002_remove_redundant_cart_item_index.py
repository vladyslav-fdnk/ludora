from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("carts", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="cartitem",
            name="cart_item_lookup_idx",
        ),
    ]
