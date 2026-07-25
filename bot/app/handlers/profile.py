from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api.exceptions import APIError
from app.auth.service import TelegramAuthService
from app.localization import LanguagePreferences, Translator
from app.presentation import format_profile

from .common import active_language, show_error

router = Router(name="profile")


async def _show_profile(
    event: Message | CallbackQuery,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    telegram_user = event.from_user
    language = active_language(telegram_user, language_preferences)
    try:
        profile = await auth_service.get_profile(telegram_user)
        text = format_profile(profile, language, translator)
        if isinstance(event, CallbackQuery):
            if event.message:
                await event.message.edit_text(text)
        else:
            await event.answer(text)
    except APIError as error:
        await show_error(event, error, language, translator)
    except Exception as error:
        await show_error(event, error, language, translator)


@router.message(Command("profile"))
async def profile_command(
    message: Message,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await _show_profile(message, auth_service, translator, language_preferences)


@router.callback_query(F.data == "profile")
async def profile_callback(
    callback: CallbackQuery,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    await _show_profile(callback, auth_service, translator, language_preferences)
