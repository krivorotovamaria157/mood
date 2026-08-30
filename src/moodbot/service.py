"""The analysis pipeline: screen for crisis, then analyse.

Orchestration lives here rather than in the Telegram handlers so that the order
of operations — and in particular the guarantee that screening happens first —
is testable without a bot, a network, or a framework.
"""

from __future__ import annotations

import logging
from typing import Sequence

from .analyzer.base import Analyzer
from .models import Analysis
from .safety import detect_crisis
from .safety_texts import crisis_analysis

__all__ = ["ReflectionService", "SafetyGate"]

logger = logging.getLogger(__name__)


class SafetyGate:
    """Turns a crisis signal into the reply that replaces normal analysis."""

    def screen(self, text: str) -> Analysis | None:
        signal = detect_crisis(text)
        if signal is None:
            return None

        # Category only — the matched phrase is the user's own words about a
        # crisis and does not belong in a log.
        logger.warning("crisis signal detected: %s", signal.category.value)
        return crisis_analysis(signal.category)


class ReflectionService:
    """Screen first, analyse second. Never the other way round."""

    def __init__(self, analyzer: Analyzer, gate: SafetyGate | None = None) -> None:
        self._analyzer = analyzer
        self._gate = gate or SafetyGate()

    async def analyze(self, text: str, history: Sequence[str] = ()) -> Analysis:
        crisis = self._gate.screen(text)
        if crisis is not None:
            return crisis

        return await self._analyzer.analyze(text, history)
