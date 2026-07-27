from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api.exceptions import APIError
from app.auth.service import TelegramAuthService
from app.keyboards.callbacks import (
    AddCartCallback,
    CartActionCallback,
    CartItemCallback,
    PaymentStatusCallback,
)
from app.keyboards.cart import (
    added_to_cart_keyboard,
    cart_keyboard,
    confirmation_keyboard,
    payment_keyboard,
    payment_status_keyboard,
)
from app.localization import LanguagePreferences, Translator
from app.presentation import format_cart, format_order_detail

from .common import active_language, show_error

router = Router(name="cart")


async def _show_cart(
    event: Message | CallbackQuery,
    auth_service: TelegramAuthService,
    translator: Translator,
    preferences: LanguagePreferences,
) -> None:
    language = active_language(event.from_user, preferences)
    try:
        cart = await auth_service.get_cart(event.from_user)
        markup = (
            cart_keyboard(cart, event.from_user.id, language, translator)
            if event.from_user
            else None
        )
        if isinstance(event, CallbackQuery):
            if event.message:
                await event.message.edit_text(
                    format_cart(cart, language, translator), reply_markup=markup
                )
        else:
            await event.answer(
                format_cart(cart, language, translator), reply_markup=markup
            )
    except APIError as error:
        await show_error(event, error, language, translator)
    except Exception as error:
        await show_error(event, error, language, translator)


@router.message(Command("cart"))
async def cart_command(message, auth_service, translator, language_preferences):
    await _show_cart(message, auth_service, translator, language_preferences)


@router.callback_query(F.data == "cart")
async def cart_callback(callback, auth_service, translator, language_preferences):
    await callback.answer()
    await _show_cart(callback, auth_service, translator, language_preferences)


@router.callback_query(AddCartCallback.filter())
async def add_to_cart(
    callback: CallbackQuery,
    callback_data: AddCartCallback,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    try:
        await auth_service.add_cart_item(
            callback.from_user, callback_data.product_id, 1
        )
        if callback.message:
            await callback.message.edit_text(
                translator.get("cart.added", language),
                reply_markup=added_to_cart_keyboard(language, translator),
            )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


def _owned(callback: CallbackQuery, owner_id: int) -> bool:
    return bool(callback.from_user and callback.from_user.id == owner_id)


@router.callback_query(CartItemCallback.filter())
async def change_cart_item(
    callback: CallbackQuery,
    callback_data: CartItemCallback,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if not _owned(callback, callback_data.owner_id):
        if callback.message:
            await callback.message.edit_text(
                translator.get("error.invalid_callback", language)
            )
        return
    try:
        cart = await auth_service.get_cart(callback.from_user)
        item = next((item for item in cart.items if item.id == callback_data.item_id), None)
        if item is None:
            if callback.message:
                await callback.message.edit_text(
                    translator.get("error.resource_not_found", language)
                )
            return
        if callback_data.action == "remove" or (
            callback_data.action == "dec" and item.quantity == 1
        ):
            await auth_service.remove_cart_item(callback.from_user, item.id)
        else:
            quantity = item.quantity + (1 if callback_data.action == "inc" else -1)
            await auth_service.update_cart_item(callback.from_user, item.id, quantity)
        await _show_cart(callback, auth_service, translator, language_preferences)
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(CartActionCallback.filter())
async def cart_action(
    callback: CallbackQuery,
    callback_data: CartActionCallback,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if not _owned(callback, callback_data.owner_id):
        if callback.message:
            await callback.message.edit_text(
                translator.get("error.invalid_callback", language)
            )
        return
    if callback_data.action in {"clear", "checkout"}:
        key = (
            "cart.clear_confirm"
            if callback_data.action == "clear"
            else "cart.checkout_confirm"
        )
        if callback.message:
            await callback.message.edit_text(
                translator.get(key, language),
                reply_markup=confirmation_keyboard(
                    callback_data.action,
                    callback_data.owner_id,
                    language,
                    translator,
                ),
            )
        return
    try:
        if callback_data.action == "clear_yes":
            await auth_service.clear_cart(callback.from_user)
            if callback.message:
                await callback.message.edit_text(
                    translator.get("cart.cleared", language)
                )
        else:
            order = await auth_service.checkout_cart(callback.from_user)
            payment = await auth_service.create_payment(
                callback.from_user, order.id
            )
            if callback.message:
                await callback.message.edit_text(
                    translator.get(
                        "payment.created",
                        language,
                        amount=format(payment.amount, ".2f"),
                        status=escape(payment.status),
                    ),
                    reply_markup=payment_keyboard(
                        payment, callback_data.owner_id, language, translator
                    ),
                )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(PaymentStatusCallback.filter())
async def check_payment_status(
    callback: CallbackQuery,
    callback_data: PaymentStatusCallback,
    auth_service: TelegramAuthService,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if not _owned(callback, callback_data.owner_id):
        if callback.message:
            await callback.message.edit_text(
                translator.get("error.invalid_callback", language)
            )
        return
    try:
        order = await auth_service.get_my_order(
            callback.from_user, callback_data.order_id
        )
        if not callback.message:
            return
        if order.status == "PAID":
            await callback.message.edit_text(
                "\n\n".join(
                    (
                        translator.get("payment.completed", language),
                        format_order_detail(order, language, translator),
                    )
                )
            )
            return
        if not order.payments:
            await callback.message.edit_text(
                translator.get("payment.missing", language)
            )
            return
        latest_payment = order.payments[-1]
        await callback.message.edit_text(
            translator.get(
                "payment.pending",
                language,
                status=escape(latest_payment.status),
            ),
            reply_markup=payment_status_keyboard(
                callback_data.order_id,
                callback_data.owner_id,
                language,
                translator,
            ),
        )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(F.data.regexp(r"^(add|cit|crt|pay):"))
async def invalid_cart_callback(
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
