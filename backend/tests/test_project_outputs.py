"""Tests for project-outputs aggregation, cross-user write-back, and versions."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestProjectDocVersionModel:
    def test_model_tablename_and_key_fields(self):
        from app.extensions.models import ProjectDocVersion
        assert ProjectDocVersion.__tablename__ == "project_doc_versions"
        cols = {c.name for c in ProjectDocVersion.__table__.columns}
        # 关键列存在
        assert {"project_id", "thread_id", "rel_path", "content", "editor_user_id"}.issubset(cols)


class TestListProjectOutputs:
    @pytest.mark.asyncio
    async def test_aggregates_files_across_member_buckets(self, tmp_path: Path):
        """lisi 桶的文件对项目成员可见（跨 user 桶读）。"""
        from app.extensions.docmgr.service import AIDocumentService

        lisi, zhangsan, pid = uuid4(), uuid4(), uuid4()
        # 两个成员各一个线程 + outputs 文件
        for uid, tid, fname in [(lisi, "T1", "消防设计专篇.md"), (zhangsan, "T2", "会议纪要.md")]:
            out = tmp_path / "users" / str(uid) / "threads" / tid / "user-data" / "outputs"
            out.mkdir(parents=True)
            (out / fname).write_text("# x")

        class _M:
            def __init__(self, uid, tid): self.user_id, self.thread_id = uid, tid

        members = [_M(lisi, "T1"), _M(zhangsan, "T2")]
        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_project_members", AsyncMock(return_value=members)):
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.list_project_outputs(AsyncMock(), pid, zhangsan)
        names = {f["name"] for f in res["files"]}
        assert names == {"消防设计专篇.md", "会议纪要.md"}
        by_name = {f["name"]: f for f in res["files"]}
        assert by_name["消防设计专篇.md"]["thread_id"] == "T1"
        assert "member" in by_name["消防设计专篇.md"]

    @pytest.mark.asyncio
    async def test_non_member_forbidden(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        pid, member, outsider = uuid4(), uuid4(), uuid4()

        class _M:
            def __init__(self, uid, tid): self.user_id, self.thread_id = uid, tid

        with patch.object(AIDocumentService, "_project_members",
                          AsyncMock(return_value=[_M(member, "T1")])):
            with pytest.raises(PermissionError):
                await AIDocumentService.list_project_outputs(AsyncMock(), pid, outsider)

    @pytest.mark.asyncio
    async def test_skips_member_without_thread_or_missing_dir(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        caller, pid = uuid4(), uuid4()

        class _M:
            def __init__(self, uid, tid): self.user_id, self.thread_id = uid, tid

        out = tmp_path / "users" / str(caller) / "threads" / "Tc" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "a.md").write_text("a")
        members = [_M(caller, "Tc"), _M(uuid4(), None), _M(uuid4(), "Tghost")]
        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_project_members", AsyncMock(return_value=members)):
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.list_project_outputs(AsyncMock(), pid, caller)
        assert [f["name"] for f in res["files"]] == ["a.md"]
