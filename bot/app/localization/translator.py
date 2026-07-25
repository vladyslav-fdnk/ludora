"""Lightweight localization and replaceable in-memory preferences."""

from .messages import MESSAGES

SUPPORTED_LANGUAGES = frozenset({"en", "ru"})


def resolve_language(language_code: str | None, default: str = "en") -> str:
    if not language_code:
        return default if default in SUPPORTED_LANGUAGES else "en"
    base = language_code.replace("_", "-").split("-", 1)[0].lower()
    return base if base in SUPPORTED_LANGUAGES else "en"


class Translator:
    def get(self, key: str, language: str, **values: object) -> str:
        locale = resolve_language(language)
        template = MESSAGES.get(locale, {}).get(key) or MESSAGES["en"].get(key)
        if template is None:
            return key
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template


class LanguagePreferences:
    """Process-local preferences; replaceable by persistent storage later."""

    def __init__(self, default_language: str = "en") -> None:
        self.default_language = resolve_language(default_language)
        self._preferences: dict[int, str] = {}

    def get(self, user_id: int | None, telegram_language: str | None) -> str:
        if user_id is not None and user_id in self._preferences:
            return self._preferences[user_id]
        detected = resolve_language(telegram_language)
        return detected if telegram_language else self.default_language

    def set(self, user_id: int, language: str) -> str:
        resolved = resolve_language(language)
        if language.lower() not in SUPPORTED_LANGUAGES:
            raise ValueError("Unsupported language")
        self._preferences[user_id] = resolved
        return resolved
