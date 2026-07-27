from typing import Annotated, Literal

from aiogram.filters.callback_data import CallbackData
from pydantic import Field

PositiveInt = Annotated[int, Field(gt=0)]


class CataloguePageCallback(CallbackData, prefix="cat"):
    page: PositiveInt


class ProductCallback(CallbackData, prefix="prd"):
    product_id: PositiveInt
    page: PositiveInt


class LanguageCallback(CallbackData, prefix="lng"):
    language: Literal["en", "ru"]


class AddCartCallback(CallbackData, prefix="add"):
    product_id: PositiveInt


class CartItemCallback(CallbackData, prefix="cit"):
    action: Literal["inc", "dec", "remove"]
    item_id: PositiveInt
    owner_id: PositiveInt


class CartActionCallback(CallbackData, prefix="crt"):
    action: Literal["clear", "clear_yes", "checkout", "checkout_yes"]
    owner_id: PositiveInt


class OrderDetailCallback(CallbackData, prefix="ord"):
    order_id: PositiveInt
    owner_id: PositiveInt


class PaymentStatusCallback(CallbackData, prefix="pay"):
    order_id: PositiveInt
    owner_id: PositiveInt
