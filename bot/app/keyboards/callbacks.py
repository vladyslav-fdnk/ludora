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
