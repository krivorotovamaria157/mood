"""Unit tests for deterministic crisis detection.

Two failure modes matter here and they pull in opposite directions: missing a
real crisis signal, and firing on an idiom. Both are tested explicitly.
"""

from __future__ import annotations

import pytest

from moodbot.safety import CrisisCategory, detect_crisis, normalize


# --- normalization --------------------------------------------------------


def test_normalize_lowercases_and_collapses_whitespace():
    assert normalize("  НЕ   ХОЧУ\nЖИТЬ ") == "не хочу жить"


def test_normalize_folds_yo_to_ye():
    assert normalize("причинён") == "причинен"


def test_normalize_maps_latin_homoglyphs_to_cyrillic():
    """Mixed-script text must not slip past the patterns."""
    assert normalize("не хочу жutь".replace("u", "и")) == "не хочу жить"
    assert normalize("хочу yмepeть") == "хочу умереть"


def test_normalize_strips_punctuation_between_words():
    assert normalize("не... хочу, жить!") == "не хочу жить"


# --- true positives -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "я больше не хочу жить",
        "не хочется жить совсем",
        "хочу умереть",
        "думаю покончить с собой",
        "мысли о самоубийстве не уходят",
        "хочу свести счёты с жизнью",
        "я решил уйти из жизни",
        "не вижу смысла жить дальше",
        "I want to kill myself",
        "thinking about ending my life",
        "there is no reason to live anymore",
    ],
)
def test_detects_suicidal_statements(text):
    signal = detect_crisis(text)
    assert signal is not None, text
    assert signal.category is CrisisCategory.SUICIDE


@pytest.mark.parametrize(
    "text",
    [
        "я снова режу себя",
        "хочу причинить себе вред",
        "это селфхарм и я знаю",
        "I cut myself again last night",
    ],
)
def test_detects_self_harm(text):
    signal = detect_crisis(text)
    assert signal is not None, text
    assert signal.category is CrisisCategory.SELF_HARM


@pytest.mark.parametrize(
    "text",
    [
        "меня бьют дома",
        "он угрожает убить меня",
        "я боюсь за свою жизнь",
        "he hits me every week",
    ],
)
def test_detects_violence(text):
    signal = detect_crisis(text)
    assert signal is not None, text
    assert signal.category is CrisisCategory.VIOLENCE


@pytest.mark.parametrize(
    "text",
    [
        "я не могу дышать уже час",
        "сильная боль в груди",
        "выпила таблетки все сразу",
        "I think this is an overdose",
    ],
)
def test_detects_medical_emergency(text):
    signal = detect_crisis(text)
    assert signal is not None, text
    assert signal.category is CrisisCategory.MEDICAL


def test_signal_reports_the_phrase_that_matched():
    signal = detect_crisis("сегодня тяжело, хочу умереть")
    assert signal is not None
    assert "умереть" in signal.matched


# --- false positives ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "умираю от смеха, коллега пошутил",
        "устала до смерти, но день был хороший",
        "эта работа меня убивает, надо в отпуск",
        "хочу умереть от стыда, так неловко вышло",
        "убила весь день на отчёт",
        "dead tired after the gym",
        "this deadline is killing me",
        "я убил время в очереди",
        "мне грустно и тяжело на душе",
        "тревога, ком в горле, плохо сплю",
        "поругалась с мамой, очень обидно",
        "у меня болит голова второй день",
    ],
)
def test_does_not_fire_on_idioms_or_ordinary_distress(text):
    assert detect_crisis(text) is None, text


def test_empty_and_none_input_are_safe():
    assert detect_crisis("") is None
    assert detect_crisis("   ") is None
    assert detect_crisis(None) is None


# --- precedence -----------------------------------------------------------


def test_suicide_wins_over_other_categories_when_both_present():
    signal = detect_crisis("меня бьют дома и я больше не хочу жить")
    assert signal is not None
    assert signal.category is CrisisCategory.SUICIDE
