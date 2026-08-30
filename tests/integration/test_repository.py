"""Integration tests for the entry repository against a real temp database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from moodbot.models import Analysis, Entry, RiskLevel, Urgency
from moodbot.storage.repository import EntryRepository

BASE_TIME = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path) -> EntryRepository:
    repository = EntryRepository(tmp_path / "bot.sqlite3")
    repository.initialize()
    return repository


def _analysis(summary: str = "разбор", risk: RiskLevel = RiskLevel.LOW) -> Analysis:
    return Analysis(
        summary=summary,
        risk_level=risk,
        urgency=Urgency.MONITOR,
        source="fallback",
    )


def _entry(user_id: int, text: str, offset_minutes: int = 0) -> Entry:
    return Entry(
        user_id=user_id,
        text=text,
        created_at=BASE_TIME + timedelta(minutes=offset_minutes),
    )


async def test_add_returns_a_row_id(repo):
    row_id = await repo.add(_entry(1, "тревожно"), _analysis())
    assert isinstance(row_id, int)
    assert row_id > 0


async def test_added_entry_is_readable_back(repo):
    await repo.add(_entry(1, "тревожно перед встречей"), _analysis("итог"))

    records = await repo.history(1)

    assert len(records) == 1
    assert records[0].text == "тревожно перед встречей"
    assert records[0].summary == "итог"
    assert records[0].risk_level is RiskLevel.LOW


async def test_history_is_newest_first(repo):
    await repo.add(_entry(1, "первая", 0), _analysis())
    await repo.add(_entry(1, "вторая", 10), _analysis())
    await repo.add(_entry(1, "третья", 20), _analysis())

    records = await repo.history(1)

    assert [r.text for r in records] == ["третья", "вторая", "первая"]


async def test_history_respects_the_limit(repo):
    for i in range(10):
        await repo.add(_entry(1, f"запись {i}", i), _analysis())

    assert len(await repo.history(1, limit=3)) == 3


async def test_history_is_scoped_to_one_user(repo):
    await repo.add(_entry(1, "моя запись"), _analysis())
    await repo.add(_entry(2, "чужая запись"), _analysis())

    records = await repo.history(1)

    assert [r.text for r in records] == ["моя запись"]


async def test_history_of_unknown_user_is_empty(repo):
    assert await repo.history(999) == []


async def test_recent_texts_are_oldest_first_for_the_analyzer(repo):
    """The analyzer reads history as a chronological narrative."""
    await repo.add(_entry(1, "первая", 0), _analysis())
    await repo.add(_entry(1, "вторая", 10), _analysis())

    assert await repo.recent_texts(1, limit=5) == ["первая", "вторая"]


async def test_recent_texts_limit_keeps_the_latest_entries(repo):
    for i in range(5):
        await repo.add(_entry(1, f"запись {i}", i), _analysis())

    assert await repo.recent_texts(1, limit=2) == ["запись 3", "запись 4"]


async def test_delete_user_removes_only_that_users_rows(repo):
    await repo.add(_entry(1, "моя"), _analysis())
    await repo.add(_entry(1, "моя вторая"), _analysis())
    await repo.add(_entry(2, "чужая"), _analysis())

    deleted = await repo.delete_user(1)

    assert deleted == 2
    assert await repo.history(1) == []
    assert len(await repo.history(2)) == 1


async def test_delete_user_with_no_data_reports_zero(repo):
    assert await repo.delete_user(404) == 0


async def test_count_for_user(repo):
    await repo.add(_entry(1, "раз"), _analysis())
    await repo.add(_entry(1, "два"), _analysis())

    assert await repo.count(1) == 2
    assert await repo.count(2) == 0


async def test_risk_level_survives_the_round_trip(repo):
    await repo.add(_entry(1, "тяжело"), _analysis(risk=RiskLevel.HIGH))

    records = await repo.history(1)

    assert records[0].risk_level is RiskLevel.HIGH
    assert records[0].source == "fallback"


async def test_initialize_is_safe_to_call_twice(repo, tmp_path):
    repo.initialize()
    await repo.add(_entry(1, "после повторной инициализации"), _analysis())
    assert await repo.count(1) == 1
