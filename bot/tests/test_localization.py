import pytest

from app.localization.messages import MESSAGES
from app.localization.translator import Translator, resolve_language


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("en", "en"),
        ("ru", "ru"),
        ("ru-RU", "ru"),
        ("ru_UA", "ru"),
        ("en-US", "en"),
        ("RU-ru", "ru"),
        ("de", "en"),
        (None, "en"),
    ],
)
def test_language_resolution(source, expected):
    assert resolve_language(source) == expected


def test_translation_fallbacks(monkeypatch):
    translator = Translator()
    monkeypatch.delitem(MESSAGES["ru"], "welcome")
    assert translator.get("welcome", "ru") == MESSAGES["en"]["welcome"]
    assert translator.get("does.not.exist", "ru") == "does.not.exist"


def test_all_user_facing_keys_are_complete():
    assert MESSAGES["en"]
    assert set(MESSAGES["ru"]) == set(MESSAGES["en"])
    assert all(MESSAGES["en"].values())
    assert all(MESSAGES["ru"].values())
