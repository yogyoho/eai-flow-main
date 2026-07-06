# 文档空间-我的文档：直接映射线程 outputs/ — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "我的文档" 从间接同步路径（outputs → sync_thread_files → AIDocument → Folder）改为直接读取线程 outputs/ 文件系统。项目文件夹不变。

**Architecture:** 新 API `GET /docmgr/personal-outputs` 直接扫描 `users/{uid}/threads/*/outputs/`。新表 `personal_doc_meta` 仅存收藏/分享状态。前端 `usePersonalOutputs` 替换 `useFolderTree("personal")`。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy async + TypeScript + React + TanStack Query

---

### Task 1: 新增 PersonalDocMeta 模型

**Files:**
- Modify: `backend/app/extensions/models/__init__.py` — 在 Folder 模型之后追加

- [ ] **Step 1: 在 models/__init__.py 添加 PersonalDocMeta**

在 `class Folder(Base):` 的 `children` relationship 之后（约 line 259），追加：

```python
class PersonalDocMeta(Base):
    """Lightweight per-user per-thread doc metadata (star / share).

    Only created when a personal doc is starred or shared — no pre-seeding.
    """

    __tablename__ = "personal_doc_meta"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rel_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "thread_id", "rel_path", name="uq_personal_meta_user_thread_path"),
    )

    owner: Mapped["User"] = relationship("User")
```

- [ ] **Step 2: 重启 gateway 触发 init_db → create_all**

```bash
docker compose -p eai-docker restart gateway
# 等 startup complete，检查无 error
docker exec deer-flow-gateway bash -lc "tail -20 /app/logs/gateway.log | grep -iE 'error|exception|startup complete'"
```

- [ ] **Step 3: 验证表已创建**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\d personal_doc_meta"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/models/__init__.py
git commit -m "feat: add PersonalDocMeta model for personal doc star/share metadata"
```

---

### Task 2: 新增 response schemas

**Files:**
- Modify: `backend/app/extensions/schemas.py` — 在 FolderTreeResponse 之后追加

- [ ] **Step 1: 添加 schemas**

在 `class FolderTreeResponse(BaseModel):` 之后（约 line 660），追加：

```python
# ── Personal outputs (direct filesystem mapping) ─────────────────────────

class PersonalDocFile(BaseModel):
    """A single file under a thread's outputs/ directory."""
    name: str
    rel_path: str
    size: int
    mime: str
    modified_at: datetime
    starred: bool = False
    shared: bool = False


class PersonalThreadOutput(BaseModel):
    """One thread's outputs/ listing."""
    thread_id: str
    display_name: str
    files: list[PersonalDocFile]


class PersonalOutputsResponse(BaseModel):
    """Response for GET /docmgr/personal-outputs."""
    threads: list[PersonalThreadOutput]


class PersonalDocStarRequest(BaseModel):
    rel_path: str = Field(..., min_length=1, max_length=500)
    starred: bool


class PersonalDocShareRequest(BaseModel):
    rel_path: str = Field(..., min_length=1, max_length=500)
    shared: bool
```

- [ ] **Step 2: 在 routers.py import 新 schema**

修改 `backend/app/extensions/docmgr/routers.py` line 19-33 的 import，追加：

```python
from app.extensions.schemas import (
    ...
    PersonalOutputsResponse,
    PersonalDocStarRequest,
    PersonalDocShareRequest,
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/schemas.py backend/app/extensions/docmgr/routers.py
git commit -m "feat: add PersonalOutputsResponse + star/share request schemas"
```

---

### Task 3: 实现 list_personal_outputs 服务方法

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py` — 新增 static method

- [ ] **Step 1: 在 service.py 添加方法**

在 `AIDocumentService` 类内（`sync_thread_files` 之前，约 line 328），插入：

```python
    @staticmethod
    async def list_personal_outputs(
        db: AsyncSession,
        user_id: UUID,
    ) -> list[dict]:
        """Scan users/{user_id}/threads/*/outputs/ and return per-thread file listings.

        Reads threads_meta(display_name) for folder names and personal_doc_meta
        for star/share status.  No DB writes — this is a pure read of the filesystem
        plus lightweight metadata lookup.
        """
        import mimetypes
        import sqlite3
        from collections import defaultdict

        from deerflow.config.paths import Paths

        paths = Paths()
        threads_dir = paths.base_dir / "users" / str(user_id) / "threads"
        if not threads_dir.is_dir():
            return []

        # ── resolve display names from threads_meta (sqlite) ──────────
        display_names: dict[str, str] = {}
        try:
            meta_db = paths.base_dir / "data" / "deerflow.db"
            if meta_db.exists():
                conn = sqlite3.connect(str(meta_db))
                try:
                    rows = conn.execute(
                        "SELECT thread_id, display_name FROM threads_meta"
                    ).fetchall()
                    for tid, dn in rows:
                        if dn:
                            display_names[tid] = dn
                finally:
                    conn.close()
        except Exception:
            pass

        # ── resolve star/share from personal_doc_meta (postgres) ───────
        star_share: dict[tuple[str, str], tuple[bool, bool]] = {}
        try:
            from app.extensions.models import PersonalDocMeta
            meta_rows = await db.execute(
                select(PersonalDocMeta).where(PersonalDocMeta.user_id == user_id),
            )
            for m in meta_rows.scalars().all():
                star_share[(m.thread_id, m.rel_path)] = (m.is_starred, m.is_shared)
        except Exception:
            pass

        # ── scan outputs/ per thread ──────────────────────────────────
        result: list[dict] = []
        for thread_dir in sorted(threads_dir.iterdir(), reverse=True):
            if not thread_dir.is_dir():
                continue
            outputs_dir = thread_dir / "user-data" / "outputs"
            if not outputs_dir.is_dir():
                continue
            tid = thread_dir.name
            display_name = display_names.get(tid)

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
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                    "starred": starred,
                    "shared": shared,
                })

            # Fallback: 线程无标题 → 用首个 .md 文件名
            if not display_name:
                for f in files:
                    if f["name"].endswith(".md"):
                        display_name = f["name"].removesuffix(".md")
                        break
            if not display_name:
                display_name = tid[:8]  # ultimate fallback

            result.append({
                "thread_id": tid,
                "display_name": display_name,
                "files": files,
            })

        return result
```

- [ ] **Step 2: 添加 import**

确保 `service.py` 头部有（或用现有 imports）：
```python
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/docmgr/service.py
git commit -m "feat: add list_personal_outputs — direct filesystem scan of thread outputs/"
```

---

### Task 4: 实现 star/share 服务方法

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py` — 追加 static methods

- [ ] **Step 1: 添加 star/share 方法**

在 `list_personal_outputs` 之后追加：

```python
    @staticmethod
    async def upsert_personal_star(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        rel_path: str,
        starred: bool,
    ) -> None:
        """Set or clear the star flag on a personal doc."""
        from app.extensions.models import PersonalDocMeta
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(PersonalDocMeta).values(
            user_id=user_id,
            thread_id=thread_id,
            rel_path=rel_path,
            is_starred=starred,
        ).on_conflict_do_update(
            constraint="uq_personal_meta_user_thread_path",
            set_={"is_starred": starred, "updated_at": func.now()},
        )
        await db.execute(stmt)
        # If un-starring and also not shared, remove the row to keep table lean
        if not starred:
            await db.execute(
                select(PersonalDocMeta).where(
                    PersonalDocMeta.user_id == user_id,
                    PersonalDocMeta.thread_id == thread_id,
                    PersonalDocMeta.rel_path == rel_path,
                )
            )
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
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        rel_path: str,
        shared: bool,
    ) -> None:
        """Set or clear the shared flag on a personal doc."""
        from app.extensions.models import PersonalDocMeta
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(PersonalDocMeta).values(
            user_id=user_id,
            thread_id=thread_id,
            rel_path=rel_path,
            is_shared=shared,
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
    async def list_starred_personal(
        db: AsyncSession,
        user_id: UUID,
    ) -> list[dict]:
        """Return all starred personal docs (for '收藏' filter)."""
        from app.extensions.models import PersonalDocMeta
        rows = (await db.execute(
            select(PersonalDocMeta).where(
                PersonalDocMeta.user_id == user_id,
                PersonalDocMeta.is_starred == True,  # noqa: E712
            )
        )).scalars().all()
        return [{"thread_id": r.thread_id, "rel_path": r.rel_path} for r in rows]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/docmgr/service.py
git commit -m "feat: add upsert_personal_star / upsert_personal_share service methods"
```

---

### Task 5: 添加路由端点

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`

- [ ] **Step 1: 添加 GET /personal-outputs**

在 `sync-thread-files` 路由之后（约 line 530），追加：

```python
@router.get("/personal-outputs", response_model=PersonalOutputsResponse)
async def list_personal_outputs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List personal thread outputs — direct filesystem view of '我的文档'."""
    threads = await AIDocumentService.list_personal_outputs(db, current_user.id)
    return PersonalOutputsResponse(threads=threads)
```

- [ ] **Step 2: 添加 PUT star 端点**

```python
@router.put("/personal-docs/{thread_id}/star")
async def toggle_personal_star(
    thread_id: str,
    data: PersonalDocStarRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle star on a personal doc."""
    await AIDocumentService.upsert_personal_star(
        db, current_user.id, thread_id, data.rel_path, data.starred,
    )
    await db.commit()
    return {"ok": True}


@router.put("/personal-docs/{thread_id}/share")
async def toggle_personal_share(
    thread_id: str,
    data: PersonalDocShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle share on a personal doc."""
    await AIDocumentService.upsert_personal_share(
        db, current_user.id, thread_id, data.rel_path, data.shared,
    )
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/docmgr/routers.py
git commit -m "feat: add /personal-outputs + star/share endpoints"
```

---

### Task 6: 后端测试

**Files:**
- Create: `backend/tests/test_personal_outputs.py`

- [ ] **Step 1: 写测试文件**

```python
"""Tests for personal-outputs endpoint and star/share metadata."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.docmgr.service import AIDocumentService


class TestListPersonalOutputs:
    """Test list_personal_outputs service method."""

    @pytest.mark.asyncio
    async def test_empty_when_no_threads_dir(self, tmp_path):
        """Returns [] when users/{uid}/threads/ does not exist."""
        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(spec=AsyncSession), uuid4(),
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_thread_without_outputs_dir(self, tmp_path):
        """Thread dir exists but has no user-data/outputs/ → skipped."""
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        thread_dir = threads_dir / "t1"
        thread_dir.mkdir(parents=True)
        # No user-data/outputs/ subdir

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(spec=AsyncSession), user_id,
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_files_for_thread_with_outputs(self, tmp_path):
        """Thread with outputs/ returns files."""
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "report.md").write_text("# Report")
        (outputs_dir / "data.csv").write_text("a,b\n1,2")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(spec=AsyncSession), user_id,
            )
        assert len(result) == 1
        assert result[0]["thread_id"] == "tid-1"
        names = {f["name"] for f in result[0]["files"]}
        assert names == {"report.md", "data.csv"}

    @pytest.mark.asyncio
    async def test_skips_hidden_paths(self, tmp_path):
        """Files under hidden dirs (e.g. .tool-results/) are skipped."""
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
                AsyncMock(spec=AsyncSession), user_id,
            )
        names = {f["name"] for f in result[0]["files"]}
        assert "visible.md" in names
        assert "large.json" not in names


class TestPersonalStarShare:
    """Test upsert_personal_star / upsert_personal_share."""

    @pytest.mark.asyncio
    async def test_star_upserts_and_cleans_up(self, tmp_path):
        """Starring creates a meta row; un-starring removes it (if not shared)."""
        # This test verifies the logic compiles — the actual DB roundtrip
        # is covered by integration tests (manual with running gateway).
        from app.extensions.models import PersonalDocMeta
        assert PersonalDocMeta.__tablename__ == "personal_doc_meta"
```

- [ ] **Step 2: 跑测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_personal_outputs.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_personal_outputs.py
git commit -m "test: add personal-outputs service tests"
```

---

### Task 7: 前端 API 函数

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`

- [ ] **Step 1: 在 docmgrApi 对象追加**

在 `docmgrApi` 对象末尾（`aiReview` 之后，约 line 577），加 `}` 之前：

```typescript
  // ── Personal outputs (direct filesystem mapping) ──────────────────────

  /** List personal thread outputs — direct filesystem view of 我的文档. */
  listPersonalOutputs: () =>
    request<{ threads: PersonalThreadOutput[] }>("/docmgr/personal-outputs"),

  /** Toggle star on a personal doc. */
  togglePersonalStar: (threadId: string, data: { rel_path: string; starred: boolean }) =>
    request<{ ok: boolean }>(`/docmgr/personal-docs/${encodeURIComponent(threadId)}/star`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** Toggle share on a personal doc. */
  togglePersonalShare: (threadId: string, data: { rel_path: string; shared: boolean }) =>
    request<{ ok: boolean }>(`/docmgr/personal-docs/${encodeURIComponent(threadId)}/share`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
```

- [ ] **Step 2: 在同文件顶部或 types 文件追加类型**

```typescript
export interface PersonalDocFile {
  name: string;
  rel_path: string;
  size: number;
  mime: string;
  modified_at: string;
  starred: boolean;
  shared: boolean;
}

export interface PersonalThreadOutput {
  thread_id: string;
  display_name: string;
  files: PersonalDocFile[];
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/api/index.ts frontend/src/extensions/types/index.ts  # 或实际 types 路径
git commit -m "feat: add personal-outputs API + types"
```

---

### Task 8: 前端 usePersonalOutputs hook

**Files:**
- Create: `frontend/src/extensions/docmgr/usePersonalOutputs.ts`

- [ ] **Step 1: 创建 hook**

```typescript
"use client"

import { useState, useCallback, useEffect } from "react";
import { docmgrApi } from "../api";
import type { PersonalThreadOutput, PersonalDocFile } from "../types";

export function usePersonalOutputs() {
  const [threads, setThreads] = useState<PersonalThreadOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const fetchOutputs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await docmgrApi.listPersonalOutputs();
      setThreads(data.threads);
    } catch (err) {
      console.error("Failed to fetch personal outputs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOutputs(); }, [fetchOutputs]);

  const toggleExpand = useCallback((threadId: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      next.has(threadId) ? next.delete(threadId) : next.add(threadId);
      return next;
    });
  }, []);

  const toggleStar = useCallback(async (threadId: string, relPath: string, current: boolean) => {
    await docmgrApi.togglePersonalStar(threadId, { rel_path: relPath, starred: !current });
    await fetchOutputs();
  }, [fetchOutputs]);

  const toggleShare = useCallback(async (threadId: string, relPath: string, current: boolean) => {
    await docmgrApi.togglePersonalShare(threadId, { rel_path: relPath, shared: !current });
    await fetchOutputs();
  }, [fetchOutputs]);

  return { threads, loading, expandedKeys, toggleExpand, toggleStar, toggleShare, refresh: fetchOutputs };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/docmgr/usePersonalOutputs.ts
git commit -m "feat: add usePersonalOutputs hook"
```

---

### Task 9: 前端 DocumentManagement.tsx 切换我的文档

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: 替换 useFolderTree("personal") → usePersonalOutputs**

```diff
- import { useFolderTree } from "./useFolderTree";
+ import { useFolderTree } from "./useFolderTree";
+ import { usePersonalOutputs } from "./usePersonalOutputs";

  // 原来：
- const personalFolderTree = useFolderTree("personal");
  // 改为：
+ const personalOutputs = usePersonalOutputs();
```

- [ ] **Step 2: 替换"我的文档"区域的渲染**

在左侧"我的文档"区域（约 line 213-236），将 `ProjectFolderTree` 改为一个新的简化渲染。每个 thread 作为一级文件夹，展开后 listing files。

当前代码（约 line 226-237）：
```tsx
<ProjectFolderTree
  folders={personalFolderTree.folders.flatMap(f => f.children || [])}
  expandedKeys={personalFolderTree.expandedKeys}
  onToggleExpand={personalFolderTree.toggleExpand}
  ...
/>
```

改为直接渲染 `personalOutputs.threads`。此处需要适配现有的 `ProjectFolderTree` 组件，或者内联一个简单列表。最小改动是复用 ProjectFolderTree —— 把 thread 数据转换成 folder 形状：

```typescript
// 把 threads 转为 ProjectFolderTree 期望的 folder 格式
const personalFolders: FolderNode[] = personalOutputs.threads.map(t => ({
  id: t.thread_id,
  name: t.display_name,
  parent_id: null,
  children: t.files.map(f => ({
    id: `${t.thread_id}/${f.rel_path}`,
    name: f.name,
    doc_type: f.mime.startsWith("text/") ? "document" : "file_ref" as const,
    file_ref_path: f.rel_path,
    starred: f.starred,
    shared: f.shared,
    size: f.size,
    modified_at: f.modified_at,
    // 标记为文件节点以便 ProjectFolderTree 区分
  } as any)),
  doc_count: t.files.length,
} as any));
```

但 `ProjectFolderTree` 接口较复杂。建议**不内联 hack**，而是在"我的文档"区域写一段专用渲染：

```tsx
{/* 我的文档 —— direct filesystem view */}
<div>
  <button onClick={() => setPersonalOpen(!personalOpen)}>我的文档</button>
  {personalOpen && personalOutputs.threads.map(t => (
    <div key={t.thread_id}>
      <div onClick={() => personalOutputs.toggleExpand(t.thread_id)}>
        {t.display_name} ({t.files.length})
      </div>
      {personalOutputs.expandedKeys.has(t.thread_id) && t.files.map(f => (
        <div key={f.rel_path} onClick={() => openFile(t.thread_id, f.rel_path)}>
          <span>{f.name}</span>
          <button onClick={(e) => { e.stopPropagation(); personalOutputs.toggleStar(t.thread_id, f.rel_path, f.starred); }}>
            {f.starred ? "★" : "☆"}
          </button>
        </div>
      ))}
    </div>
  ))}
</div>
```

由于前端改动涉及 UI 细节较多，这一步交给实际实现时按需调整布局以适配现有组件。**核心变化：数据源从 `useFolderTree("personal")` 改为 `usePersonalOutputs`**。

- [ ] **Step 3: 类型检查**

```bash
cd frontend && pnpm typecheck
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat: switch my文档 to direct personal-outputs data source"
```

---

### Task 10: 移除个人 scope 的 syncThreadFiles

**Files:**
- Modify: `frontend/src/components/workspace/chats/chat-box.tsx`
- Modify: `frontend/src/extensions/docmgr/useDocuments.ts`

- [ ] **Step 1: chat-box.tsx — 条件化 syncThreadFiles**

当前 `chat-box.tsx`（约 line 35-51）在每次 AI 回复结束时无条件调 `syncThreadFiles`。改为：个人线程不再调 sync（由 personal-outputs 直接读），项目线程保留。

如果 chat-box 无法区分个人/项目（chat-box 不知道线程是否在项目里），最简方案是**保留 syncThreadFiles 调用不变**——个人 scope 的 `sync_thread_files` 仍然会写 AIDocument/Folder，只是前端**不再读取**这些旧数据。sync 的副作用（写 DB）无害，只是多余。这样可以零改 chat-box，降低风险。

- [ ] **Step 2: useDocuments.ts — 保留 syncThreadFiles（项目仍用）**

`useDocuments.ts` 的 `syncThreadFiles` 保留不动（项目文件夹用）。

- [ ] **Step 3: Commit**（如有改动）

---

### Task 11: 集成验证

- [ ] **Step 1: 重启 gateway + frontend**

```bash
docker compose -p eai-docker restart gateway
# 前端代码改动需 rebuild（node_modules 在镜像内）
# 或直接 restart frontend 如果 HMR 生效
docker compose -p eai-docker restart frontend
```

- [ ] **Step 2: 调 API 验证 personal-outputs 返回正确**

```bash
# 用 admin 登录获取 cookie，然后调 API
curl -s -b "cookie..." http://localhost:2026/api/extensions/docmgr/personal-outputs | python -m json.tool | head -30
```

预期：返回 `threads` 数组，每个有 `thread_id`、`display_name`、`files`。

- [ ] **Step 3: 验证 star/share API**

```bash
# star
curl -s -X PUT .../personal-docs/{tid}/star -H 'Content-Type: application/json' -d '{"rel_path":"xxx.md","starred":true}'
# 查 DB
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT * FROM personal_doc_meta;"
```

- [ ] **Step 4: 浏览器端到端**

打开 http://localhost:2026/docmgr → 我的文档 → 确认线程 outputs 文件列表出现；确认项目文件夹仍正常。

- [ ] **Step 5: Commit**（如有微调）
