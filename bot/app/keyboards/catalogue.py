from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.api.schemas import ProductPage
from app.localization import Translator

from .callbacks import (
    AddCartCallback,
    CataloguePageCallback,
    LanguageCallback,
    ProductCallback,
)


def catalogue_keyboard(
    product_page: ProductPage,
    language: str,
    translator: Translator,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{translator.get('button.details', language)} · {product.title[:32]}",
                callback_data=ProductCallback(
                    product_id=product.id,
                    page=product_page.page,
                ).pack(),
            )
        ]
        for product in product_page.products
    ]
    navigation: list[InlineKeyboardButton] = []
    if product_page.has_previous and product_page.page > 1:
        navigation.append(
            InlineKeyboardButton(
                text=translator.get("button.previous", language),
                callback_data=CataloguePageCallback(page=product_page.page - 1).pack(),
            )
        )
    if product_page.has_next:
        navigation.append(
            InlineKeyboardButton(
                text=translator.get("button.next", language),
                callback_data=CataloguePageCallback(page=product_page.page + 1).pack(),
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text=translator.get("button.language", language),
                callback_data="choose_language",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_keyboard(
    page: int,
    language: str,
    translator: Translator,
    product_id: int | None = None,
) -> InlineKeyboardMarkup:
    safe_page = max(1, page)
    rows = []
    if product_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translator.get("button.add_cart", language),
                    callback_data=AddCartCallback(product_id=product_id).pack(),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=translator.get("button.back", language),
                    callback_data=CataloguePageCallback(page=safe_page).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translator.get("button.language", language),
                    callback_data="choose_language",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English",
                    callback_data=LanguageCallback(language="en").pack(),
                ),
                InlineKeyboardButton(
                    text="Русский",
                    callback_data=LanguageCallback(language="ru").pack(),
                ),
            ]
        ]
    )
