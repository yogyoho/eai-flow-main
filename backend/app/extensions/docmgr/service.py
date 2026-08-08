"""AI Document service for extensions module."""

import json
import logging
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import AIDocument, ProjectMember
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentResponse,
    AIDocumentUpdate,
)

if TYPE_CHECKING:
    # Type-only import — avoids a runtime import cycle at module load time.
    from app.extensions.auth.engine import FilterRule

logger = logging.getLogger(__name__)


class AIDocumentService:
    """AI Document service."""

    @staticmethod
    async def list_docs(
        db: AsyncSession,
        user_id: UUID,
        folder: str | None = None,
        folder_id: UUID | None = None,
        starred: bool | None = None,
        shared: bool | None = None,
        doc_type: str | None = None,
        project_scope: str | None = None,
        project_id: UUID | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 12,
        scope: "FilterRule | None" = None,
    ) -> tuple[list[AIDocument], int]:
        """List documents with filters.

        Shows user's own documents plus documents from projects the user is a member of.
        project_scope: "personal" = no project, "project" = has project, None = both.
        project_id: filter to a specific project (takes precedence over project_scope).

        EAI-CUSTOM (Task 13): When *scope* is provided (router path), the visibility
        predicate is taken from the ABAC data-scope engine. For roles bound to
        doc_owner + doc_project_member (the default for every role carrying
        doc:read), the produced SQL is identical to the hand-rolled clause below:
            (user_id == caller) OR (project_id IN member_projects)
        — identity.member_projects is populated from the same ProjectMember query.
        When *scope* is None (tests, internal callers), the original hand-rolled
        clause runs unchanged for backward compatibility.
        """
        if scope is not None:
            # Route through the scope engine so deny_data_scopes can later narrow
            # document visibility. Superadmin gets allow_all via with_data_scope.
            column_map = {
                "user_id": AIDocument.user_id,
                "project_id": AIDocument.project_id,
            }
            visibility_filter = scope.to_sqlalchemy(AIDocument, column_map)
        else:
            # Backward-compat branch — original hand-rolled visibility clause.
            own_docs = AIDocument.user_id == user_id
            my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
            project_docs = AIDocument.project_id.in_(my_project_ids)
            visibility_filter = or_(own_docs, project_docs)

        query = select(AIDocument).where(visibility_filter)
        count_query = select(func.count(AIDocument.id)).where(visibility_filter)

        if folder is not None:
            query = query.where(AIDocument.folder == folder)
            count_query = count_query.where(AIDocument.folder == folder)

        if folder_id is not None:
            query = query.where(AIDocument.folder_id == folder_id)
            count_query = count_query.where(AIDocument.folder_id == folder_id)

        if starred is not None:
            query = query.where(AIDocument.is_starred == starred)
            count_query = count_query.where(AIDocument.is_starred == starred)

        if shared is not None:
            query = query.where(AIDocument.is_shared == shared)
            count_query = count_query.where(AIDocument.is_shared == shared)

        if doc_type is not None:
            query = query.where(AIDocument.doc_type == doc_type)
            count_query = count_query.where(AIDocument.doc_type == doc_type)

        if project_scope == "personal":
            query = query.where(AIDocument.project_id.is_(None))
            count_query = count_query.where(AIDocument.project_id.is_(None))
        elif project_scope == "project":
            query = query.where(AIDocument.project_id.isnot(None))
            count_query = count_query.where(AIDocument.project_id.isnot(None))

        if project_id is not None:
            query = query.where(AIDocument.project_id == project_id)
            count_query = count_query.where(AIDocument.project_id == project_id)

        if q is not None:
            search_filter = AIDocument.title.ilike(f"%{q}%")
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        query = query.offset(skip).limit(limit).order_by(AIDocument.updated_at.desc())

        result = await db.execute(query)
        documents = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(documents), total

    @staticmethod
    async def get_by_id(db: AsyncSession, doc_id: UUID, user_id: UUID) -> AIDocument | None:
        """Get document by ID — accessible by owner or project member.

        Backward-compat hand-rolled visibility clause; retained for internal
        callers/tests that don't have a scope in hand. Router by-id endpoints
        should call ``get_by_id_scoped`` instead so ``deny_data_scopes`` can
        narrow by-id visibility (mirrors Task 13's ``list_docs`` wiring).
        """
        own_docs = AIDocument.user_id == user_id
        my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        project_docs = AIDocument.project_id.in_(my_project_ids)
        stmt = select(AIDocument).where(AIDocument.id == doc_id, or_(own_docs, project_docs))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_scoped(
        db: AsyncSession,
        doc_id: UUID,
        scope: "FilterRule",
    ) -> AIDocument | None:
        """Load a document by id ONLY if *scope* permits it.

        EAI-CUSTOM (Task L2 / follow-up to Task 13): unifies by-id access with
        ``list_docs``'s ``with_data_scope("docmgr")`` FilterRule so list and
        by-id enforce identical visibility. For roles bound to
        ``doc_owner`` + ``doc_project_member`` (the default for every role
        carrying ``doc:read``), the compiled SQL is identical to the prior
        hand-rolled clause:
            (user_id == caller) OR (project_id IN member_projects)
        Superadmin gets ``allow_all`` via ``with_data_scope``. Returns None if
        the document does not exist or is out of scope; callers raise 404 to
        avoid existence leakage. Mirrors ``_load_kb_scoped`` in
        ``app/extensions/knowledge/routers.py``.
        """
        column_map = {
            "user_id": AIDocument.user_id,
            "project_id": AIDocument.project_id,
        }
        stmt = (
            select(AIDocument)
            .where(AIDocument.id == doc_id)
            .where(scope.to_sqlalchemy(AIDocument, column_map))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, data: AIDocumentCreate) -> AIDocument:
        """Create a new document."""
        # Auto-detect project_id from thread if not explicitly provided
        project_id = data.project_id
        if not project_id and data.source_thread_id:
            project_id = await AIDocumentService._detect_project_from_thread(db, data.source_thread_id)

        # File the doc into the per-thread subfolder when it originates from a
        # chat thread, so it appears in 文档空间 instead of being homeless.
        folder_id = None
        folder_str = data.folder
        if data.source_thread_id:
            folder_name = await AIDocumentService._get_thread_title(db, data.source_thread_id)
            folder_id, folder_str = await AIDocumentService._ensure_subfolder(
                db, user_id, folder_name, project_id,
            )

        document = AIDocument(
            user_id=user_id,
            title=data.title,
            content=data.content,
            folder=folder_str,
            folder_id=folder_id,
            source_thread_id=data.source_thread_id,
            project_id=project_id,
            doc_type=data.doc_type,
            file_ref_path=data.file_ref_path,
            file_size=data.file_size,
            file_mime=data.file_mime,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def update(db: AsyncSession, doc: AIDocument, data: AIDocumentUpdate) -> AIDocument:
        """Update an existing document."""
        if data.title is not None:
            doc.title = data.title
        if data.content is not None:
            doc.content = data.content
        if data.folder is not None:
            doc.folder = data.folder
        if data.is_starred is not None:
            doc.is_starred = data.is_starred
        if data.is_shared is not None:
            doc.is_shared = data.is_shared
        if data.status is not None:
            doc.status = data.status
        if data.doc_type is not None:
            doc.doc_type = data.doc_type
        if data.file_ref_path is not None:
            doc.file_ref_path = data.file_ref_path
        if data.file_size is not None:
            doc.file_size = data.file_size
        if data.file_mime is not None:
            doc.file_mime = data.file_mime

        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def delete(db: AsyncSession, doc: AIDocument) -> None:
        """Delete a document."""
        await db.delete(doc)
        await db.commit()

    @staticmethod
    async def list_folders(
        db: AsyncSession,
        user_id: UUID,
        project_scope: str | None = None,
        scope: "FilterRule | None" = None,
    ) -> list[str]:
        """List all folders for a user (own + project docs)."""
        if scope is not None:
            # EAI-CUSTOM (F3): 与 list_docs 同一 scope 引擎，deny_data_scopes 可窄化文件夹
            column_map = {
                "user_id": AIDocument.user_id,
                "project_id": AIDocument.project_id,
            }
            visibility_filter = scope.to_sqlalchemy(AIDocument, column_map)
        else:
            own_docs = AIDocument.user_id == user_id
            my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
            project_docs = AIDocument.project_id.in_(my_project_ids)
            visibility_filter = or_(own_docs, project_docs)

        stmt = select(AIDocument.folder).where(visibility_filter)

        if project_scope == "personal":
            stmt = stmt.where(AIDocument.project_id.is_(None))
        elif project_scope == "project":
            stmt = stmt.where(AIDocument.project_id.isnot(None))

        stmt = stmt.distinct()
        result = await db.execute(stmt)
        folders = [row[0] for row in result.all()]
        return folders

    @staticmethod
    async def to_response(doc: AIDocument) -> AIDocumentResponse:
        """Convert document model to response."""
        return AIDocumentResponse(
            id=doc.id,
            user_id=doc.user_id,
            source_thread_id=doc.source_thread_id,
            project_id=doc.project_id,
            title=doc.title,
            content=doc.content,
            folder=doc.folder,
            folder_id=doc.folder_id,
            is_starred=doc.is_starred,
            is_shared=doc.is_shared,
            status=doc.status,
            doc_type=doc.doc_type,
            file_ref_path=doc.file_ref_path,
            file_size=doc.file_size,
            file_mime=doc.file_mime,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    @staticmethod
    async def to_detail_response(doc: AIDocument) -> AIDocumentResponse:
        """Convert document model to detailed response (includes content)."""
        return await AIDocumentService.to_response(doc)

    @staticmethod
    def _is_text_mime(mime: str | None) -> bool:
        """文本 mime 判定：text/* 及常见文本 application 类型；None/'' → False。

        EAI-CUSTOM: 从直接映射重构中恢复的助手（原被删，检测逻辑前移到前端 isBinaryFile）。
        """
        if not mime:
            return False
        if mime.startswith("text/"):
            return True
        return mime in {
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-yaml",
            "application/x-sh",
            "application/x-python",
            "image/svg+xml",
        }

    @staticmethod
    async def move_to_documents(db: AsyncSession, doc: AIDocument) -> AIDocument:
        """Move a file_ref document to '我的文档' by reading file content into DB."""
        if doc.doc_type != "file_ref":
            return doc
        if doc.file_ref_path and os.path.exists(doc.file_ref_path):
            if AIDocumentService._is_text_mime(doc.file_mime):
                with open(doc.file_ref_path, encoding="utf-8", errors="replace") as f:
                    doc.content = f.read()
            else:
                doc.content = json.dumps({"type": "binary_ref", "file_ref_path": doc.file_ref_path, "file_mime": doc.file_mime})
        else:
            doc.content = json.dumps({"type": "file_missing", "file_ref_path": doc.file_ref_path})

        doc.doc_type = "document"
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def batch_delete(db: AsyncSession, user_id: UUID, doc_ids: list[UUID]) -> int:
        """Delete multiple documents. Returns count deleted."""
        if not doc_ids:
            return 0
        if len(doc_ids) > 50:
            raise ValueError("Batch delete limited to 50 documents")
        stmt = select(AIDocument).where(
            AIDocument.user_id == user_id,
            AIDocument.id.in_(doc_ids),
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()
        count = 0
        for doc in docs:
            await db.delete(doc)
            count += 1
        await db.commit()
        return count

    @staticmethod
    async def rename(db: AsyncSession, doc: AIDocument, new_title: str) -> AIDocument:
        """Rename a document. For file_ref, also rename physical file."""
        if doc.doc_type == "file_ref" and doc.file_ref_path:
            old_path = Path(doc.file_ref_path)
            if old_path.exists():
                new_path = old_path.parent / new_title
                old_path.rename(new_path)
                doc.file_ref_path = str(new_path)
        doc.title = new_title
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def read_file_content(doc: AIDocument) -> str | None:
        """Read file content for preview. Returns None for missing files."""
        if not doc.file_ref_path or not os.path.exists(doc.file_ref_path):
            return None
        file_size = os.path.getsize(doc.file_ref_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return None
        with open(doc.file_ref_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    @staticmethod
    async def _get_thread_title(db: AsyncSession, thread_id: str) -> str:
        """Get thread display name.

        The ``threads_meta`` table lives in the Gateway SQLite database, not
        the extensions PostgreSQL database that *db* is connected to.  Querying
        it through *db* would abort the PostgreSQL transaction.  Read from the
        Gateway's SQLite file directly instead.
        """
        try:
            import sqlite3

            from deerflow.config.paths import Paths

            paths = Paths()
            db_path = paths.base_dir / "data" / "deerflow.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                try:
                    row = conn.execute(
                        "SELECT display_name FROM threads_meta WHERE thread_id = ?",
                        (thread_id,),
                    ).fetchone()
                    if row and row[0]:
                        return row[0]
                finally:
                    conn.close()
        except Exception:
            pass

        return thread_id[:8]

    @staticmethod
    async def list_personal_outputs(
        db: AsyncSession,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> dict:
        """分页扫描线程 outputs/：先按 created_at 排序全部线程（不扫文件），

        切片后只对分页内的线程扫描文件详情。返回 {threads, total, has_more}。
        """
        import sqlite3
        from datetime import datetime as _dt

        from deerflow.config.paths import Paths
        from deerflow.runtime.user_context import get_effective_user_id

        paths = Paths()
        effective_uid = get_effective_user_id()
        threads_dir = paths.base_dir / "users" / effective_uid / "threads"
        if not threads_dir.is_dir():
            threads_dir = paths.base_dir / "users" / str(user_id) / "threads"
        if not threads_dir.is_dir():
            return {"threads": [], "total": 0, "has_more": False}

        # created_at + display_name from threads_meta（一次 sqlite 查询）
        display_names: dict[str, str] = {}
        thread_created: dict[str, str] = {}
        try:
            meta_db = paths.base_dir / "data" / "deerflow.db"
            if meta_db.exists():
                conn = sqlite3.connect(str(meta_db))
                try:
                    rows = conn.execute(
                        "SELECT thread_id, display_name, created_at FROM threads_meta"
                    ).fetchall()
                    for tid, dn, ca in rows:
                        if dn:
                            display_names[tid] = dn
                        if ca:
                            thread_created[tid] = ca
                finally:
                    conn.close()
        except Exception:
            pass

        # 第一遍：收集所有线程目录（只检查 outputs 目录存在，不扫文件）+ 排序
        all_threads: list[dict] = []
        for thread_dir in threads_dir.iterdir():
            if not thread_dir.is_dir():
                continue
            if not (thread_dir / "user-data" / "outputs").is_dir():
                continue
            tid = thread_dir.name
            all_threads.append({
                "thread_id": tid,
                "thread_dir": thread_dir,
                "_created_at": thread_created.get(tid, ""),
                "display_name": display_names.get(tid, ""),
            })

        def _sort_key(t: dict) -> float:
            ca = t.get("_created_at")
            if ca:
                try:
                    if isinstance(ca, (int, float)):
                        return float(ca)
                    return _dt.fromisoformat(str(ca).replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
            return 0.0

        # 次级 key thread_id 保证排序稳定（created_at 相同/为空时分页不重复/遗漏）
        all_threads.sort(key=lambda t: (_sort_key(t), t["thread_id"]), reverse=True)

        total = len(all_threads)
        page = all_threads[skip:skip + limit]
        has_more = skip + limit < total

        if not page:
            return {"threads": [], "total": total, "has_more": has_more}

        # star/share：只查分页内的线程
        page_tids = [t["thread_id"] for t in page]
        star_share: dict[tuple[str, str], tuple[bool, bool]] = {}
        try:
            from app.extensions.models import PersonalDocMeta

            meta_rows = await db.execute(
                select(PersonalDocMeta).where(
                    PersonalDocMeta.user_id == user_id,
                    PersonalDocMeta.thread_id.in_(page_tids),
                ),
            )
            for m in meta_rows.scalars().all():
                star_share[(m.thread_id, m.rel_path)] = (m.is_starred, m.is_shared)
        except Exception:
            pass

        # 第二遍：只对分页线程扫描文件详情
        result: list[dict] = []
        for t in page:
            outputs_dir = t["thread_dir"] / "user-data" / "outputs"
            tid = t["thread_id"]
            display_name = t["display_name"] or None

            files: list[dict] = []
            for fp in sorted(outputs_dir.rglob("*")):
                if not fp.is_file():
                    continue
                rel = str(fp.relative_to(outputs_dir))
                if any(p.startswith(".") for p in Path(rel).parts):
                    continue
                st = fp.stat()
                mime, _ = mimetypes.guess_type(fp.name)
                starred, shared = star_share.get((tid, rel), (False, False))
                files.append({
                    "name": fp.name,
                    "rel_path": rel,
                    "size": st.st_size,
                    "mime": mime or "application/octet-stream",
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=UTC),
                    "starred": starred,
                    "shared": shared,
                })

            if not files:
                continue  # 空目录不显示

            if not display_name:
                for f in files:
                    if f["name"].endswith(".md"):
                        display_name = f["name"].removesuffix(".md")
                        break
            if not display_name and files:
                display_name = Path(files[0]["name"]).stem
            if not display_name:
                display_name = tid[:8]

            result.append({
                "thread_id": tid,
                "display_name": display_name,
                "files": files,
            })

        return {"threads": result, "total": total, "has_more": has_more}

    # ── EAI-CUSTOM: 项目 outputs 跨用户聚合（不动 harness） ──────────────────

    @staticmethod
    async def _project_members(db: AsyncSession, project_id) -> list:
        """本项目全部 ProjectMember 行（含 user_id / thread_id）。失败返回空列表。"""
        try:
            from app.extensions.models import ProjectMember

            rows = await db.execute(
                select(ProjectMember).where(ProjectMember.project_id == project_id)
            )
            return list(rows.scalars().all())
        except Exception:
            return []

    @staticmethod
    async def _resolve_member_username(db: AsyncSession, user_id) -> str:
        """Resolve display username for a member; fall back to str(user_id)."""
        try:
            from app.extensions.models import User

            user = await db.get(User, user_id)
            return getattr(user, "username", None) or str(user_id)
        except Exception:
            return str(user_id)

    @staticmethod
    async def list_project_outputs(
        db: AsyncSession,
        project_id: UUID,
        caller_user_id: UUID,
    ) -> dict:
        """聚合本项目所有成员线程的 outputs/ 文件（跨 user 桶，服务器全盘读）。

        返回 {files: [{name, rel_path, size, mime, modified_at, member, thread_id}]}。
        非 member 抛 PermissionError（router 映射 403）。
        """
        from datetime import UTC, datetime
        from pathlib import Path

        from deerflow.config.paths import Paths

        members = await AIDocumentService._project_members(db, project_id)
        if not any(getattr(m, "user_id", None) == caller_user_id for m in members):
            raise PermissionError("not a project member")

        paths = Paths()
        users_dir = paths.base_dir / "users"

        username_cache: dict = {}

        async def _username(uid) -> str:
            if uid not in username_cache:
                username_cache[uid] = await AIDocumentService._resolve_member_username(db, uid)
            return username_cache[uid]

        files: list[dict] = []
        for m in members:
            tid = getattr(m, "thread_id", None)
            if not tid:
                continue
            # 找到真正含该 thread 的 user 桶（thread_id 全局唯一）
            resolved = None
            if users_dir.is_dir():
                for bucket in sorted(users_dir.iterdir()):
                    cand = bucket / "threads" / tid / "user-data" / "outputs"
                    if cand.is_dir():
                        resolved = cand
                        break
            if resolved is None:
                continue
            for fp in sorted(resolved.rglob("*")):
                if not fp.is_file():
                    continue
                rel = str(fp.relative_to(resolved))
                if any(p.startswith(".") for p in Path(rel).parts):
                    continue
                st = fp.stat()
                mime, _ = mimetypes.guess_type(fp.name)
                files.append({
                    "name": fp.name,
                    "rel_path": rel,
                    "size": st.st_size,
                    "mime": mime or "application/octet-stream",
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=UTC),
                    "member": await _username(getattr(m, "user_id", None)),
                    "thread_id": tid,
                })

        files.sort(key=lambda f: f["modified_at"], reverse=True)
        return {"files": files, "total": len(files)}

    @staticmethod
    async def upsert_personal_star(
        db: AsyncSession, user_id: UUID, thread_id: str, rel_path: str, starred: bool,
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.extensions.models import PersonalDocMeta

        stmt = insert(PersonalDocMeta).values(
            user_id=user_id, thread_id=thread_id, rel_path=rel_path, is_starred=starred,
        ).on_conflict_do_update(
            constraint="uq_personal_meta_user_thread_path",
            set_={"is_starred": starred, "updated_at": func.now()},
        )
        await db.execute(stmt)
        if not starred:
            row = (await db.execute(
                select(PersonalDocMeta).where(
                    PersonalDocMeta.user_id == user_id,
                    PersonalDocMeta.thread_id == thread_id,
                    PersonalDocMeta.rel_path == rel_path,
                )
            )).scalar_one_or_none()
            if row and not row.is_shared:
                await db.delete(row)

    @staticmethod
    async def upsert_personal_share(
        db: AsyncSession, user_id: UUID, thread_id: str, rel_path: str, shared: bool,
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.extensions.models import PersonalDocMeta

        stmt = insert(PersonalDocMeta).values(
            user_id=user_id, thread_id=thread_id, rel_path=rel_path, is_shared=shared,
        ).on_conflict_do_update(
            constraint="uq_personal_meta_user_thread_path",
            set_={"is_shared": shared, "updated_at": func.now()},
        )
        await db.execute(stmt)
        if not shared:
            row = (await db.execute(
                select(PersonalDocMeta).where(
                    PersonalDocMeta.user_id == user_id,
                    PersonalDocMeta.thread_id == thread_id,
                    PersonalDocMeta.rel_path == rel_path,
                )
            )).scalar_one_or_none()
            if row and not row.is_starred:
                await db.delete(row)

    @staticmethod
    async def list_starred_personal(db: AsyncSession, user_id: UUID) -> list[dict]:
        from app.extensions.models import PersonalDocMeta

        rows = (await db.execute(
            select(PersonalDocMeta).where(
                PersonalDocMeta.user_id == user_id, PersonalDocMeta.is_starred.is_(True),
            )
        )).scalars().all()
        return [{"thread_id": r.thread_id, "rel_path": r.rel_path} for r in rows]

    @staticmethod
    async def write_personal_output(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        rel_path: str,
        content: str,
    ) -> None:
        """写回线程 outputs/ 文件（编辑器保存）。"""
        import asyncio

        from deerflow.config.paths import Paths
        from deerflow.runtime.user_context import get_effective_user_id

        paths = Paths()
        effective_uid = get_effective_user_id()
        base = paths.base_dir / "users" / effective_uid / "threads" / thread_id / "user-data" / "outputs"
        if not base.is_dir():
            base = paths.base_dir / "users" / str(user_id) / "threads" / thread_id / "user-data" / "outputs"
        if not base.is_dir():
            base.mkdir(parents=True, exist_ok=True)  # auto-create for standalone docs

        target = (base / rel_path).resolve()
        # 防路径穿越：target 必须在 outputs 目录内
        if not str(target).startswith(str(base.resolve())):
            raise ValueError(f"path escape detected: {rel_path}")

        await asyncio.to_thread(lambda: target.write_text(content, encoding="utf-8"))

    # ── EAI-CUSTOM (C10): 个人文档版本历史 ────────────────────────────────

    _PERSONAL_VERSION_LIMIT = 20

    @staticmethod
    async def create_personal_version(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        rel_path: str,
        content: str,
        label: str | None = None,
    ) -> UUID:
        """Create a content snapshot; cap per-file history at 20 (delete oldest)."""
        from sqlalchemy import delete as sa_delete

        from app.extensions.models import PersonalDocVersion

        version = PersonalDocVersion(
            user_id=user_id, thread_id=thread_id, rel_path=rel_path, content=content, label=label,
        )
        db.add(version)
        await db.flush()
        # 每文件保留最新 N 条，超出的旧版本删除
        stmt = (
            select(PersonalDocVersion.id)
            .where(
                PersonalDocVersion.user_id == user_id,
                PersonalDocVersion.thread_id == thread_id,
                PersonalDocVersion.rel_path == rel_path,
            )
            .order_by(PersonalDocVersion.created_at.desc())
            .offset(AIDocumentService._PERSONAL_VERSION_LIMIT)
        )
        old_ids = (await db.execute(stmt)).scalars().all()
        if old_ids:
            await db.execute(sa_delete(PersonalDocVersion).where(PersonalDocVersion.id.in_(old_ids)))
        return version.id

    @staticmethod
    async def list_personal_versions(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        rel_path: str,
    ) -> list[dict]:
        """List versions newest-first with content preview."""
        from app.extensions.models import PersonalDocVersion

        rows = (
            await db.execute(
                select(PersonalDocVersion)
                .where(
                    PersonalDocVersion.user_id == user_id,
                    PersonalDocVersion.thread_id == thread_id,
                    PersonalDocVersion.rel_path == rel_path,
                )
                .order_by(PersonalDocVersion.created_at.desc())
            )
        ).scalars().all()
        return [
            {
                "id": v.id,
                "label": v.label,
                "created_at": v.created_at,
                "preview": (v.content or "")[:120],
                "content_length": len(v.content or ""),
            }
            for v in rows
        ]

    @staticmethod
    async def get_personal_version(
        db: AsyncSession,
        user_id: UUID,
        version_id: UUID,
    ) -> dict | None:
        """Fetch a single version scoped by user."""
        from app.extensions.models import PersonalDocVersion

        v = (
            await db.execute(
                select(PersonalDocVersion).where(
                    PersonalDocVersion.id == version_id,
                    PersonalDocVersion.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if v is None:
            return None
        return {
            "id": v.id,
            "label": v.label,
            "created_at": v.created_at,
            "content": v.content,
            "thread_id": v.thread_id,
            "rel_path": v.rel_path,
        }

    @staticmethod
    async def restore_personal_version(
        db: AsyncSession,
        user_id: UUID,
        version_id: UUID,
    ) -> dict | None:
        """Restore: write the version's content back to the outputs file."""
        from app.extensions.models import PersonalDocVersion

        v = (
            await db.execute(
                select(PersonalDocVersion).where(
                    PersonalDocVersion.id == version_id,
                    PersonalDocVersion.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if v is None:
            return None
        await AIDocumentService.write_personal_output(db, user_id, v.thread_id, v.rel_path, v.content)
        return {"content": v.content, "thread_id": v.thread_id, "rel_path": v.rel_path}

    @staticmethod
    async def sync_thread_files(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        sandbox_dir: str,
    ) -> dict:
        """Sync sandbox files for a thread into document space as file_ref records."""
        folder_name = await AIDocumentService._get_thread_title(db, thread_id)
        project_id = await AIDocumentService._detect_project_from_thread(db, thread_id)
        synced = 0
        skipped = 0
        max_per_sync = 100

        sandbox_path = Path(sandbox_dir)
        if not sandbox_path.exists():
            return {"synced": 0, "skipped": 0}

        # 线程无标题时 _get_thread_title 回退成 thread_id[:8]（无意义 id 片段，
        # 用户在文档空间认不出）。改用 outputs 里首个 .md 文件名作文件夹名。
        if folder_name == thread_id[:8]:
            for fp in sorted(sandbox_path.rglob("*")):
                if fp.is_file() and fp.suffix.lower() == ".md":
                    rel = fp.relative_to(sandbox_path)
                    if not any(p.startswith(".") for p in rel.parts):
                        folder_name = fp.stem
                        break

        # Resolve (or create) the per-thread subfolder under the personal/project
        # root so docs are filed into the folder tree — not left homeless. Without
        # this, docs get folder_id=NULL and never appear in 文档空间.
        folder_id, folder_name = await AIDocumentService._ensure_subfolder(
            db, user_id, folder_name, project_id,
        )

        for filepath in sandbox_path.rglob("*"):
            if not filepath.is_file():
                continue
            # Skip framework-internal files under hidden paths (notably
            # .tool-results/, where tool_output_budget_middleware auto-dumps large
            # MCP tool returns). These are intermediates, not deliverables — syncing
            # them pollutes 文档空间 with raw tool-output blobs (bug-410).
            if any(p.startswith(".") for p in filepath.relative_to(sandbox_path).parts):
                continue
            if synced >= max_per_sync:
                break

            abs_path = str(filepath)
            file_size = filepath.stat().st_size
            mime_type, _ = mimetypes.guess_type(filepath.name)
            if mime_type is None:
                mime_type = "application/octet-stream"

            # Check for existing file_ref with same path and thread
            existing = await db.execute(
                select(AIDocument).where(
                    AIDocument.user_id == user_id,
                    AIDocument.file_ref_path == abs_path,
                    AIDocument.source_thread_id == thread_id,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            doc = AIDocument(
                user_id=user_id,
                title=filepath.name,
                folder=folder_name,
                folder_id=folder_id,
                source_thread_id=thread_id,
                project_id=project_id,
                doc_type="file_ref",
                file_ref_path=abs_path,
                file_size=file_size,
                file_mime=mime_type,
                status="active",
            )
            db.add(doc)
            synced += 1

        await db.commit()
        return {"synced": synced, "skipped": skipped}

    @staticmethod
    async def _detect_project_from_thread(db: AsyncSession, thread_id: str) -> UUID | None:
        """Detect project_id from a thread_id by checking project_members."""
        stmt = select(ProjectMember.project_id).where(ProjectMember.thread_id == thread_id).limit(1)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    # ── Auto-sync: present_files → docmgr ──────────────────────────────

    @staticmethod
    async def _ensure_subfolder(
        db: AsyncSession,
        user_id: UUID,
        folder_name: str,
        project_id: UUID | None,
    ) -> tuple[UUID | None, str]:
        """Find or create a subfolder named *folder_name* under the appropriate root.

        Returns (folder_id, folder_string) — folder_id may be None if no root
        folder exists or user not in extensions DB (falls back to folder_string only).
        """
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        from app.extensions.models import Folder

        # Find root folder (project or personal)
        if project_id:
            root_stmt = select(Folder).where(
                Folder.project_id == project_id,
                Folder.parent_id.is_(None),
            ).limit(1)
        else:
            root_stmt = select(Folder).where(
                Folder.owner_id == user_id,
                Folder.project_id.is_(None),
                Folder.parent_id.is_(None),
            ).limit(1)

        root_result = await db.execute(root_stmt)
        root_folder = root_result.scalar_one_or_none()
        if root_folder is None:
            if project_id:
                return None, folder_name
            try:
                root_folder = Folder(
                    name="我的文档",
                    owner_id=user_id,
                    project_id=None,
                    parent_id=None,
                    is_system=False,
                )
                db.add(root_folder)
                await db.flush()
            except SAIntegrityError:
                # user_id not in extensions users table (dual-auth: core user_id ≠
                # extensions user_id). Roll back folder creation, fall back to
                # folder_id=None — document still visible in 文档空间, just unfiled.
                await db.rollback()
                logger.info("_ensure_subfolder: user %s not in extensions DB, skipping folder", user_id)
                return None, folder_name

        # Find or create subfolder under root
        sub_stmt = select(Folder).where(
            Folder.parent_id == root_folder.id,
            Folder.name == folder_name,
        ).limit(1)
        sub_result = await db.execute(sub_stmt)
        sub_folder = sub_result.scalar_one_or_none()

        if sub_folder is None:
            try:
                sub_folder = Folder(
                    name=folder_name,
                    parent_id=root_folder.id,
                    project_id=project_id,
                    owner_id=user_id,
                    is_system=False,
                )
                db.add(sub_folder)
                await db.flush()
            except SAIntegrityError:
                await db.rollback()
                return None, folder_name

        return sub_folder.id, folder_name

    @staticmethod
    async def sync_outputs_to_docmgr(
        user_id: str,
        thread_id: str,
        virtual_paths: list[str],
    ) -> dict[str, any] | None:
        """Sync presented files into document space (called from present_files callback).

        Receives virtual paths (e.g. /mnt/user-data/outputs/report.md), resolves
        them to physical paths, and creates file_ref AIDocument records.
        """
        from app.extensions.database import get_db_context
        from deerflow.config.paths import get_paths

        try:
            user_uuid = UUID(user_id)
        except (ValueError, TypeError):
            logger.warning("sync_outputs_to_docmgr: invalid user_id=%s", user_id)
            return None

        # 双 auth 系统: 核心 auth user_id 可能不在 extensions users 表。
        # 如果不在，回退到 admin 用户（保证文件能在文档空间显示）。
        from app.extensions.models import User

        paths = get_paths()
        synced = 0
        skipped = 0

        try:
            async with get_db_context() as db:
                try:
                    # 检查 user_id 是否在 extensions users 表
                    user_check = await db.execute(
                        select(User).where(User.id == user_uuid)
                    )
                    if user_check.scalar_one_or_none() is None:
                        # 回退到 admin 用户
                        admin_result = await db.execute(
                            select(User).where(User.email == "admin@eai-flow.com")
                        )
                        admin_user = admin_result.scalar_one_or_none()
                        if admin_user:
                            logger.info(
                                "sync_outputs_to_docmgr: user %s not in extensions DB, "
                                "falling back to admin %s", user_id, admin_user.id,
                            )
                            user_uuid = admin_user.id
                        else:
                            logger.warning("sync_outputs_to_docmgr: no admin user found, cannot sync")
                            return None

                    folder_name = await AIDocumentService._get_thread_title(db, thread_id)
                    project_id = await AIDocumentService._detect_project_from_thread(db, thread_id)
                    folder_id, folder_str = await AIDocumentService._ensure_subfolder(
                        db, user_uuid, folder_name, project_id,
                    )

                    for vpath in virtual_paths:
                        # Resolve virtual path to physical path
                        try:
                            try:
                                phys_path = paths.resolve_virtual_path(thread_id, vpath, user_id=user_id)
                            except TypeError:
                                phys_path = paths.resolve_virtual_path(thread_id, vpath)
                        except Exception:
                            logger.debug("Cannot resolve virtual path %s: skipping", vpath, exc_info=True)
                            continue

                        phys_str = str(phys_path)
                        if not phys_path.exists():
                            logger.debug("File does not exist, skipping: %s", phys_str)
                            continue

                        # Dedup by file_ref_path + source_thread_id
                        existing = await db.execute(
                            select(AIDocument).where(
                                AIDocument.user_id == user_uuid,
                                AIDocument.file_ref_path == phys_str,
                                AIDocument.source_thread_id == thread_id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped += 1
                            continue

                        file_size = phys_path.stat().st_size
                        mime_type, _ = mimetypes.guess_type(phys_path.name)
                        if mime_type is None:
                            mime_type = "application/octet-stream"

                        doc = AIDocument(
                            user_id=user_uuid,
                            title=phys_path.name,
                            folder=folder_str,
                            folder_id=folder_id,
                            source_thread_id=thread_id,
                            project_id=project_id,
                            doc_type="file_ref",
                            file_ref_path=phys_str,
                            file_size=file_size,
                            file_mime=mime_type,
                            status="active",
                        )
                        db.add(doc)
                        synced += 1

                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except Exception:
            logger.exception(
                "sync_outputs_to_docmgr failed (thread=%s, user=%s)",
                thread_id, user_id,
            )
            return None

        logger.info(
            "sync_outputs_to_docmgr: thread=%s synced=%d skipped=%d",
            thread_id, synced, skipped,
        )
        return {"synced": synced, "skipped": skipped}
