"""Tests for notification activities."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.workflow.temporal.activities import (
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
)

# The activities use lazy imports (from app.extensions.database import get_db_context),
# so we patch at the source module where the name is resolved at import time.
_DB_CTX_PATCH = "app.extensions.database.get_db_context"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db_mock(rows: list[tuple]) -> AsyncMock:
    """Create a mock DB session that returns the given rows from execute()."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_result.scalars.return_value.all.return_value = [row[0] for row in rows]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def _make_db_context(db: AsyncMock) -> AsyncMock:
    """Create an async context manager that yields the given db session."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── notify_phase_start ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_phase_start_creates_notifications():
    """notify_phase_start should create a Notification for each project member."""
    user_id_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[(user_id_a,), (user_id_b,)])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_phase_start("phase-1", project_id)

    assert result["status"] == "ok"
    assert result["phase_id"] == "phase-1"
    assert result["notified"] == 2
    assert db.add.call_count == 2
    assert db.commit.await_count >= 1


@pytest.mark.asyncio
async def test_notify_phase_start_no_members():
    """notify_phase_start should return notified=0 when project has no members."""
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_phase_start("phase-1", project_id)

    assert result["status"] == "ok"
    assert result["notified"] == 0
    db.add.assert_not_called()


# ── notify_review_pending ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_review_pending_creates_notifications():
    """notify_review_pending should create Notifications for pending reviewers."""
    reviewer_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[(reviewer_id,)])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_review_pending("review-1", project_id)

    assert result["status"] == "ok"
    assert result["node_id"] == "review-1"
    assert result["notified"] == 1
    assert db.add.call_count == 1
    assert db.commit.await_count >= 1


@pytest.mark.asyncio
async def test_notify_review_pending_no_pending_reviewers():
    """notify_review_pending should return notified=0 when no pending reviews."""
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_review_pending("review-1", project_id)

    assert result["status"] == "ok"
    assert result["notified"] == 0
    db.add.assert_not_called()


# ── notify_workflow_complete ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_workflow_complete_creates_notifications_and_updates_status():
    """notify_workflow_complete should update project status and notify members."""
    user_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[(user_id,)])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_workflow_complete(project_id)

    assert result["status"] == "ok"
    assert result["project_id"] == project_id
    assert result["notified"] == 1
    # Should have executed both the update and the select
    assert db.execute.await_count >= 2
    assert db.add.call_count == 1
    assert db.commit.await_count >= 1


@pytest.mark.asyncio
async def test_notify_workflow_complete_no_members():
    """notify_workflow_complete should still update status even with no members."""
    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    db = _make_db_mock(rows=[])
    ctx = _make_db_context(db)

    with patch(_DB_CTX_PATCH, return_value=ctx):
        result = await notify_workflow_complete(project_id)

    assert result["status"] == "ok"
    assert result["notified"] == 0
    # Status update should still execute
    assert db.execute.await_count >= 2
