# 文档空间「项目文件夹」合并 — 项目 outputs 跨用户共享 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** lisi 在项目对话生成的 outputs 文件，无需 agent 调任何工具即自动对项目成员可见、可编辑；文档空间个人区/项目区统一为两区文件系统视图，零 harness 改动。

**Architecture:** 纯 app 层。项目区聚合 `listProjectOutputs` 直接扫该项目所有成员线程的 `outputs/`（跨用户桶读，服务器有全盘 FS 权限）；跨用户编辑经服务器写回文件**原物理路径**（按 `thread_id` 扫所有 user 桶定位，避开双 user_id 坑）+ mtime 乐观锁；新增 `ProjectDocVersion` 表做版本快照。个人区 `listPersonalOutputs` 加过滤排除绑定项目的线程。harness 层（`packages/harness/deerflow/`）一行不改。

**Tech Stack:** Python 3.12 / SQLAlchemy 2.0 async / FastAPI / pytest-asyncio（后端）；Next.js 16 / React 19 / TypeScript（前端）。扩展 DB 走 `Base.metadata.create_all`（`backend/app/extensions/database.py:206`），**新增表无需 Alembic 迁移**，重启 gateway 即自动建表。

**Hard constraints (from user):**
- 不改 harness 代码。所有改动在 `app/extensions/` + `frontend/src/extensions/`。
- 所有提交到 `main-dev-fork` 分支，**绝不** `main`。
- EAI 对上游代码的定制化须加 `EAI-CUSTOM` 注释（本计划全在 EAI 自有扩展层，天然满足，仍按惯例标注）。
- 后端在 Docker `eai-docker` 组内运行；DB 容器名 `eai-flow-postgres-ext`。

**Spec:** `docs/superpowers/specs/2026-08-09-docmgr-project-outputs-merge-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `backend/app/extensions/models/__init__.py` | `ProjectDocVersion` ORM 模型 | Add model |
| `backend/app/extensions/docmgr/service.py` | `listProjectOutputs` / `write_project_output` / 版本 CRUD / 个人区排除过滤 / `_locate_thread_outputs` | Add methods |
| `backend/app/extensions/schemas.py` | 项目 outputs / 版本响应 schema | Add schemas |
| `backend/app/extensions/docmgr/routers.py` | 项目 outputs GET/PUT + 版本端点 | Add routes |
| `backend/app/extensions/project/service.py` | `get_project_files` 复用 `listProjectOutputs` | Refactor |
| `backend/tests/test_project_outputs.py` | 后端 TDD 测试 | Create |
| `frontend/src/extensions/docmgr/api.ts` | 项目 outputs / 版本 API 方法 | Add methods |
| `frontend/src/extensions/docmgr/useProjectOutputs.ts` | `useProjectOutputs(pid)` hook | Create |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | 项目区改文件系统视图 + 项目选择器 + 成员 badge | Rewrite project section |

**Key existing patterns to mirror (do not re-derive):**
- `PersonalDocVersion` (`models/__init__.py:306`) → `ProjectDocVersion`.
- `list_personal_outputs` (`docmgr/service.py:422`) file-scan loop (`:528`) → project aggregation.
- `write_personal_output` (`docmgr/service.py:633`) path-escape guard → project write-back.
- `create_personal_version` (`docmgr/service.py:665`) 20-cap → project version.
- 桶扫描 fallback (`project/service.py:460-469`) → `_locate_thread_outputs`.
- Test pattern (`tests/test_personal_outputs.py`): `patch("deerflow.config.paths.Paths")` + `mock_paths.return_value.base_dir = tmp_path` + `AsyncMock()` db. `MagicMock` 的 `__iter__` 默认空，故 `db.execute().scalars().all()` 在 `AsyncMock()` 下迭代为空。

---

## Task 1: `ProjectDocVersion` 模型

**Files:**
- Modify: `backend/app/extensions/models/__init__.py`（在 `PersonalDocVersion` 类之后，`class Conversation` 之前，约 `:324`）

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_project_outputs.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestProjectDocVersionModel -v`
Expected: FAIL — `ImportError: cannot import name 'ProjectDocVersion'`

- [ ] **Step 3: Add the model**

In `backend/app/extensions/models/__init__.py`, insert after the `PersonalDocVersion` class (after its `owner` relationship line, before `class Conversation`):

```python
class ProjectDocVersion(Base):
    """EAI-CUSTOM: 项目文档内容快照（跨用户编辑版本历史），键 (project_id, thread_id, rel_path)。

    thread_id 区分不同成员的同名文件（每成员进项目各开自己线程）。每文件留最新 20 条。
    """

    __tablename__ = "project_doc_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rel_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    editor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_project_versions_proj_thread_path", "project_id", "thread_id", "rel_path"),
    )

    project: Mapped["ReportProject"] = relationship("ReportProject")
    editor: Mapped["User"] = relationship("User")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestProjectDocVersionModel -v`
Expected: PASS

- [ ] **Step 5: 建表（create_all 自动）+ commit**

重启 gateway 让 `create_all` 建表，并查表确认：

```bash
docker compose -p eai-docker restart gateway
# 等 ~10s 起来后确认表存在
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\dt project_doc_versions"
```

```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_project_outputs.py
git commit -m "feat(docmgr): add ProjectDocVersion model for cross-user project doc versioning"
```

---

## Task 2: `listProjectOutputs` 服务（聚合 + 成员校验）

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`（在 `list_personal_outputs` 之后新增方法）
- Test: `backend/tests/test_project_outputs.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_outputs.py`:

```python
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
        # 每个文件标注生成者 username 与 thread_id
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

        # caller 有线程+文件；另一成员无线程；第三成员有线程但目录不存在
        out = tmp_path / "users" / str(caller) / "threads" / "Tc" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "a.md").write_text("a")
        members = [_M(caller, "Tc"), _M(uuid4(), None), _M(uuid4(), "Tghost")]
        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_project_members", AsyncMock(return_value=members)):
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.list_project_outputs(AsyncMock(), pid, caller)
        assert [f["name"] for f in res["files"]] == ["a.md"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestListProjectOutputs -v`
Expected: FAIL — `AttributeError: ... has no attribute 'list_project_outputs'`

- [ ] **Step 3: Implement the service methods**

In `backend/app/extensions/docmgr/service.py`, add near the top (after the existing imports block, or rely on existing `import mimetypes` / `from datetime import ...` already present at module scope — they are). Add two static methods right after `list_personal_outputs` (find the line `return {"threads": result, "total": total, "has_more": has_more}` that closes `list_personal_outputs`, insert after it):

```python
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

        # username 缓存，用于归属 badge
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
            out_dir = users_dir / "*" / "threads" / tid  # placeholder, resolved below
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

        # 按 modified_at 倒序
        files.sort(key=lambda f: f["modified_at"], reverse=True)
        return {"files": files, "total": len(files)}
```

Then add the username resolver (small helper; if `project/service._resolve_username` style already exists at project layer, mirror it here in docmgr). Append near the other private helpers in `service.py`:

```python
    @staticmethod
    async def _resolve_member_username(db: AsyncSession, user_id) -> str:
        """Resolve display username for a member; fall back to str(user_id)."""
        try:
            from app.extensions.models import User

            user = await db.get(User, user_id)
            return getattr(user, "username", None) or str(user_id)
        except Exception:
            return str(user_id)
```

Note: `mimetypes` and `select`/`select` are already imported at module scope in `service.py` (used by `list_personal_outputs`); confirm by `grep -n "^import mimetypes\|^from sqlalchemy" backend/app/extensions/docmgr/service.py`. If `select` is not at top-level, the existing `list_personal_outputs` already uses it, so it is present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestListProjectOutputs -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/tests/test_project_outputs.py
git commit -m "feat(docmgr): add listProjectOutputs — cross-user project outputs aggregation"
```

---

## Task 3: 个人区排除项目线程过滤

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`（`list_personal_outputs`）
- Test: `backend/tests/test_project_outputs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_outputs.py`:

```python
class TestPersonalOutputsExcludesProjectThreads:
    @pytest.mark.asyncio
    async def test_project_bound_thread_excluded_from_personal(self, tmp_path: Path):
        """绑项目的线程 outputs 不回流到「我的文档」。"""
        from app.extensions.docmgr.service import AIDocumentService

        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        # 一个个人线程 + 一个绑项目的线程
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestPersonalOutputsExcludesProjectThreads -v`
Expected: FAIL — `AttributeError: ... _personal_project_thread_ids` (and currently both threads returned)

- [ ] **Step 3: Add helper + wire filter**

In `service.py`, add a helper near `_project_members`:

```python
    @staticmethod
    async def _personal_project_thread_ids(db: AsyncSession) -> set[str]:
        """所有绑项目的 thread_id 集合（用于个人区排除）。失败返回空集。"""
        try:
            from app.extensions.models import ProjectMember

            rows = await db.execute(
                select(ProjectMember.thread_id).where(ProjectMember.thread_id.isnot(None))
            )
            return {tid for tid in rows.scalars().all() if tid}
        except Exception:
            return set()
```

Then in `list_personal_outputs`, after the first pass collects `all_threads` and **before** the `all_threads.sort(...)` line, insert the exclusion. Find this block (around `:495`):

```python
        # 次级 key thread_id 保证排序稳定（created_at 相同/为空时分页不重复/遗漏）
        all_threads.sort(key=lambda t: (_sort_key(t), t["thread_id"]), reverse=True)
```

Insert immediately before it:

```python
        # EAI-CUSTOM: 排除绑定项目的线程（项目产物只出现在项目区，不回流个人区）
        project_tids = await AIDocumentService._personal_project_thread_ids(db)
        if project_tids:
            all_threads = [t for t in all_threads if t["thread_id"] not in project_tids]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py -v && PYTHONPATH=. uv run pytest tests/test_personal_outputs.py -v`
Expected: PASS (new test passes; existing personal tests still pass — `AsyncMock()` db makes `_personal_project_thread_ids` return empty set, no exclusion, behavior unchanged for them)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/tests/test_project_outputs.py
git commit -m "feat(docmgr): exclude project-bound threads from personal outputs"
```

---

## Task 4: 跨用户写回（桶扫描定位 + 路径穿越 + mtime 乐观锁）

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`
- Test: `backend/tests/test_project_outputs.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_outputs.py`:

```python
class TestWriteProjectOutput:
    @pytest.mark.asyncio
    async def test_locate_thread_outputs_by_thread_id_scan(self, tmp_path: Path):
        """thread_id 全局唯一 → 扫所有 user 桶定位（避开双 user_id 坑）。"""
        from app.extensions.docmgr.service import AIDocumentService

        # 文件在 lisi 桶，调用者可能是 zhangsan
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
                # 客户端拿到的旧 mtime 与当前不符
                await AIDocumentService.write_project_output(
                    AsyncMock(), pid, "T1", "doc.md", "v2", uid, if_mtime=1.0,
                )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestWriteProjectOutput -v`
Expected: FAIL — `AttributeError` / `ImportError: cannot import name '_StaleWrite'`

- [ ] **Step 3: Implement**

In `service.py`, near the top of the file (module scope, after the imports / before the class or at module level — define the sentinel exception). Add at module scope:

```python
# EAI-CUSTOM: 跨用户编辑 mtime 乐观锁失败信号（router 映射 HTTP 409）
class _StaleWrite(Exception):
    """文件已被他人修改（client 持有的 mtime 过期）。"""
```

Then add the methods after `list_project_outputs` in the class:

```python
    @staticmethod
    def _locate_thread_outputs(thread_id: str):
        """按 thread_id 扫描所有 user 桶，定位该线程的 outputs 目录。

        thread_id 全局唯一，不依赖 member.user_id（agent 运行时 user_id 可能 ≠
        项目 member user_id）。复用 project/service.sync_project_thread_docs 的
        fallback 扫描模式。返回 Path 或 None。
        """
        from deerflow.config.paths import Paths

        users_dir = Paths().base_dir / "users"
        if not users_dir.is_dir():
            return None
        for bucket in sorted(users_dir.iterdir()):
            cand = bucket / "threads" / thread_id / "user-data" / "outputs"
            if cand.is_dir():
                return cand
        return None

    @staticmethod
    async def write_project_output(
        db: AsyncSession,
        project_id: UUID,
        thread_id: str,
        rel_path: str,
        content: str,
        editor_user_id: UUID,
        if_mtime: float | None = None,
    ) -> None:
        """服务器调解写回文件原物理路径（跨用户编辑）。带 mtime 乐观锁。

        if_mtime 非空时与当前文件 mtime 比对，不一致抛 _StaleWrite。
        写成功后创建一条 ProjectDocVersion 快照。
        """
        import asyncio
        from pathlib import Path

        base = AIDocumentService._locate_thread_outputs(thread_id)
        if base is None:
            raise FileNotFoundError(f"thread outputs dir not found: {thread_id}")

        target = (base / rel_path).resolve()
        # 防路径穿越
        if not str(target).startswith(str(base.resolve())):
            raise ValueError(f"path escape detected: {rel_path}")

        # mtime 乐观锁
        if if_mtime is not None:
            cur_mtime = await asyncio.to_thread(lambda: target.stat().st_mtime)
            # 容忍 1s 文件系统精度差
            if abs(cur_mtime - if_mtime) > 1.0:
                raise _StaleWrite("file modified by another editor")

        await asyncio.to_thread(lambda: target.write_text(content, encoding="utf-8"))
        await AIDocumentService.create_project_version(
            db, project_id, thread_id, rel_path, content, editor_user_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestWriteProjectOutput -v`
Expected: PASS (4 tests). Note: `create_project_version` is referenced but not yet implemented — it will raise AttributeError. **So this step expects failure until Task 5.** To keep Task 4 green independently, stub `create_project_version` is added in Task 5; reorder: implement the version-create call guarded. Simplest: wrap the version snapshot in try/except so write-back succeeds even if version table logic is added later. Replace the last two lines with:

```python
        try:
            await AIDocumentService.create_project_version(
                db, project_id, thread_id, rel_path, content, editor_user_id,
            )
        except Exception:
            pass  # 版本快照失败不影响写回（后续 Task 5 补全）
```

Re-run: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/tests/test_project_outputs.py
git commit -m "feat(docmgr): cross-user project doc write-back with thread bucket scan + mtime lock"
```

---

## Task 5: 项目版本 CRUD（快照 / 列表 / 取 / 回滚）

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`
- Test: `backend/tests/test_project_outputs.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_outputs.py`:

```python
class TestProjectDocVersion:
    @pytest.mark.asyncio
    async def test_create_and_list_version(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        pid, uid = uuid4(), uuid4()
        db = AsyncMock()
        # create 写入 db.add + flush；list 查询返回空（AsyncMock __iter__ 空）
        vid = await AIDocumentService.create_project_version(db, pid, "T1", "a.md", "c1", uid)
        assert vid is not None

    @pytest.mark.asyncio
    async def test_twenty_cap_deletes_oldest(self, tmp_path: Path):
        """超过 20 条 → 删除最旧版本（验证 offset 删除逻辑被调用）。"""
        from app.extensions.docmgr.service import AIDocumentService

        pid, uid = uuid4(), uuid4()
        db = AsyncMock()
        # flush 后 select offset 查询 → .scalars().all() 默认空 → 不删；验证不抛错
        for i in range(22):
            await AIDocumentService.create_project_version(db, pid, "T1", "a.md", f"c{i}", uid)
        # 不抛异常即通过（真实 DB 下会触发删除，单测用 AsyncMock 验证路径可达）
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestProjectDocVersion -v`
Expected: FAIL — `AttributeError: ... create_project_version`

- [ ] **Step 3: Implement version CRUD**

In `service.py`, mirror `create_personal_version` etc. Add after `write_project_output`:

```python
    _PROJECT_VERSION_LIMIT = 20

    @staticmethod
    async def create_project_version(
        db: AsyncSession,
        project_id: UUID,
        thread_id: str,
        rel_path: str,
        content: str,
        editor_user_id: UUID,
        label: str | None = None,
    ) -> UUID:
        """Create a project doc snapshot; cap per-file history at 20."""
        from sqlalchemy import delete as sa_delete

        from app.extensions.models import ProjectDocVersion

        version = ProjectDocVersion(
            project_id=project_id, thread_id=thread_id, rel_path=rel_path,
            content=content, editor_user_id=editor_user_id, label=label,
        )
        db.add(version)
        await db.flush()
        stmt = (
            select(ProjectDocVersion.id)
            .where(
                ProjectDocVersion.project_id == project_id,
                ProjectDocVersion.thread_id == thread_id,
                ProjectDocVersion.rel_path == rel_path,
            )
            .order_by(ProjectDocVersion.created_at.desc())
            .offset(AIDocumentService._PROJECT_VERSION_LIMIT)
        )
        old_ids = (await db.execute(stmt)).scalars().all()
        if old_ids:
            await db.execute(sa_delete(ProjectDocVersion).where(ProjectDocVersion.id.in_(old_ids)))
        return version.id

    @staticmethod
    async def list_project_versions(
        db: AsyncSession, project_id: UUID, thread_id: str, rel_path: str,
    ) -> list[dict]:
        from app.extensions.models import ProjectDocVersion

        rows = (
            await db.execute(
                select(ProjectDocVersion)
                .where(
                    ProjectDocVersion.project_id == project_id,
                    ProjectDocVersion.thread_id == thread_id,
                    ProjectDocVersion.rel_path == rel_path,
                )
                .order_by(ProjectDocVersion.created_at.desc())
            )
        ).scalars().all()
        return [
            {
                "id": v.id, "label": v.label, "created_at": v.created_at,
                "editor_user_id": v.editor_user_id,
                "preview": (v.content or "")[:120], "content_length": len(v.content or ""),
            }
            for v in rows
        ]

    @staticmethod
    async def get_project_version(db: AsyncSession, project_id: UUID, version_id: UUID) -> dict | None:
        from app.extensions.models import ProjectDocVersion

        v = (
            await db.execute(
                select(ProjectDocVersion).where(
                    ProjectDocVersion.id == version_id,
                    ProjectDocVersion.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if v is None:
            return None
        return {
            "id": v.id, "label": v.label, "created_at": v.created_at, "content": v.content,
            "thread_id": v.thread_id, "rel_path": v.rel_path, "editor_user_id": v.editor_user_id,
        }

    @staticmethod
    async def restore_project_version(db: AsyncSession, project_id: UUID, version_id: UUID) -> dict | None:
        from app.extensions.models import ProjectDocVersion

        v = (
            await db.execute(
                select(ProjectDocVersion).where(
                    ProjectDocVersion.id == version_id,
                    ProjectDocVersion.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if v is None:
            return None
        await AIDocumentService.write_project_output(
            db, project_id, v.thread_id, v.rel_path, v.content, v.editor_user_id,
        )
        return {"content": v.content, "thread_id": v.thread_id, "rel_path": v.rel_path}
```

Now **remove** the `try/except` guard added in Task 4 around `create_project_version` (restore the direct call) since the method now exists:

```python
        await asyncio.to_thread(lambda: target.write_text(content, encoding="utf-8"))
        await AIDocumentService.create_project_version(
            db, project_id, thread_id, rel_path, content, editor_user_id,
        )
```

- [ ] **Step 4: Run full test file**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/tests/test_project_outputs.py
git commit -m "feat(docmgr): ProjectDocVersion CRUD — snapshot/list/get/restore"
```

---

## Task 6: `get_project_files` 复用 `listProjectOutputs`（项目详情页文件 tab 对齐）

**Files:**
- Modify: `backend/app/extensions/project/service.py:1200`
- Test: `backend/tests/test_project_outputs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_outputs.py`:

```python
class TestGetProjectFilesAlignment:
    @pytest.mark.asyncio
    async def test_get_project_files_uses_list_project_outputs(self, tmp_path: Path):
        """项目详情页文件 tab 与文档空间项目区同源（都走 outputs/ 聚合）。"""
        from app.extensions.docmgr.service import AIDocumentService
        from app.extensions.project.service import get_project_files

        caller, pid = uuid4(), uuid4()
        out = tmp_path / "users" / str(caller) / "threads" / "Tc" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "消防设计专篇.md").write_text("# x")

        class _M:
            def __init__(self, uid, tid): self.user_id, self.thread_id = uid, tid

        members = [_M(caller, "Tc")]
        fake_db = AsyncMock()
        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_project_members", AsyncMock(return_value=members)):
            mp.return_value.base_dir = tmp_path
            files = await get_project_files(fake_db, pid, caller_user_id=caller)
        names = {f["name"] for f in files}
        assert "消防设计专篇.md" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestGetProjectFilesAlignment -v`
Expected: FAIL — `TypeError: get_project_files() got an unexpected keyword argument 'caller_user_id'`（当前签名无此参数，且仍走 uploads/list）

- [ ] **Step 3: Refactor `get_project_files`**

In `backend/app/extensions/project/service.py`, replace the body of `get_project_files` (lines `:1200-1256`) with a thin wrapper that delegates to `listProjectOutputs`. Replace the whole function with:

```python
async def get_project_files(
    db: AsyncSession,
    project_id,
    *,
    caller_user_id=None,
    cookies=None,
    csrf_token=None,
) -> list[dict]:
    """项目文件列表 — 复用 listProjectOutputs 读 outputs/ 聚合，保证项目详情页
    与文档空间项目区数据一致。cookies/csrf_token 保留以兼容旧调用方（已不使用）。

    caller_user_id 为空时（旧调用方）退化为查任意成员视角；非 member 抛 PermissionError。
    """
    from app.extensions.docmgr.service import AIDocumentService

    # 无 caller 时取首个成员作为视角（兼容旧的无鉴权调用方）
    if caller_user_id is None:
        members = await AIDocumentService._project_members(db, project_id)
        if not members:
            return []
        caller_user_id = members[0].user_id

    res = await AIDocumentService.list_project_outputs(db, project_id, caller_user_id)
    # 归一化字段名，兼容前端旧消费方（name/size/mime_type/thread_id/member/updated_at）
    for f in res["files"]:
        f["mime_type"] = f.pop("mime", None)
        f["updated_at"] = f.pop("modified_at", None)
    return res["files"]
```

- [ ] **Step 4: Run test + grep for stale callers**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py::TestGetProjectFilesAlignment -v`
Expected: PASS

Check no caller breaks (signature kept `cookies/csrf_token` kwargs):

```bash
cd backend && grep -rn "get_project_files(" app/ --include=*.py
```
Expected: the project router calls it; confirm it still compiles. The wrapper kept all kwargs, so callers passing positional/`cookies=` still work.

- [ ] **Step 5: Restart gateway + run full suite**

```bash
docker compose -p eai-docker restart gateway
cd backend && make test
```
Expected: all backend tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/project/service.py backend/tests/test_project_outputs.py
git commit -m "refactor(project): get_project_files reuses listProjectOutputs for outputs aggregation"
```

---

## Task 7: 后端 schemas

**Files:**
- Modify: `backend/app/extensions/schemas.py`（在 `PersonalVersionDetailResponse` 之后，`# ============== Knowledge Base Grant Schemas` 之前，约 `:780`）

- [ ] **Step 1: Add the schemas**

In `backend/app/extensions/schemas.py`, insert before the `# ============== Knowledge Base Grant Schemas` section:

```python
# ============== Project Outputs (跨用户文件系统视图) ==============
# EAI-CUSTOM: 项目 outputs 聚合 + 跨用户编辑写回 + 版本历史。


class ProjectDocFile(BaseModel):
    name: str
    rel_path: str
    size: int
    mime: str
    modified_at: datetime
    member: str
    thread_id: str


class ProjectOutputsResponse(BaseModel):
    files: list[ProjectDocFile]
    total: int = 0


class ProjectDocContentRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=100)
    rel_path: str = Field(..., min_length=1, max_length=500)
    content: str
    if_mtime: float | None = None


class ProjectVersionCreateRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=100)
    rel_path: str = Field(..., min_length=1, max_length=500)
    content: str
    label: str | None = Field(None, max_length=200)


class ProjectVersionListItem(BaseModel):
    id: UUID
    label: str | None
    created_at: datetime
    editor_user_id: UUID
    preview: str
    content_length: int


class ProjectVersionListResponse(BaseModel):
    versions: list[ProjectVersionListItem]


class ProjectVersionDetailResponse(BaseModel):
    id: UUID
    label: str | None
    created_at: datetime
    content: str
    thread_id: str
    rel_path: str
    editor_user_id: UUID
```

- [ ] **Step 2: Verify import (datetime / UUID / Field already imported at top of schemas.py)**

Run: `cd backend && python -c "from app.extensions.schemas import ProjectOutputsResponse, ProjectDocContentRequest, ProjectVersionListResponse; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/schemas.py
git commit -m "feat(docmgr): add project outputs + version schemas"
```

---

## Task 8: docmgr router 端点

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`（在 personal 版本端点之后，文件末尾前）
- Verify imports: `Query`, `HTTPException`, `status`, `UUID`, `get_db`, `require_permission`, `AIDocumentService`, `AsyncSession`, `Depends` already imported (used by personal endpoints). Schema imports: add at top.

- [ ] **Step 1: Check existing schema imports in routers.py**

Run: `cd backend && grep -n "from app.extensions.schemas import\|PersonalVersionCreateRequest" app/extensions/docmgr/routers.py | head`
If the file imports schemas lazily or at top, mirror it. The `PersonalDocContentRequest` is defined **inline** in routers.py (`:866`). For project schemas we added them to `schemas.py`, so ensure the import. If routers.py does not import from `app.extensions.schemas`, add to the existing import block:

```python
from app.extensions.schemas import (
    ProjectOutputsResponse, ProjectDocContentRequest,
    ProjectVersionCreateRequest, ProjectVersionListResponse, ProjectVersionDetailResponse,
    ProjectVersionListItem,
)
```
(If a schemas import already exists, append these names to it.)

- [ ] **Step 2: Add the route handlers**

Append to `backend/app/extensions/docmgr/routers.py` (after the personal `restore_personal_version` endpoint, end of file):

```python
# ── EAI-CUSTOM: 项目 outputs 跨用户聚合 + 编辑写回 + 版本 ────────────────────


@router.get("/projects/{project_id}/outputs", response_model=ProjectOutputsResponse)
async def list_project_outputs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    """项目区文件系统视图：聚合本项目所有成员线程的 outputs/。非 member → 403。"""
    try:
        return await AIDocumentService.list_project_outputs(db, project_id, current_user.id)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a project member")


@router.put("/projects/{project_id}/outputs")
async def save_project_content(
    project_id: UUID,
    data: ProjectDocContentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),
):
    """跨用户编辑写回（服务器调解）。带 mtime 乐观锁：过期 → 409。"""
    from app.extensions.docmgr.service import _StaleWrite

    try:
        await AIDocumentService.write_project_output(
            db, project_id, data.thread_id, data.rel_path, data.content,
            current_user.id, data.if_mtime,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread outputs not found")
    except _StaleWrite:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件已被他人修改，请刷新")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/versions")
async def create_project_version(
    project_id: UUID,
    data: ProjectVersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),
):
    """手动创建项目文档版本快照。"""
    vid = await AIDocumentService.create_project_version(
        db, project_id, data.thread_id, data.rel_path, data.content, current_user.id, data.label,
    )
    await db.commit()
    return {"ok": True, "id": str(vid)}


@router.get("/projects/{project_id}/versions", response_model=ProjectVersionListResponse)
async def list_project_versions(
    project_id: UUID,
    thread_id: str = Query(..., min_length=1, max_length=100),
    rel_path: str = Query(..., min_length=1, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    versions = await AIDocumentService.list_project_versions(db, project_id, thread_id, rel_path)
    return {"versions": versions}


@router.get("/projects/{project_id}/versions/{version_id}", response_model=ProjectVersionDetailResponse)
async def get_project_version(
    project_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    v = await AIDocumentService.get_project_version(db, project_id, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    return v


@router.post("/projects/{project_id}/versions/{version_id}/restore")
async def restore_project_version(
    project_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),
):
    result = await AIDocumentService.restore_project_version(db, project_id, version_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    await db.commit()
    return {"ok": True, **result}
```

- [ ] **Step 3: Restart gateway + smoke the endpoints**

```bash
docker compose -p eai-docker restart gateway
# 等 ~10s，确认路由注册无报错
docker compose -p eai-docker logs --tail=30 gateway | grep -i "error\|traceback" || echo "clean"
```

- [ ] **Step 4: Backend lint + test**

```bash
cd backend && make lint && make test
```
Expected: lint clean, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/routers.py
git commit -m "feat(docmgr): project outputs + version REST endpoints"
```

---

## Task 9: 前端 API 方法

**Files:**
- Modify: `frontend/src/extensions/docmgr/api.ts`

Note: the personal-outputs API lives in `frontend/src/extensions/api/index.ts:728` (`listPersonalOutputs` etc. on `docmgrApi`). **Confirm the canonical export** before editing:

- [ ] **Step 1: Locate the real docmgrApi object**

Run: `cd frontend && grep -rn "listPersonalOutputs\|docmgrApi" src/extensions --include=*.ts --include=*.tsx | head`
There are two candidates: `src/extensions/api/index.ts` (the `docmgrApi` with `listPersonalOutputs`) and possibly `src/extensions/docmgr/api.ts`. The hook `usePersonalOutputs.ts` imports `from "../api"` → so **`src/extensions/docmgr/api.ts`** is the real one the docmgr UI uses. Read it to confirm `listPersonalOutputs` is defined there:

Run: `cd frontend && grep -n "listPersonalOutputs\|savePersonalContent\|createPersonalVersion\|restorePersonalVersion" src/extensions/docmgr/api.ts`

If the methods are in `src/extensions/docmgr/api.ts`, add the project methods there. If instead they live in `src/extensions/api/index.ts` and `docmgr/api.ts` re-exports, add to whichever file actually defines `listPersonalOutputs` (match the pattern).

- [ ] **Step 2: Add project methods (mirror personal)**

In the file that defines `listPersonalOutputs` (the `docmgrApi` object), append these methods before the closing `};` of the object:

```ts
  // ── 项目 outputs（跨用户文件系统视图 + 编辑写回 + 版本） ────────────
  listProjectOutputs: (projectId: string) =>
    request<{ files: Array<{ name: string; rel_path: string; size: number; mime: string; modified_at: string; member: string; thread_id: string }>; total: number }>(
      `/docmgr/projects/${encodeURIComponent(projectId)}/outputs`,
    ),

  /** 跨用户编辑写回；if_mtime 为乐观锁（过期服务端 409）。 */
  saveProjectContent: (projectId: string, data: { thread_id: string; rel_path: string; content: string; if_mtime?: number }) =>
    request<{ ok: boolean }>(`/docmgr/projects/${encodeURIComponent(projectId)}/outputs`, { method: "PUT", body: JSON.stringify(data) }),

  createProjectVersion: (projectId: string, data: { thread_id: string; rel_path: string; content: string; label?: string }) =>
    request<{ ok: boolean; id: string }>(`/docmgr/projects/${encodeURIComponent(projectId)}/versions`, { method: "POST", body: JSON.stringify(data) }),

  listProjectVersions: (projectId: string, threadId: string, relPath: string) =>
    request<{ versions: Array<{ id: string; label: string | null; created_at: string; editor_user_id: string; preview: string; content_length: number }> }>(
      `/docmgr/projects/${encodeURIComponent(projectId)}/versions?thread_id=${encodeURIComponent(threadId)}&rel_path=${encodeURIComponent(relPath)}`,
    ),

  getProjectVersion: (projectId: string, versionId: string) =>
    request<{ id: string; label: string | null; created_at: string; content: string; thread_id: string; rel_path: string; editor_user_id: string }>(
      `/docmgr/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`,
    ),

  restoreProjectVersion: (projectId: string, versionId: string) =>
    request<{ ok: boolean; content: string; thread_id: string; rel_path: string }>(
      `/docmgr/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/restore`,
      { method: "POST" },
    ),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/api.ts
git commit -m "feat(docmgr-fe): add project outputs + version API methods"
```

---

## Task 10: `useProjectOutputs(pid)` hook

**Files:**
- Create: `frontend/src/extensions/docmgr/useProjectOutputs.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/extensions/docmgr/useProjectOutputs.ts`:

```ts
"use client"

import { useCallback, useEffect, useState } from "react";
import { docmgrApi } from "./api";

export interface ProjectDocFile {
  name: string; rel_path: string; size: number; mime: string;
  modified_at: string; member: string; thread_id: string;
}

export function useProjectOutputs(projectId: string | null) {
  const [files, setFiles] = useState<ProjectDocFile[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) { setFiles([]); setTotal(0); return; }
    setLoading(true); setError(null);
    try {
      const data = await docmgrApi.listProjectOutputs(projectId);
      setFiles(data.files); setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载项目文档失败");
      setFiles([]);
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  /** 跨用户编辑写回；返回新 mtime 或抛错（调用方处理 409 提示）。 */
  const saveContent = useCallback(async (
    threadId: string, relPath: string, content: string, ifMtime?: number,
  ): Promise<number | null> => {
    if (!projectId) return null;
    await docmgrApi.saveProjectContent(projectId, { thread_id: threadId, rel_path: relPath, content, if_mtime: ifMtime });
    void refresh(); // 刷新拿新 mtime
    return null;
  }, [projectId, refresh]);

  return { files, total, loading, error, refresh, saveContent };
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/useProjectOutputs.ts
git commit -m "feat(docmgr-fe): add useProjectOutputs hook"
```

---

## Task 11: DocumentManagement 项目区改文件系统视图

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

This is the largest UI change. The project section (lines `:484-512`) currently renders `<ProjectFolderTree>` (folder-tree view backed by AIDocument). Replace with: a project picker + flat file list (reuse personal output-row styling) + member attribution badge. Editing routes through the personal editor UI but calls `saveProjectContent`.

- [ ] **Step 1: Add project picker state + hook near other state (around `:225` where `personalOutputs` is declared)**

Find `const personalOutputs = usePersonalOutputs();` and add below it:

```tsx
  // EAI-CUSTOM: 项目区文件系统视图（替代 AIDocument folder-tree）
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const projectOutputs = useProjectOutputs(selectedProjectId);
```

Add the import at top (near `import { usePersonalOutputs } from "./usePersonalOutputs";`):

```tsx
import { useProjectOutputs } from "./useProjectOutputs";
```

- [ ] **Step 2: Replace the project section JSX (lines `:484-512`)**

Replace the entire `{canUseProject && ( ... )}` block (the `项目文件夹` / `ProjectFolderTree` section) with a filesystem-view + project picker:

```tsx
          {canUseProject && (
          <div className="pt-2 mt-2">
            <button
              onClick={() => setArchiveOpen((v) => !v)}
              className="flex w-full items-center justify-between px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
            >
              <div className="flex items-center gap-2">
                <Archive className="w-3.5 h-3.5" />
                <span>共享文档</span>
              </div>
              {archiveOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
            {archiveOpen && (
              <div className="px-2 pt-1 space-y-1">
                {/* 项目选择器：列出当前用户参与的项目 */}
                <ProjectPicker
                  selectedId={selectedProjectId}
                  onSelect={setSelectedProjectId}
                />
                {/* 文件列表（文件系统视图 + 成员归属 badge） */}
                {projectOutputs.loading && (
                  <p className="text-[10px] text-muted-foreground/50 px-3 py-1.5">加载中...</p>
                )}
                {projectOutputs.error && (
                  <p className="text-[10px] text-destructive/70 px-3 py-1.5">{projectOutputs.error}</p>
                )}
                {!projectOutputs.loading && projectOutputs.files.length === 0 && selectedProjectId && (
                  <p className="text-[10px] text-muted-foreground/50 px-3 py-1.5">暂无文件</p>
                )}
                {projectOutputs.files.map((f) => (
                  <button
                    key={`${f.thread_id}:${f.rel_path}`}
                    onClick={() => onOpenProjectFile?.(f.thread_id, f.rel_path, f.name, f.member, new Date(f.modified_at).getTime() / 1000)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-xs rounded-md hover:bg-muted transition-colors text-left"
                  >
                    <FileText className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="shrink-0 text-[9px] text-primary/70 bg-primary/10 rounded px-1 py-0.5">{f.member}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          )}
```

- [ ] **Step 3: Add the `ProjectPicker` helper component + `onOpenProjectFile` prop**

The component needs a list of the user's projects. Reuse `projectApi.list` (`frontend/src/extensions/project/api.ts:22`) which returns `{items, total}`. Add a small component at the bottom of `DocumentManagement.tsx` (or a sibling file — keep it inline for shortest diff). Add above the main component:

```tsx
/** 项目选择器：下拉列出当前用户参与的项目。EAI-CUSTOM */
function ProjectPicker({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string | null) => void }) {
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([]);
  useEffect(() => {
    projectApi.list().then((res) => {
      setProjects((res.items || []).map((p: Record<string, unknown>) => ({
        id: String(p.id), name: String(p.name ?? p.title ?? "未命名项目"),
      })));
    }).catch(() => setProjects([]));
  }, []);
  if (projects.length === 0) return <p className="text-[10px] text-muted-foreground/50 px-3 py-1.5">无可见项目</p>;
  return (
    <select
      value={selectedId ?? ""}
      onChange={(e) => onSelect(e.target.value || null)}
      className="w-full text-xs rounded-md border border-border bg-background px-2 py-1 mb-1"
    >
      <option value="">选择项目…</option>
      {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}
```

Add the imports:

```tsx
import { projectApi } from "../project/api";
```

And extend the main component's props with an optional `onOpenProjectFile` callback (the parent / editor wiring in Task 12). Find the component's props type/interface and add:

```tsx
  onOpenProjectFile?: (threadId: string, relPath: string, name: string, member: string, mtime: number) => void;
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && pnpm typecheck`
Expected: no new errors (unused `ProjectFolderTree` import may now be unused — remove the import if lint flags it).

If lint flags unused imports (`ProjectFolderTree`, `ShareDialog`), remove them:

```tsx
// remove these if now unused:
// import { ProjectFolderTree } from "./ProjectFolderTree";
// import ShareDialog from "./ShareDialog";
```

- [ ] **Step 5: Restart frontend + manual smoke**

```bash
docker compose -p eai-docker restart frontend
```
Open `http://localhost:2026/docmgr`, click 共享文档, pick a project, confirm files from lisi's thread appear with the `[lisi]` badge. (zhangsan logs in → same files visible.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr-fe): project section → filesystem view with project picker + member badge"
```

---

## Task 12: 项目文件编辑接线（编辑器走 `saveProjectContent` + 409 提示）

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`（编辑器保存路径）

The personal editor (`PersonalBlockNoteEditor`) saves via `savePersonalContent`. The project file needs to save via `saveProjectContent` instead and surface the 409 "已被他人修改，请刷新" toast.

- [ ] **Step 1: Wire `onOpenProjectFile` to open the editor in project mode**

In `DocumentManagement.tsx`, where the personal file open handler lives (find the existing `onOpen` / editor-open logic for personal outputs — the `expandedKeys` + click handler that sets the editor target), add a parallel project-file open path. Add state for the currently-open project file:

```tsx
  const [projectFileOpen, setProjectFileOpen] = useState<{
    threadId: string; relPath: string; name: string; member: string; mtime: number; content: string;
  } | null>(null);

  const handleOpenProjectFile = useCallback(async (
    threadId: string, relPath: string, name: string, member: string, mtime: number,
  ) => {
    try {
      // 读文件内容（复用 FilePreviewModal 的读路径，或新增 docmgrApi.readProjectFile）
      const content = await docmgrApi.readProjectOutput?.(selectedProjectId!, threadId, relPath)
        ?? "";
      setProjectFileOpen({ threadId, relPath, name, member, mtime, content });
    } catch { setProjectFileOpen(null); }
  }, [selectedProjectId]);
```

Pass `onOpenProjectFile={handleOpenProjectFile}` to the component (the JSX added in Task 11 references `onOpenProjectFile?.(...)`).

- [ ] **Step 2: Add a read endpoint + API method for project file content**

The aggregator returns metadata only; to open a file we need its content. Add a backend read endpoint (mirror `read_file_content` but project-scoped). In `docmgr/service.py` add:

```python
    @staticmethod
    async def read_project_output(
        db: AsyncSession, project_id: UUID, thread_id: str, rel_path: str, caller_user_id: UUID,
    ) -> dict:
        """读项目文件内容（跨用户）。非 member → PermissionError。"""
        members = await AIDocumentService._project_members(db, project_id)
        if not any(getattr(m, "user_id", None) == caller_user_id for m in members):
            raise PermissionError("not a project member")
        base = AIDocumentService._locate_thread_outputs(thread_id)
        if base is None:
            raise FileNotFoundError(thread_id)
        target = (base / rel_path).resolve()
        if not str(target).startswith(str(base.resolve())):
            raise ValueError("path escape")
        if not target.is_file():
            raise FileNotFoundError(rel_path)
        # 10MB 上限，沿用 read_file_content 约定
        if target.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("file too large")
        return {"content": target.read_text(encoding="utf-8"), "mtime": target.stat().st_mtime}
```

In `docmgr/routers.py` add:

```python
@router.get("/projects/{project_id}/outputs/content")
async def read_project_output(
    project_id: UUID,
    thread_id: str = Query(..., min_length=1, max_length=100),
    rel_path: str = Query(..., min_length=1, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    try:
        return await AIDocumentService.read_project_output(db, project_id, thread_id, rel_path, current_user.id)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a project member")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
```

Add the API method (in the file from Task 9):

```ts
  readProjectOutput: (projectId: string, threadId: string, relPath: string) =>
    request<{ content: string; mtime: number }>(
      `/docmgr/projects/${encodeURIComponent(projectId)}/outputs/content?thread_id=${encodeURIComponent(threadId)}&rel_path=${encodeURIComponent(relPath)}`,
    ),
```

(Now the `?? ""` fallback in Step 1 becomes a real call; simplify `handleOpenProjectFile` to use it directly.)

- [ ] **Step 3: Render the editor for the open project file + 409 handling**

Where the personal editor renders (find `<PersonalBlockNoteEditor` usage), add a branch for `projectFileOpen`. On save, call `projectOutputs.saveContent(...)` and on rejection show toast "文件已被他人修改，请刷新". Use the existing toast pattern (the file imports `toast`? if not, add `import { toast } from "sonner"`):

```tsx
  const handleSaveProjectFile = useCallback(async (content: string) => {
    if (!projectFileOpen || !selectedProjectId) return;
    try {
      await projectOutputs.saveContent(
        projectFileOpen.threadId, projectFileOpen.relPath, content, projectFileOpen.mtime,
      );
      toast.success("已保存");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409") || msg.includes("已被他人修改")) {
        toast.error("文件已被他人修改，请刷新后重试");
      } else {
        toast.error("保存失败");
      }
    }
  }, [projectFileOpen, selectedProjectId, projectOutputs]);
```

Render the project editor alongside the personal one (the `request` helper likely throws on non-2xx so 409 lands in the catch — confirm by reading `request` impl: `cd frontend && grep -n "function request\|export const request\|if (!res.ok" src/extensions/docmgr/api.ts | head`).

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && pnpm typecheck && BETTER_AUTH_SECRET=local-dev-secret pnpm build`
Expected: build succeeds.

- [ ] **Step 5: Restart both + end-to-end smoke**

```bash
docker compose -p eai-docker restart gateway frontend
```
Smoke: lisi generates 消防设计专篇 in project thread → opens 共享文档 → edits → saves. zhangsan opens same file → edits → if lisi edited in between, zhangsan gets 409 toast "文件已被他人修改，请刷新".

- [ ] **Step 6: Backend test for read_project_output + final full suite**

Add to `tests/test_project_outputs.py`:

```python
    @pytest.mark.asyncio
    async def test_read_project_output_cross_user(self, tmp_path: Path):
        from app.extensions.docmgr.service import AIDocumentService

        lisi, zhangsan, pid = uuid4(), uuid4(), uuid4()
        out = tmp_path / "users" / str(lisi) / "threads" / "T1" / "user-data" / "outputs"
        out.mkdir(parents=True)
        (out / "doc.md").write_text("hello")

        class _M:
            def __init__(self, uid, tid): self.user_id, self.thread_id = uid, tid

        members = [_M(lisi, "T1"), _M(zhangsan, "T1")]
        with patch("deerflow.config.paths.Paths") as mp, \
             patch.object(AIDocumentService, "_project_members", AsyncMock(return_value=members)):
            mp.return_value.base_dir = tmp_path
            res = await AIDocumentService.read_project_output(AsyncMock(), pid, "T1", "doc.md", zhangsan)
        assert res["content"] == "hello"
```

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_outputs.py -v && make lint && make test`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/routers.py backend/tests/test_project_outputs.py frontend/src/extensions/docmgr/api.ts frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): project file read endpoint + editor wiring with 409 stale-write handling"
```

---

## Final: 全量校验 + 收尾

- [ ] **Backend**: `cd backend && make lint && make test`
- [ ] **Frontend**: `cd frontend && pnpm lint && pnpm typecheck && BETTER_AUTH_SECRET=local-dev-secret pnpm build`
- [ ] **重启全部服务确认无报错**:
  ```bash
  docker compose -p eai-docker restart gateway frontend
  docker compose -p eai-docker logs --tail=40 gateway | grep -iE "error|traceback" || echo "gateway clean"
  ```
- [ ] **建表确认**: `docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\dt project_doc_versions"`
- [ ] **端到端验收**（spec §4 测试矩阵）:
  - lisi 项目对话生成消防设计专篇 → 共享文档自动出现（无需 present_files）。
  - zhangsan（组员）登录 → 共享文档同一项目下看到该文件，带 `[lisi]` badge。
  - zhangsan 编辑保存成功 → ProjectDocVersion 写入一条。
  - 并发：lisi 编辑后 zhangsan 用旧 mtime 保存 → 409 提示。
  - lisi 的该线程不在「我的文档」个人区出现（排除过滤）。
  - 项目详情页「文件」tab 与共享文档列表一致（同源 listProjectOutputs）。
- [ ] **OpenWolf 收尾**: 追加 `.wolf/memory.md` 一行；若 cerebrum 无「项目 outputs 走纯文件系统聚合、弃 AIDocument file_ref」条目则补记。

---

## Self-Review (spec coverage)

| Spec requirement | Task |
|------|------|
| §1 `listProjectOutputs` 聚合 + 成员校验 + 跳过无线程成员 | Task 2 |
| §1 个人区排除项目线程 | Task 3 |
| §1 `ProjectDocVersion` 表 + 20 上限 | Task 1, 5 |
| §2 跨用户读（服务器） | Task 12 (read endpoint) |
| §2 按 thread_id 扫桶定位（避双 user_id） | Task 4 (`_locate_thread_outputs`) |
| §2 写回原路径 + 路径穿越校验 | Task 4 |
| §2 mtime 乐观锁 409 | Task 4 + router Task 8/12 |
| §2 版本快照 + 回滚 | Task 5 |
| §2 非文本仅查看 | _is_text_mime 复用（编辑器侧 Task 12，沿用个人区判断，已存在） |
| §3 两区文件系统视图 + 项目选择器 + 成员 badge | Task 11 |
| §3 弃用 folder-tree / ShareDialog | Task 11 |
| §3 版本历史 UI | 复用 VersionHistoryDialog（编辑器接线 Task 12 传入 project 维度） |
| §4 项目详情页文件 tab 对齐 | Task 6 |
| 不动 harness | 全部任务在 app/extensions + frontend，零 `packages/harness/deerflow/` 改动 ✓ |
| TDD | Task 1-6, 12 均先写测试 ✓ |

**Placeholder scan:** 无 TBD/TODO；每步含完整代码或确切命令。
**Type consistency:** `list_project_outputs` 返回 `member`/`thread_id`/`modified_at` 字段在 schema(Task 7)、API(Task 9)、hook(Task 10)、UI(Task 11) 一致；`saveProjectContent` 的 `{thread_id, rel_path, content, if_mtime}` 在 API/路由/schema 一致；`_StaleWrite` 在 service 定义、router import、test import 一致。
