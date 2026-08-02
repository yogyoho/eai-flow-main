"""Tests for personal-doc version history (EAI-CUSTOM C10).

Covers: route registration, restore-writes-file, and the cap-at-20 pruning.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.sql.dml import Delete

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
        id=uuid4(), user_id=user_id, thread_id="tid-1", rel_path="doc.md",
        content="# restored", label=None, created_at=None,
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
