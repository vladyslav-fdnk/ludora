from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.api.schemas import OrderSummary
from app.localization import Translator

from .callbacks import OrderDetailCallback


def orders_keyboard(
    orders: tuple[OrderSummary, ...],
    owner_id: int,
    language: str,
    translator: Translator,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translator.get(
                        "button.order_details", language, order_id=order.id
                    ),
                    callback_data=OrderDetailCallback(
                        order_id=order.id, owner_id=owner_id
                    ).pack(),
                )
            ]
            for order in orders
        ]
    )
