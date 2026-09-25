"""Populate the catalogue with demo platforms, products, and license keys."""

import secrets
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.games.models import Category, LicenseKey, Platform, Product

PLATFORMS = {
    "steam": "Steam",
    "gog": "GOG",
    "epic": "Epic Games Store",
    "playstation": "PlayStation Network",
    "xbox": "Xbox",
}

CATEGORIES = {
    "action": "Action",
    "rpg": "RPG",
    "strategy": "Strategy",
    "indie": "Indie",
    "adventure": "Adventure",
    "subscriptions": "Subscriptions",
    "gift-cards": "Gift cards",
}

# (slug, title, type, platform, price, categories, description)
PRODUCTS = [
    ("the-witcher-3-goty", "The Witcher 3: Wild Hunt GOTY", "GAME", "gog", "29.99",
     ["rpg", "adventure"], "Open-world RPG with both expansions included."),
    ("baldurs-gate-3", "Baldur's Gate 3", "GAME", "steam", "59.99",
     ["rpg", "strategy"], "Party-based RPG set in the Forgotten Realms."),
    ("hades-ii", "Hades II", "GAME", "steam", "29.99",
     ["action", "indie"], "Roguelike dungeon crawler from Supergiant Games."),
    ("stardew-valley", "Stardew Valley", "GAME", "steam", "14.99",
     ["indie", "adventure"], "Farming and life simulation game."),
    ("civilization-vi", "Sid Meier's Civilization VI", "GAME", "epic", "59.99",
     ["strategy"], "Turn-based 4X strategy game."),
    ("hollow-knight", "Hollow Knight", "GAME", "gog", "14.99",
     ["action", "indie", "adventure"], "Hand-drawn action adventure."),
    ("phantom-liberty", "Cyberpunk 2077: Phantom Liberty", "DLC", "gog", "29.99",
     ["rpg", "action"], "Spy-thriller expansion for Cyberpunk 2077."),
    ("game-pass-ultimate-1m", "Xbox Game Pass Ultimate — 1 month", "SUBSCRIPTION", "xbox",
     "19.99", ["subscriptions"], "One month of Game Pass Ultimate."),
    ("ps-plus-essential-3m", "PlayStation Plus Essential — 3 months", "SUBSCRIPTION",
     "playstation", "24.99", ["subscriptions"], "Three months of PlayStation Plus."),
    ("steam-gift-card-20", "Steam Gift Card — $20", "GIFT_CARD", "steam", "20.00",
     ["gift-cards"], "Steam Wallet top-up code."),
]


def generate_demo_key() -> str:
    """Return a readable, clearly fake key such as ``DEMO-7F3A-91C2-04BE``."""
    return "DEMO-" + "-".join(secrets.token_hex(2).upper() for _ in range(3))


class Command(BaseCommand):
    help = (
        "Create or update demo platforms, categories, and products, and top up "
        "each demo product to the requested number of available license keys. "
        "Safe to run repeatedly."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--keys-per-product",
            type=int,
            default=10,
            help="Minimum number of AVAILABLE keys per demo product (default: 10).",
        )

    @transaction.atomic
    def handle(self, *args, keys_per_product: int, **options) -> None:
        platforms = {
            slug: Platform.objects.update_or_create(slug=slug, defaults={"name": name})[0]
            for slug, name in PLATFORMS.items()
        }
        categories = {
            slug: Category.objects.update_or_create(slug=slug, defaults={"name": name})[0]
            for slug, name in CATEGORIES.items()
        }

        keys_created = 0
        for slug, title, product_type, platform, price, category_slugs, description in PRODUCTS:
            product, _ = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "product_type": product_type,
                    "platform": platforms[platform],
                    "price": Decimal(price),
                    "description": description,
                    "is_active": True,
                },
            )
            product.categories.set(categories[c] for c in category_slugs)

            available = product.license_keys.filter(status=LicenseKey.Status.AVAILABLE).count()
            missing = max(keys_per_product - available, 0)
            LicenseKey.objects.bulk_create(
                LicenseKey(product=product, value=generate_demo_key()) for _ in range(missing)
            )
            keys_created += missing

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo catalogue ready: {len(PLATFORMS)} platforms, {len(CATEGORIES)} "
                f"categories, {len(PRODUCTS)} products, {keys_created} new license keys."
            )
        )
