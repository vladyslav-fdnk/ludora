import pytest
from pydantic import ValidationError

from app.api.schemas import Product, ProductPage
from app.keyboards.callbacks import CataloguePageCallback, LanguageCallback, ProductCallback
from app.keyboards.catalogue import catalogue_keyboard, language_keyboard
from app.keyboards.menu import main_menu
from app.localization import Translator


def page(language="en", previous=False, following=False):
    from decimal import Decimal

    product = Product(42, "Portal", Decimal("9.99"), "Steam", "GAME")
    return ProductPage((product,), 1, 2 if previous else 1, following, previous)


def test_callback_contents_and_size():
    packed = ProductCallback(product_id=42, page=3).pack()
    assert packed == "prd:42:3"
    assert len(packed.encode()) < 64
    assert CataloguePageCallback.unpack("cat:2").page == 2


@pytest.mark.parametrize("raw", ["cat:no", "prd:1", "lng:en:extra"])
def test_malformed_callbacks_are_rejected(raw):
    callback_type = (
        CataloguePageCallback if raw.startswith("cat") else
        ProductCallback if raw.startswith("prd") else LanguageCallback
    )
    with pytest.raises((ValueError, TypeError, ValidationError)):
        callback_type.unpack(raw)


def test_language_callback_only_accepts_supported_via_service_boundary():
    assert LanguageCallback.unpack("lng:ru").language == "ru"
    assert LanguageCallback.unpack("lng:en").language == "en"
    with pytest.raises(ValidationError):
        LanguageCallback.unpack("lng:de")


@pytest.mark.parametrize("raw", ["cat:0", "cat:-1", "prd:0:1", "prd:1:0"])
def test_callback_page_and_product_ids_must_be_positive(raw):
    callback_type = CataloguePageCallback if raw.startswith("cat") else ProductCallback
    with pytest.raises(ValidationError):
        callback_type.unpack(raw)


def test_localized_labels_and_navigation_bounds():
    translator = Translator()
    english = catalogue_keyboard(page(following=True), "en", translator)
    russian = catalogue_keyboard(page(previous=True), "ru", translator)
    assert any(button.text == "Next ›" for row in english.inline_keyboard for button in row)
    assert not any("Previous" in button.text for row in english.inline_keyboard for button in row)
    assert any(button.text == "‹ Назад" for row in russian.inline_keyboard for button in row)
    assert main_menu("ru", translator).inline_keyboard[0][0].text == "🛍 Открыть каталог"
    assert [button.text for button in language_keyboard().inline_keyboard[0]] == [
        "English",
        "Русский",
    ]
