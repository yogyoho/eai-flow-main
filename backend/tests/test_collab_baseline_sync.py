"""协同写作链审计 B5/B6/B8/B9 修复的回归测试。

- B5: open_chapter_document P1 命中已有文档时的基线对账（collab_documents 无行才刷新）。
- B6: POST /projects/{pid}/documents/{did}/sync-baseline —— [chapter:] 解析/回写/
      非成员 403/非章节文档 400/文档跨项目 404。
- B8: 标题行匹配（_title_in_headings）+ P2 正文误命中回落 fallback。
- B9: fallback 建档补 chapter_id + folder_id（项目根文件夹）。

仓库惯例：DB 一律 mock（AsyncMock 按 SQL 形状路由），identity 经 patch_identity。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from rbac_helpers import build_app, fake_identity, make_user, patch_identity

from app.extensions.auth import admin as _admin_mod
from app.extensions.project import service as project_service
from app.extensions.project.routers import router as project_router

PID = uuid4()
DID = uuid4()
CHID = uuid4()
UID = uuid4()


# ── fixtures ──


@pytest.fixture(autouse=True)
def _no_superadmin(monkeypatch):
    async def _false(db, user_id):  # noqa: ARG001
        return False

    monkeypatch.setattr(_admin_mod, "is_superadmin", _false)


def _doc_ns(doc_id, title, content, project_id=PID):
    """_doc_info 所需字段的 duck-typed AIDocument 行。"""
    return SimpleNamespace(
        id=doc_id,
        title=title,
        content=content,
        project_id=project_id,
        status="active",
        doc_type="document",
        source_thread_id=None,
        folder="project-chapters",
        file_ref_path=None,
        file_size=None,
        file_mime=None,
        created_at=None,
        updated_at=None,
    )


def _chapter_ns(chapter_id=CHID, title="第一章 总则", content="# 第一章 总则\n\n新稿内容"):
    return SimpleNamespace(
        id=chapter_id,
        project_id=PID,
        parent_id=None,
        title=title,
        level=1,
        sort_order=0,
        status="draft",
        content=content,
        word_count_current=0,
    )


def _service_db(*, chapter, p1_doc, collab_row=None, p2_docs=None, folder_id=None):
    """按 SQL 形状路由的 AsyncMock session（service 层用）。

    - project_chapters → chapter
    - ai_documents     → scalar_one_or_none=p1_doc；scalars().all()=p2_docs（P1/P2/P3 同表）
    - collab_documents → collab_row
    - folders          → scalar_one_or_none=folder_id（B9 根文件夹查询）；scalars().all()=[]
    - report_projects  → all()=[]（ensure_project_root_folders 的 projects 查询）
    - 其它             → 空
    """
    db = AsyncMock()
    db.add = MagicMock()  # Session.add 是同步方法，勿用 AsyncMock（避免 coroutine 告警）

    def _execute(stmt, *a, **k):  # noqa: ARG001
        sql = str(stmt).lower()
        result = MagicMock()
        if "collab_documents" in sql:
            result.scalar_one_or_none.return_value = collab_row
        elif "project_chapters" in sql:
            result.scalar_one_or_none.return_value = chapter
        elif "ai_documents" in sql:
            result.scalar_one_or_none.return_value = p1_doc
            result.scalars.return_value.all.return_value = list(p2_docs or [])
        elif "folders" in sql:
            result.scalar_one_or_none.return_value = folder_id
            result.scalars.return_value.all.return_value = []
            result.all.return_value = []
        elif "report_projects" in sql:
            result.all.return_value = []
            result.scalars.return_value.all.return_value = []
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    return db


# ── B5: P1 命中后的基线对账 ──


class TestB5ReconcileBaseline:
    @pytest.mark.asyncio
    async def test_refreshes_baseline_when_no_collab_row(self):
        """collab_documents 无行 + 章节新稿 ≠ doc.content → 刷新基线并提交。"""
        chapter = _chapter_ns(content="# 第一章 总则\n\nMCP 重写后的新稿")
        doc = _doc_ns(DID, f"[chapter:{CHID}] 第一章 总则", "旧稿")
        db = _service_db(chapter=chapter, p1_doc=doc, collab_row=None)

        info = await project_service.open_chapter_document(db, PID, CHID, user_id=UID)

        assert doc.content == "# 第一章 总则\n\nMCP 重写后的新稿"
        assert db.commit.await_count == 1
        assert info["content"] == "# 第一章 总则\n\nMCP 重写后的新稿"

    @pytest.mark.asyncio
    async def test_skips_refresh_when_collab_row_exists(self):
        """编辑器已接管（有 collab 行，D6 语义）→ collab 存储为准，不动基线。"""
        chapter = _chapter_ns(content="章节新稿")
        doc = _doc_ns(DID, f"[chapter:{CHID}] 第一章 总则", "编辑器已接管的内容")
        db = _service_db(chapter=chapter, p1_doc=doc, collab_row=object())

        await project_service.open_chapter_document(db, PID, CHID, user_id=UID)

        assert doc.content == "编辑器已接管的内容"
        assert db.commit.await_count == 0

    @pytest.mark.asyncio
    async def test_skips_refresh_when_content_identical(self):
        """章节内容与文档基线一致 → 不写库。"""
        same = "# 第一章 总则\n\n一致的内容"
        chapter = _chapter_ns(content=same)
        doc = _doc_ns(DID, f"[chapter:{CHID}] 第一章 总则", same)
        db = _service_db(chapter=chapter, p1_doc=doc, collab_row=None)

        await project_service.open_chapter_document(db, PID, CHID, user_id=UID)

        assert doc.content == same
        assert db.commit.await_count == 0


# ── B8: 标题行匹配 ──


class TestB8TitleInHeadings:
    def test_heading_line_matches(self):
        assert project_service._title_in_headings("# 第一章 总则\n\n正文", "第一章 总则")
        assert project_service._title_in_headings("## 1.2 设计说明", "1.2 设计说明")
        assert project_service._title_in_headings("###A.2 通风", "A.2 通风") is False  # 无空格不算标题行

    def test_body_mention_does_not_match(self):
        """标题只出现在正文段落 → 不命中（修复全文包含误绑定）。"""
        body = "本章依据《设计规范》编写。\n\n如第一章 总则 所述，各项指标需满足要求。\n\n| 引用 | 第一章 总则 |\n"
        assert project_service._title_in_headings(body, "第一章 总则") is False

    @pytest.mark.asyncio
    async def test_p2_body_only_falls_through_to_fallback(self):
        """P2 候选正文含标题但无标题行 → 不绑定，回落 fallback 新建。"""
        chapter = _chapter_ns()
        body_only_doc = _doc_ns(
            uuid4(),
            "整本报告",
            "报告正文里提到了 第一章 总则 四个字，但不是标题行。",
        )
        # P1 无 chapter 前缀文档；P2 候选只有 body_only_doc
        db = _service_db(chapter=chapter, p1_doc=None, p2_docs=[body_only_doc], folder_id=None)

        info = await project_service.open_chapter_document(db, PID, CHID, user_id=UID)

        assert db.add.call_count >= 1
        added = db.add.call_args[0][0]
        assert added.title == f"[chapter:{CHID}] 第一章 总则"
        assert info["document_id"] == str(added.id)


# ── B9: fallback 建档补 chapter_id + folder_id ──


class TestB9FallbackFields:
    @pytest.mark.asyncio
    async def test_fallback_sets_chapter_id_and_folder_id(self):
        chapter = _chapter_ns()
        root_folder_id = uuid4()
        db = _service_db(chapter=chapter, p1_doc=None, p2_docs=[], folder_id=root_folder_id)

        info = await project_service.open_chapter_document(db, PID, CHID, user_id=UID)

        added = db.add.call_args[0][0]
        assert added.chapter_id == CHID
        assert added.folder_id == root_folder_id
        assert added.project_id == PID
        assert info["chapter_id"] == str(CHID)


# ── B6: sync-baseline 端点 ──


def _sync_route_db(*, doc_row=None, chapter_row=None, member_row=object()):
    """sync-baseline 路由用的 mock db：policies 空、成员行、AIDocument(db.get)、章节查询。"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=doc_row)

    def _execute(stmt, *a, **k):  # noqa: ARG001
        sql = str(stmt).lower()
        result = MagicMock()
        if "policies" in sql:
            result.scalars.return_value.all.return_value = []
        elif "project_members" in sql:
            result.scalar_one_or_none.return_value = member_row
        elif "project_chapters" in sql:
            result.scalar_one_or_none.return_value = chapter_row
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    return db


def _route_doc(project_id=PID):
    return SimpleNamespace(
        id=DID,
        project_id=project_id,
        title=f"[chapter:{CHID}] 第一章 总则",
        content="旧稿",
    )


class TestB6SyncBaselineRoute:
    def _client(self, db, monkeypatch):
        patch_identity(monkeypatch, fake_identity(role_code="user", member_projects=[str(PID)]))
        return build_app(project_router, user=make_user(), db=db)

    def test_parses_chapter_prefix_and_writes_back(self, monkeypatch):
        chapter = _chapter_ns()
        doc = _route_doc()
        db = _sync_route_db(doc_row=doc, chapter_row=chapter)
        tc = self._client(db, monkeypatch)

        body = "# 第一章 总则\n\n编辑器里的最新内容"
        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": body})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["chapter_id"] == str(CHID)
        assert data["word_count"] == len(body)
        assert chapter.content == body
        assert chapter.word_count_current == len(body)
        assert doc.content == body
        assert db.commit.await_count == 1

    def test_400_for_non_chapter_document(self, monkeypatch):
        doc = _route_doc()
        doc.title = "普通文档（无 chapter 前缀）"
        db = _sync_route_db(doc_row=doc)
        tc = self._client(db, monkeypatch)

        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": "x"})

        assert resp.status_code == 400

    def test_400_for_malformed_chapter_prefix(self, monkeypatch):
        doc = _route_doc()
        doc.title = "[chapter:not-a-uuid] 坏前缀"
        db = _sync_route_db(doc_row=doc)
        tc = self._client(db, monkeypatch)

        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": "x"})

        assert resp.status_code == 400

    def test_404_for_document_outside_project(self, monkeypatch):
        doc = _route_doc(project_id=uuid4())  # 属于别的项目
        db = _sync_route_db(doc_row=doc)
        tc = self._client(db, monkeypatch)

        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": "x"})

        assert resp.status_code == 404

    def test_404_for_missing_chapter(self, monkeypatch):
        db = _sync_route_db(doc_row=_route_doc(), chapter_row=None)
        tc = self._client(db, monkeypatch)

        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": "x"})

        assert resp.status_code == 404

    def test_403_for_non_member(self, monkeypatch):
        db = _sync_route_db(doc_row=_route_doc(), member_row=None)  # 非成员
        tc = self._client(db, monkeypatch)

        resp = tc.post(f"/api/extensions/project/projects/{PID}/documents/{DID}/sync-baseline", json={"content": "x"})

        assert resp.status_code == 403


# SQL 文本依赖 SQLAlchemy 渲染表名——冒烟断言防止上游改 ORM 命名后 mock 静默失配
def test_collab_documents_table_present_in_metadata():
    from sqlalchemy import select as _select

    from app.extensions.docmgr.collab_models import CollabDocument

    assert "collab_documents" in str(_select(CollabDocument.doc_id)).lower()
