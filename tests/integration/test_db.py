"""Integration tests for the SQLite schema against a real temp file."""

from __future__ import annotations

import sqlite3

import pytest

from moodbot.storage.db import SCHEMA_VERSION, apply_migrations, connect


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.sqlite3"


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def test_migrations_create_the_expected_tables(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        assert {"entries", "schema_version"} <= _tables(conn)


def test_migrations_record_the_schema_version(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION


def test_migrations_are_idempotent(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        apply_migrations(conn)
        apply_migrations(conn)

        rows = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert rows == 1


def test_migrations_preserve_existing_rows(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO entries (user_id, text, created_at) VALUES (?, ?, ?)",
            (1, "существующая запись", "2026-08-30T10:00:00+00:00"),
        )
        conn.commit()

    with connect(db_path) as conn:
        apply_migrations(conn)
        count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        assert count == 1


def test_creates_parent_directory_if_missing(tmp_path):
    nested = tmp_path / "deep" / "deeper" / "bot.sqlite3"
    with connect(nested) as conn:
        apply_migrations(conn)
    assert nested.exists()


def test_foreign_keys_and_row_factory_are_configured(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO entries (user_id, text, created_at) VALUES (?, ?, ?)",
            (7, "тест", "2026-08-30T10:00:00+00:00"),
        )
        row = conn.execute("SELECT user_id, text FROM entries").fetchone()

        # Row factory gives named access, which keeps the repository readable.
        assert row["user_id"] == 7
        assert row["text"] == "тест"


def test_index_on_user_and_time_exists(db_path):
    with connect(db_path) as conn:
        apply_migrations(conn)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert any("entries" in name and "user" in name for name in indexes)
