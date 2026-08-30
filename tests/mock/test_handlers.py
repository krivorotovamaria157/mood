"""Mock-layer tests for the framework-free bot handlers."""

from __future__ import annotations

import pytest

from tests.fakes import FakeAnalyzer, FakeRepository

from moodbot.bot.handlers import BotHandlers
from moodbot.models import RiskLevel
from moodbot.safety_texts import DISCLAIMER
from moodbot.service import ReflectionService

USER = 4242


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def analyzer() -> FakeAnalyzer:
    return FakeAnalyzer()


@pytest.fixture
def handlers(analyzer, repo) -> BotHandlers:
    return BotHandlers(service=ReflectionService(analyzer=analyzer), repository=repo)


def _joined(chunks) -> str:
    return "\n".join(chunks)


# --- commands -------------------------------------------------------------


async def test_start_greets_and_states_the_disclaimer(handlers):
    text = _joined(await handlers.start())
    assert DISCLAIMER in text
    assert text.strip()


async def test_start_explains_what_to_write(handlers):
    text = _joined(await handlers.start()).lower()
    assert "напиши" in text or "опиши" in text


async def test_help_lists_the_commands(handlers):
    text = _joined(await handlers.help())
    for command in ("/start", "/history", "/delete_me"):
        assert command in text


async def test_history_is_empty_for_a_new_user(handlers):
    text = _joined(await handlers.history(USER)).lower()
    assert "пока" in text or "нет" in text


async def test_history_lists_previous_entries(handlers, repo):
    await handlers.on_text(USER, "тревожно перед встречей")
    await handlers.on_text(USER, "сегодня спокойнее")

    text = _joined(await handlers.history(USER))

    assert "тревожно перед встречей" in text
    assert "сегодня спокойнее" in text


async def test_delete_me_removes_data_and_confirms(handlers, repo):
    await handlers.on_text(USER, "запись")
    text = _joined(await handlers.delete_me(USER))

    assert repo.rows == []
    assert "удал" in text.lower()


async def test_delete_me_on_empty_history_is_not_an_error(handlers):
    text = _joined(await handlers.delete_me(USER))
    assert text.strip()


# --- free text ------------------------------------------------------------


async def test_free_text_is_analyzed_and_stored(handlers, analyzer, repo):
    chunks = await handlers.on_text(USER, "мне тревожно перед собеседованием")

    assert analyzer.calls[0][0] == "мне тревожно перед собеседованием"
    assert len(repo.rows) == 1
    assert _joined(chunks).strip()


async def test_reply_contains_the_analysis_summary(handlers):
    text = _joined(await handlers.on_text(USER, "тревожно"))
    assert "разбор" in text


async def test_previous_entries_are_passed_to_the_analyzer(handlers, analyzer):
    await handlers.on_text(USER, "первая запись")
    await handlers.on_text(USER, "вторая запись")

    _, history = analyzer.calls[-1]
    assert "первая запись" in history


async def test_history_is_scoped_to_the_sender(handlers, analyzer):
    await handlers.on_text(1, "чужая запись")
    await handlers.on_text(2, "моя запись")

    _, history = analyzer.calls[-1]
    assert "чужая запись" not in history


async def test_stored_row_carries_the_analysis(handlers, repo):
    await handlers.on_text(USER, "тревожно")

    entry, analysis = repo.rows[0]
    assert entry.user_id == USER
    assert analysis.summary == "разбор"


# --- crisis short-circuit -------------------------------------------------


async def test_crisis_message_is_not_sent_to_the_analyzer(handlers, analyzer):
    chunks = await handlers.on_text(USER, "я больше не хочу жить")

    assert analyzer.calls == []
    assert "112" in _joined(chunks)


async def test_crisis_message_is_still_recorded(handlers, repo):
    """The entry matters for continuity even though the reply is a crisis one."""
    await handlers.on_text(USER, "я больше не хочу жить")

    assert len(repo.rows) == 1
    assert repo.rows[0][1].risk_level is RiskLevel.CRISIS
