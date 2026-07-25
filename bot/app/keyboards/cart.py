from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.api.schemas import Cart
from app.localization import Translator

from .callbacks import CartActionCallback, CartItemCallback


def cart_keyboard(
    cart: Cart, owner_id: int, language: str, translator: Translator
) -> InlineKeyboardMarkup:
    rows = []
    for item in cart.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text="−",
                    callback_data=CartItemCallback(
                        action="dec", item_id=item.id, owner_id=owner_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=f"{item.quantity} · {item.product.title[:24]}",
                    callback_data=CartItemCallback(
                        action="inc", item_id=item.id, owner_id=owner_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="✕",
                    callback_data=CartItemCallback(
                        action="remove", item_id=item.id, owner_id=owner_id
                    ).pack(),
                ),
            ]
        )
    if cart.items:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text=translator.get("button.checkout", language),
                        callback_data=CartActionCallback(
                            action="checkout", owner_id=owner_id
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=translator.get("button.clear_cart", language),
                        callback_data=CartActionCallback(
                            action="clear", owner_id=owner_id
                        ).pack(),
                    )
                ],
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard(
    action: str, owner_id: int, language: str, translator: Translator
) -> InlineKeyboardMarkup:
    confirmed = "clear_yes" if action == "clear" else "checkout_yes"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translator.get("button.confirm", language),
                    callback_data=CartActionCallback(
                        action=confirmed, owner_id=owner_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=translator.get("button.cancel", language),
                    callback_data="cart",
                ),
            ]
        ]
    )
