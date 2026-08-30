"""Domain model for the bot.

Nothing here touches I/O, the network, or a framework — everything is a value
object plus the parsing that turns a model's structured answer into one. That is
what lets the whole layer be unit-tested without a single fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any, Mapping, Sequence

__all__ = [
    "Analysis",
    "AnalysisParseError",
    "Entry",
    "Observation",
    "Recommendation",
    "RiskLevel",
    "Urgency",
]

DEFAULT_MAX_TEXT_LENGTH = 4000


class AnalysisParseError(ValueError):
    """The model's structured answer could not be read as an analysis."""


class RiskLevel(IntEnum):
    """How much attention the described state seems to warrant.

    Ordered, so callers can compare (`risk >= RiskLevel.HIGH`) rather than
    enumerate. This is deliberately *not* a clinical severity scale — it drives
    the tone of the reply and whether professional contact is suggested.
    """

    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    CRISIS = 4

    @classmethod
    def parse(cls, raw: Any) -> "RiskLevel":
        """Read a level from model output.

        An unrecognised value returns MODERATE, never NONE: failing to parse a
        risk assessment must not be indistinguishable from assessing no risk.
        """
        if not isinstance(raw, str):
            return cls.MODERATE
        try:
            return cls[raw.strip().upper()]
        except KeyError:
            return cls.MODERATE

    @property
    def requires_immediate_action(self) -> bool:
        return self >= RiskLevel.HIGH


class Urgency(StrEnum):
    """When the suggested steps are worth taking."""

    NOW = "now"
    SOON = "soon"
    MONITOR = "monitor"

    @classmethod
    def parse(cls, raw: Any) -> "Urgency":
        if isinstance(raw, str):
            try:
                return cls(raw.strip().lower())
            except ValueError:
                pass
        return cls.SOON


@dataclass(frozen=True, slots=True)
class Entry:
    """One thing a user told the bot."""

    user_id: int
    text: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_length: int = DEFAULT_MAX_TEXT_LENGTH

    def __post_init__(self) -> None:
        cleaned = (self.text or "").strip()
        if not cleaned:
            raise ValueError("Entry text is empty")
        object.__setattr__(self, "text", cleaned[: self.max_length])


@dataclass(frozen=True, slots=True)
class Observation:
    """Something the analysis noticed, with the wording it came from."""

    statement: str
    evidence: str = ""

    def __post_init__(self) -> None:
        cleaned = (self.statement or "").strip()
        if not cleaned:
            raise ValueError("Observation statement is empty")
        object.__setattr__(self, "statement", cleaned)
        object.__setattr__(self, "evidence", (self.evidence or "").strip())


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A concrete next step and why it follows from what was said."""

    action: str
    rationale: str = ""

    def __post_init__(self) -> None:
        cleaned = (self.action or "").strip()
        if not cleaned:
            raise ValueError("Recommendation action is empty")
        object.__setattr__(self, "action", cleaned)
        object.__setattr__(self, "rationale", (self.rationale or "").strip())


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "yes", "1", "да"}
    return bool(raw) if raw is not None else False


@dataclass(frozen=True, slots=True)
class Analysis:
    """The structured reading returned to the user.

    Built only through :meth:`from_payload`, so every path into it goes through
    the same validation — including the ones fed by a language model.
    """

    MAX_ITEMS = 6

    summary: str
    risk_level: RiskLevel
    urgency: Urgency
    observations: tuple[Observation, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    needs_professional_help: bool = False
    source: str = "claude"

    @classmethod
    def from_payload(cls, payload: Any, *, source: str = "claude") -> "Analysis":
        if not isinstance(payload, Mapping):
            raise AnalysisParseError(
                f"expected a mapping, got {type(payload).__name__}"
            )

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise AnalysisParseError("summary is missing or empty")

        risk = RiskLevel.parse(payload.get("risk_level"))
        needs_help = _coerce_bool(payload.get("needs_professional_help"))

        # A crisis reading always points at a human, regardless of what the
        # model put in the flag.
        if risk is RiskLevel.CRISIS:
            needs_help = True

        return cls(
            summary=summary,
            risk_level=risk,
            urgency=Urgency.parse(payload.get("urgency")),
            observations=cls._build(payload.get("observations"), _observation),
            recommendations=cls._build(payload.get("recommendations"), _recommendation),
            needs_professional_help=needs_help,
            source=source,
        )

    @staticmethod
    def _build(raw: Any, factory) -> tuple:
        """Build a tuple of value objects, dropping items that do not parse.

        One malformed entry in a list is not a reason to discard an otherwise
        usable analysis — the user still gets the parts that were readable.
        """
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return ()

        built = []
        for item in raw:
            if len(built) >= Analysis.MAX_ITEMS:
                break
            if not isinstance(item, Mapping):
                continue
            try:
                built.append(factory(item))
            except ValueError:
                continue
        return tuple(built)


def _observation(item: Mapping[str, Any]) -> Observation:
    return Observation(
        statement=str(item.get("statement") or ""),
        evidence=str(item.get("evidence") or ""),
    )


def _recommendation(item: Mapping[str, Any]) -> Recommendation:
    return Recommendation(
        action=str(item.get("action") or ""),
        rationale=str(item.get("rationale") or ""),
    )
