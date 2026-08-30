"""Mock-layer tests for the aiogram adapter.

The adapter is thin, but it owns two things nothing else checks: that the chat
id reaches the handlers, and that every returned chunk is actually sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tests.fakes import FakeAnalyzer, FakeRepository

from moodbot.bot.handlers import BotHandlers
from moodbot.bot.telegram import build_dispatcher, build_router
from moodbot.service import ReflectionService

CHAT_ID = 90210


@dataclass
class FakeChat:
    id: int = CHAT_ID


@dataclass
class FakeMessage:
    text: str | None = None
    chat: FakeChat = field(default_factory=FakeChat)
    sent: list[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def handlers(repo) -> BotHandlers:
    return BotHandlers(
        service=ReflectionService(analyzer=FakeAnalyzer()), repository=repo
    )


def _callbacks(handlers: BotHandlers) -> list:
    return [h.callback for h in build_router(handlers).message.handlers]


def _by_index(handlers: BotHandlers, index: int):
    """Callbacks are registered in declaration order: start, help, history,
    delete_me, text, fallback."""
    return _callbacks(handlers)[index]


async def test_start_sends_every_chunk(handlers):
    message = FakeMessage(text="/start")
    await _by_index(handlers, 0)(message)

    assert message.sent
    assert all(chunk.strip() for chunk in message.sent)


async def test_help_lists_commands(handlers):
    message = FakeMessage(text="/help")
    await _by_index(handlers, 1)(message)

    assert "/delete_me" in "\n".join(message.sent)


async def test_history_uses_the_chat_id(handlers, repo):
    await handlers.on_text(CHAT_ID, "запись этого чата")
    await handlers.on_text(11111, "чужая запись")

    message = FakeMessage(text="/history")
    await _by_index(handlers, 2)(message)

    joined = "\n".join(message.sent)
    assert "запись этого чата" in joined
    assert "чужая запись" not in joined


async def test_delete_uses_the_chat_id(handlers, repo):
    await handlers.on_text(CHAT_ID, "запись")

    message = FakeMessage(text="/delete_me")
    await _by_index(handlers, 3)(message)

    assert repo.rows == []
    assert message.sent


async def test_free_text_is_forwarded_with_the_chat_id(handlers, repo):
    message = FakeMessage(text="мне тревожно")
    await _by_index(handlers, 4)(message)

    assert message.sent
    entry, _ = repo.rows[0]
    assert entry.user_id == CHAT_ID
    assert entry.text == "мне тревожно"


async def test_non_text_message_gets_a_usable_answer(handlers):
    message = FakeMessage(text=None)
    await _by_index(handlers, 5)(message)

    assert "текст" in "\n".join(message.sent).lower()


async def test_long_reply_is_sent_as_several_messages(repo):
    """Every chunk the handlers produce must reach Telegram, not just the first."""

    class ChattyHandlers(BotHandlers):
        async def on_text(self, user_id, text):
            return ["первое", "второе", "третье"]

    handlers = ChattyHandlers(
        service=ReflectionService(analyzer=FakeAnalyzer()), repository=repo
    )
    message = FakeMessage(text="что-то длинное")
    await _by_index(handlers, 4)(message)

    assert message.sent == ["первое", "второе", "третье"]


def test_dispatcher_includes_the_router(handlers):
    dispatcher = build_dispatcher(handlers)
    assert any(router.name == "moodbot" for router in dispatcher.sub_routers)
