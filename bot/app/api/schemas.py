"""Validated domain structures for backend API responses."""

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class CartItem:
    id: int
    product: Product
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    @classmethod
    def from_mapping(cls, value: Any) -> "CartItem":
        if not isinstance(value, dict):
            raise InvalidResponse("Cart item must be an object")
        item_id = _positive_int(value, "id")
        quantity = _positive_int(value, "quantity")
        return cls(
            id=item_id,
            product=Product.from_mapping(value.get("product")),
            quantity=quantity,
            unit_price=_decimal(value, "unit_price"),
            line_total=_decimal(value, "line_total"),
        )


@dataclass(frozen=True, slots=True)
class Cart:
    id: int
    items: tuple[CartItem, ...]
    total_quantity: int
    total_price: Decimal

    @classmethod
    def from_mapping(cls, value: Any) -> "Cart":
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise InvalidResponse("Cart must be an object with items")
        cart_id = _positive_int(value, "id")
        total_quantity = value.get("total_quantity")
        if (
            isinstance(total_quantity, bool)
            or not isinstance(total_quantity, int)
            or total_quantity < 0
        ):
            raise InvalidResponse("Cart total quantity is invalid")
        return cls(
            id=cart_id,
            items=tuple(CartItem.from_mapping(item) for item in value["items"]),
            total_quantity=total_quantity,
            total_price=_decimal(value, "total_price"),
        )


@dataclass(frozen=True, slots=True)
class OrderItem:
    product: int
    product_title: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    @classmethod
    def from_mapping(cls, value: Any) -> "OrderItem":
        if not isinstance(value, dict):
            raise InvalidResponse("Order item must be an object")
        title = value.get("product_title")
        if not isinstance(title, str) or not title:
            raise InvalidResponse("Order item title is invalid")
        return cls(
            product=_positive_int(value, "product"),
            product_title=title,
            quantity=_positive_int(value, "quantity"),
            unit_price=_decimal(value, "unit_price"),
            line_total=_decimal(value, "line_total"),
        )


@dataclass(frozen=True, slots=True)
class CheckoutOrder:
    id: int
    order_number: str
    status: str
    total_price: Decimal
    items: tuple[OrderItem, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "CheckoutOrder":
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise InvalidResponse("Checkout order is invalid")
        order_number = value.get("order_number")
        status = value.get("status")
        if not isinstance(order_number, str) or not order_number:
            raise InvalidResponse("Order number is invalid")
        if not isinstance(status, str) or not status:
            raise InvalidResponse("Order status is invalid")
        return cls(
            id=_positive_int(value, "id"),
            order_number=order_number,
            status=status,
            total_price=_decimal(value, "total_price"),
            items=tuple(OrderItem.from_mapping(item) for item in value["items"]),
        )


@dataclass(frozen=True, slots=True)
class Payment:
    id: int
    order: int
    status: str
    amount: Decimal
    payment_url: str

    @classmethod
    def from_mapping(cls, value: Any) -> "Payment":
        if not isinstance(value, dict):
            raise InvalidResponse("Payment must be an object")
        payment_url = value.get("payment_url")
        if not isinstance(payment_url, str) or not payment_url:
            raise InvalidResponse("Payment URL is invalid")
        return cls(
            id=_positive_int(value, "id"),
            order=_positive_int(value, "order"),
            status=_required_string(value, "status"),
            amount=_decimal(value, "amount"),
            payment_url=payment_url,
        )


@dataclass(frozen=True, slots=True)
class OrderSummary:
    id: int
    status: str
    created_at: datetime
    number_of_items: int
    total_price: Decimal

    @classmethod
    def from_mapping(cls, value: Any) -> "OrderSummary":
        if not isinstance(value, dict):
            raise InvalidResponse("Order summary must be an object")
        status = _required_string(value, "status")
        number_of_items = value.get("number_of_items")
        if (
            isinstance(number_of_items, bool)
            or not isinstance(number_of_items, int)
            or number_of_items < 0
        ):
            raise InvalidResponse("Order item count is invalid")
        return cls(
            id=_positive_int(value, "id"),
            status=status,
            created_at=_datetime(value, "created_at"),
            number_of_items=number_of_items,
            total_price=_decimal(value, "total_price"),
        )


@dataclass(frozen=True, slots=True)
class LicenseAssignment:
    id: int
    license_key: str | None

    @classmethod
    def from_mapping(cls, value: Any) -> "LicenseAssignment":
        if not isinstance(value, dict):
            raise InvalidResponse("License assignment must be an object")
        return cls(
            id=_positive_int(value, "id"),
            license_key=_optional_string(value, "license_key"),
        )


@dataclass(frozen=True, slots=True)
class OrderDetailItem:
    product: int
    product_title: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    license_assignments: tuple[LicenseAssignment, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "OrderDetailItem":
        if not isinstance(value, dict) or not isinstance(
            value.get("license_assignments"), list
        ):
            raise InvalidResponse("Order detail item is invalid")
        return cls(
            product=_positive_int(value, "product"),
            product_title=_required_string(value, "product_title"),
            quantity=_positive_int(value, "quantity"),
            unit_price=_decimal(value, "unit_price"),
            line_total=_decimal(value, "line_total"),
            license_assignments=tuple(
                LicenseAssignment.from_mapping(item)
                for item in value["license_assignments"]
            ),
        )


@dataclass(frozen=True, slots=True)
class OrderPayment:
    id: int
    status: str
    provider: str
    transaction_id: str
    amount: Decimal
    created_at: datetime
    paid_at: datetime | None

    @classmethod
    def from_mapping(cls, value: Any) -> "OrderPayment":
        if not isinstance(value, dict):
            raise InvalidResponse("Order payment must be an object")
        return cls(
            id=_positive_int(value, "id"),
            status=_required_string(value, "status"),
            provider=_string(value, "provider"),
            transaction_id=_string(value, "transaction_id"),
            amount=_decimal(value, "amount"),
            created_at=_datetime(value, "created_at"),
            paid_at=_optional_datetime(value, "paid_at"),
        )


@dataclass(frozen=True, slots=True)
class OrderDetail:
    id: int
    order_number: str
    status: str
    total_price: Decimal
    created_at: datetime
    items: tuple[OrderDetailItem, ...]
    payments: tuple[OrderPayment, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "OrderDetail":
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("items"), list)
            or not isinstance(value.get("payments"), list)
        ):
            raise InvalidResponse("Order detail is invalid")
        return cls(
            id=_positive_int(value, "id"),
            order_number=_required_string(value, "order_number"),
            status=_required_string(value, "status"),
            total_price=_decimal(value, "total_price"),
            created_at=_datetime(value, "created_at"),
            items=tuple(OrderDetailItem.from_mapping(item) for item in value["items"]),
            payments=tuple(
                OrderPayment.from_mapping(item) for item in value["payments"]
            ),
        )


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise InvalidResponse(f"Product {key} is invalid")
    return item


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise InvalidResponse(f"{key} is invalid")
    return item


def _string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise InvalidResponse(f"{key} is invalid")
    return item


def _datetime(value: dict[str, Any], key: str) -> datetime:
    item = value.get(key)
    if not isinstance(item, str):
        raise InvalidResponse(f"{key} is invalid")
    try:
        result = datetime.fromisoformat(item.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidResponse(f"{key} is invalid") from exc
    if result.tzinfo is None:
        raise InvalidResponse(f"{key} is invalid")
    return result


def _optional_datetime(value: dict[str, Any], key: str) -> datetime | None:
    if value.get(key) is None:
        return None
    return _datetime(value, key)


def _positive_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
        raise InvalidResponse(f"{key} is invalid")
    return item


def _decimal(value: dict[str, Any], key: str) -> Decimal:
    try:
        result = Decimal(str(value[key]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidResponse(f"{key} is invalid") from exc
    if not result.is_finite():
        raise InvalidResponse(f"{key} is invalid")
    return result
