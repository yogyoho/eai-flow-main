"""Tests for personal-outputs endpoint and star/share metadata."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.extensions.docmgr.service import AIDocumentService


class TestListPersonalOutputs:

    @pytest.mark.asyncio
    async def test_empty_when_no_threads_dir(self, tmp_path: Path):
        user_id = uuid4()
        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(), user_id,
            )
        assert result["threads"] == [] and result["total"] == 0

    @pytest.mark.asyncio
    async def test_skips_thread_without_outputs_dir(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        (threads_dir / "t1").mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(), user_id,
            )
        assert result["threads"] == [] and result["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_files_for_thread_with_outputs(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "report.md").write_text("# Report")
        (outputs_dir / "data.csv").write_text("a,b\n1,2")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(), user_id,
            )
        assert len(result["threads"]) == 1
        assert result["total"] == 1
        assert result["threads"][0]["thread_id"] == "tid-1"
        names = {f["name"] for f in result["threads"][0]["files"]}
        assert names == {"report.md", "data.csv"}

    @pytest.mark.asyncio
    async def test_skips_hidden_paths(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        hidden_dir = outputs_dir / ".tool-results"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / "large.json").write_text("{}")
        (outputs_dir / "visible.md").write_text("# ok")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(), user_id,
            )
        names = {f["name"] for f in result["threads"][0]["files"]}
        assert "visible.md" in names
        assert "large.json" not in names

    @pytest.mark.asyncio
    async def test_fallback_display_name_from_md_file(self, tmp_path: Path):
        """线程无标题 -> fallback 用首个 .md 文件名。"""
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "基地项目消防设计专篇.md").write_text("# doc")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(), user_id,
            )
        assert result["threads"][0]["display_name"] == "基地项目消防设计专篇"


class TestPersonalDocMetaModel:
    def test_model_tablename(self):
        from app.extensions.models import PersonalDocMeta
        assert PersonalDocMeta.__tablename__ == "personal_doc_meta"
