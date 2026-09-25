from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import Chat, InaccessibleMessage

from app.handlers.common import edit_or_send


async def test_edit_or_send_edits_accessible_message():
    edit_text = AsyncMock()
    callback = SimpleNamespace(message=SimpleNamespace(edit_text=edit_text), bot=None)

    await edit_or_send(callback, "Updated", reply_markup=None)

    edit_text.assert_awaited_once_with("Updated", reply_markup=None)


async def test_edit_or_send_sends_new_message_when_original_is_inaccessible():
    bot = SimpleNamespace(send_message=AsyncMock())
    message = InaccessibleMessage(chat=Chat(id=42, type="private"), message_id=7)
    callback = SimpleNamespace(message=message, bot=bot)

    await edit_or_send(callback, "Updated")

    bot.send_message.assert_awaited_once_with(42, "Updated", reply_markup=None)


async def test_edit_or_send_ignores_callback_without_message():
    bot = SimpleNamespace(send_message=AsyncMock())

    await edit_or_send(SimpleNamespace(message=None, bot=bot), "Updated")

    bot.send_message.assert_not_awaited()
