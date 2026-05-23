"""Tests for project service: _build_chapter_tree, _chapter_to_out, and core logic."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.extensions.project.schemas import ChapterOut, ChapterTreeNode
from app.extensions.project.service import (
    _build_chapter_tree,
    _chapter_to_out,
    _create_chapters_from_tree,
)


def _make_chapter(**overrides):
    """Create a mock ProjectChapter with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "project_id": uuid4(),
        "parent_id": None,
        "title": "Untitled",
        "level": 1,
        "sort_order": 0,
        "status": "pending",
        "content": None,
        "assigned_to": None,
        "word_count_target": 3000,
        "word_count_current": 0,
        "purpose": None,
        "generation_hint": None,
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(overrides)
    ch = MagicMock()
    for k, v in defaults.items():
        setattr(ch, k, v)
    return ch


# ── _build_chapter_tree ──


class TestBuildChapterTree:
    def test_empty_list(self):
        result = _build_chapter_tree([], {})
        assert result == []

    def test_flat_chapters(self):
        c1 = _make_chapter(title="Ch1", sort_order=0)
        c2 = _make_chapter(title="Ch2", sort_order=1)
        result = _build_chapter_tree([c1, c2], {})
        assert len(result) == 2
        assert result[0].title == "Ch1"
        assert result[1].title == "Ch2"
        assert result[0].children == []

    def test_nested_chapters(self):
        parent = _make_chapter(title="Parent", sort_order=0)
        child = _make_chapter(title="Child", parent_id=parent.id, level=2, sort_order=0)
        result = _build_chapter_tree([parent, child], {})
        assert len(result) == 1
        assert result[0].title == "Parent"
        assert len(result[0].children) == 1
        assert result[0].children[0].title == "Child"

    def test_assigned_names_resolved(self):
        uid = uuid4()
        c = _make_chapter(title="Ch", assigned_to=uid)
        result = _build_chapter_tree([c], {uid: "Alice"})
        assert result[0].assigned_name == "Alice"

    def test_sort_order_respected(self):
        c2 = _make_chapter(title="Second", sort_order=1)
        c1 = _make_chapter(title="First", sort_order=0)
        result = _build_chapter_tree([c2, c1], {})
        assert result[0].title == "First"
        assert result[1].title == "Second"

    def test_deeply_nested(self):
        root = _make_chapter(title="Root", level=1, sort_order=0)
        mid = _make_chapter(title="Mid", parent_id=root.id, level=2, sort_order=0)
        leaf = _make_chapter(title="Leaf", parent_id=mid.id, level=3, sort_order=0)
        result = _build_chapter_tree([root, mid, leaf], {})
        assert len(result) == 1
        assert result[0].title == "Root"
        mid_out = result[0].children[0]
        assert mid_out.title == "Mid"
        assert mid_out.children[0].title == "Leaf"

    def test_orphan_parent_treated_as_root(self):
        """Chapter with parent_id pointing to non-existent parent becomes root."""
        orphan = _make_chapter(title="Orphan", parent_id=uuid4(), sort_order=0)
        result = _build_chapter_tree([orphan], {})
        assert len(result) == 1
        assert result[0].title == "Orphan"


# ── _chapter_to_out ──


class TestChapterToOut:
    def test_basic_conversion(self):
        ch = _make_chapter(title="Test Chapter", level=2)
        out = _chapter_to_out(ch)
        assert isinstance(out, ChapterOut)
        assert out.title == "Test Chapter"
        assert out.level == 2
        assert out.children == []
        assert out.assigned_name is None

    def test_with_children(self):
        ch = _make_chapter(title="Parent")
        child_out = ChapterOut(
            id=uuid4(), project_id=ch.project_id, title="Child",
        )
        out = _chapter_to_out(ch, children=[child_out])
        assert len(out.children) == 1


# ── _create_chapters_from_tree ──


class TestCreateChaptersFromTree:
    @pytest.mark.asyncio
    async def test_creates_flat_chapters(self):
        db = AsyncMock()
        pid = uuid4()
        nodes = [
            ChapterTreeNode(title="Ch1", sort_order=0),
            ChapterTreeNode(title="Ch2", sort_order=1),
        ]
        result = await _create_chapters_from_tree(db, pid, nodes)
        assert len(result) == 2
        assert db.add.call_count == 2
        assert db.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_creates_nested_chapters(self):
        db = AsyncMock()
        pid = uuid4()
        nodes = [
            ChapterTreeNode(
                title="Root",
                children=[ChapterTreeNode(title="Child", level=2)],
            ),
        ]
        result = await _create_chapters_from_tree(db, pid, nodes)
        assert len(result) == 2  # root + child
        # First created is root, second is child
        assert result[0].title == "Root"
        assert result[1].title == "Child"

    @pytest.mark.asyncio
    async def test_empty_nodes(self):
        db = AsyncMock()
        result = await _create_chapters_from_tree(db, uuid4(), [])
        assert result == []
        db.add.assert_not_called()


# ── confirm_outline (via mock) ──


class TestConfirmOutline:
    @pytest.mark.asyncio
    async def test_advances_stage_to_writing(self):
        from app.extensions.project import service

        pid = uuid4()
        project_mock = MagicMock()
        project_mock.id = pid
        project_mock.current_stage = 2
        project_mock.status = "outline"

        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = project_mock
        db.execute.return_value = scalar_result

        # Mock get_project to return a valid ProjectOut
        with patch.object(service, "get_project", new_callable=AsyncMock) as mock_get:
            from app.extensions.project.schemas import ProjectOut

            mock_get.return_value = ProjectOut(
                id=pid, name="Test", report_type="other",
                current_stage=3, status="writing",
            )
            result = await service.confirm_outline(db, pid)

        assert project_mock.current_stage == 3
        assert project_mock.status == "writing"
        assert result.status == "writing"
        assert result.current_stage == 3

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_project(self):
        from app.extensions.project import service

        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute.return_value = scalar_result

        result = await service.confirm_outline(db, uuid4())
        assert result is None


# ── delete_project ──


class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_deletes_existing(self):
        from app.extensions.project import service

        db = AsyncMock()
        project_mock = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = project_mock
        db.execute.return_value = scalar_result

        result = await service.delete_project(db, uuid4())
        assert result is True
        db.delete.assert_called_once_with(project_mock)

    @pytest.mark.asyncio
    async def test_returns_false_for_missing(self):
        from app.extensions.project import service

        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute.return_value = scalar_result

        result = await service.delete_project(db, uuid4())
        assert result is False


# ── add_member / remove_member ──


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_new_member(self):
        from app.extensions.project import service

        pid = uuid4()
        uid = uuid4()
        db = AsyncMock()

        # First call: check project exists
        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = MagicMock()
        # Second call: check existing member
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = None
        db.execute.side_effect = [proj_result, mem_result]

        result = await service.add_member(db, pid, uid, "editor")
        assert result is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_project(self):
        from app.extensions.project import service

        db = AsyncMock()
        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = None
        db.execute.return_value = proj_result

        result = await service.add_member(db, uuid4(), uuid4(), "editor")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_for_existing_member(self):
        from app.extensions.project import service

        pid = uuid4()
        uid = uuid4()
        db = AsyncMock()

        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = MagicMock()
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = MagicMock()
        db.execute.side_effect = [proj_result, mem_result]

        result = await service.add_member(db, pid, uid, "editor")
        assert result is True
        db.add.assert_not_called()


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_existing(self):
        from app.extensions.project import service

        db = AsyncMock()
        member_mock = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = member_mock
        db.execute.return_value = scalar_result

        result = await service.remove_member(db, uuid4(), uuid4())
        assert result is True
        db.delete.assert_called_once_with(member_mock)

    @pytest.mark.asyncio
    async def test_returns_false_for_missing(self):
        from app.extensions.project import service

        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute.return_value = scalar_result

        result = await service.remove_member(db, uuid4(), uuid4())
        assert result is False


# ── update_chapter ──


class TestUpdateChapter:
    @pytest.mark.asyncio
    async def test_updates_fields(self):
        from app.extensions.project import service

        ch = _make_chapter(title="Old Title", status="pending")
        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = ch
        db.execute.return_value = scalar_result

        # Mock _get_assigned_names to return empty
        with patch.object(service, "_get_assigned_names", new_callable=AsyncMock, return_value={}):
            result = await service.update_chapter(db, ch.id, title="New Title", status="writing")

        assert ch.title == "New Title"
        assert ch.status == "writing"
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self):
        from app.extensions.project import service

        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute.return_value = scalar_result

        result = await service.update_chapter(db, uuid4(), title="X")
        assert result is None
