"""Persistence for entries and the analysis they received.

`sqlite3` is synchronous and its connections are not shareable across threads,
so every operation opens its own connection inside :func:`asyncio.to_thread`.
For a bot handling one message at a time per user this costs nothing measurable
and removes a whole class of threading bugs.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..models import Analysis, Entry, RiskLevel
from .db import apply_migrations, connect

__all__ = ["EntryRepository", "StoredEntry"]

DEFAULT_HISTORY_LIMIT = 10


@dataclass(frozen=True, slots=True)
class StoredEntry:
    """One persisted entry together with the reading it got at the time."""

    id: int
    user_id: int
    text: str
    created_at: str
    risk_level: RiskLevel
    urgency: str
    summary: str
    source: str


def _to_stored(row: sqlite3.Row) -> StoredEntry:
    return StoredEntry(
        id=row["id"],
        user_id=row["user_id"],
        text=row["text"],
        created_at=row["created_at"],
        risk_level=RiskLevel(row["risk_level"] if row["risk_level"] is not None else 0),
        urgency=row["urgency"] or "",
        summary=row["summary"] or "",
        source=row["source"] or "",
    )


class EntryRepository:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    # -- schema ------------------------------------------------------------

    def initialize(self) -> None:
        """Create or upgrade the schema. Synchronous — called once at startup."""
        with connect(self._path) as conn:
            apply_migrations(conn)

    # -- writes ------------------------------------------------------------

    async def add(self, entry: Entry, analysis: Analysis) -> int:
        return await asyncio.to_thread(self._add, entry, analysis)

    def _add(self, entry: Entry, analysis: Analysis) -> int:
        with connect(self._path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO entries
                    (user_id, text, created_at, risk_level, urgency, summary, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.user_id,
                    entry.text,
                    _isoformat(entry.created_at),
                    int(analysis.risk_level),
                    str(analysis.urgency),
                    analysis.summary,
                    analysis.source,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    async def delete_user(self, user_id: int) -> int:
        """Remove everything stored for one user. Returns the number of rows."""
        return await asyncio.to_thread(self._delete_user, user_id)

    def _delete_user(self, user_id: int) -> int:
        with connect(self._path) as conn:
            cursor = conn.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount

    # -- reads -------------------------------------------------------------

    async def history(
        self, user_id: int, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> list[StoredEntry]:
        """Most recent entries first — the order a person expects to read."""
        return await asyncio.to_thread(self._history, user_id, limit)

    def _history(self, user_id: int, limit: int) -> list[StoredEntry]:
        with connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [_to_stored(row) for row in rows]

    async def recent_texts(
        self, user_id: int, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> list[str]:
        """The latest entries, oldest first — the order an analyzer should read."""
        records = await self.history(user_id, limit)
        return [record.text for record in reversed(records)]

    async def count(self, user_id: int) -> int:
        return await asyncio.to_thread(self._count, user_id)

    def _count(self, user_id: int) -> int:
        with connect(self._path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE user_id = ?", (user_id,)
            ).fetchone()
            return int(row[0])


def _isoformat(value: datetime | str) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)
