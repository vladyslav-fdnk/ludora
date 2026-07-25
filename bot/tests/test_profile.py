import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.exceptions import BackendUnavailable, MissingTelegramUser
from app.auth import BackendUser
from app.handlers.profile import profile_command
from app.localization import LanguagePreferences, Translator
from app.presentation import format_profile


def backend_user(**overrides):
    values = {
        "email": "telegram-123@bot.ludora.invalid",
        "first_name": "<b>Vlad</b>",
        "last_name": "& Co",
        "telegram_username": "user<script>",
        "telegram_language_code": "ru",
        "date_joined": datetime(2026, 7, 25, tzinfo=UTC),
    }
    values.update(overrides)
    return BackendUser(**values)


@pytest.mark.parametrize(
    ("language", "title"),
    [("en", "Your profile"), ("ru", "Ваш профиль")],
)
def test_profile_is_localized_and_escapes_dynamic_html(language, title):
    text = format_profile(backend_user(), language, Translator())
    assert title in text
    assert "&lt;b&gt;Vlad&lt;/b&gt;" in text
    assert "user&lt;script&gt;" in text
    assert "<script>" not in text


async def test_direct_profile_works_without_prior_start():
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=123, language_code="en"),
        answer=AsyncMock(),
    )
    auth = SimpleNamespace(get_profile=AsyncMock(return_value=backend_user()))
    await profile_command(event, auth, Translator(), LanguagePreferences())
    auth.get_profile.assert_awaited_once_with(event.from_user)
    assert "Your profile" in event.answer.await_args.args[0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MissingTelegramUser(), "user information is unavailable"),
        (BackendUnavailable(), "temporarily unavailable"),
    ],
)
async def test_profile_expected_failures_are_friendly_without_traceback(
    error, expected, caplog
):
    event = SimpleNamespace(
        from_user=None,
        answer=AsyncMock(),
    )
    auth = SimpleNamespace(get_profile=AsyncMock(side_effect=error))
    with caplog.at_level(logging.WARNING):
        await profile_command(event, auth, Translator(), LanguagePreferences())
    assert expected in event.answer.await_args.args[0]
    assert all(record.exc_info is None for record in caplog.records)


async def test_unexpected_profile_failure_keeps_real_traceback(caplog):
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=123, language_code="en"),
        answer=AsyncMock(),
    )
    auth = SimpleNamespace(get_profile=AsyncMock(side_effect=RuntimeError("boom")))
    with caplog.at_level(logging.ERROR):
        await profile_command(event, auth, Translator(), LanguagePreferences())
    record = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert record.exc_info is not None
    assert record.exc_info[2] is not None
    assert "Something went wrong" in event.answer.await_args.args[0]
