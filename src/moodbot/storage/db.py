"""SQLite connection and schema.

Migrations are a plain ordered list of DDL batches guarded by a version row.
That is enough for a single-file bot database and keeps the whole thing
inspectable — no migration framework to reason about when something goes wrong.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["SCHEMA_VERSION", "apply_migrations", "connect"]

# Bump when appending to _MIGRATIONS.
SCHEMA_VERSION = 1

_MIGRATIONS: list[tuple[str, ...]] = [
    # v1 — entries and their analysis summary
    (
        """
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            text        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            risk_level  INTEGER,
            urgency     TEXT,
            summary     TEXT,
            source      TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entries_user_created
            ON entries (user_id, created_at DESC)
        """,
    ),
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection, creating the parent directory if needed."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring the database up to :data:`SCHEMA_VERSION`. Safe to call repeatedly."""
    version = _current_version(conn)

    for index, batch in enumerate(_MIGRATIONS, start=1):
        if index <= version:
            continue
        for statement in batch:
            conn.execute(statement)
        version = index

    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()
    return version
