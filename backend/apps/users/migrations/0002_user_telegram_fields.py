from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="telegram_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Stable Telegram account identifier for bot-managed users.",
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="telegram_language_code",
            field=models.CharField(blank=True, max_length=35),
        ),
        migrations.AddField(
            model_name="user",
            name="telegram_username",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
