"""Regression tests: chat-originated docs must be filed into the folder tree.

Bug: ``AIDocumentService.sync_thread_files`` (the active chat auto-sync path)
created ``file_ref`` docs with ``folder_id=NULL`` → homeless, never appeared
under 文档空间 → 我的文档. Same for ``create`` (save-to-doc). These tests lock
the fix: docs get a ``folder_id`` and a per-thread subfolder (and a personal
root "我的文档" is auto-created when missing).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.extensions.docmgr.service import AIDocumentService
from app.extensions.models import AIDocument, Folder


class _Result:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return []


class _FakeDb:
    """Minimal async session: pops canned scalars per execute(), records add()s."""

    def __init__(self, scalars=None):
        self._q = list(scalars or [])
        self.added = []

    async def execute(self, stmt):
        return _Result(self._q.pop(0) if self._q else None)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


@pytest.mark.asyncio
async def test_sync_files_docs_under_auto_created_personal_root(tmp_path):
    """Fresh user (no 我的文档 root) → root + subfolder auto-created, doc filed."""
    user_id = uuid4()
    sandbox = tmp_path
    (sandbox / "report.md").write_text("# 消防设计专篇", encoding="utf-8")

    db = _FakeDb()  # every execute() returns None → nothing exists yet
    with patch.object(AIDocumentService, "_get_thread_title", new=AsyncMock(return_value="消防专篇")):
        result = await AIDocumentService.sync_thread_files(db, user_id, "thread-1", str(sandbox))

    docs = [o for o in db.added if isinstance(o, AIDocument)]
    folders = [o for o in db.added if isinstance(o, Folder)]

    assert result == {"synced": 1, "skipped": 0}
    assert len(docs) == 1
    assert docs[0].folder_id is not None  # the bug: was None before the fix
    # personal root auto-created + thread subfolder created under it
    assert {f.name for f in folders} == {"我的文档", "消防专篇"}
    sub = next(f for f in folders if f.name == "消防专篇")
    assert docs[0].folder_id == sub.id


@pytest.mark.asyncio
async def test_sync_files_files_under_existing_root_no_duplicate(tmp_path):
    """When a personal root already exists, don't create a second one."""
    user_id = uuid4()
    sandbox = tmp_path
    (sandbox / "a.md").write_text("x", encoding="utf-8")

    existing_root = Folder(name="我的文档", owner_id=user_id, parent_id=None)
    existing_root.id = uuid4()
    # execute() order: project_id(None), root(existing), subfolder(None), existing-doc(None)
    db = _FakeDb([None, existing_root, None, None])
    with patch.object(AIDocumentService, "_get_thread_title", new=AsyncMock(return_value="消防专篇")):
        await AIDocumentService.sync_thread_files(db, user_id, "thread-1", str(sandbox))

    docs = [o for o in db.added if isinstance(o, AIDocument)]
    folders = [o for o in db.added if isinstance(o, Folder)]

    assert len(folders) == 1  # only the subfolder, no duplicate root
    assert folders[0].name == "消防专篇"
    assert docs[0].folder_id == folders[0].id


@pytest.mark.asyncio
async def test_create_files_thread_doc_under_subfolder():
    """create() with source_thread_id resolves a folder_id (save-to-doc path)."""
    from app.extensions.schemas import AIDocumentCreate

    user_id = uuid4()
    db = _FakeDb([None, None, None])  # project(None), root(None→create), subfolder(None→create)
    with patch.object(AIDocumentService, "_get_thread_title", new=AsyncMock(return_value="消防专篇")):
        doc = await AIDocumentService.create(
            db,
            user_id,
            AIDocumentCreate(title="大连石化消防设计专篇", source_thread_id="thread-1"),
        )

    folders = [o for o in db.added if isinstance(o, Folder)]
    assert doc.folder_id is not None  # the bug: was None before the fix
    assert {f.name for f in folders} == {"我的文档", "消防专篇"}


@pytest.mark.asyncio
async def test_sync_files_skips_tool_results_and_hidden_paths(tmp_path):
    """Internal externalized tool outputs (.tool-results/) and other hidden paths
    under the sandbox must NOT be synced into 文档空间 — they're framework
    intermediates (large MCP returns auto-dumped by tool_output_budget_middleware),
    not deliverables. Regression for bug-410."""
    user_id = uuid4()
    sandbox = tmp_path
    (sandbox / "report.md").write_text("# 报告", encoding="utf-8")
    (sandbox / ".tool-results").mkdir()
    (sandbox / ".tool-results" / "knowledge-factory_kf_resolve_template-abc.txt").write_text(
        '{"found": true, "sections": []}', encoding="utf-8"
    )
    (sandbox / ".cache").mkdir()
    (sandbox / ".cache" / "internal.json").write_text("{}", encoding="utf-8")

    db = _FakeDb()
    with patch.object(AIDocumentService, "_get_thread_title", new=AsyncMock(return_value="消防专篇")):
        result = await AIDocumentService.sync_thread_files(db, user_id, "thread-1", str(sandbox))

    docs = [o for o in db.added if isinstance(o, AIDocument)]
    titles = {d.title for d in docs}
    # Only the deliverable is synced; .tool-results/ and .cache/ excluded
    assert titles == {"report.md"}
    assert result["synced"] == 1
