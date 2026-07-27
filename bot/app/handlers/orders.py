from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api.exceptions import APIError, ResourceNotFound
from app.auth.service import TelegramAuthService
from app.keyboards.callbacks import OrderDetailCallback
from app.keyboards.orders import orders_keyboard
from app.localization import LanguagePreferences, Translator
from app.presentation import format_order_detail, format_order_history

from .common import active_language, show_error

router = Router(name="orders")


async def _show_orders(
    event: Message | CallbackQuery,
    auth_service: TelegramAuthService,
    translator: Translator,
    preferences: LanguagePreferences,
) -> None:
    language = active_language(event.from_user, preferences)
    try:
        orders = await auth_service.get_my_orders(event.from_user)
        markup = (
            orders_keyboard(
                orders, event.from_user.id, language, translator
            )
            if orders and event.from_user
            else None
        )
        text = format_order_history(orders, language, translator)
        if isinstance(event, CallbackQuery):
            if event.message:
                await event.message.edit_text(text, reply_markup=markup)
        else:
            await event.answer(text, reply_markup=markup)
    except APIError as error:
        await show_error(event, error, language, translator)
    except Exception as error:
        await show_error(event, error, language, translator)


@router.message(Command("orders"))
async def orders_command(
    message: Message,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await _show_orders(message, auth_service, translator, language_preferences)


@router.callback_query(F.data == "orders")
async def orders_callback(
    callback: CallbackQuery,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    await _show_orders(callback, auth_service, translator, language_preferences)


@router.callback_query(OrderDetailCallback.filter())
async def order_detail(
    callback: CallbackQuery,
    callback_data: OrderDetailCallback,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if (
        not callback.from_user
        or callback.from_user.id != callback_data.owner_id
    ):
        if callback.message:
            await callback.message.edit_text(
                translator.get("error.invalid_callback", language)
            )
        return
    try:
        order = await auth_service.get_my_order(
            callback.from_user, callback_data.order_id
        )
        if callback.message:
            await callback.message.edit_text(
                format_order_detail(order, language, translator)
            )
    except ResourceNotFound:
        if callback.message:
            await callback.message.edit_text(
                translator.get("orders.not_found", language)
            )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(F.data.regexp(r"^ord:"))
async def invalid_order_callback(
    callback: CallbackQuery,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if callback.message:
        await callback.message.edit_text(
            translator.get("error.invalid_callback", language)
        )
