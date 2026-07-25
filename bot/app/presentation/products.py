"""Telegram-safe product presentation."""

from decimal import Decimal
from html import escape

from app.api.schemas import Product, ProductPage
from app.localization import Translator

MAX_DESCRIPTION_LENGTH = 2800
MAX_CATEGORIES_LENGTH = 600


def format_catalogue(page: ProductPage, language: str, translator: Translator) -> str:
    lines = [translator.get("catalogue.title", language), ""]
    for product in page.products:
        lines.extend(
            [
                f"<b>{escape(_shorten(product.title, 180))}</b>",
                _field("field.platform", product.platform or "—", language, translator),
                _field(
                    "field.type",
                    _product_type(product.product_type, language, translator),
                    language,
                    translator,
                ),
                _field("field.price", _price(product.price), language, translator),
                "",
            ]
        )
    lines.append(translator.get("catalogue.page", language, page=page.page))
    return "\n".join(lines)


def format_product(product: Product, language: str, translator: Translator) -> str:
    description = product.description.strip() if product.description else ""
    if not description:
        description = translator.get("description.missing", language)
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        marker = translator.get("description.truncated", language)
        description = f"{description[: MAX_DESCRIPTION_LENGTH - len(marker)].rstrip()}{marker}"
    categories = (
        ", ".join(product.categories)
        if product.categories
        else translator.get("categories.missing", language)
    )
    if len(categories) > MAX_CATEGORIES_LENGTH:
        marker = translator.get("description.truncated", language)
        categories = f"{categories[: MAX_CATEGORIES_LENGTH - len(marker)].rstrip()}{marker}"
    return "\n".join(
        [
            f"<b>{escape(product.title)}</b>",
            "",
            _field("field.platform", product.platform or "—", language, translator),
            _field(
                "field.type",
                _product_type(product.product_type, language, translator),
                language,
                translator,
            ),
            _field("field.price", _price(product.price), language, translator),
            _field("field.categories", categories, language, translator),
            "",
            f"<b>{translator.get('field.description', language)}:</b>",
            escape(description),
        ]
    )


def _field(key: str, value: str, language: str, translator: Translator) -> str:
    return f"<b>{translator.get(key, language)}:</b> {escape(value)}"


def _product_type(value: str | None, language: str, translator: Translator) -> str:
    if not value:
        return "—"
    key = f"type.{value}"
    translated = translator.get(key, language)
    return value if translated == key else translated


def _price(value: Decimal) -> str:
    return format(value, ".2f")


def _shorten(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else f"{value[: maximum - 1].rstrip()}…"
