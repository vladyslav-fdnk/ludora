from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.localization import Translator

from .callbacks import CataloguePageCallback


def main_menu(language: str, translator: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translator.get("button.catalogue", language),
                    callback_data=CataloguePageCallback(page=1).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translator.get("button.cart", language),
                    callback_data="cart",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translator.get("button.profile", language),
                    callback_data="profile",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translator.get("button.orders", language),
                    callback_data="orders",
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
