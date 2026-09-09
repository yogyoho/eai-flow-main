"""Tests for personal-doc version history (EAI-CUSTOM C10).

Covers: route registration, restore-writes-file, and the cap-at-20 pruning.
Also covers the collab (在线协同) restore endpoint pre-backup (EAI-CUSTOM bug B12).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.sql.dml import Delete

from app.extensions.docmgr.collab_routers import restore_version
from app.extensions.docmgr.collab_service import VersionService
from app.extensions.docmgr.routers import router
from app.extensions.docmgr.service import AIDocumentService


def _routes():
    return {(r.path, m) for r in router.routes for m in (getattr(r, "methods", None) or set())}


def test_version_routes_registered():
    """全部 4 个版本历史路由必须注册，否则前端 404。"""
    routes = _routes()
    for path, method in [
        ("/api/extensions/docmgr/personal-docs/{thread_id}/versions", "POST"),
        ("/api/extensions/docmgr/personal-docs/{thread_id}/versions", "GET"),
        ("/api/extensions/docmgr/personal-docs/versions/{version_id}", "GET"),
        ("/api/extensions/docmgr/personal-docs/versions/{version_id}/restore", "POST"),
    ]:
        assert (path, method) in routes, f"missing route {method} {path}"


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
    """Configure a mock AsyncSession that captures added versions and assigns id on flush."""
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


@pytest.mark.asyncio
async def test_restore_personal_version_writes_file():
    """restore 必须把版本内容写回 outputs 文件。"""
    db = AsyncMock()
    user_id = uuid4()
    version = _FakeVersion(
        id=uuid4(),
        user_id=user_id,
        thread_id="tid-1",
        rel_path="doc.md",
        content="# restored",
        label=None,
        created_at=None,
    )
    db.execute = AsyncMock(return_value=_FakeResult([version]))
    with patch.object(AIDocumentService, "write_personal_output", new=AsyncMock()) as mock_write:
        result = await AIDocumentService.restore_personal_version(db, user_id, version.id)
    assert result["content"] == "# restored"
    mock_write.assert_awaited_once_with(db, user_id, "tid-1", "doc.md", "# restored")


@pytest.mark.asyncio
async def test_restore_personal_version_missing_returns_none():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeResult([]))
    result = await AIDocumentService.restore_personal_version(db, uuid4(), uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_create_personal_version_caps_history():
    """超过每文件上限时发出 DELETE 裁剪旧版本。"""
    db = _fake_version_db(old_ids=[uuid4() for _ in range(21)])
    vid = await AIDocumentService.create_personal_version(db, uuid4(), "tid-1", "doc.md", "content", "标签")
    assert vid is not None
    delete_calls = [c for c in db.execute.await_args_list if isinstance(c.args[0], Delete)]
    assert len(delete_calls) == 1, "超过上限时应发出一次 DELETE 裁剪"


@pytest.mark.asyncio
async def test_create_personal_version_no_delete_when_within_limit():
    """未超过上限时不发 DELETE。"""
    db = _fake_version_db(old_ids=[])
    vid = await AIDocumentService.create_personal_version(db, uuid4(), "tid-1", "doc.md", "content")
    assert vid is not None
    delete_calls = [c for c in db.execute.await_args_list if isinstance(c.args[0], Delete)]
    assert len(delete_calls) == 0


# ── EAI-CUSTOM (bug B12 协同链审计): collab restore 前置备份 ────────────────────


@pytest.mark.asyncio
async def test_collab_restore_creates_pre_restore_backup_before_overwrite():
    """restore 覆写 collab_documents.yjs_doc 前必须先落 Pre-restore backup 版本。"""
    doc_id = uuid4()
    user_id = uuid4()
    fake_doc = SimpleNamespace(id=doc_id, content="# current markdown", user_id=user_id)
    collab = SimpleNamespace(yjs_doc=b"current-yjs-bytes", version=3, last_editor_id=None)
    db = AsyncMock()
    db.get = AsyncMock(return_value=collab)

    with (
        patch.object(AIDocumentService, "get_by_id", new=AsyncMock(return_value=fake_doc)),
        patch.object(
            VersionService,
            "get_version",
            new=AsyncMock(return_value={"snapshot": b"target-yjs", "snapshot_text": "target text", "version": 7}),
        ),
        patch.object(VersionService, "create_version", new=AsyncMock(return_value={"version": 8, "id": uuid4()})) as mock_create,
    ):
        resp = await restore_version(doc_id, 7, db=db, current_user=SimpleNamespace(id=user_id))

    assert mock_create.await_count == 2, "应有两条版本记录: Pre-restore backup + Restored to version N"
    pre, post = mock_create.await_args_list[0], mock_create.await_args_list[1]
    # 前置备份携带恢复前的当前 yjs_doc，而非目标快照
    assert pre.args[3] == b"current-yjs-bytes"
    assert pre.kwargs["summary"] == "Pre-restore backup"
    # 后置标记携带目标快照
    assert post.args[3] == b"target-yjs"
    assert post.kwargs["summary"] == "Restored to version 7"
    # yjs_doc 已被覆写为目标快照
    assert collab.yjs_doc == b"target-yjs"
    # 恢复响应提示在线协作者刷新
    assert "刷新" in resp.message


@pytest.mark.asyncio
async def test_collab_restore_without_existing_collab_row_skips_pre_backup():
    """无 collab_documents 行（从未协同编辑过）时没有当前态可备份，仅落恢复标记一条。"""
    doc_id = uuid4()
    user_id = uuid4()
    fake_doc = SimpleNamespace(id=doc_id, content=None, user_id=user_id)
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = lambda v: None  # sync，避免 AsyncMock 产生未 await 的协程告警

    with (
        patch.object(AIDocumentService, "get_by_id", new=AsyncMock(return_value=fake_doc)),
        patch.object(
            VersionService,
            "get_version",
            new=AsyncMock(return_value={"snapshot": b"target-yjs", "snapshot_text": None, "version": 2}),
        ),
        patch.object(VersionService, "create_version", new=AsyncMock(return_value={"version": 3, "id": uuid4()})) as mock_create,
    ):
        resp = await restore_version(doc_id, 2, db=db, current_user=SimpleNamespace(id=user_id))

    assert mock_create.await_count == 1
    call = mock_create.await_args_list[0]
    assert call.kwargs["summary"] == "Restored to version 2"
    assert "刷新" in resp.message
