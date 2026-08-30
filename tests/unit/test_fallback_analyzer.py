"""Unit tests for the rule-based analyzer used when Claude is unavailable."""

from __future__ import annotations

import pytest

from moodbot.analyzer.base import Analyzer
from moodbot.analyzer.fallback import RuleBasedAnalyzer
from moodbot.models import RiskLevel, Urgency


@pytest.fixture
def analyzer() -> RuleBasedAnalyzer:
    return RuleBasedAnalyzer()


def test_satisfies_the_analyzer_protocol(analyzer):
    assert isinstance(analyzer, Analyzer)


async def test_always_returns_a_usable_analysis(analyzer):
    analysis = await analyzer.analyze("не знаю даже что сказать")

    assert analysis.summary
    assert analysis.source == "fallback"
    assert analysis.recommendations, "the user must never get an empty reply"


async def test_marks_its_own_source_so_the_reply_can_be_honest(analyzer):
    analysis = await analyzer.analyze("устал")
    assert analysis.source == "fallback"


# --- emotion detection ----------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_word",
    [
        ("мне очень тревожно перед завтра", "тревог"),
        ("злюсь на коллегу весь день", "гнев"),
        ("грустно и пусто", "грусть"),
        ("страшно идти к врачу", "страх"),
        ("radostno, всё получилось", "радость"),
    ],
)
async def test_names_the_emotion_family_it_recognised(analyzer, text, expected_word):
    analysis = await analyzer.analyze(text)
    haystack = (
        analysis.summary + " ".join(o.statement for o in analysis.observations)
    ).lower()
    assert expected_word in haystack, haystack


async def test_unrecognised_emotion_still_produces_an_observation(analyzer):
    analysis = await analyzer.analyze("сегодня был вторник")
    assert analysis.summary


# --- intensity ------------------------------------------------------------


async def test_intensity_markers_raise_the_risk_level(analyzer):
    mild = await analyzer.analyze("немного тревожно")
    strong = await analyzer.analyze("невыносимо тревожно, не могу это терпеть")

    assert strong.risk_level > mild.risk_level


async def test_duration_markers_raise_the_risk_level(analyzer):
    short = await analyzer.analyze("сегодня тревожно")
    long = await analyzer.analyze("тревожно каждый день уже третий месяц")

    assert long.risk_level > short.risk_level


async def test_risk_never_reaches_crisis_without_the_safety_layer(analyzer):
    """Only the deterministic gate may declare a crisis."""
    analysis = await analyzer.analyze(
        "невыносимо, каждый день, месяцами, совершенно безнадёжно и ужасно"
    )
    assert analysis.risk_level < RiskLevel.CRISIS


async def test_high_risk_suggests_professional_help(analyzer):
    analysis = await analyzer.analyze(
        "тревожно каждый день уже полгода, невыносимо, ничего не помогает"
    )
    if analysis.risk_level >= RiskLevel.HIGH:
        assert analysis.needs_professional_help is True


# --- urgency --------------------------------------------------------------


async def test_low_risk_is_only_worth_monitoring(analyzer):
    analysis = await analyzer.analyze("немного скучно сегодня")
    assert analysis.urgency is Urgency.MONITOR


# --- history --------------------------------------------------------------


async def test_repeated_theme_in_history_is_noticed(analyzer):
    history = ["опять тревожно на работе", "тревожно, не сплю"]
    analysis = await analyzer.analyze("снова тревожно", history=history)

    joined = " ".join(o.statement for o in analysis.observations).lower()
    assert "повтор" in joined or "снова" in joined or "раз" in joined


async def test_empty_history_is_fine(analyzer):
    analysis = await analyzer.analyze("тревожно", history=[])
    assert analysis.summary


# --- robustness -----------------------------------------------------------


async def test_blank_text_does_not_crash(analyzer):
    analysis = await analyzer.analyze("   ")
    assert analysis.summary


async def test_very_long_text_does_not_crash(analyzer):
    analysis = await analyzer.analyze("тревожно " * 5000)
    assert analysis.summary
    assert len(analysis.recommendations) <= 6
