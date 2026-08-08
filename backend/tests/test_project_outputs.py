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


class TestPersonalOutputsExcludesProjectThreads:
    @pytest.mark.asyncio
    async def test_project_bound_thread_excluded_from_personal(self, tmp_path: Path):
        """绑项目的线程 outputs 不回流到「我的文档」。"""
        from app.extensions.docmgr.service import AIDocumentService

        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        for tid in ("t-personal", "t-project"):
            out = threads_dir / tid / "user-data" / "outputs"
            out.mkdir(parents=True)
            (out / f"{tid}.md").write_text("# x")

        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_personal_project_thread_ids",
                          AsyncMock(return_value={"t-project"})):
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.list_personal_outputs(AsyncMock(), user_id)
        tids = {t["thread_id"] for t in res["threads"]}
        assert "t-personal" in tids
        assert "t-project" not in tids


class TestWriteProjectOutput:
    @pytest.mark.asyncio
    async def test_locate_thread_outputs_by_thread_id_scan(self, tmp_path: Path):
        """thread_id 全局唯一 → 扫所有 user 桶定位（避开双 user_id 坑）。"""
        from app.extensions.docmgr.service import AIDocumentService

        # 文件在 lisi 桶，调用者可能是别人
        lisi = uuid4()
        out = tmp_path / "users" / str(lisi) / "threads" / "T-lisi" / "user-data" / "outputs"
        out.mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            located = AIDocumentService._locate_thread_outputs("T-lisi")
        assert located is not None and located.name == "outputs"

    @pytest.mark.asyncio
    async def test_write_back_to_original_path(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        lisi, zhangsan, pid = uuid4(), uuid4(), uuid4()
        out = tmp_path / "users" / str(lisi) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "doc.md").write_text("original")
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            await AIDocumentService.write_project_output(
                AsyncMock(), pid, "T1", "doc.md", "edited by zhangsan", zhangsan,
            )
        assert (out / "doc.md").read_text() == "edited by zhangsan"

    @pytest.mark.asyncio
    async def test_path_escape_rejected(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(ValueError):
                await AIDocumentService.write_project_output(
                    AsyncMock(), pid, "T1", "../../etc/passwd", "x", uid,
                )

    @pytest.mark.asyncio
    async def test_stale_mtime_raises(self, tmp_path: Path):
        """保存带过期 mtime → 抛 _StaleWrite（router 映射 409）。"""
        from app.extensions.docmgr.service import AIDocumentService, _StaleWrite

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        f = out / "doc.md"
        f.write_text("v1")
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(_StaleWrite):
                # 客户端拿到的旧 mtime=1.0 与当前文件 mtime 不符
                await AIDocumentService.write_project_output(
                    AsyncMock(), pid, "T1", "doc.md", "v2", uid, if_mtime=1.0,
                )
