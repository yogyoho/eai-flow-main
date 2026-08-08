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


class TestRequireProjectMemberThread:
    """C1 回归：thread_id 必须属于本项目成员的线程，防跨项目越权读写他人 outputs。"""

    @pytest.mark.asyncio
    async def test_non_member_thread_id_rejected(self):
        """成员用不属于本项目的 thread_id 读写 → 403（核心越权场景）。"""
        from fastapi import HTTPException

        from app.extensions.docmgr.routers import _require_project_member_thread
        from app.extensions.docmgr.service import AIDocumentService

        pid, member = uuid4(), uuid4()

        class _M:
            def __init__(self, uid, tid):
                self.user_id, self.thread_id = uid, tid

        # member 属本项目（线程 T1），但请求 T_other（不属于本项目任何成员）
        with patch.object(AIDocumentService, "_project_members",
                          AsyncMock(return_value=[_M(member, "T1")])):
            with pytest.raises(HTTPException) as exc:
                await _require_project_member_thread(AsyncMock(), pid, member, "T_other")
            assert exc.value.status_code == 403
            assert "thread" in exc.value.detail

    @pytest.mark.asyncio
    async def test_member_thread_id_allowed(self):
        from app.extensions.docmgr.routers import _require_project_member_thread
        from app.extensions.docmgr.service import AIDocumentService

        pid, member = uuid4(), uuid4()

        class _M:
            def __init__(self, uid, tid):
                self.user_id, self.thread_id = uid, tid

        with patch.object(AIDocumentService, "_project_members",
                          AsyncMock(return_value=[_M(member, "T1")])):
            await _require_project_member_thread(AsyncMock(), pid, member, "T1")  # 不抛即通过

    @pytest.mark.asyncio
    async def test_non_member_user_rejected(self):
        from fastapi import HTTPException

        from app.extensions.docmgr.routers import _require_project_member_thread
        from app.extensions.docmgr.service import AIDocumentService

        pid, member, outsider = uuid4(), uuid4(), uuid4()

        class _M:
            def __init__(self, uid, tid):
                self.user_id, self.thread_id = uid, tid

        with patch.object(AIDocumentService, "_project_members",
                          AsyncMock(return_value=[_M(member, "T1")])):
            with pytest.raises(HTTPException) as exc:
                await _require_project_member_thread(AsyncMock(), pid, outsider, "T1")
            assert exc.value.status_code == 403


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
        with patch("deerflow.config.paths.Paths") as mp, patch.object(
            AIDocumentService, "create_project_version", new=AsyncMock()
        ):
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
    async def test_prefix_sibling_path_escape_rejected(self, tmp_path: Path):
        """I1 回归：../outputs_archive/secret 这类「前缀兄弟目录」不能绕过 startswith。"""
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out.parent / "outputs_archive").mkdir()  # 前缀兄弟目录：旧 startswith 会误判通过
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(ValueError):
                await AIDocumentService.write_project_output(
                    AsyncMock(), pid, "T1", "../outputs_archive/secret.md", "x", uid,
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


# ---- version CRUD test fakes (mirror tests/test_docmgr_versions.py) ----
class _FakeVersion:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _fake_version_db(old_ids=None):
    """Mock AsyncSession that captures the added version and assigns id on flush."""
    db = AsyncMock()
    captured: dict = {}
    db.add = lambda v: captured.setdefault("v", v)

    async def _flush():
        v = captured.get("v")
        if v is not None and getattr(v, "id", None) is None:
            v.id = uuid4()

    db.flush = _flush
    db.execute = AsyncMock(return_value=_FakeResult(old_ids or []))
    return db


class TestProjectVersionCrud:
    @pytest.mark.asyncio
    async def test_create_caps_history_at_20(self):
        """超过每文件上限时发出 DELETE 裁剪旧版本。"""
        from sqlalchemy.sql.dml import Delete

        from app.extensions.docmgr.service import AIDocumentService

        pid, uid = uuid4(), uuid4()
        db = _fake_version_db(old_ids=[uuid4() for _ in range(21)])
        vid = await AIDocumentService.create_project_version(
            db, pid, "T1", "doc.md", "content", uid, "标签",
        )
        assert vid is not None
        delete_calls = [c for c in db.execute.await_args_list if isinstance(c.args[0], Delete)]
        assert len(delete_calls) == 1, "超过上限时应发出一次 DELETE 裁剪"

    @pytest.mark.asyncio
    async def test_create_no_delete_within_limit(self):
        from sqlalchemy.sql.dml import Delete

        from app.extensions.docmgr.service import AIDocumentService

        pid, uid = uuid4(), uuid4()
        db = _fake_version_db(old_ids=[])
        vid = await AIDocumentService.create_project_version(db, pid, "T1", "doc.md", "content", uid)
        assert vid is not None
        delete_calls = [c for c in db.execute.await_args_list if isinstance(c.args[0], Delete)]
        assert len(delete_calls) == 0

    @pytest.mark.asyncio
    async def test_restore_writes_back_and_returns_content(self):
        from app.extensions.docmgr.service import AIDocumentService

        pid, uid = uuid4(), uuid4()
        version = _FakeVersion(
            id=uuid4(), project_id=pid, thread_id="T1", rel_path="doc.md",
            content="# restored", editor_user_id=uid, label=None, created_at=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult([version]))
        with patch.object(AIDocumentService, "write_project_output", new=AsyncMock()) as mock_write:
            result = await AIDocumentService.restore_project_version(db, pid, version.id, uid)
        assert result["content"] == "# restored"
        mock_write.assert_awaited_once_with(db, pid, "T1", "doc.md", "# restored", uid)

    @pytest.mark.asyncio
    async def test_restore_missing_returns_none(self):
        from app.extensions.docmgr.service import AIDocumentService

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult([]))
        assert await AIDocumentService.restore_project_version(db, uuid4(), uuid4(), uuid4()) is None

    @pytest.mark.asyncio
    async def test_write_project_output_creates_version_snapshot(self, tmp_path: Path):
        """write_project_output 写盘后必须建一条版本快照。"""
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        db = _fake_version_db(old_ids=[])
        with patch("deerflow.config.paths.Paths") as mp, patch.object(
            AIDocumentService, "create_project_version", new=AsyncMock(return_value=uuid4())
        ) as mock_snap:
            mp.return_value.base_dir = tmp_path
            await AIDocumentService.write_project_output(
                db, pid, "T1", "doc.md", "edited", uid,
            )
        mock_snap.assert_awaited_once_with(db, pid, "T1", "doc.md", "edited", uid)


# ---- router route registration (mirror tests/test_docmgr_versions.py) ----
class TestProjectOutputRoutesRegistered:
    def test_all_project_routes_registered(self):
        """项目区 5 个路由必须注册，否则前端 404。"""
        from app.extensions.docmgr.routers import router

        routes = {
            (r.path, m)
            for r in router.routes
            for m in (getattr(r, "methods", None) or set())
        }
        for path, method in [
            ("/api/extensions/docmgr/projects/{project_id}/outputs", "GET"),
            ("/api/extensions/docmgr/projects/{project_id}/outputs/content", "GET"),
            ("/api/extensions/docmgr/projects/{project_id}/outputs", "PUT"),
            ("/api/extensions/docmgr/projects/{project_id}/versions", "GET"),
            ("/api/extensions/docmgr/projects/{project_id}/versions/{version_id}", "GET"),
            ("/api/extensions/docmgr/projects/{project_id}/versions/{version_id}/restore", "POST"),
        ]:
            assert (path, method) in routes, f"missing route {method} {path}"


class TestReadProjectOutput:
    @pytest.mark.asyncio
    async def test_reads_content_and_mtime(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "doc.md").write_text("# hello")
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.read_project_output(AsyncMock(), pid, "T1", "doc.md")
        assert res["content"] == "# hello"
        assert isinstance(res["mtime"], float)

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(FileNotFoundError):
                await AIDocumentService.read_project_output(AsyncMock(), pid, "T1", "ghost.md")

    @pytest.mark.asyncio
    async def test_path_escape_rejected(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(ValueError):
                await AIDocumentService.read_project_output(
                    AsyncMock(), pid, "T1", "../../etc/passwd",
                )

    @pytest.mark.asyncio
    async def test_prefix_sibling_path_escape_rejected(self, tmp_path: Path):
        """I1 回归：../outputs_archive/secret 不能绕过 startswith（前缀兄弟目录）。"""
        from app.extensions.docmgr.service import AIDocumentService

        uid, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(uid) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out.parent / "outputs_archive").mkdir()
        with patch("deerflow.config.paths.Paths") as mp:
            mp.return_value.base_dir = tmp_path
            with pytest.raises(ValueError):
                await AIDocumentService.read_project_output(
                    AsyncMock(), pid, "T1", "../outputs_archive/secret.md",
                )
