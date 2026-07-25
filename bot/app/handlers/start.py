from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.api.exceptions import APIError
from app.auth.service import TelegramAuthService
from app.keyboards.callbacks import LanguageCallback
from app.keyboards.catalogue import language_keyboard
from app.keyboards.menu import main_menu
from app.localization import LanguagePreferences, Translator

from .common import active_language, show_error

router = Router(name="start")


@router.message(CommandStart())
async def start_command(
    message: Message,
    translator: Translator,
    language_preferences: LanguagePreferences,
    auth_service: TelegramAuthService,
) -> None:
    language = active_language(message.from_user, language_preferences)
    try:
        await auth_service.synchronize(message.from_user)
        await message.answer(
            translator.get("welcome", language),
            reply_markup=main_menu(language, translator),
        )
    except APIError as error:
        await show_error(message, error, language, translator)
    except Exception as error:
        await show_error(message, error, language, translator)


@router.callback_query(F.data == "choose_language")
async def choose_language(
    callback: CallbackQuery,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if callback.message:
        await callback.message.edit_text(
            translator.get("language.choose", language),
            reply_markup=language_keyboard(),
        )


@router.callback_query(LanguageCallback.filter())
async def select_language(
    callback: CallbackQuery,
    callback_data: LanguageCallback,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    try:
        language = language_preferences.set(callback.from_user.id, callback_data.language)
    except ValueError:
        language = active_language(callback.from_user, language_preferences)
        if callback.message:
            await callback.message.edit_text(translator.get("error.invalid_callback", language))
        return
    if callback.message:
        await callback.message.edit_text(
            "\n\n".join(
                [
                    translator.get("language.changed", language),
                    translator.get("welcome", language),
                ]
            ),
            reply_markup=main_menu(language, translator),
        )
