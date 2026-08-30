"""The analyzer contract.

Everything downstream depends on this protocol rather than on a concrete
implementation, which is what lets the bot swap Claude for the rule-based
fallback at runtime and for a spy in tests.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from ..models import Analysis

__all__ = ["Analyzer"]


@runtime_checkable
class Analyzer(Protocol):
    async def analyze(
        self, text: str, history: Sequence[str] = ()
    ) -> Analysis:
        """Turn a free-form description into a structured reading.

        ``history`` carries the user's recent entries, oldest first, so an
        implementation can notice repetition. Implementations must not raise on
        ordinary provider failure — they either degrade or let the caller's
        fallback handle it, and the caller decides which.
        """
        ...
