"""Mock-layer tests: the Claude analyzer against a fake SDK client."""

from __future__ import annotations

import json

from tests.fakes import VALID_PAYLOAD, client_returning

from moodbot.analyzer.base import Analyzer
from moodbot.analyzer.claude import ClaudeAnalyzer
from moodbot.models import RiskLevel, Urgency


def _analyzer(client) -> ClaudeAnalyzer:
    return ClaudeAnalyzer(client=client, model="claude-opus-5")


def test_satisfies_the_analyzer_protocol():
    assert isinstance(_analyzer(client_returning(VALID_PAYLOAD)), Analyzer)


async def test_parses_a_well_formed_response():
    analysis = await _analyzer(client_returning(VALID_PAYLOAD)).analyze("тревожно")

    assert analysis.summary.startswith("Похоже")
    assert analysis.risk_level is RiskLevel.LOW
    assert analysis.urgency is Urgency.MONITOR
    assert analysis.observations[0].evidence == "перед собеседованием"
    assert analysis.source == "claude"


async def test_sends_the_configured_model():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("тревожно")

    assert client.messages.calls[0]["model"] == "claude-opus-5"


async def test_requests_structured_output_with_a_schema():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("тревожно")

    fmt = client.messages.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert "summary" in fmt["schema"]["required"]


async def test_system_prompt_forbids_diagnosis():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("тревожно")

    system = client.messages.calls[0]["system"]
    text = system if isinstance(system, str) else json.dumps(system, ensure_ascii=False)
    assert "диагноз" in text.lower()


async def test_user_text_is_sent_as_the_user_turn():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("мне тревожно перед собеседованием")

    messages = client.messages.calls[0]["messages"]
    assert messages[-1]["role"] == "user"
    assert "собеседованием" in json.dumps(messages, ensure_ascii=False)


async def test_history_is_included_when_present():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("снова тревожно", history=["вчера тоже тревожно"])

    payload = json.dumps(client.messages.calls[0]["messages"], ensure_ascii=False)
    assert "вчера тоже тревожно" in payload


async def test_history_is_omitted_when_empty():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("тревожно", history=[])

    messages = client.messages.calls[0]["messages"]
    assert len(messages) == 1


async def test_adaptive_thinking_is_requested():
    client = client_returning(VALID_PAYLOAD)
    await _analyzer(client).analyze("тревожно")

    assert client.messages.calls[0]["thinking"]["type"] == "adaptive"


async def test_thinking_blocks_do_not_confuse_the_parser():
    """The JSON lives in the text block; thinking blocks come first."""
    analysis = await _analyzer(client_returning(VALID_PAYLOAD)).analyze("тревожно")
    assert analysis.source == "claude"


async def test_crisis_risk_from_the_model_forces_professional_help():
    payload = dict(VALID_PAYLOAD, risk_level="crisis", needs_professional_help=False)
    analysis = await _analyzer(client_returning(payload)).analyze("тяжело")

    assert analysis.risk_level is RiskLevel.CRISIS
    assert analysis.needs_professional_help is True
