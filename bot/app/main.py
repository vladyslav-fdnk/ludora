"""Entry point for the Telegram bot.

This only wires up the Bot/Dispatcher and starts polling. No handlers are
registered yet — see app/handlers for details.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # TODO: dp.include_router(...) for each router defined in app/handlers.

    await dp.start_polling(bot)


if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not configured, skipping bot startup.")
        sys.exit(0)

    asyncio.run(main())
