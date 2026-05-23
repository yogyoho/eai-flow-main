"""Tests for start_writing and start_chapter_editing service functions."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def chapter_id():
    return uuid4()


class TestStartWriting:
    @pytest.mark.asyncio
    async def test_creates_thread_and_updates_project(self, mock_db, project_id):
        tid = str(uuid4())
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.thread_id = None
        mock_project.report_type = "environmental_impact"

        with (
            patch("app.extensions.project.service._get_project_or_404", return_value=mock_project),
            patch("app.extensions.project.service._create_deerflow_thread", return_value=tid),
        ):
            from app.extensions.project.service import start_writing

            result = await start_writing(mock_db, project_id, user_id=uuid4())

        assert result["thread_id"] == tid
        assert result["project_id"] == project_id
        assert mock_project.thread_id == tid

    @pytest.mark.asyncio
    async def test_returns_existing_thread_if_present(self, mock_db, project_id):
        existing_tid = str(uuid4())
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.thread_id = existing_tid

        with patch("app.extensions.project.service._get_project_or_404", return_value=mock_project):
            from app.extensions.project.service import start_writing

            result = await start_writing(mock_db, project_id, user_id=uuid4())

        assert result["thread_id"] == existing_tid


class TestStartChapterEditing:
    @pytest.mark.asyncio
    async def test_creates_chapter_thread(self, mock_db, project_id, chapter_id):
        tid = str(uuid4())
        mock_chapter = MagicMock()
        mock_chapter.id = chapter_id
        mock_chapter.project_id = project_id
        mock_chapter.assigned_to = uuid4()
        mock_chapter.status = "draft"

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.thread_id = str(uuid4())

        with (
            patch("app.extensions.project.service._get_chapter_or_404", return_value=mock_chapter),
            patch("app.extensions.project.service._get_project_or_404", return_value=mock_project),
            patch("app.extensions.project.service._create_deerflow_thread", return_value=tid),
        ):
            from app.extensions.project.service import start_chapter_editing

            result = await start_chapter_editing(mock_db, project_id, chapter_id, user_id=uuid4())

        assert result["thread_id"] == tid
        assert result["chapter_id"] == chapter_id
        assert mock_chapter.status == "editing"
