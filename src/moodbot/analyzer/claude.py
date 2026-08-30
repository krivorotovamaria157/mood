"""Claude-backed analyzer.

The model is asked for a JSON object matching a fixed schema, which is then run
through the same :meth:`Analysis.from_payload` validator as every other source.
The model constrains the shape; the validator enforces the invariants that
matter (a crisis reading always points at a human, an unreadable risk is never
read as "no risk").

Any failure — transport, refusal, malformed JSON — degrades to the rule-based
analyzer rather than propagating. A person who just described a hard day should
not receive a stack trace.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Sequence

from ..models import Analysis, AnalysisParseError
from .base import Analyzer
from .fallback import RuleBasedAnalyzer

__all__ = ["ANALYSIS_SCHEMA", "SYSTEM_PROMPT", "ClaudeAnalyzer"]

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_TIMEOUT = 45.0
DEFAULT_MAX_TOKENS = 8000

SYSTEM_PROMPT = """\
Ты помогаешь человеку разобраться в собственном состоянии по его свободному \
описанию симптомов, ситуации и эмоций.

Рамка, из которой нельзя выходить:
- Ты не ставишь диагнозов и не называешь заболеваний. Ты описываешь то, что \
видно в тексте, и задаёшь направление для самонаблюдения.
- Ты не назначаешь лекарства и не отменяешь назначения врача.
- Ты пишешь на языке пользователя, коротко и без сюсюканья. Не преувеличиваешь \
тяжесть и не преуменьшаешь её.
- Каждое наблюдение опирается на конкретные слова из сообщения. Если данных мало \
— так и говоришь, а не додумываешь.

Как оценивать:
- risk_level — насколько состояние требует внимания: none, low, moderate, high, \
crisis. "crisis" ставь только при прямых признаках угрозы жизни или здоровью.
- urgency — когда стоит действовать: now, soon, monitor.
- needs_professional_help — правда, если стоит обратиться к специалисту.

Рекомендации должны быть выполнимыми сегодня и следовать из сказанного, \
а не быть общими советами о здоровом образе жизни."""

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-4 предложения: что видно в описании и как это связано между собой.",
        },
        "risk_level": {
            "type": "string",
            "enum": ["none", "low", "moderate", "high", "crisis"],
        },
        "urgency": {"type": "string", "enum": ["now", "soon", "monitor"]},
        "observations": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "evidence": {
                        "type": "string",
                        "description": "Слова из сообщения, на которых основано наблюдение.",
                    },
                },
                "required": ["statement", "evidence"],
                "additionalProperties": False,
            },
        },
        "recommendations": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["action", "rationale"],
                "additionalProperties": False,
            },
        },
        "needs_professional_help": {"type": "boolean"},
    },
    "required": [
        "summary",
        "risk_level",
        "urgency",
        "observations",
        "recommendations",
        "needs_professional_help",
    ],
    "additionalProperties": False,
}


class ClaudeAnalyzer:
    def __init__(
        self,
        client: Any,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        fallback: Analyzer | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._fallback: Analyzer = fallback or RuleBasedAnalyzer()

    async def analyze(self, text: str, history: Sequence[str] = ()) -> Analysis:
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(**self._request(text, history)),
                timeout=self._timeout,
            )
            return self._parse(response)
        except asyncio.CancelledError:
            # Shutdown, not a provider failure — must not be swallowed.
            raise
        except Exception as exc:
            # Deliberately broad: every remaining failure mode has the same
            # correct response, which is to answer the user with the fallback.
            # Only the exception type is logged — the message is the user's.
            logger.warning(
                "claude analysis failed (%s), using fallback", type(exc).__name__
            )
            return await self._fallback.analyze(text, history)

    # -- request -----------------------------------------------------------

    def _request(self, text: str, history: Sequence[str]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []

        if history:
            recent = "\n".join(f"- {item}" for item in history)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Мои предыдущие записи, от старых к новым:\n"
                        f"{recent}\n\n"
                        "Учти их, если видишь повтор темы."
                    ),
                }
            )
            messages.append(
                {"role": "assistant", "content": "Понял, учту при разборе."}
            )

        messages.append({"role": "user", "content": text})

        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": "medium",
                "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA},
            },
        }

    # -- response ----------------------------------------------------------

    @staticmethod
    def _parse(response: Any) -> Analysis:
        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError("model refused the request")

        text = next(
            (
                block.text
                for block in getattr(response, "content", [])
                if getattr(block, "type", None) == "text"
            ),
            None,
        )
        if not text:
            raise AnalysisParseError("response contained no text block")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnalysisParseError("response was not valid JSON") from exc

        return Analysis.from_payload(payload, source="claude")
