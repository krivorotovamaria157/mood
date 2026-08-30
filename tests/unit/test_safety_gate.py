"""Unit tests for the safety gate and the crisis short-circuit."""

from __future__ import annotations

import pytest

from moodbot.models import Analysis, RiskLevel, Urgency
from moodbot.safety import CrisisCategory
from moodbot.safety_texts import DISCLAIMER, crisis_analysis
from moodbot.service import ReflectionService, SafetyGate


# --- crisis_analysis ------------------------------------------------------


@pytest.mark.parametrize("category", list(CrisisCategory))
def test_every_category_produces_a_crisis_analysis(category):
    analysis = crisis_analysis(category)

    assert analysis.risk_level is RiskLevel.CRISIS
    assert analysis.urgency is Urgency.NOW
    assert analysis.needs_professional_help is True
    assert analysis.source == "safety"
    assert analysis.recommendations, "a crisis reply must offer concrete steps"


@pytest.mark.parametrize("category", list(CrisisCategory))
def test_crisis_reply_points_at_emergency_services(category):
    analysis = crisis_analysis(category)
    text = analysis.summary + " ".join(
        r.action + r.rationale for r in analysis.recommendations
    )
    assert "112" in text


def test_medical_crisis_mentions_an_ambulance():
    analysis = crisis_analysis(CrisisCategory.MEDICAL)
    joined = analysis.summary + " ".join(r.action for r in analysis.recommendations)
    assert "103" in joined or "скорую" in joined.lower()


def test_disclaimer_states_the_bot_does_not_diagnose():
    lowered = DISCLAIMER.lower()
    assert "не" in lowered and "диагноз" in lowered


# --- SafetyGate -----------------------------------------------------------


def test_gate_returns_analysis_for_crisis_text():
    assert SafetyGate().screen("я больше не хочу жить") is not None


def test_gate_returns_none_for_ordinary_distress():
    assert SafetyGate().screen("грустно и устала, поругалась с мамой") is None


# --- short-circuit --------------------------------------------------------


class SpyAnalyzer:
    """Records whether it was consulted at all."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, text: str, history=()) -> Analysis:
        self.calls.append(text)
        return Analysis.from_payload(
            {"summary": "обычный разбор", "risk_level": "low", "urgency": "monitor"},
            source="spy",
        )


async def test_crisis_text_never_reaches_the_analyzer():
    """The guarantee this whole layer exists for."""
    analyzer = SpyAnalyzer()
    service = ReflectionService(analyzer=analyzer, gate=SafetyGate())

    analysis = await service.analyze("я хочу умереть")

    assert analyzer.calls == [], "the model must not be consulted on crisis text"
    assert analysis.risk_level is RiskLevel.CRISIS
    assert analysis.source == "safety"


async def test_ordinary_text_does_reach_the_analyzer():
    analyzer = SpyAnalyzer()
    service = ReflectionService(analyzer=analyzer, gate=SafetyGate())

    analysis = await service.analyze("тревожно перед собеседованием")

    assert analyzer.calls == ["тревожно перед собеседованием"]
    assert analysis.source == "spy"


async def test_gate_runs_before_the_analyzer_even_when_it_would_raise():
    """A broken analyzer must not stop a crisis reply from being produced."""

    class ExplodingAnalyzer:
        async def analyze(self, text: str, history=()) -> Analysis:
            raise RuntimeError("provider down")

    service = ReflectionService(analyzer=ExplodingAnalyzer(), gate=SafetyGate())

    analysis = await service.analyze("думаю покончить с собой")

    assert analysis.risk_level is RiskLevel.CRISIS
