from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import BackendClient
from app.api.exceptions import AuthenticationRequired, BackendUnavailable, ResourceNotFound
from app.api.schemas import (
    LicenseAssignment,
    OrderDetail,
    OrderDetailItem,
    OrderPayment,
    OrderSummary,
)
from app.auth import AuthTokens, InMemoryTokenStorage
from app.handlers.orders import order_detail, orders_command
from app.keyboards.callbacks import OrderDetailCallback
from app.keyboards.orders import orders_keyboard
from app.localization import LanguagePreferences, Translator
from app.presentation import format_order_detail, format_order_history

NOW = datetime(2026, 7, 25, 10, 30, tzinfo=UTC)


def summary() -> OrderSummary:
    return OrderSummary(7, "PAID", NOW, 2, Decimal("29.99"))


def detail(with_key: bool = True) -> OrderDetail:
    assignments = (
        (LicenseAssignment(4, "<KEY&123>"),)
        if with_key
        else (LicenseAssignment(4, None),)
    )
    item = OrderDetailItem(
        1,
        "<Game>",
        2,
        Decimal("10.00"),
        Decimal("20.00"),
        assignments,
    )
    payment = OrderPayment(
        3, "PAID", "local", "tx-1", Decimal("20.00"), NOW, NOW
    )
    return OrderDetail(
        7, "LUD-7", "PAID", Decimal("20.00"), NOW, (item,), (payment,)
    )


def message():
    return SimpleNamespace(
        from_user=SimpleNamespace(id=123, language_code="en"),
        answer=AsyncMock(),
    )


def callback(user_id: int = 123):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, language_code="en"),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )


def list_payload():
    return {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 7,
                "status": "PAID",
                "created_at": "2026-07-25T10:30:00Z",
                "number_of_items": 2,
                "total_price": "29.99",
            }
        ],
    }


def detail_payload():
    return {
        "id": 7,
        "order_number": "LUD-7",
        "status": "PAID",
        "total_price": "20.00",
        "created_at": "2026-07-25T10:30:00Z",
        "items": [
            {
                "product": 1,
                "product_title": "Game",
                "quantity": 2,
                "unit_price": "10.00",
                "line_total": "20.00",
                "license_assignments": [{"id": 4, "license_key": "KEY-123"}],
            }
        ],
        "payments": [
            {
                "id": 3,
                "status": "PAID",
                "provider": "local",
                "transaction_id": "tx-1",
                "amount": "20.00",
                "created_at": "2026-07-25T10:30:00Z",
                "paid_at": "2026-07-25T10:31:00Z",
            }
        ],
    }


def test_history_presentation_uses_backend_values_and_empty_state():
    text = format_order_history((summary(),), "en", Translator())
    assert "Order:</b> #7" in text
    assert "PAID" in text
    assert "2026-07-25" in text
    assert "Items:</b> 2" in text
    assert "29.99" in text
    assert "do not have any orders" in format_order_history((), "en", Translator())


def test_detail_presentation_escapes_content_and_separates_license_keys():
    text = format_order_detail(detail(), "en", Translator())
    assert "&lt;Game&gt;" in text
    assert "2 × 10.00 — 20.00" in text
    assert "Payment information" in text
    assert "local" in text and "tx-1" in text
    assert "License keys" in text
    assert "<code>&lt;KEY&amp;123&gt;</code>" in text
    assert "License keys" not in format_order_detail(
        detail(with_key=False), "en", Translator()
    )


def test_order_keyboard_has_owned_detail_callback():
    markup = orders_keyboard((summary(),), 123, "en", Translator())
    button = markup.inline_keyboard[0][0]
    assert button.text == "Order #7 details"
    assert OrderDetailCallback.unpack(button.callback_data) == OrderDetailCallback(
        order_id=7, owner_id=123
    )


async def test_orders_command_and_detail_callback():
    event = message()
    auth = SimpleNamespace(
        get_my_orders=AsyncMock(return_value=(summary(),)),
        get_my_order=AsyncMock(return_value=detail()),
    )
    await orders_command(event, auth, Translator(), LanguagePreferences())
    auth.get_my_orders.assert_awaited_once_with(event.from_user)
    assert "My orders" in event.answer.await_args.args[0]

    detail_event = callback()
    await order_detail(
        detail_event,
        OrderDetailCallback(order_id=7, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    auth.get_my_order.assert_awaited_once_with(detail_event.from_user, 7)
    assert "Payment information" in detail_event.message.edit_text.await_args.args[0]


async def test_stale_and_deleted_order_callbacks_are_friendly():
    stale = callback(user_id=999)
    auth = SimpleNamespace(get_my_order=AsyncMock())
    await order_detail(
        stale,
        OrderDetailCallback(order_id=7, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    auth.get_my_order.assert_not_awaited()
    assert "invalid or outdated" in stale.message.edit_text.await_args.args[0]

    deleted = callback()
    auth.get_my_order.side_effect = ResourceNotFound()
    await order_detail(
        deleted,
        OrderDetailCallback(order_id=7, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    assert "no longer exists" in deleted.message.edit_text.await_args.args[0]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (BackendUnavailable(), "temporarily unavailable"),
        (AuthenticationRequired(), "session expired"),
    ],
)
async def test_order_history_failures_are_friendly(failure, expected):
    event = message()
    auth = SimpleNamespace(get_my_orders=AsyncMock(side_effect=failure))
    await orders_command(event, auth, Translator(), LanguagePreferences())
    assert expected in event.answer.await_args.args[0]


async def test_client_parses_order_list_and_detail_from_owned_endpoints():
    paths = []

    async def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/api/orders/my/":
            return httpx.Response(200, json=list_payload())
        return httpx.Response(200, json=detail_payload())

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("access", "refresh"))
    client = BackendClient(
        "http://backend",
        1,
        token_storage=storage,
        transport=httpx.MockTransport(handler),
    )
    try:
        orders = await client.get_my_orders(123)
        order = await client.get_my_order(123, 7)
    finally:
        await client.close()
    assert paths == ["/api/orders/my/", "/api/orders/my/7/"]
    assert orders[0].number_of_items == 2
    assert order.items[0].license_assignments[0].license_key == "KEY-123"
    assert order.payments[0].amount == Decimal("20.00")
