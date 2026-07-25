from html import escape

from app.auth.models import BackendUser
from app.localization import Translator


def format_profile(user: BackendUser, language: str, translator: Translator) -> str:
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    if not display_name:
        display_name = translator.get("profile.name_missing", language)
    username = f"@{user.telegram_username}" if user.telegram_username else "—"
    preferred_language = user.telegram_language_code or language
    return "\n".join(
        [
            translator.get("profile.title", language),
            translator.get("profile.name", language, value=escape(display_name)),
            translator.get("profile.email", language, value=escape(user.email)),
            translator.get("profile.username", language, value=escape(username)),
            translator.get("profile.language", language, value=escape(preferred_language)),
            translator.get(
                "profile.registered",
                language,
                value=escape(user.date_joined.date().isoformat()),
            ),
        ]
    )
