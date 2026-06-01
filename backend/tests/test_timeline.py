"""Tests for ProjectTimeline CRUD operations."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.workflow.models import ProjectTimeline
from app.extensions.workflow.timeline.schemas import (
    MilestoneCreate,
    MilestoneUpdate,
    TimelineEntryCreate,
    TimelineEntryOut,
    TimelineEntryUpdate,
    TimelineListResponse,
)
from app.extensions.workflow.timeline.service import (
    delete_timeline_entry,
    get_timeline,
    upsert_timeline_entry,
)


# ── Pydantic schema tests ──


class TestTimelineSchemas:
    """Tests for Pydantic timeline schemas."""

    def test_timeline_entry_create_defaults(self):
        entry = TimelineEntryCreate(phase_node="draft")
        assert entry.phase_node == "draft"
        assert entry.planned_start is None
        assert entry.progress_pct == 0
        assert entry.depends_on is None
        assert entry.milestones is None

    def test_timeline_entry_create_full(self):
        pid = uuid.uuid4()
        oid = uuid.uuid4()
        entry = TimelineEntryCreate(
            phase_node="review",
            planned_start=date(2026, 1, 1),
            planned_end=date(2026, 1, 15),
            actual_start=date(2026, 1, 2),
            actual_end=date(2026, 1, 14),
            depends_on=["draft", "research"],
            milestones=[{"label": "First Review", "target_date": "2026-01-10"}],
            progress_pct=75,
            owner_id=oid,
        )
        assert entry.phase_node == "review"
        assert entry.progress_pct == 75
        assert len(entry.depends_on) == 2

    def test_timeline_entry_update_partial(self):
        update = TimelineEntryUpdate(progress_pct=100, actual_end=date(2026, 2, 1))
        assert update.progress_pct == 100
        assert update.actual_end == date(2026, 2, 1)
        # Unset fields should be None
        assert update.planned_start is None

    def test_timeline_entry_out_from_attributes(self):
        pid = uuid.uuid4()
        prjid = uuid.uuid4()
        entry = ProjectTimeline(
            id=pid,
            project_id=prjid,
            phase_node="draft",
            progress_pct=50,
        )
        out = TimelineEntryOut.model_validate(entry)
        assert out.id == pid
        assert out.project_id == prjid
        assert out.phase_node == "draft"
        assert out.progress_pct == 50

    def test_timeline_list_response(self):
        pid = uuid.uuid4()
        prjid = uuid.uuid4()
        entries = [
            TimelineEntryOut(
                id=pid, project_id=prjid, phase_node="draft", progress_pct=0
            )
        ]
        resp = TimelineListResponse(entries=entries)
        assert len(resp.entries) == 1

    def test_milestone_create_defaults(self):
        ms = MilestoneCreate(label="Checkpoint")
        assert ms.label == "Checkpoint"
        assert ms.target_date is None
        assert ms.status == "pending"

    def test_milestone_update(self):
        ms = MilestoneUpdate(label="Updated", status="done")
        assert ms.label == "Updated"
        assert ms.status == "done"


# ── Service tests ──


@pytest.fixture()
def mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture()
def sample_project_id():
    return uuid.uuid4()


class TestTimelineService:
    """Tests for timeline CRUD service functions."""

    @pytest.mark.asyncio
    async def test_get_timeline_empty(self, mock_db, sample_project_id):
        """get_timeline returns empty list when no entries exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await get_timeline(mock_db, sample_project_id)
        assert entries == []

    @pytest.mark.asyncio
    async def test_get_timeline_returns_entries(self, mock_db, sample_project_id):
        """get_timeline returns entries ordered by planned_start."""
        entry1 = ProjectTimeline(
            id=uuid.uuid4(), project_id=sample_project_id, phase_node="research"
        )
        entry2 = ProjectTimeline(
            id=uuid.uuid4(), project_id=sample_project_id, phase_node="draft"
        )
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entry1, entry2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await get_timeline(mock_db, sample_project_id)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_upsert_creates_new_entry(self, mock_db, sample_project_id):
        """upsert_timeline_entry creates a new entry when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = {"progress_pct": 30}
        entry = await upsert_timeline_entry(
            mock_db, sample_project_id, "draft", data
        )

        mock_db.add.assert_called_once()
        assert isinstance(entry, ProjectTimeline)
        assert entry.phase_node == "draft"
        assert entry.progress_pct == 30
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(entry)

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_entry(self, mock_db, sample_project_id):
        """upsert_timeline_entry updates an existing entry."""
        existing = ProjectTimeline(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            phase_node="draft",
            progress_pct=0,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = {"progress_pct": 50, "actual_start": date(2026, 1, 5)}
        entry = await upsert_timeline_entry(
            mock_db, sample_project_id, "draft", data
        )

        mock_db.add.assert_not_called()
        assert entry.progress_pct == 50
        assert entry.actual_start == date(2026, 1, 5)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_existing_entry(self, mock_db):
        """delete_timeline_entry returns True for existing entry."""
        entry_id = uuid.uuid4()
        mock_entry = ProjectTimeline(id=entry_id)
        mock_db.get = AsyncMock(return_value=mock_entry)
        mock_db.delete = AsyncMock()

        result = await delete_timeline_entry(mock_db, entry_id)
        assert result is True
        mock_db.delete.assert_awaited_once_with(mock_entry)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_entry(self, mock_db):
        """delete_timeline_entry returns False for missing entry."""
        entry_id = uuid.uuid4()
        mock_db.get = AsyncMock(return_value=None)

        result = await delete_timeline_entry(mock_db, entry_id)
        assert result is False
        mock_db.commit.assert_not_awaited()


# ── Model tests ──


class TestProjectTimelineModel:
    """Tests for the ProjectTimeline SQLAlchemy model."""

    def test_model_table_name(self):
        assert ProjectTimeline.__tablename__ == "project_timeline"

    def test_model_columns(self):
        """Verify model has expected columns."""
        mapper = ProjectTimeline.__mapper__
        col_names = {c.name for c in mapper.columns}
        expected = {
            "id",
            "project_id",
            "phase_node",
            "planned_start",
            "planned_end",
            "actual_start",
            "actual_end",
            "depends_on",
            "milestones",
            "progress_pct",
            "owner_id",
        }
        assert col_names == expected
