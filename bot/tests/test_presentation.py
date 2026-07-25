from decimal import Decimal

from app.api.schemas import Product, ProductPage
from app.localization import Translator
from app.presentation.products import MAX_DESCRIPTION_LENGTH, format_catalogue, format_product


def product(**overrides):
    values = {
        "id": 1,
        "title": "<a href='bad'>Bad</a>",
        "price": Decimal("29.90"),
        "platform": "Steam & <b>evil</b>",
        "product_type": "UNKNOWN<script>",
    }
    values.update(overrides)
    return Product(**values)


def test_detail_escapes_dynamic_html_and_falls_back():
    text = format_product(product(description=None), "en", Translator())
    assert "&lt;a href=" in text
    assert "<a href=" not in text
    assert "&lt;b&gt;evil&lt;/b&gt;" in text
    assert "UNKNOWN&lt;script&gt;" in text
    assert "No description available." in text
    assert "No categories specified." in text
    assert "29.90" in text


def test_russian_labels_and_long_description_truncation():
    text = format_product(
        product(title="Игра", product_type="GAME", description="<b>" + "x" * 4000),
        "ru",
        Translator(),
    )
    assert "<b>Платформа:</b>" in text
    assert "<b>Тип:</b> Игра" in text
    assert "[сокращено]" in text
    assert len(text) < MAX_DESCRIPTION_LENGTH + 500
    assert "&lt;b&gt;" in text


def test_catalogue_uses_english_labels():
    page = ProductPage((product(title="Portal", product_type="GAME"),), 1, 1, False, False)
    text = format_catalogue(page, "en", Translator())
    assert "<b>Platform:</b>" in text
    assert "<b>Type:</b> Game" in text
