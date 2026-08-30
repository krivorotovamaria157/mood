"""The aiogram adapter — the only module that knows Telegram exists.

It does one thing: turn incoming updates into calls on :class:`BotHandlers` and
send back the chunks it returns. Keeping it this thin is what allows every
behavioural test to run without the framework.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .handlers import BotHandlers

__all__ = ["build_bot", "build_dispatcher", "build_router"]

logger = logging.getLogger(__name__)


async def _reply(message: Message, chunks: list[str]) -> None:
    for chunk in chunks:
        await message.answer(chunk)


def build_router(handlers: BotHandlers) -> Router:
    router = Router(name="moodbot")

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        await _reply(message, await handlers.start())

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await _reply(message, await handlers.help())

    @router.message(Command("history"))
    async def on_history(message: Message) -> None:
        await _reply(message, await handlers.history(message.chat.id))

    @router.message(Command("delete_me"))
    async def on_delete(message: Message) -> None:
        await _reply(message, await handlers.delete_me(message.chat.id))

    @router.message(F.text)
    async def on_text(message: Message) -> None:
        await _reply(message, await handlers.on_text(message.chat.id, message.text))

    @router.message()
    async def on_other(message: Message) -> None:
        await message.answer(
            "Я понимаю только текст. Опиши словами, что происходит."
        )

    return router


def build_dispatcher(handlers: BotHandlers) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(handlers))
    return dispatcher


def build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
