import logging
from typing import cast

from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    Message,
    User,
)

from app.api.exceptions import (
    AuthenticationFailed,
    AuthenticationRequired,
    BackendTimeout,
    BackendUnavailable,
    Conflict,
    InvalidResponse,
    MissingTelegramUser,
    PermissionDenied,
    ProductNotFound,
    ResourceNotFound,
    UnexpectedAPIStatus,
    ValidationFailed,
)
from app.localization import LanguagePreferences, Translator

logger = logging.getLogger(__name__)


def active_language(user: User | None, preferences: LanguagePreferences) -> str:
    return preferences.get(
        user.id if user else None,
        user.language_code if user else None,
    )


async def edit_or_send(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Replace the callback's message text, or send a new message.

    Telegram stops allowing edits of old messages and then delivers them as
    ``InaccessibleMessage``, which has no ``edit_text``. In that case the reply
    is sent as a new message to the same chat instead of failing the handler.
    """
    message = callback.message
    if not message:
        return
    if isinstance(message, InaccessibleMessage):
        if callback.bot is not None:
            await callback.bot.send_message(message.chat.id, text, reply_markup=reply_markup)
        return
    await message.edit_text(text, reply_markup=reply_markup)


def error_key(error: Exception) -> str:
    if isinstance(error, BackendTimeout):
        return "error.timeout"
    if isinstance(error, BackendUnavailable | UnexpectedAPIStatus):
        return "error.unavailable"
    if isinstance(error, InvalidResponse):
        return "error.invalid_response"
    if isinstance(error, ProductNotFound):
        return "error.not_found"
    if isinstance(error, ResourceNotFound):
        return "error.resource_not_found"
    if isinstance(error, ValidationFailed):
        return "error.validation"
    if isinstance(error, Conflict):
        return "error.conflict"
    if isinstance(error, PermissionDenied):
        return "error.permission"
    if isinstance(error, MissingTelegramUser):
        return "error.missing_user"
    if isinstance(error, AuthenticationRequired):
        return "error.auth_expired"
    if isinstance(error, AuthenticationFailed):
        return "error.auth_failed"
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
        logger.warning("Expected bot API failure: %s", type(error).__name__)
    text = translator.get(error_key(error), language)
    if isinstance(event, CallbackQuery) or hasattr(event, "message"):
        await edit_or_send(cast(CallbackQuery, event), text)
    else:
        await event.answer(text)
