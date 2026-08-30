"""Unit tests for the domain model and structured-response parsing."""

from __future__ import annotations

import pytest

from moodbot.models import (
    Analysis,
    AnalysisParseError,
    Entry,
    Observation,
    Recommendation,
    RiskLevel,
    Urgency,
)


# --- RiskLevel ------------------------------------------------------------


def test_risk_levels_are_ordered_from_calm_to_crisis():
    assert RiskLevel.NONE < RiskLevel.LOW < RiskLevel.MODERATE < RiskLevel.HIGH
    assert RiskLevel.HIGH < RiskLevel.CRISIS


def test_risk_level_parses_from_model_output():
    assert RiskLevel.parse("moderate") is RiskLevel.MODERATE
    assert RiskLevel.parse("HIGH") is RiskLevel.HIGH
    assert RiskLevel.parse(" low ") is RiskLevel.LOW


def test_unknown_risk_level_falls_back_to_moderate_not_none():
    """An unparseable risk must never silently read as 'nothing to see here'."""
    assert RiskLevel.parse("banana") is RiskLevel.MODERATE
    assert RiskLevel.parse("") is RiskLevel.MODERATE
    assert RiskLevel.parse(None) is RiskLevel.MODERATE


def test_crisis_level_requires_immediate_action():
    assert RiskLevel.CRISIS.requires_immediate_action is True
    assert RiskLevel.HIGH.requires_immediate_action is True
    assert RiskLevel.MODERATE.requires_immediate_action is False


# --- Urgency --------------------------------------------------------------


def test_urgency_parses_and_defaults_to_soon():
    assert Urgency.parse("now") is Urgency.NOW
    assert Urgency.parse("monitor") is Urgency.MONITOR
    assert Urgency.parse("nonsense") is Urgency.SOON


# --- Entry ----------------------------------------------------------------


def test_entry_rejects_blank_text():
    with pytest.raises(ValueError, match="empty"):
        Entry(user_id=1, text="   ")


def test_entry_strips_surrounding_whitespace():
    assert Entry(user_id=1, text="  устала  ").text == "устала"


def test_entry_truncates_text_beyond_limit():
    entry = Entry(user_id=1, text="a" * 5000, max_length=100)
    assert len(entry.text) == 100


# --- Observation / Recommendation ----------------------------------------


def test_observation_requires_non_empty_statement():
    with pytest.raises(ValueError):
        Observation(statement="  ")


def test_recommendation_requires_non_empty_action():
    with pytest.raises(ValueError):
        Recommendation(action="", rationale="потому что")


# --- Analysis.from_payload ------------------------------------------------


def _payload(**overrides) -> dict:
    base = {
        "summary": "Похоже на усталость и перегрузку.",
        "risk_level": "low",
        "urgency": "monitor",
        "observations": [
            {"statement": "Тяжесть в груди упоминается второй раз", "evidence": "тяжело дышать"},
        ],
        "recommendations": [
            {"action": "Лечь спать раньше", "rationale": "сон третью ночь короткий"},
        ],
        "needs_professional_help": False,
    }
    base.update(overrides)
    return base


def test_from_payload_builds_full_analysis():
    analysis = Analysis.from_payload(_payload())

    assert analysis.summary.startswith("Похоже")
    assert analysis.risk_level is RiskLevel.LOW
    assert analysis.urgency is Urgency.MONITOR
    assert len(analysis.observations) == 1
    assert analysis.observations[0].evidence == "тяжело дышать"
    assert analysis.recommendations[0].action == "Лечь спать раньше"
    assert analysis.needs_professional_help is False


def test_from_payload_rejects_non_mapping():
    with pytest.raises(AnalysisParseError):
        Analysis.from_payload(["not", "a", "dict"])


def test_from_payload_requires_summary():
    with pytest.raises(AnalysisParseError, match="summary"):
        Analysis.from_payload(_payload(summary="   "))


def test_from_payload_tolerates_missing_optional_lists():
    payload = _payload()
    del payload["observations"]
    del payload["recommendations"]

    analysis = Analysis.from_payload(payload)

    assert analysis.observations == ()
    assert analysis.recommendations == ()


def test_from_payload_skips_malformed_list_items_without_failing():
    """One bad observation should not throw away a usable analysis."""
    analysis = Analysis.from_payload(
        _payload(
            observations=[
                {"statement": "хорошее наблюдение"},
                {"statement": ""},
                "не словарь",
                None,
            ]
        )
    )

    assert len(analysis.observations) == 1
    assert analysis.observations[0].statement == "хорошее наблюдение"


def test_from_payload_caps_list_lengths():
    analysis = Analysis.from_payload(
        _payload(
            recommendations=[
                {"action": f"шаг {i}", "rationale": "r"} for i in range(50)
            ]
        )
    )

    assert len(analysis.recommendations) <= Analysis.MAX_ITEMS


def test_needs_professional_help_coerces_truthy_strings():
    assert Analysis.from_payload(_payload(needs_professional_help="true")).needs_professional_help
    assert Analysis.from_payload(_payload(needs_professional_help=True)).needs_professional_help
    assert not Analysis.from_payload(_payload(needs_professional_help=None)).needs_professional_help


def test_crisis_risk_forces_professional_help_flag():
    """A crisis-level reading always advises professional contact, whatever the model said."""
    analysis = Analysis.from_payload(
        _payload(risk_level="crisis", needs_professional_help=False)
    )

    assert analysis.needs_professional_help is True


def test_analysis_records_which_engine_produced_it():
    analysis = Analysis.from_payload(_payload(), source="fallback")
    assert analysis.source == "fallback"
