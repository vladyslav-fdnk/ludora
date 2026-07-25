from django.db import migrations, models


def validate_product_prices(apps, schema_editor):
    Product = apps.get_model("games", "Product")
    if Product.objects.filter(price__lt=0).exists():
        raise RuntimeError("Cannot constrain products: a negative price exists.")


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(validate_product_prices, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("price__gte", 0)),
                name="product_price_nonnegative",
            ),
        ),
    ]
