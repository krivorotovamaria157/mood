"""Mock-layer tests for every way the Claude call can fail.

This is the layer that earns its keep: none of these paths are reachable from a
unit test, and all of them are reachable in production.
"""

from __future__ import annotations

import asyncio
import logging

from tests.fakes import (
    FakeAnthropicClient,
    FakeMessages,
    FakeResponse,
    FakeTextBlock,
    VALID_PAYLOAD,
    client_raising,
    client_returning,
)

from moodbot.analyzer.claude import ClaudeAnalyzer
from moodbot.analyzer.fallback import RuleBasedAnalyzer
from moodbot.models import RiskLevel


def _analyzer(client, **kwargs) -> ClaudeAnalyzer:
    kwargs.setdefault("fallback", RuleBasedAnalyzer())
    return ClaudeAnalyzer(client=client, model="claude-opus-5", **kwargs)


# --- transport failures ---------------------------------------------------


async def test_connection_error_degrades_to_the_fallback():
    analysis = await _analyzer(client_raising(ConnectionError("no route"))).analyze(
        "тревожно"
    )
    assert analysis.source == "fallback"


async def test_api_error_degrades_to_the_fallback():
    analysis = await _analyzer(client_raising(RuntimeError("500 server error"))).analyze(
        "тревожно"
    )
    assert analysis.source == "fallback"


async def test_timeout_degrades_to_the_fallback():
    client = FakeAnthropicClient(
        messages=FakeMessages(response=None, delay=0.5)
    )
    analysis = await _analyzer(client, timeout=0.01).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_cancellation_is_not_swallowed():
    """Shutdown must propagate, not be mistaken for a provider failure."""
    client = client_raising(asyncio.CancelledError())

    try:
        await _analyzer(client).analyze("тревожно")
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("CancelledError should propagate")


# --- bad responses --------------------------------------------------------


async def test_refusal_degrades_to_the_fallback():
    client = FakeAnthropicClient(
        messages=FakeMessages(
            response=FakeResponse(content=[], stop_reason="refusal")
        )
    )
    analysis = await _analyzer(client).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_response_without_a_text_block_degrades():
    client = FakeAnthropicClient(
        messages=FakeMessages(response=FakeResponse(content=[]))
    )
    analysis = await _analyzer(client).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_non_json_text_degrades():
    client = FakeAnthropicClient(
        messages=FakeMessages(
            response=FakeResponse(content=[FakeTextBlock("это не json")])
        )
    )
    analysis = await _analyzer(client).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_json_that_is_not_an_object_degrades():
    client = FakeAnthropicClient(
        messages=FakeMessages(response=FakeResponse(content=[FakeTextBlock("[1, 2, 3]")]))
    )
    analysis = await _analyzer(client).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_json_missing_summary_degrades():
    payload = dict(VALID_PAYLOAD)
    del payload["summary"]
    analysis = await _analyzer(client_returning(payload)).analyze("тревожно")

    assert analysis.source == "fallback"


async def test_partially_malformed_lists_still_yield_a_claude_analysis():
    """A bad recommendation is recoverable; it must not trigger a full fallback."""
    payload = dict(VALID_PAYLOAD, recommendations=[{"action": ""}, "мусор"])
    analysis = await _analyzer(client_returning(payload)).analyze("тревожно")

    assert analysis.source == "claude"
    assert analysis.recommendations == ()


async def test_unknown_risk_value_does_not_read_as_no_risk():
    payload = dict(VALID_PAYLOAD, risk_level="совершенно спокойно")
    analysis = await _analyzer(client_returning(payload)).analyze("тревожно")

    assert analysis.risk_level is RiskLevel.MODERATE


# --- fallback contract ----------------------------------------------------


async def test_without_a_fallback_a_failure_still_returns_something():
    """The bot must never answer a person with nothing."""
    analyzer = ClaudeAnalyzer(
        client=client_raising(ConnectionError()), model="claude-opus-5", fallback=None
    )
    analysis = await analyzer.analyze("тревожно")

    assert analysis.summary
    assert analysis.source == "fallback"


# --- logging hygiene ------------------------------------------------------


async def test_failure_logs_do_not_contain_the_user_text(caplog):
    secret = "мой очень личный текст про начальника"
    with caplog.at_level(logging.DEBUG):
        await _analyzer(client_raising(ConnectionError("boom"))).analyze(secret)

    assert secret not in caplog.text


async def test_failure_is_logged_at_warning_with_the_error_type(caplog):
    with caplog.at_level(logging.WARNING):
        await _analyzer(client_raising(ConnectionError("boom"))).analyze("тревожно")

    assert "ConnectionError" in caplog.text
