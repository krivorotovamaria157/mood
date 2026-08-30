"""Unit tests for rendering an Analysis into Telegram messages."""

from __future__ import annotations

import pytest

from moodbot.bot.formatting import TELEGRAM_LIMIT, render_analysis, split_message
from moodbot.models import (
    Analysis,
    Observation,
    Recommendation,
    RiskLevel,
    Urgency,
)
from moodbot.safety_texts import DISCLAIMER


def _analysis(**overrides) -> Analysis:
    defaults = dict(
        summary="Похоже на тревогу перед событием.",
        risk_level=RiskLevel.LOW,
        urgency=Urgency.MONITOR,
        observations=(Observation(statement="Тревога привязана к событию", evidence="перед встречей"),),
        recommendations=(Recommendation(action="Выпиши, что пугает", rationale="конкретика проверяема"),),
        needs_professional_help=False,
        source="claude",
    )
    defaults.update(overrides)
    return Analysis(**defaults)


# --- content --------------------------------------------------------------


def test_renders_the_summary():
    text = "\n".join(render_analysis(_analysis()))
    assert "Похоже на тревогу перед событием." in text


def test_renders_observations_and_recommendations():
    text = "\n".join(render_analysis(_analysis()))
    assert "Тревога привязана к событию" in text
    assert "Выпиши, что пугает" in text


def test_renders_the_evidence_behind_an_observation():
    text = "\n".join(render_analysis(_analysis()))
    assert "перед встречей" in text


def test_every_analysis_carries_the_disclaimer():
    text = "\n".join(render_analysis(_analysis()))
    assert DISCLAIMER in text


def test_professional_help_flag_produces_a_visible_note():
    text = "\n".join(render_analysis(_analysis(needs_professional_help=True)))
    assert "специалист" in text.lower()


def test_fallback_source_is_disclosed_to_the_user():
    """If the model was unavailable, the user should know the reply is simpler."""
    text = "\n".join(render_analysis(_analysis(source="fallback")))
    assert "упрощённ" in text.lower() or "правил" in text.lower()


def test_claude_source_adds_no_such_note():
    text = "\n".join(render_analysis(_analysis(source="claude")))
    assert "упрощённ" not in text.lower()


def test_crisis_analysis_omits_the_ordinary_framing():
    """A crisis reply must not be dressed up as a routine reflection."""
    crisis = _analysis(
        risk_level=RiskLevel.CRISIS,
        urgency=Urgency.NOW,
        observations=(),
        source="safety",
    )
    text = "\n".join(render_analysis(crisis))

    assert "Наблюдения" not in text


@pytest.mark.parametrize("risk", list(RiskLevel))
def test_every_risk_level_renders(risk):
    text = "\n".join(render_analysis(_analysis(risk_level=risk)))
    assert text.strip()


def test_empty_observations_and_recommendations_do_not_leave_empty_headings():
    text = "\n".join(render_analysis(_analysis(observations=(), recommendations=())))
    assert "Наблюдения" not in text
    assert "Что можно сделать" not in text


# --- escaping -------------------------------------------------------------


def test_html_special_characters_are_escaped():
    text = "\n".join(render_analysis(_analysis(summary="Тревога <b>сильная</b> & резкая")))
    assert "&lt;b&gt;" in text
    assert "&amp;" in text
    assert "<b>сильная</b>" not in text


def test_structural_markup_survives_escaping():
    text = "\n".join(render_analysis(_analysis()))
    assert "<b>" in text, "the renderer's own bold tags must remain"


# --- splitting ------------------------------------------------------------


def test_short_message_is_one_chunk():
    assert len(split_message("короткий текст")) == 1


def test_long_message_is_split_under_the_limit():
    chunks = split_message("строка\n" * 3000)
    assert len(chunks) > 1
    assert all(len(chunk) <= TELEGRAM_LIMIT for chunk in chunks)


def test_splitting_preserves_all_content():
    original = "\n".join(f"строка {i}" for i in range(2000))
    assert "".join(split_message(original)).replace("\n", "") == original.replace("\n", "")


def test_split_prefers_line_boundaries():
    chunks = split_message("\n".join("x" * 100 for _ in range(200)))
    assert not any(chunk.startswith("x" * 100 + "x") for chunk in chunks[1:])


def test_a_single_unbreakable_line_is_still_split():
    chunks = split_message("y" * (TELEGRAM_LIMIT * 2 + 10))
    assert len(chunks) == 3
    assert all(len(chunk) <= TELEGRAM_LIMIT for chunk in chunks)


def test_empty_input_yields_no_chunks():
    assert split_message("") == []
    assert split_message("   ") == []


def test_rendered_analysis_chunks_respect_the_limit():
    huge = _analysis(
        summary="слово " * 2000,
        recommendations=tuple(
            Recommendation(action="шаг " * 200, rationale="причина " * 200)
            for _ in range(6)
        ),
    )
    for chunk in render_analysis(huge):
        assert len(chunk) <= TELEGRAM_LIMIT
