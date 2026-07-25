import logging

from aiogram.types import CallbackQuery, Message, User

from app.api.exceptions import (
    BackendTimeout,
    BackendUnavailable,
    InvalidResponse,
    ProductNotFound,
    UnexpectedAPIStatus,
)
from app.localization import LanguagePreferences, Translator

logger = logging.getLogger(__name__)


def active_language(user: User | None, preferences: LanguagePreferences) -> str:
    return preferences.get(
        user.id if user else None,
        user.language_code if user else None,
    )


def error_key(error: Exception) -> str:
    if isinstance(error, BackendTimeout):
        return "error.timeout"
    if isinstance(error, BackendUnavailable | UnexpectedAPIStatus):
        return "error.unavailable"
    if isinstance(error, InvalidResponse):
        return "error.invalid_response"
    if isinstance(error, ProductNotFound):
        return "error.not_found"
    return "error.internal"


async def show_error(
    event: Message | CallbackQuery,
    error: Exception,
    language: str,
    translator: Translator,
) -> None:
    if error_key(error) == "error.internal":
        logger.error(
            "Unexpected bot handler failure",
            exc_info=(type(error), error, error.__traceback__),
        )
    else:
        logger.warning("Catalogue API failure: %s", type(error).__name__)
    text = translator.get(error_key(error), language)
    if isinstance(event, CallbackQuery) or hasattr(event, "message"):
        callback_message = getattr(event, "message", None)
        if callback_message:
            await callback_message.edit_text(text)
    else:
        await event.answer(text)
