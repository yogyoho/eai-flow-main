"""Tests for update_chapter auto-parse traceability sources.

Covers:
- Content change triggers auto-parse and persists sources
- No content change does NOT trigger parse
- Chapter not found returns None
- Content with no markers clears nothing (no crash)
- Content with markers replaces old sources
- Empty string content does not trigger parse
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUpdateChapterAutoParse:
    @pytest.mark.asyncio
    async def test_content_change_triggers_parse(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()
        new_content = "SO₂ 浓度为 0.045mg/m³[1]。\n\n[1] source:rag_retrieval:知识库「监测」p.23"

        mock_chapter = MagicMock()
        mock_chapter.id = chapter_id
        mock_chapter.content = None  # Was empty, now has content
        mock_chapter.status = "pending"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.add = MagicMock()

        result = await update_chapter(mock_db, chapter_id, content=new_content)

        assert result is not None
        assert mock_chapter.content == new_content
        # Should have called execute to delete old sources and add new ones
        assert mock_db.execute.called or mock_db.add.called

    @pytest.mark.asyncio
    async def test_no_content_change_skips_parse(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()
        existing_content = "Same content"

        mock_chapter = MagicMock()
        mock_chapter.content = existing_content

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.add = MagicMock()

        result = await update_chapter(mock_db, chapter_id, content=existing_content)

        assert result is not None
        # No parse should happen when content hasn't changed
        mock_db.execute.assert_not_called()
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_chapter_not_found_returns_none(self):
        from app.extensions.project.service import update_chapter

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        result = await update_chapter(mock_db, uuid.uuid4(), content="new")
        assert result is None

    @pytest.mark.asyncio
    async def test_content_without_markers_no_crash(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()
        plain_content = "Just plain text without any markers"

        mock_chapter = MagicMock()
        mock_chapter.content = None
        mock_chapter.status = "pending"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.add = MagicMock()

        result = await update_chapter(mock_db, chapter_id, content=plain_content)

        assert result is not None
        assert mock_chapter.content == plain_content
        # No sources to parse, but flush should still be called once for chapter update
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_empty_string_content_no_parse(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()

        mock_chapter = MagicMock()
        mock_chapter.content = "some old content"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()
        mock_db.execute = AsyncMock()

        result = await update_chapter(mock_db, chapter_id, content="")

        assert result is not None
        assert mock_chapter.content == ""
        # Empty string is falsy, should skip parse
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_content_update_skips_parse(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()

        mock_chapter = MagicMock()
        mock_chapter.content = "existing"
        mock_chapter.status = "pending"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()

        result = await update_chapter(mock_db, chapter_id, status="completed")

        assert result is not None
        assert mock_chapter.status == "completed"
        mock_db.flush.assert_called_once()
        # Only one flush call = chapter update, no second flush from auto-parse
        # (content didn't change)

    @pytest.mark.asyncio
    async def test_parse_with_multiple_markers(self):
        from app.extensions.project.service import update_chapter

        chapter_id = uuid.uuid4()
        content = (
            "SO₂ 为 0.045[1]，NO₂ 为 0.03[2]。\n\n"
            "[1] source:rag_retrieval:知识库「监测」p.23\n"
            "[2] source:regulation:GB 3095-2012 表2"
        )

        mock_chapter = MagicMock()
        mock_chapter.content = None
        mock_chapter.status = "pending"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.flush = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.add = MagicMock()

        result = await update_chapter(mock_db, chapter_id, content=content)

        assert result is not None
        # Should have added 2 sources
        assert mock_db.add.call_count == 2
