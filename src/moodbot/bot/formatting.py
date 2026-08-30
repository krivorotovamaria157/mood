"""Rendering an :class:`Analysis` into Telegram messages.

Telegram's HTML parse mode is used rather than MarkdownV2: user-supplied words
are echoed back inside the reply, and `html.escape` is a far smaller correctness
surface than MarkdownV2's eighteen reserved characters.
"""

from __future__ import annotations

from html import escape

from ..models import Analysis, RiskLevel, Urgency
from ..safety_texts import DISCLAIMER

__all__ = ["TELEGRAM_LIMIT", "render_analysis", "split_message"]

# Telegram's hard cap is 4096 characters; leave room for the split marker.
TELEGRAM_LIMIT = 4000

_RISK_LABEL: dict[RiskLevel, str] = {
    RiskLevel.NONE: "🟢 Спокойный фон",
    RiskLevel.LOW: "🟢 Лёгкое напряжение",
    RiskLevel.MODERATE: "🟡 Заметное состояние",
    RiskLevel.HIGH: "🟠 Требует внимания",
    RiskLevel.CRISIS: "🔴 Нужна помощь прямо сейчас",
}

_URGENCY_LABEL: dict[Urgency, str] = {
    Urgency.NOW: "действовать стоит сейчас",
    Urgency.SOON: "стоит заняться в ближайшие дни",
    Urgency.MONITOR: "пока достаточно наблюдать",
}

_FALLBACK_NOTE = (
    "<i>Разбор упрощённый: модель сейчас недоступна, использованы правила.</i>"
)

_HELP_NOTE = (
    "❗ Похоже, стоит обсудить это со специалистом — психологом или врачом."
)


def render_analysis(analysis: Analysis) -> list[str]:
    """Render an analysis into one or more Telegram-ready HTML messages."""
    if analysis.risk_level is RiskLevel.CRISIS:
        return split_message(_render_crisis(analysis))
    return split_message(_render_regular(analysis))


def _render_crisis(analysis: Analysis) -> str:
    """A crisis reply is stripped of the usual sections — it is not a reflection."""
    parts = [
        f"<b>{escape(_RISK_LABEL[RiskLevel.CRISIS])}</b>",
        "",
        escape(analysis.summary),
    ]

    if analysis.recommendations:
        parts += ["", "<b>Что сделать прямо сейчас</b>"]
        for index, rec in enumerate(analysis.recommendations, start=1):
            line = f"{index}. {escape(rec.action)}"
            if rec.rationale:
                line += f" — <i>{escape(rec.rationale)}</i>"
            parts.append(line)

    parts += ["", f"<i>{escape(DISCLAIMER)}</i>"]
    return "\n".join(parts)


def _render_regular(analysis: Analysis) -> str:
    parts = [
        f"<b>{escape(_RISK_LABEL[analysis.risk_level])}</b> "
        f"— {escape(_URGENCY_LABEL[analysis.urgency])}",
        "",
        escape(analysis.summary),
    ]

    if analysis.observations:
        parts += ["", "<b>Наблюдения</b>"]
        for obs in analysis.observations:
            line = f"• {escape(obs.statement)}"
            if obs.evidence:
                line += f" <i>({escape(obs.evidence)})</i>"
            parts.append(line)

    if analysis.recommendations:
        parts += ["", "<b>Что можно сделать</b>"]
        for index, rec in enumerate(analysis.recommendations, start=1):
            line = f"{index}. {escape(rec.action)}"
            if rec.rationale:
                line += f" — <i>{escape(rec.rationale)}</i>"
            parts.append(line)

    if analysis.needs_professional_help:
        parts += ["", _HELP_NOTE]

    if analysis.source == "fallback":
        parts += ["", _FALLBACK_NOTE]

    parts += ["", f"<i>{escape(DISCLAIMER)}</i>"]
    return "\n".join(parts)


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split text into chunks under ``limit``, preferring line boundaries.

    A single line longer than the limit is cut hard — there is nowhere better to
    break it, and dropping it would lose content.
    """
    if not text or not text.strip():
        return []

    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current, length = [], 0
            chunks.append(line[:limit])
            line = line[limit:]

        # +1 for the newline that will rejoin this line to the previous one.
        addition = len(line) + (1 if current else 0)
        if length + addition > limit:
            chunks.append("\n".join(current))
            current, length = [line], len(line)
        else:
            current.append(line)
            length += addition

    if current:
        chunks.append("\n".join(current))

    return [chunk for chunk in chunks if chunk]
