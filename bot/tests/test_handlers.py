from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.exceptions import BackendTimeout, BackendUnavailable, ProductNotFound
from app.api.schemas import Product, ProductPage
from app.handlers.catalogue import catalogue_command, catalogue_page, product_detail
from app.handlers.start import select_language, start_command
from app.keyboards.callbacks import CataloguePageCallback, LanguageCallback, ProductCallback
from app.localization import LanguagePreferences, Translator


def user(language="en"):
    return SimpleNamespace(
        id=123,
        language_code=language,
        username="tester",
        first_name="Test",
        last_name="User",
    )


def message(language="en"):
    return SimpleNamespace(from_user=user(language), answer=AsyncMock())


def callback(language="en"):
    return SimpleNamespace(
        from_user=user(language),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )


def products():
    item = Product(
        7,
        "<b>Portal</b>",
        Decimal("19.99"),
        "Steam",
        "GAME",
        description="<a href='bad'>Puzzle</a>",
    )
    return ProductPage((item,), 1, 1, False, False)


async def test_start_detects_language_and_has_menu_actions():
    event = message("ru-RU")
    auth = SimpleNamespace(synchronize=AsyncMock())
    await start_command(event, Translator(), LanguagePreferences(), auth)
    auth.synchronize.assert_awaited_once_with(event.from_user)
    text = event.answer.await_args.args[0]
    keyboard = event.answer.await_args.kwargs["reply_markup"]
    assert "Добро пожаловать" in text
    callback_values = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]
    assert "cat:1" in callback_values
    assert "choose_language" in callback_values


async def test_start_falls_back_to_english():
    event = message("pl")
    await start_command(
        event,
        Translator(),
        LanguagePreferences(),
        SimpleNamespace(synchronize=AsyncMock()),
    )
    assert "Welcome" in event.answer.await_args.args[0]


@pytest.mark.parametrize(
    ("language", "expected"),
    [("ru", "Добро пожаловать"), ("en", "Welcome")],
)
async def test_language_selection_refreshes_and_answers(language, expected):
    event = callback()
    await select_language(
        event,
        LanguageCallback(language=language),
        Translator(),
        LanguagePreferences(),
    )
    event.answer.assert_awaited_once()
    assert expected in event.message.edit_text.await_args.args[0]


async def test_catalogue_success_is_localized_and_escaped():
    event = message("ru")
    api = SimpleNamespace(get_products=AsyncMock(return_value=products()))
    await catalogue_command(event, api, Translator(), LanguagePreferences())
    text = event.answer.await_args.args[0]
    assert "Каталог товаров" in text
    assert "&lt;b&gt;Portal&lt;/b&gt;" in text


async def test_empty_catalogue_is_friendly():
    event = message()
    empty = ProductPage((), 0, 1, False, False)
    api = SimpleNamespace(get_products=AsyncMock(return_value=empty))
    await catalogue_command(event, api, Translator(), LanguagePreferences())
    assert "currently empty" in event.answer.await_args.args[0]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (BackendUnavailable(), "temporarily unavailable"),
        (BackendTimeout(), "timed out"),
    ],
)
async def test_catalogue_api_errors_are_friendly(failure, expected):
    event = message()
    api = SimpleNamespace(get_products=AsyncMock(side_effect=failure))
    await catalogue_command(event, api, Translator(), LanguagePreferences())
    assert expected in event.answer.await_args.args[0]


async def test_catalogue_callback_is_answered():
    event = callback()
    api = SimpleNamespace(get_products=AsyncMock(return_value=products()))
    await catalogue_page(
        event,
        CataloguePageCallback(page=1),
        api,
        Translator(),
        LanguagePreferences(),
    )
    event.answer.assert_awaited_once()
    assert "&lt;b&gt;Portal&lt;/b&gt;" in event.message.edit_text.await_args.args[0]


async def test_invalid_page_callback_does_not_call_api():
    event = callback()
    api = SimpleNamespace(get_products=AsyncMock())
    await catalogue_page(
        event,
        CataloguePageCallback.model_construct(page=0),
        api,
        Translator(),
        LanguagePreferences(),
    )
    event.answer.assert_awaited_once()
    api.get_products.assert_not_awaited()
    assert "invalid or outdated" in event.message.edit_text.await_args.args[0]


async def test_product_not_found_is_friendly_and_callback_answered():
    event = callback()
    api = SimpleNamespace(get_product=AsyncMock(side_effect=ProductNotFound()))
    await product_detail(
        event,
        ProductCallback(product_id=7, page=1),
        api,
        Translator(),
        LanguagePreferences(),
    )
    event.answer.assert_awaited_once()
    assert "no longer available" in event.message.edit_text.await_args.args[0]
