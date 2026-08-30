"""Shared fakes for the mock and integration layers.

Deliberately hand-written rather than `unittest.mock`: the shape of what the SDK
returns is the thing under test, and a hand-built fake documents that shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeThinkingBlock:
    thinking: str = ""
    type: str = "thinking"


@dataclass
class FakeResponse:
    content: list[Any]
    stop_reason: str = "end_turn"
    stop_details: Any = None


@dataclass
class FakeMessages:
    """Stands in for `client.messages`."""

    response: Any = None
    error: BaseException | None = None
    delay: float = 0.0
    calls: list[dict] = field(default_factory=list)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            import asyncio

            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.response


@dataclass
class FakeAnthropicClient:
    messages: FakeMessages = field(default_factory=FakeMessages)


def json_response(payload: dict, stop_reason: str = "end_turn") -> FakeResponse:
    """A well-formed structured-output response."""
    return FakeResponse(
        content=[FakeThinkingBlock(), FakeTextBlock(json.dumps(payload, ensure_ascii=False))],
        stop_reason=stop_reason,
    )


def client_returning(payload: dict) -> FakeAnthropicClient:
    return FakeAnthropicClient(messages=FakeMessages(response=json_response(payload)))


def client_raising(error: BaseException) -> FakeAnthropicClient:
    return FakeAnthropicClient(messages=FakeMessages(error=error))


VALID_PAYLOAD = {
    "summary": "Похоже на тревогу перед важным событием.",
    "risk_level": "low",
    "urgency": "monitor",
    "observations": [
        {"statement": "Тревога привязана к конкретному событию", "evidence": "перед собеседованием"}
    ],
    "recommendations": [
        {"action": "Выпиши, что именно пугает", "rationale": "конкретный страх проще проверить"}
    ],
    "needs_professional_help": False,
}


# --- bot-side fakes -------------------------------------------------------


class FakeAnalyzer:
    """Analyzer returning a canned analysis, or raising on demand."""

    def __init__(self, analysis=None, error: BaseException | None = None) -> None:
        self._analysis = analysis
        self._error = error
        self.calls: list[tuple[str, tuple]] = []

    async def analyze(self, text: str, history=()):
        self.calls.append((text, tuple(history)))
        if self._error is not None:
            raise self._error
        if self._analysis is not None:
            return self._analysis
        from moodbot.models import Analysis

        return Analysis.from_payload(
            {"summary": "разбор", "risk_level": "low", "urgency": "monitor"},
            source="claude",
        )


class FakeRepository:
    """In-memory stand-in for EntryRepository."""

    def __init__(
        self,
        add_error: BaseException | None = None,
        read_error: BaseException | None = None,
    ) -> None:
        self.rows: list[tuple] = []
        self.deleted: list[int] = []
        self.add_error = add_error
        self.read_error = read_error

    async def add(self, entry, analysis) -> int:
        if self.add_error is not None:
            raise self.add_error
        self.rows.append((entry, analysis))
        return len(self.rows)

    async def recent_texts(self, user_id: int, limit: int = 10) -> list[str]:
        if self.read_error is not None:
            raise self.read_error
        return [e.text for e, _ in self.rows if e.user_id == user_id][-limit:]

    async def history(self, user_id: int, limit: int = 10):
        if self.read_error is not None:
            raise self.read_error
        from moodbot.storage.repository import StoredEntry

        found = [
            StoredEntry(
                id=i + 1,
                user_id=e.user_id,
                text=e.text,
                created_at=e.created_at.isoformat(),
                risk_level=a.risk_level,
                urgency=str(a.urgency),
                summary=a.summary,
                source=a.source,
            )
            for i, (e, a) in enumerate(self.rows)
            if e.user_id == user_id
        ]
        return list(reversed(found))[:limit]

    async def delete_user(self, user_id: int) -> int:
        removed = [r for r in self.rows if r[0].user_id == user_id]
        self.rows = [r for r in self.rows if r[0].user_id != user_id]
        self.deleted.append(user_id)
        return len(removed)

    async def count(self, user_id: int) -> int:
        return sum(1 for e, _ in self.rows if e.user_id == user_id)
