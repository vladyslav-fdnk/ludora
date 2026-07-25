"""Validated domain structures for catalogue API responses."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .exceptions import InvalidResponse


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    title: str
    price: Decimal
    platform: str | None
    product_type: str | None
    slug: str | None = None
    description: str | None = None
    categories: tuple[str, ...] = ()
    is_active: bool | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "Product":
        if not isinstance(value, dict):
            raise InvalidResponse("Product must be an object")
        product_id = value.get("id")
        title = value.get("title")
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
            raise InvalidResponse("Product id is invalid")
        if not isinstance(title, str) or not title.strip():
            raise InvalidResponse("Product title is invalid")
        try:
            price = Decimal(str(value["price"]))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidResponse("Product price is invalid") from exc
        if not price.is_finite():
            raise InvalidResponse("Product price is invalid")

        platform = _optional_string(value, "platform")
        product_type = _optional_string(value, "product_type")
        slug = _optional_string(value, "slug")
        description = _optional_string(value, "description")
        raw_categories = value.get("categories", [])
        if raw_categories is None:
            raw_categories = []
        if not isinstance(raw_categories, list) or not all(
            isinstance(item, str) for item in raw_categories
        ):
            raise InvalidResponse("Product categories are invalid")
        is_active = value.get("is_active")
        if is_active is not None and not isinstance(is_active, bool):
            raise InvalidResponse("Product active flag is invalid")
        return cls(
            id=product_id,
            title=title,
            price=price,
            platform=platform,
            product_type=product_type,
            slug=slug,
            description=description,
            categories=tuple(raw_categories),
            is_active=is_active,
        )


@dataclass(frozen=True, slots=True)
class ProductPage:
    products: tuple[Product, ...]
    count: int
    page: int
    has_next: bool
    has_previous: bool

    @classmethod
    def from_mapping(cls, value: Any, page: int) -> "ProductPage":
        if not isinstance(value, dict):
            raise InvalidResponse("Product page must be an object")
        count = value.get("count")
        results = value.get("results")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise InvalidResponse("Product count is invalid")
        if not isinstance(results, list):
            raise InvalidResponse("Product results are invalid")
        return cls(
            products=tuple(Product.from_mapping(item) for item in results),
            count=count,
            page=page,
            has_next=value.get("next") is not None,
            has_previous=value.get("previous") is not None,
        )


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise InvalidResponse(f"Product {key} is invalid")
    return item
