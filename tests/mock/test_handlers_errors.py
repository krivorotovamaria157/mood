"""Mock-layer tests for handler error paths.

The invariant under test throughout: whatever breaks, the user gets a reply.
"""

from __future__ import annotations

import logging

import pytest

from tests.fakes import FakeAnalyzer, FakeRepository

from moodbot.bot.handlers import MAX_INPUT_CHARS, BotHandlers
from moodbot.service import ReflectionService


def _handlers(analyzer=None, repo=None) -> BotHandlers:
    return BotHandlers(
        service=ReflectionService(analyzer=analyzer or FakeAnalyzer()),
        repository=repo or FakeRepository(),
    )


def _joined(chunks) -> str:
    return "\n".join(chunks)


USER = 7


# --- input validation -----------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\n", None])
async def test_blank_input_asks_for_a_description(text):
    chunks = await _handlers().on_text(USER, text)
    assert _joined(chunks).strip()
    assert "опиши" in _joined(chunks).lower() or "напиши" in _joined(chunks).lower()


async def test_blank_input_is_not_analyzed_or_stored():
    analyzer, repo = FakeAnalyzer(), FakeRepository()
    await _handlers(analyzer, repo).on_text(USER, "   ")

    assert analyzer.calls == []
    assert repo.rows == []


async def test_overlong_input_is_truncated_and_the_user_is_told():
    analyzer = FakeAnalyzer()
    chunks = await _handlers(analyzer).on_text(USER, "а" * (MAX_INPUT_CHARS + 500))

    analyzed_text, _ = analyzer.calls[0]
    assert len(analyzed_text) == MAX_INPUT_CHARS
    assert "сокращ" in _joined(chunks).lower() or "длин" in _joined(chunks).lower()


# --- analyzer failure -----------------------------------------------------


async def test_analyzer_failure_still_answers_the_user():
    analyzer = FakeAnalyzer(error=RuntimeError("everything is on fire"))
    chunks = await _handlers(analyzer).on_text(USER, "тревожно")

    assert _joined(chunks).strip()
    assert "не получилось" in _joined(chunks).lower() or "ошибка" in _joined(chunks).lower()


async def test_analyzer_failure_does_not_leak_the_exception_text():
    analyzer = FakeAnalyzer(error=RuntimeError("secret internal detail"))
    chunks = await _handlers(analyzer).on_text(USER, "тревожно")

    assert "secret internal detail" not in _joined(chunks)


async def test_analyzer_failure_does_not_log_the_user_text(caplog):
    secret = "очень личный текст про семью"
    analyzer = FakeAnalyzer(error=RuntimeError("boom"))

    with caplog.at_level(logging.DEBUG):
        await _handlers(analyzer).on_text(USER, secret)

    assert secret not in caplog.text


# --- storage failure ------------------------------------------------------


async def test_read_failure_degrades_to_no_history():
    analyzer = FakeAnalyzer()
    repo = FakeRepository(read_error=OSError("database is locked"))

    chunks = await _handlers(analyzer, repo).on_text(USER, "тревожно")

    assert analyzer.calls[0][1] == ()
    assert _joined(chunks).strip()


async def test_write_failure_still_delivers_the_analysis():
    repo = FakeRepository(add_error=OSError("disk full"))
    chunks = await _handlers(repo=repo).on_text(USER, "тревожно")

    text = _joined(chunks)
    assert "разбор" in text
    assert "сохранить" in text.lower()


async def test_history_command_survives_a_storage_failure():
    repo = FakeRepository(read_error=OSError("database is locked"))
    chunks = await _handlers(repo=repo).history(USER)

    assert _joined(chunks).strip()


async def test_delete_command_reports_failure_honestly():
    class BrokenRepo(FakeRepository):
        async def delete_user(self, user_id: int) -> int:
            raise OSError("database is locked")

    chunks = await _handlers(repo=BrokenRepo()).delete_me(USER)
    text = _joined(chunks).lower()

    assert "не" in text and ("удал" in text or "получилось" in text)


# --- crisis resilience ----------------------------------------------------


async def test_crisis_reply_survives_a_storage_failure():
    """Nothing may stand between a crisis message and its reply."""
    repo = FakeRepository(add_error=OSError("disk full"))
    chunks = await _handlers(repo=repo).on_text(USER, "хочу умереть")

    assert "112" in _joined(chunks)


async def test_crisis_reply_survives_an_analyzer_failure():
    analyzer = FakeAnalyzer(error=RuntimeError("provider down"))
    chunks = await _handlers(analyzer).on_text(USER, "хочу умереть")

    assert "112" in _joined(chunks)
