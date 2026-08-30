"""Rule-based analyzer — the answer when Claude is not available.

This is deliberately modest. It does not pretend to understand the message; it
names the emotion family it recognised, notes how intense and how long-running
the description sounds, and offers a few steps that are safe regardless. That is
worth more than an apology, and it keeps the bot useful with no API key at all.

It can never return a CRISIS reading: declaring a crisis is the exclusive job of
the deterministic gate in :mod:`moodbot.safety`.
"""

from __future__ import annotations

import re
from typing import Sequence

from ..models import (
    Analysis,
    Observation,
    Recommendation,
    RiskLevel,
    Urgency,
)
from ..safety import normalize

__all__ = ["RuleBasedAnalyzer"]

_MAX_CHARS = 4000

# Emotion families and the stems that hint at them. Stems, not whole words, so
# that inflected Russian forms match without a morphology library.
_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Stems are cut before the consonant alternation (трево|га / трево|жно), which
    # is where a naive prefix like "тревог" silently stops matching.
    ("тревога", ("трево", "беспоко", "волну", "паник", "anxious", "anxiety", "worried")),
    ("гнев", ("злюсь", "злость", "злит", "злой", "злая", "разозл", "гнев", "раздраж", "бесит", "ярост", "angry", "furious")),
    ("грусть", ("грус", "печал", "тоск", "уныл", "пусто", "плак", "sad", "lonely")),
    ("страх", ("страш", "боюсь", "боязн", "испуг", "afraid", "scared", "fear")),
    ("стыд", ("стыд", "неловк", "ashamed", "guilty")),
    ("усталость", ("устал", "вымот", "истощ", "нет сил", "выгор", "exhausted", "burnout", "tired")),
    ("радость", ("радост", "счаст", "здорово", "получилось", "happy", "glad", "joy")),
    ("спокойствие", ("споко", "расслаб", "calm", "relaxed")),
)

_INTENSITY = (
    "невыносим", "ужасн", "кошмар", "нестерпим", "не могу это терпеть",
    "не выдерж", "на пределе", "сильно", "очень сильно", "безнадеж",
    "unbearable", "terrible", "hopeless", "overwhelming",
)

_DURATION = (
    "каждый день", "постоянно", "всё время", "все время", "неделю", "недел",
    "месяц", "полгода", "год", "давно", "всегда", "не проходит",
    "every day", "for months", "for weeks", "constantly",
)

_POSITIVE_FAMILIES = {"радость", "спокойствие"}

_GENERIC_STEPS: tuple[tuple[str, str], ...] = (
    (
        "Запиши, что происходило за час до этого состояния",
        "триггер обычно виден только задним числом, и записи его проявляют",
    ),
    (
        "Отметь, где это чувствуется в теле",
        "телесный сигнал часто точнее слов и помогает заметить повтор",
    ),
    (
        "Спроси себя, чего тебе сейчас не хватает: сна, еды, тишины или человека рядом",
        "часть состояний снимается базовыми вещами, а не разбором",
    ),
)

_HIGH_RISK_STEP = (
    "Подумай о разговоре со специалистом",
    "то, что длится долго и ощущается тяжело, редко проходит само",
)


class RuleBasedAnalyzer:
    """Deterministic analyzer. No network, no model, no randomness."""

    async def analyze(
        self, text: str, history: Sequence[str] = ()
    ) -> Analysis:
        normalized = normalize(text)[:_MAX_CHARS]

        families = self._families(normalized)
        intensity = self._count(normalized, _INTENSITY)
        duration = self._count(normalized, _DURATION)
        repeats = self._repeated_families(families, history)

        risk = self._risk(families, intensity, duration, repeats)

        return Analysis(
            summary=self._summary(families, risk),
            risk_level=risk,
            urgency=self._urgency(risk),
            observations=self._observations(families, intensity, duration, repeats),
            recommendations=self._recommendations(risk),
            needs_professional_help=risk >= RiskLevel.HIGH,
            source="fallback",
        )

    # -- pieces ------------------------------------------------------------

    @staticmethod
    def _families(normalized: str) -> list[str]:
        return [
            name
            for name, stems in _FAMILIES
            if any(stem in normalized for stem in stems)
        ]

    @staticmethod
    def _count(normalized: str, markers: Sequence[str]) -> int:
        return sum(1 for marker in markers if marker in normalized)

    def _repeated_families(
        self, families: Sequence[str], history: Sequence[str]
    ) -> list[str]:
        """Families that also show up in the user's recent entries."""
        if not families or not history:
            return []

        previous: set[str] = set()
        for entry in history:
            previous.update(self._families(normalize(entry)))

        return [name for name in families if name in previous]

    @staticmethod
    def _risk(
        families: Sequence[str],
        intensity: int,
        duration: int,
        repeats: Sequence[str],
    ) -> RiskLevel:
        negative = [f for f in families if f not in _POSITIVE_FAMILIES]
        if not negative:
            return RiskLevel.NONE if families else RiskLevel.LOW

        score = 1 + min(intensity, 2) + min(duration, 2) + (1 if repeats else 0)
        # Capped below CRISIS on purpose — see the module docstring.
        return RiskLevel(min(score, RiskLevel.HIGH))

    @staticmethod
    def _urgency(risk: RiskLevel) -> Urgency:
        if risk >= RiskLevel.HIGH:
            return Urgency.NOW
        if risk >= RiskLevel.MODERATE:
            return Urgency.SOON
        return Urgency.MONITOR

    @staticmethod
    def _summary(families: Sequence[str], risk: RiskLevel) -> str:
        if not families:
            return (
                "Не удалось уверенно определить эмоцию по тексту. "
                "Опиши, что ты чувствуешь и что этому предшествовало — "
                "так разбор будет точнее."
            )

        listed = ", ".join(families)
        if risk >= RiskLevel.HIGH:
            tail = "Судя по описанию, это длится и ощущается тяжело."
        elif risk >= RiskLevel.MODERATE:
            tail = "Состояние заметное, но не выглядит острым."
        else:
            tail = "Ничего тревожного в описании не видно."

        return f"В тексте прослеживается: {listed}. {tail}"

    @staticmethod
    def _observations(
        families: Sequence[str],
        intensity: int,
        duration: int,
        repeats: Sequence[str],
    ) -> tuple[Observation, ...]:
        found: list[Observation] = []

        if families:
            found.append(
                Observation(statement=f"Названные состояния: {', '.join(families)}")
            )
        if intensity:
            found.append(
                Observation(statement="В тексте есть маркеры высокой интенсивности")
            )
        if duration:
            found.append(
                Observation(statement="Описание указывает на длительность, а не разовый эпизод")
            )
        if repeats:
            found.append(
                Observation(
                    statement=(
                        f"Это повторяется: {', '.join(repeats)} — уже встречалось "
                        "в прошлых записях"
                    )
                )
            )
        if not found:
            found.append(
                Observation(statement="Описание короткое, деталей для разбора мало")
            )

        return tuple(found)

    @staticmethod
    def _recommendations(risk: RiskLevel) -> tuple[Recommendation, ...]:
        steps = list(_GENERIC_STEPS)
        if risk >= RiskLevel.HIGH:
            steps.insert(0, _HIGH_RISK_STEP)

        return tuple(
            Recommendation(action=action, rationale=rationale)
            for action, rationale in steps[: Analysis.MAX_ITEMS]
        )
