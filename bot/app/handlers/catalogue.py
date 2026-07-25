from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api import BackendClient
from app.api.exceptions import APIError
from app.keyboards.callbacks import CataloguePageCallback, ProductCallback
from app.keyboards.catalogue import catalogue_keyboard, product_keyboard
from app.localization import LanguagePreferences, Translator
from app.presentation import format_catalogue, format_product

from .common import active_language, show_error

router = Router(name="catalogue")


@router.message(Command("catalogue"))
async def catalogue_command(
    message: Message,
    api_client: BackendClient,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    language = active_language(message.from_user, language_preferences)
    try:
        page = await api_client.get_products(1)
        if not page.products:
            await message.answer(translator.get("catalogue.empty", language))
            return
        await message.answer(
            format_catalogue(page, language, translator),
            reply_markup=catalogue_keyboard(page, language, translator),
        )
    except APIError as error:
        await show_error(message, error, language, translator)
    except Exception as error:
        await show_error(message, error, language, translator)


@router.callback_query(CataloguePageCallback.filter())
async def catalogue_page(
    callback: CallbackQuery,
    callback_data: CataloguePageCallback,
    api_client: BackendClient,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if callback_data.page < 1:
        if callback.message:
            await callback.message.edit_text(translator.get("error.invalid_callback", language))
        return
    try:
        page = await api_client.get_products(callback_data.page)
        if not page.products:
            if callback.message:
                await callback.message.edit_text(translator.get("catalogue.empty", language))
            return
        if callback.message:
            await callback.message.edit_text(
                format_catalogue(page, language, translator),
                reply_markup=catalogue_keyboard(page, language, translator),
            )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(ProductCallback.filter())
async def product_detail(
    callback: CallbackQuery,
    callback_data: ProductCallback,
    api_client: BackendClient,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if callback_data.product_id < 1 or callback_data.page < 1:
        if callback.message:
            await callback.message.edit_text(translator.get("error.invalid_callback", language))
        return
    try:
        product = await api_client.get_product(callback_data.product_id)
        if callback.message:
            await callback.message.edit_text(
                format_product(product, language, translator),
                reply_markup=product_keyboard(callback_data.page, language, translator),
            )
    except APIError as error:
        await show_error(callback, error, language, translator)
    except Exception as error:
        await show_error(callback, error, language, translator)


@router.callback_query(F.data.regexp(r"^(cat|prd|lng):"))
async def invalid_structured_callback(
    callback: CallbackQuery,
    translator: Translator,
    language_preferences: LanguagePreferences,
) -> None:
    await callback.answer()
    language = active_language(callback.from_user, language_preferences)
    if callback.message:
        await callback.message.edit_text(translator.get("error.invalid_callback", language))
