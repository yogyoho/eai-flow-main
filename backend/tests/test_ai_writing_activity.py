"""Tests for start_ai_writing Temporal activity.

Covers:
- No chapter_id → skip
- Chapter not found → error
- Successful generation → writes content, returns dict
- Model failure → graceful fallback (no crash)
- Prompt includes chapter metadata (title, purpose, hint)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStartAiWritingNoChapter:
    @pytest.mark.asyncio
    async def test_returns_skipped_when_no_chapter_id(self):
        from app.extensions.workflow.temporal.activities import start_ai_writing

        result = await start_ai_writing("node-1", "proj-1", None)
        assert result["status"] == "skipped"
        assert result["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_returns_skipped_with_reason(self):
        from app.extensions.workflow.temporal.activities import start_ai_writing

        result = await start_ai_writing("node-2", "proj-1", None)
        assert "reason" in result


class TestStartAiWritingChapterNotFound:
    @pytest.mark.asyncio
    async def test_returns_error_for_missing_chapter(self):
        from app.extensions.workflow.temporal.activities import start_ai_writing

        fake_chapter_id = str(uuid.uuid4())
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await start_ai_writing("node-1", "proj-1", fake_chapter_id)

        assert result["status"] == "error"
        assert result["node_id"] == "node-1"
        assert "reason" in result


class TestStartAiWritingSuccess:
    @pytest.mark.asyncio
    async def test_writes_content_to_chapter(self):
        from app.extensions.workflow.temporal.activities import start_ai_writing

        chapter_id = uuid.uuid4()
        generated_content = "Generated text with data[1].\n\n[1] source:ai:thread-123"

        mock_chapter = MagicMock()
        mock_chapter.title = "Test Chapter"
        mock_chapter.purpose = None
        mock_chapter.generation_hint = None
        mock_chapter.word_count_target = 3000

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.commit = AsyncMock()

        with patch("app.extensions.database.get_db_context") as mock_ctx, patch(
            "app.extensions.workflow.temporal.activities._generate_content",
            new_callable=AsyncMock,
            return_value=generated_content,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await start_ai_writing("node-1", "proj-1", str(chapter_id))

        assert result["status"] == "ok"
        assert result["chapter_id"] == str(chapter_id)
        assert result["content"] == generated_content
        assert mock_chapter.content == generated_content
        assert mock_chapter.status == "draft"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_content_write_when_generation_returns_none(self):
        from app.extensions.workflow.temporal.activities import start_ai_writing

        chapter_id = uuid.uuid4()
        original_content = "old content"

        mock_chapter = MagicMock()
        mock_chapter.title = "Fail Chapter"
        mock_chapter.purpose = None
        mock_chapter.generation_hint = None
        mock_chapter.word_count_target = 0
        mock_chapter.content = original_content

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_chapter)
        mock_db.commit = AsyncMock()

        with patch("app.extensions.database.get_db_context") as mock_ctx, patch(
            "app.extensions.workflow.temporal.activities._generate_content",
            new_callable=AsyncMock,
            return_value=None,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await start_ai_writing("node-1", "proj-1", str(chapter_id))

        assert result["content"] == ""
        # Original content should remain unchanged
        assert mock_chapter.content == original_content


class TestBuildWritingPrompt:
    def test_includes_chapter_title(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = "Air Quality Assessment"
        chapter.purpose = None
        chapter.generation_hint = None
        chapter.word_count_target = 0

        prompt = _build_writing_prompt(chapter)
        assert "Air Quality Assessment" in prompt

    def test_includes_purpose_when_present(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = "Test"
        chapter.purpose = "Analyze SO2 levels"
        chapter.generation_hint = None
        chapter.word_count_target = 0

        prompt = _build_writing_prompt(chapter)
        assert "Analyze SO2 levels" in prompt

    def test_includes_generation_hint_when_present(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = "Test"
        chapter.purpose = None
        chapter.generation_hint = "Focus on northern region"
        chapter.word_count_target = 0

        prompt = _build_writing_prompt(chapter)
        assert "Focus on northern region" in prompt

    def test_includes_word_count_target(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = "Test"
        chapter.purpose = None
        chapter.generation_hint = None
        chapter.word_count_target = 5000

        prompt = _build_writing_prompt(chapter)
        assert "5000" in prompt

    def test_includes_source_marker_instructions(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = "Test"
        chapter.purpose = None
        chapter.generation_hint = None
        chapter.word_count_target = 0

        prompt = _build_writing_prompt(chapter)
        assert "source:" in prompt
        assert "[N]" in prompt

    def test_uses_default_title_when_empty(self):
        from app.extensions.workflow.temporal.activities import _build_writing_prompt

        chapter = MagicMock()
        chapter.title = ""
        chapter.purpose = None
        chapter.generation_hint = None
        chapter.word_count_target = 0

        prompt = _build_writing_prompt(chapter)
        assert "未命名章节" in prompt


class TestGenerateContentFallback:
    @pytest.mark.asyncio
    async def test_returns_none_on_model_failure(self):
        from app.extensions.workflow.temporal.activities import _generate_content

        with patch("deerflow.models.create_chat_model", side_effect=Exception("Model unavailable")):
            result = await _generate_content("test prompt")
            assert result is None
