"""Ludora Telegram bot application lifecycle."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault

from app.api import BackendClient
from app.config import Settings
from app.handlers import catalogue_router, start_router
from app.localization import LanguagePreferences, Translator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_application(
    settings: Settings,
) -> tuple[Bot, Dispatcher, BackendClient]:
    bot = Bot(
        token=settings.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(catalogue_router)
    api_client = BackendClient(settings.backend_base_url, settings.api_timeout)
    dispatcher["api_client"] = api_client
    dispatcher["translator"] = Translator()
    dispatcher["language_preferences"] = LanguagePreferences(settings.default_language)
    return bot, dispatcher, api_client


async def register_commands(bot: Bot, translator: Translator) -> None:
    for language in ("en", "ru"):
        commands = [
            BotCommand(command="start", description=translator.get("command.start", language)),
            BotCommand(
                command="catalogue",
                description=translator.get("command.catalogue", language),
            ),
        ]
        try:
            await bot.set_my_commands(
                commands,
                scope=BotCommandScopeDefault(),
                language_code=language,
            )
        except Exception:
            logger.exception("Could not register Telegram commands for %s", language)


async def main() -> None:
    settings = Settings.from_env()
    bot, dispatcher, api_client = create_application(settings)
    try:
        await register_commands(bot, dispatcher["translator"])
        await dispatcher.start_polling(bot)
    finally:
        await api_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
