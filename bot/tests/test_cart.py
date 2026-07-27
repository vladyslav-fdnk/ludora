from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import BackendClient
from app.api.exceptions import BackendUnavailable, InvalidResponse, ValidationFailed
from app.api.schemas import (
    Cart,
    CartItem,
    CheckoutOrder,
    LicenseAssignment,
    OrderDetail,
    OrderDetailItem,
    OrderItem,
    OrderPayment,
    Payment,
    Product,
)
from app.auth import AuthTokens, InMemoryTokenStorage
from app.handlers.cart import (
    add_to_cart,
    cart_action,
    cart_command,
    change_cart_item,
    check_payment_status,
)
from app.keyboards.callbacks import (
    AddCartCallback,
    CartActionCallback,
    CartItemCallback,
    PaymentStatusCallback,
)
from app.localization import LanguagePreferences, Translator
from app.presentation import format_cart, format_order


def product(title="<Game>"):
    return Product(1, title, Decimal("12.50"), "Steam", "GAME")


def cart(quantity=2, title="<Game>"):
    item = CartItem(7, product(title), quantity, Decimal("12.50"), Decimal("25.00"))
    return Cart(3, (item,), quantity, Decimal("25.00"))


def order():
    item = OrderItem(1, "<Game>", 2, Decimal("12.50"), Decimal("25.00"))
    return CheckoutOrder(9, "LUD-<123>", "CREATED", Decimal("25.00"), (item,))


def payment():
    return Payment(4, 9, "PENDING", Decimal("25.00"), "https://pay.test/4")


def detail(status="CREATED", payment_status="PENDING", with_keys=False):
    assignments = (
        (LicenseAssignment(3, "KEY-<123>"),) if with_keys else ()
    )
    item = OrderDetailItem(
        1, "<Game>", 2, Decimal("12.50"), Decimal("25.00"), assignments
    )
    backend_payment = OrderPayment(
        4,
        payment_status,
        "provider",
        "tx-4",
        Decimal("25.00"),
        datetime(2026, 7, 27, tzinfo=UTC),
        datetime(2026, 7, 27, tzinfo=UTC) if status == "PAID" else None,
    )
    return OrderDetail(
        9,
        "LUD-123",
        status,
        Decimal("25.00"),
        datetime(2026, 7, 27, tzinfo=UTC),
        (item,),
        (backend_payment,),
    )


def message(language="en"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=123, language_code=language),
        answer=AsyncMock(),
    )


def callback(language="en"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=123, language_code=language),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Your cart"), ("ru", "Ваша корзина")],
)
def test_cart_presentation_localizes_and_escapes_html(language, expected):
    text = format_cart(cart(title="<b>Bad</b>"), language, Translator())
    assert expected in text
    assert "&lt;b&gt;Bad&lt;/b&gt;" in text
    assert "<b>Bad</b>" not in text


def test_empty_cart_and_order_presentation_are_safe():
    assert format_cart(Cart(1, (), 0, Decimal("0")), "en", Translator()) == (
        "Your cart is empty."
    )
    text = format_order(order(), "en", Translator())
    assert "LUD-&lt;123&gt;" in text
    assert "&lt;Game&gt;" in text


async def test_direct_cart_command_authenticates_without_start():
    event = message()
    auth = SimpleNamespace(get_cart=AsyncMock(return_value=cart()))
    await cart_command(event, auth, Translator(), LanguagePreferences())
    auth.get_cart.assert_awaited_once_with(event.from_user)
    assert "Your cart" in event.answer.await_args.args[0]


async def test_add_to_cart_callback():
    event = callback()
    auth = SimpleNamespace(add_cart_item=AsyncMock())
    await add_to_cart(
        event,
        AddCartCallback(product_id=1),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    auth.add_cart_item.assert_awaited_once_with(event.from_user, 1, 1)
    assert "Added" in event.message.edit_text.await_args.args[0]
    markup = event.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = markup.inline_keyboard[0]
    assert [button.text for button in buttons] == ["View cart", "Continue shopping"]
    assert [button.callback_data for button in buttons] == ["cart", "cat:1"]


@pytest.mark.parametrize(
    ("action", "quantity", "method", "expected"),
    [
        ("inc", 2, "update_cart_item", 3),
        ("dec", 2, "update_cart_item", 1),
        ("dec", 1, "remove_cart_item", None),
        ("remove", 2, "remove_cart_item", None),
    ],
)
async def test_quantity_and_remove_callbacks(action, quantity, method, expected):
    event = callback()
    auth = SimpleNamespace(
        get_cart=AsyncMock(side_effect=[cart(quantity), Cart(3, (), 0, Decimal("0"))]),
        update_cart_item=AsyncMock(),
        remove_cart_item=AsyncMock(),
    )
    await change_cart_item(
        event,
        CartItemCallback(action=action, item_id=7, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    if expected is None:
        auth.remove_cart_item.assert_awaited_once_with(event.from_user, 7)
    else:
        auth.update_cart_item.assert_awaited_once_with(event.from_user, 7, expected)


async def test_callback_owner_is_validated():
    event = callback()
    auth = SimpleNamespace(get_cart=AsyncMock())
    await change_cart_item(
        event,
        CartItemCallback(action="inc", item_id=7, owner_id=999),
        auth,
        Translator(),
        LanguagePreferences(),
    )
    auth.get_cart.assert_not_awaited()
    assert "invalid or outdated" in event.message.edit_text.await_args.args[0]


async def test_clear_and_checkout_confirmations_and_success():
    translator = Translator()
    preferences = LanguagePreferences()
    confirm = callback()
    auth = SimpleNamespace(
        clear_cart=AsyncMock(),
        checkout_cart=AsyncMock(return_value=order()),
        create_payment=AsyncMock(return_value=payment()),
    )
    await cart_action(
        confirm,
        CartActionCallback(action="clear", owner_id=123),
        auth,
        translator,
        preferences,
    )
    assert "Clear every" in confirm.message.edit_text.await_args.args[0]
    await cart_action(
        confirm,
        CartActionCallback(action="clear_yes", owner_id=123),
        auth,
        translator,
        preferences,
    )
    auth.clear_cart.assert_awaited_once()
    await cart_action(
        confirm,
        CartActionCallback(action="checkout", owner_id=123),
        auth,
        translator,
        preferences,
    )
    assert "Create an order" in confirm.message.edit_text.await_args.args[0]
    await cart_action(
        confirm,
        CartActionCallback(action="checkout_yes", owner_id=123),
        auth,
        translator,
        preferences,
    )
    auth.create_payment.assert_awaited_once_with(confirm.from_user, 9)
    assert "Payment created" in confirm.message.edit_text.await_args.args[0]
    markup = confirm.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://pay.test/4"
    assert markup.inline_keyboard[1][0].text == "Check payment status"


async def test_payment_status_refreshes_from_backend():
    event = callback()
    auth = SimpleNamespace(get_my_order=AsyncMock(return_value=detail()))

    await check_payment_status(
        event,
        PaymentStatusCallback(order_id=9, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )

    auth.get_my_order.assert_awaited_once_with(event.from_user, 9)
    text = event.message.edit_text.await_args.args[0]
    assert "PENDING" in text
    assert "not been completed" in text


async def test_completed_payment_immediately_shows_backend_license_keys():
    event = callback()
    auth = SimpleNamespace(
        get_my_order=AsyncMock(
            return_value=detail(
                status="PAID", payment_status="PAID", with_keys=True
            )
        )
    )

    await check_payment_status(
        event,
        PaymentStatusCallback(order_id=9, owner_id=123),
        auth,
        Translator(),
        LanguagePreferences(),
    )

    text = event.message.edit_text.await_args.args[0]
    assert "Payment completed successfully" in text
    assert "License keys" in text
    assert "<code>KEY-&lt;123&gt;</code>" in text


async def test_payment_status_callback_validates_owner():
    event = callback()
    auth = SimpleNamespace(get_my_order=AsyncMock())

    await check_payment_status(
        event,
        PaymentStatusCallback(order_id=9, owner_id=999),
        auth,
        Translator(),
        LanguagePreferences(),
    )

    auth.get_my_order.assert_not_awaited()
    assert "invalid or outdated" in event.message.edit_text.await_args.args[0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValidationFailed(), "not available"),
        (BackendUnavailable(), "temporarily unavailable"),
        (InvalidResponse(), "invalid response"),
    ],
)
async def test_cart_failures_are_friendly(error, expected):
    event = message()
    auth = SimpleNamespace(get_cart=AsyncMock(side_effect=error))
    await cart_command(event, auth, Translator(), LanguagePreferences())
    assert expected in event.answer.await_args.args[0]


async def test_typed_client_cart_and_refresh_retry():
    calls = []

    async def handler(request):
        calls.append(request)
        if request.url.path == "/api/auth/refresh/":
            return httpx.Response(200, json={"access": "new-access"})
        if len([call for call in calls if call.url.path == "/api/cart/"]) == 1:
            return httpx.Response(401)
        return httpx.Response(
            200,
            json={
                "id": 3,
                "items": [],
                "total_quantity": 0,
                "total_price": "0.00",
            },
        )

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("expired", "refresh"))
    client = BackendClient(
        "http://backend",
        1,
        token_storage=storage,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.get_cart(123)
    finally:
        await client.close()
    assert result.items == ()
    assert calls[-1].headers["Authorization"] == "Bearer new-access"


async def test_typed_client_rejects_malformed_cart_and_maps_validation():
    responses = iter(
        [
            httpx.Response(200, json={"id": 1, "items": "bad"}),
            httpx.Response(400, json={"quantity": ["invalid"]}),
        ]
    )
    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("access", "refresh"))
    client = BackendClient(
        "http://backend",
        1,
        token_storage=storage,
        transport=httpx.MockTransport(lambda request: next(responses)),
    )
    try:
        with pytest.raises(InvalidResponse):
            await client.get_cart(123)
        with pytest.raises(ValidationFailed):
            await client.add_cart_item(123, 1)
    finally:
        await client.close()


async def test_typed_client_creates_payment():
    async def handler(request):
        assert request.url.path == "/api/orders/payments/"
        assert request.headers["Authorization"] == "Bearer access"
        assert request.method == "POST"
        assert request.content == b'{"order":9}'
        return httpx.Response(
            201,
            json={
                "id": 4,
                "order": 9,
                "status": "PENDING",
                "amount": "25.00",
                "payment_url": "https://pay.test/4",
            },
        )

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("access", "refresh"))
    client = BackendClient(
        "http://backend",
        1,
        token_storage=storage,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.create_payment(123, 9)
    finally:
        await client.close()

    assert result == payment()
