"""Regression: seed_builtin_templates is per-id idempotent (adds only missing builtins)."""
import uuid
from unittest.mock import AsyncMock

import pytest

from app.extensions.output import seed


class _FakeResult:
    """Fake Result object: .all() returns list of (id,) tuples."""

    def __init__(self, ids):
        self._rows = [(i,) for i in ids]

    def all(self):
        return self._rows


def _fake_db(existing_ids):
    """Minimal AsyncSession fake: execute returns existing ids, records added; commit stays AsyncMock."""
    db = AsyncMock()

    async def _execute(stmt):
        return _FakeResult(existing_ids)

    db.execute = _execute
    added = []
    db.add = lambda obj: added.append(obj)
    db._added = added
    # db.commit stays the AsyncMock (awaitable + assertable)
    return db


@pytest.mark.asyncio
async def test_seeds_only_missing_builtins():
    existing = {uuid.UUID(seed.BUILTIN_TEMPLATES[0]["id"])}
    db = _fake_db(existing)
    await seed.seed_builtin_templates(db)
    added_ids = {t.id for t in db._added}
    expected_new = {uuid.UUID(t["id"]) for t in seed.BUILTIN_TEMPLATES[1:]}
    assert added_ids == expected_new
    assert uuid.UUID(seed.BUILTIN_TEMPLATES[0]["id"]) not in added_ids


@pytest.mark.asyncio
async def test_seeds_nothing_when_all_present():
    existing = {uuid.UUID(t["id"]) for t in seed.BUILTIN_TEMPLATES}
    db = _fake_db(existing)
    await seed.seed_builtin_templates(db)
    assert db._added == []
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_seeds_all_when_empty():
    db = _fake_db(set())
    await seed.seed_builtin_templates(db)
    assert len(db._added) == len(seed.BUILTIN_TEMPLATES)
