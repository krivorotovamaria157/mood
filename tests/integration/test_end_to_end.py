"""End-to-end: message → screening → analysis → storage → reply.

Real handlers, real service, real SQLite on a temp file. The only fake is the
analyzer, because the alternative is a network call.
"""

from __future__ import annotations

import pytest

from tests.fakes import FakeAnalyzer

from moodbot.analyzer.fallback import RuleBasedAnalyzer
from moodbot.bot.app import build_analyzer, build_handlers
from moodbot.bot.handlers import BotHandlers
from moodbot.config import Settings
from moodbot.models import RiskLevel
from moodbot.safety_texts import DISCLAIMER
from moodbot.service import ReflectionService
from moodbot.storage.repository import EntryRepository

USER = 555
TOKEN = "1234567890:TEST-not-a-real-token"


@pytest.fixture
def repo(tmp_path) -> EntryRepository:
    repository = EntryRepository(tmp_path / "e2e.sqlite3")
    repository.initialize()
    return repository


@pytest.fixture
def handlers(repo) -> BotHandlers:
    return BotHandlers(
        service=ReflectionService(analyzer=RuleBasedAnalyzer()), repository=repo
    )


def _joined(chunks) -> str:
    return "\n".join(chunks)


# --- the happy path -------------------------------------------------------


async def test_message_is_analyzed_stored_and_answered(handlers, repo):
    chunks = await handlers.on_text(USER, "тревожно перед собеседованием, не сплю")

    assert _joined(chunks).strip()
    assert DISCLAIMER in _joined(chunks)
    assert await repo.count(USER) == 1


async def test_second_message_sees_the_first_as_history(repo):
    analyzer = FakeAnalyzer()
    handlers = BotHandlers(
        service=ReflectionService(analyzer=analyzer), repository=repo
    )

    await handlers.on_text(USER, "тревожно на работе")
    await handlers.on_text(USER, "снова тревожно")

    _, history = analyzer.calls[-1]
    assert "тревожно на работе" in history


async def test_history_command_reflects_stored_entries(handlers):
    await handlers.on_text(USER, "первая запись про тревогу")
    text = _joined(await handlers.history(USER))

    assert "первая запись про тревогу" in text


async def test_delete_me_really_clears_the_database(handlers, repo):
    await handlers.on_text(USER, "запись один")
    await handlers.on_text(USER, "запись два")

    await handlers.delete_me(USER)

    assert await repo.count(USER) == 0
    assert "пока нет" in _joined(await handlers.history(USER)).lower()


async def test_users_do_not_see_each_others_entries(handlers):
    await handlers.on_text(1, "запись первого пользователя")
    await handlers.on_text(2, "запись второго пользователя")

    text = _joined(await handlers.history(2))

    assert "запись первого пользователя" not in text


# --- the crisis path ------------------------------------------------------


async def test_crisis_message_gets_the_crisis_reply_and_is_recorded(handlers, repo):
    chunks = await handlers.on_text(USER, "я больше не хочу жить")
    text = _joined(chunks)

    assert "112" in text
    assert "Наблюдения" not in text

    records = await repo.history(USER)
    assert records[0].risk_level is RiskLevel.CRISIS
    assert records[0].source == "safety"


# --- wiring ---------------------------------------------------------------


def test_build_analyzer_falls_back_without_an_api_key():
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN})
    assert isinstance(build_analyzer(settings), RuleBasedAnalyzer)


def test_build_analyzer_uses_claude_when_a_key_is_present():
    from moodbot.analyzer.claude import ClaudeAnalyzer

    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "ANTHROPIC_API_KEY": "sk-ant-not-real"}
    )
    # Constructing the SDK client does not open a connection.
    assert isinstance(build_analyzer(settings), ClaudeAnalyzer)


def test_build_handlers_creates_the_database(tmp_path):
    db = tmp_path / "created.sqlite3"
    settings = Settings.from_env(
        {"TELEGRAM_BOT_TOKEN": TOKEN, "MOODBOT_DB_PATH": str(db)}
    )

    assert isinstance(build_handlers(settings), BotHandlers)
    assert db.exists()


# --- CLI ------------------------------------------------------------------


def test_check_reports_ok_without_touching_the_network(monkeypatch, capsys, tmp_path):
    from moodbot.__main__ import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MOODBOT_DB_PATH", str(tmp_path / "cli.sqlite3"))

    assert main(["--check"]) == 0

    out = capsys.readouterr().out
    assert "Configuration OK" in out
    assert "rule-based" in out


def test_check_fails_loudly_without_a_token(monkeypatch, capsys):
    from moodbot.__main__ import main

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr("moodbot.__main__.load_dotenv", lambda *a, **k: False)

    assert main(["--check"]) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_check_does_not_print_the_token(monkeypatch, capsys, tmp_path):
    from moodbot.__main__ import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("MOODBOT_DB_PATH", str(tmp_path / "cli.sqlite3"))

    main(["--check"])

    assert TOKEN not in capsys.readouterr().out


# --- telegram adapter -----------------------------------------------------


def test_router_registers_the_expected_handlers(handlers):
    from moodbot.bot.telegram import build_router

    router = build_router(handlers)
    assert len(router.message.handlers) == 6
