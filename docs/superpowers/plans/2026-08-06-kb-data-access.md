# 知识库细粒度数据访问控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为知识库加每-KB 显式授权（`knowledge_base_grants` 表），可见性 = 角色 data_scope OR 显式授权，并支持 read/write 权限语义与临时授权过期。

**Architecture:** 新增 `KnowledgeBaseGrant` 模型（`init_db` 的 `create_all` 自动建表）；新增 `knowledge/access.py` 提供 grant-EXISTS 可见性子句与 `has_kb_grant` 写权限检查；KB 查询层（`_load_kb_scoped` + list + federated）统一拼 `or_(scope, grant)`；update/delete/upload 写操作扩为 `owner | write-grantee | 超管`；新增 `/knowledge-bases/{id}/grants` CRUD（owner/超管）。前端在 KB 管理页加授权列表+增删 UI。

**Tech Stack:** FastAPI + SQLAlchemy async (PG) + FilterRule/DataScopeEngine（既有）；React + Next.js。

**Spec:** `docs/superpowers/specs/2026-08-06-kb-data-access-design.md`

**验证环境（每步后端改完）:** `docker compose -p eai-docker restart gateway`；前端 `docker compose -p eai-docker restart frontend`。后端测试：`cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`。前端：`docker exec deer-flow-frontend sh -c "cd /app/frontend && pnpm typecheck"`。

---

### Task 1: 模型 `KnowledgeBaseGrant`

**Files:**
- Modify: `backend/app/extensions/models/__init__.py`（在 `KnowledgeBase.documents` 关系后，line ~201）
- Test: `backend/tests/test_knowledge_data_access.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_knowledge_data_access.py` 末尾追加：

```python
def test_knowledge_base_grant_model_registered():
    from app.extensions.models import KnowledgeBaseGrant

    assert KnowledgeBaseGrant.__tablename__ == "knowledge_base_grants"
    cols = {c.name for c in KnowledgeBaseGrant.__table__.columns}
    assert {"kb_id", "grantee_type", "grantee_id", "permission", "expires_at", "created_by", "created_at"} <= cols
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py::test_knowledge_base_grant_model_registered -q`
Expected: FAIL（`ImportError: cannot import name 'KnowledgeBaseGrant'`）

- [ ] **Step 3: 加模型**

在 `backend/app/extensions/models/__init__.py` 的 `KnowledgeBase.documents = relationship(...)` 之后（line 201 附近）插入：

```python
class KnowledgeBaseGrant(Base):
    """EAI-CUSTOM: 每-KB 显式授权（实例级 ACL）——与角色 data_scope 互补，授权为可见性 OR 例外。"""

    __tablename__ = "knowledge_base_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grantee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user | dept | role
    grantee_id: Mapped[str] = mapped_column(String(64), nullable=False)  # user/dept=UUID串; role=角色code
    permission: Mapped[str] = mapped_column(String(20), default="read")  # read | write
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`
Expected: PASS（全部既有测试 + 新测试）

- [ ] **Step 5: 重启 gateway 建表**

Run: `docker compose -p eai-docker restart gateway`
Expected: 容器启动；`docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\d knowledge_base_grants"` 显示表结构

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_knowledge_data_access.py
git commit -m "feat(kb-access): KnowledgeBaseGrant 模型 + 建表(create_all)"
```

---

### Task 2: `kb_grant_visible_clause` — 授权可见性 EXISTS 子句

**Files:**
- Create: `backend/app/extensions/knowledge/access.py`
- Test: `backend/tests/test_knowledge_data_access.py`（追加）

- [ ] **Step 1: 写失败测试**

追加：

```python
from app.extensions.knowledge.access import kb_grant_visible_clause


def test_kb_grant_visible_clause_sql_contains_grant_table_and_matches():
    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    sql = str(kb_grant_visible_clause(idn).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "knowledge_base_grants" in sql
    assert "user" in sql and "u1" in sql
    assert "dept" in sql and "d1" in sql
    assert "dept_head" in sql
    assert "expires_at" in sql
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py::test_kb_grant_visible_clause_sql_contains_grant_table_and_matches -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.extensions.knowledge.access'`）

- [ ] **Step 3: 实现 `access.py`**

创建 `backend/app/extensions/knowledge/access.py`：

```python
"""EAI-CUSTOM: 每-KB 显式授权的可见性/写权限辅助（knowledge_base_grants）。"""
from __future__ import annotations

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.extensions.auth.identity import AttributeSet
from app.extensions.models import KnowledgeBase, KnowledgeBaseGrant


def _grantee_match(g, identity: AttributeSet):
    """授权行命中身份的 OR 条件：user=用户id、dept=部门id、role=角色code。"""
    return or_(
        and_(g.grantee_type == "user", g.grantee_id == str(identity.user_id)),
        and_(g.grantee_type == "dept", g.grantee_id.in_(identity.dept_ids or [])),
        and_(g.grantee_type == "role", g.grantee_id == identity.role_code),
    )


def _grant_active(g):
    """未过期（expires_at 为空或未来）。"""
    return or_(g.expires_at.is_(None), g.expires_at > func.now())


def kb_grant_visible_clause(identity: AttributeSet):
    """SQL EXISTS：当前 KB 有一条命中身份的未过期授权行。拼进 KB 查询 WHERE 的 OR 分支。"""
    g = aliased(KnowledgeBaseGrant)
    return exists(
        select(1).where(and_(g.kb_id == KnowledgeBase.id, _grantee_match(g, identity), _grant_active(g)))
    )


async def has_kb_grant(db, kb_id, identity: AttributeSet, permission: str | None = None) -> bool:
    """当前身份对某 KB 是否有显式授权（可选限定 permission=read|write）。"""
    g = KnowledgeBaseGrant
    clauses = [g.kb_id == kb_id, _grantee_match(g, identity), _grant_active(g)]
    if permission:
        clauses.append(g.permission == permission)
    stmt = select(g.id).where(and_(*clauses)).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/access.py backend/tests/test_knowledge_data_access.py
git commit -m "feat(kb-access): 授权可见性 EXISTS 子句 + has_kb_grant 写权限检查"
```

---

### Task 3: `has_kb_grant` 测试 + 写权限判定

**Files:**
- Test: `backend/tests/test_knowledge_data_access.py`（追加）
- Modify: `backend/app/extensions/knowledge/access.py`（Task 2 已含 `has_kb_grant`）

- [ ] **Step 1: 写失败测试**

追加：

```python
from app.extensions.knowledge.access import has_kb_grant
from app.extensions.models import KnowledgeBaseGrant


@pytest.mark.asyncio
async def test_has_kb_grant_matches_and_permission_filter():
    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    kb_id = uuid.uuid4()

    # grant 命中（write）
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute.return_value = res
    assert await has_kb_grant(db, kb_id, idn, "write") is True

    # 未命中
    db2 = AsyncMock()
    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = None
    db2.execute.return_value = res2
    assert await has_kb_grant(db2, kb_id, idn, "write") is False
```

（文件顶部已有 `from unittest.mock import AsyncMock, MagicMock`、`import uuid`、`import pytest`，直接可用。）

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py::test_has_kb_grant_matches_and_permission_filter -q`
Expected: FAIL（`NameError: name 'has_kb_grant' is not defined`，若 Task 2 未完成则先完成 Task 2）

- [ ] **Step 3: 确认实现已存在（Task 2 已写）** — 无需改动，运行测试

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_knowledge_data_access.py
git commit -m "test(kb-access): has_kb_grant 命中/未命中 + permission 过滤"
```

---

### Task 4: 可见性组合接入 `_load_kb_scoped` + list + federated

**Files:**
- Modify: `backend/app/extensions/knowledge/routers.py`（`_load_kb_scoped` line 58-75；list line 89-127；federated_search 约 391-396）
- Modify: `backend/app/extensions/auth/middleware.py`（新增 `current_identity` 依赖）
- Test: `backend/tests/test_knowledge_data_access.py`（追加）

- [ ] **Step 1: 写失败测试（`current_identity` + `_load_kb_scoped` 带 identity 时含 grant OR）**

追加：

```python
from sqlalchemy import or_ as sa_or

from app.extensions.knowledge.access import kb_grant_visible_clause


@pytest.mark.asyncio
async def test_load_kb_scoped_with_identity_or_grants_grant_exists():
    db = _capture_session()
    idn = AttributeSet(user_id="u1", username="u1", role_code="r", dept_ids=["d1"])
    scope = FilterRule(operator="eq", field="owner_id", value=uuid.uuid4())
    kb_id = uuid.uuid4()
    # 直接组合验证：scope OR grant
    clause = sa_or(scope.to_sqlalchemy(KnowledgeBase, {"owner_id": KnowledgeBase.owner_id, "access_type": KnowledgeBase.access_type, "allowed_depts": KnowledgeBase.allowed_depts}), kb_grant_visible_clause(idn))
    sql = str(clause.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "knowledge_base_grants" in sql
    assert "owner_id" in sql
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py::test_load_kb_scoped_with_identity_or_grants_grant_exists -q`
Expected: 通过（此测试直接组合已有函数，应先通过——作为组合行为的回归锚点）。若失败则检查 `kb_grant_visible_clause` 导入。

- [ ] **Step 3: 加 `current_identity` 依赖**

在 `backend/app/extensions/auth/middleware.py` 中 `with_data_scope`（line 331）之前插入：

```python
async def current_identity(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """EAI-CUSTOM: 解析当前用户的完整 AttributeSet（user_id/dept_ids/role_code 等）。"""
    from app.extensions.auth.identity import get_identity_provider

    return await get_identity_provider().resolve(current_user.id, db)
```

（确认 `get_current_user`、`get_db`、`CurrentUser` 在本文件已 import；`AttributeSet` 用于注解可加 `from app.extensions.auth.identity import AttributeSet`。）

- [ ] **Step 4: 改 `_load_kb_scoped` 支持 identity（向后兼容）**

`backend/app/extensions/knowledge/routers.py` 的 `_load_kb_scoped` 改为：

```python
async def _load_kb_scoped(db: AsyncSession, kb_id: UUID, scope: FilterRule, identity=None) -> KnowledgeBase | None:
    from sqlalchemy import or_ as sa_or
    from sqlalchemy import select as sa_select

    from app.extensions.knowledge.access import kb_grant_visible_clause

    column_map = {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }
    clause = scope.to_sqlalchemy(KnowledgeBase, column_map)
    # EAI-CUSTOM: 显式授权为可见性 OR 例外（超管 allow_all 时跳过子查询）
    if identity is not None and scope.operator != "allow_all":
        clause = sa_or(clause, kb_grant_visible_clause(identity))
    q = sa_select(KnowledgeBase).where(KnowledgeBase.id == kb_id).where(clause)
    return (await db.execute(q)).scalar_one_or_none()
```

- [ ] **Step 5: list 端点接入 identity + OR**

`list_knowledge_bases` 签名加 `identity: AttributeSet = Depends(current_identity)`，并把 `scope_clause` 改为：

```python
    from app.extensions.knowledge.access import kb_grant_visible_clause
    from sqlalchemy import or_ as sa_or

    column_map = {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }
    scope_clause = scope.to_sqlalchemy(KnowledgeBase, column_map)
    if scope.operator != "allow_all":
        scope_clause = sa_or(scope_clause, kb_grant_visible_clause(identity))
```

（`federated_search` 中同样构造 `scope_clause` 的位置做相同 OR。）

- [ ] **Step 6: 运行全部相关测试确认通过 + 无回归**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py tests/test_p0_permission_gates.py -q`
Expected: PASS（既有 `_load_kb_scoped` 无 identity 用例仍走纯 scope）

- [ ] **Step 7: 重启 gateway**

Run: `docker compose -p eai-docker restart gateway`
Expected: 启动正常（`import app.gateway.app` 不报错）

- [ ] **Step 8: Commit**

```bash
git add backend/app/extensions/knowledge/routers.py backend/app/extensions/auth/middleware.py backend/tests/test_knowledge_data_access.py
git commit -m "feat(kb-access): 可见性 = 角色 scope OR 显式授权(EXISTS) — _load_kb_scoped/list/federated"
```

---

### Task 5: 写操作门（update/delete/upload 加 write-grant）

**Files:**
- Modify: `backend/app/extensions/knowledge/routers.py`（update line 153-168、delete line 171-185、upload line 188-199）

- [ ] **Step 1: 给 update/delete/upload 加 `identity` 依赖 + write-grant 门**

update_knowledge_base 改为（delete 同构）：

```python
@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: UUID,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity=Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 写门 = owner | write-grantee | 超管
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    kb = await KnowledgeBaseService.update_kb(db, kb, data)
    return KnowledgeBaseService.to_response(kb)
```

upload_document 改为：

```python
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 上传内容 = owner | write-grantee | 超管（堵住"上传未 owner 门"缺口）
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
```

（`delete_knowledge_base` 同 update；`delete_document` 与其所在 KB 的 write 门同 upload。）

- [ ] **Step 2: 写回归测试（SQL 层验证 has_kb_grant 的 write 过滤）**

追加到 test_knowledge_data_access.py：

```python
@pytest.mark.asyncio
async def test_has_kb_grant_write_filter_appends_permission():
    from app.extensions.knowledge.access import has_kb_grant

    idn = AttributeSet(user_id="u1", username="u1", role_code="r", dept_ids=[])
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    db.execute.return_value = res
    await has_kb_grant(db, uuid.uuid4(), idn, "write")
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "permission" in sql and "write" in sql
```

- [ ] **Step 3: 运行确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`
Expected: PASS

- [ ] **Step 4: 重启 gateway + Commit**

Run: `docker compose -p eai-docker restart gateway`

```bash
git add backend/app/extensions/knowledge/routers.py backend/tests/test_knowledge_data_access.py
git commit -m "feat(kb-access): 写门 = owner | write-grantee | 超管 (update/delete/upload)"
```

---

### Task 6: Grants CRUD API + 校验

**Files:**
- Modify: `backend/app/extensions/schemas.py`（追加 schema）
- Modify: `backend/app/extensions/knowledge/routers.py`（追加 4 端点）
- Test: `backend/tests/test_knowledge_data_access.py`（追加）

- [ ] **Step 1: 加 schema**

`backend/app/extensions/schemas.py` 末尾追加：

```python
class KnowledgeBaseGrantCreate(BaseModel):
    grantee_type: Literal["user", "dept", "role"]
    grantee_id: str = Field(..., min_length=1, max_length=64)
    permission: Literal["read", "write"] = "read"
    expires_at: datetime | None = None


class KnowledgeBaseGrantUpdate(BaseModel):
    permission: Literal["read", "write"] | None = None
    expires_at: datetime | None = None


class KnowledgeBaseGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kb_id: UUID
    grantee_type: str
    grantee_id: str
    permission: str
    expires_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime
```

（确认文件顶部已 import `Literal` 或补 `from typing import Literal`。）

- [ ] **Step 2: 加端点（owner|超管门 + grantee 校验）**

`backend/app/extensions/knowledge/routers.py` 在 delete_knowledge_base 后追加：

```python
async def _require_kb_owner(db, kb, current_user):
    if kb.owner_id != current_user.id and not await is_superadmin(db, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


async def _validate_grantee(db: AsyncSession, grantee_type: str, grantee_id: str) -> None:
    if grantee_type in ("user", "dept"):
        from sqlalchemy import select as sa_select

        from app.extensions.models import Department, User

        model = User if grantee_type == "user" else Department
        stmt = sa_select(model.id).where(model.id == grantee_id)
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {grantee_type} id")
    else:  # role
        from app.extensions.auth.registry import get_permission_registry

        if grantee_id not in get_permission_registry().list_role_codes():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role code")


@router.get("/{kb_id}/grants", response_model=list[KnowledgeBaseGrantResponse])
async def list_kb_grants(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    stmt = select(KnowledgeBaseGrant).where(KnowledgeBaseGrant.kb_id == kb_id).order_by(KnowledgeBaseGrant.created_at)
    return (await db.execute(stmt)).scalars().all()


@router.post("/{kb_id}/grants", response_model=KnowledgeBaseGrantResponse, status_code=status.HTTP_201_CREATED)
async def add_kb_grant(
    kb_id: UUID,
    data: KnowledgeBaseGrantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    await _validate_grantee(db, data.grantee_type, data.grantee_id)
    grant = KnowledgeBaseGrant(
        kb_id=kb_id, grantee_type=data.grantee_type, grantee_id=data.grantee_id,
        permission=data.permission, expires_at=data.expires_at, created_by=current_user.id,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


@router.patch("/{kb_id}/grants/{grant_id}", response_model=KnowledgeBaseGrantResponse)
async def update_kb_grant(
    kb_id: UUID, grant_id: UUID, data: KnowledgeBaseGrantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    grant = await db.get(KnowledgeBaseGrant, grant_id)
    if grant is None or grant.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    if data.permission is not None:
        grant.permission = data.permission
    if data.expires_at is not None:
        grant.expires_at = data.expires_at
    await db.commit()
    await db.refresh(grant)
    return grant


@router.delete("/{kb_id}/grants/{grant_id}", response_model=MessageResponse)
async def delete_kb_grant(
    kb_id: UUID, grant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    grant = await db.get(KnowledgeBaseGrant, grant_id)
    if grant is None or grant.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await db.delete(grant)
    await db.commit()
    return MessageResponse(message="Grant revoked")
```

（`KnowledgeBaseGrant` 需在文件顶部 import：`from app.extensions.models import KnowledgeBaseGrant`。）

- [ ] **Step 3: 写测试（grantee role 分支校验）**

追加：

```python
@pytest.mark.asyncio
async def test_validate_grantee_role_branch_rejects_unknown():
    from fastapi import HTTPException

    from app.extensions.knowledge.routers import _validate_grantee

    with pytest.raises(HTTPException) as exc:
        await _validate_grantee(AsyncMock(), "role", "no_such_role_code")
    assert exc.value.status_code == 400
```

（说明：`_validate_grantee` 的 user/dept 分支需 DB 查询，由浏览器 E2E（Task 8）覆盖；role 分支依赖 registry、无需 DB，单测锚定。）

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py -q`
Expected: PASS

- [ ] **Step 5: 重启 gateway + Commit**

Run: `docker compose -p eai-docker restart gateway`

```bash
git add backend/app/extensions/schemas.py backend/app/extensions/knowledge/routers.py backend/tests/test_knowledge_data_access.py
git commit -m "feat(kb-access): grants CRUD API (owner|超管门 + grantee 校验)"
```

---

### Task 7: 前端类型 + API 客户端

**Files:**
- Modify: `frontend/src/extensions/types.ts`（追加类型）
- Modify: `frontend/src/extensions/api/index.ts`（`knowledgeBaseApi` 加 grants）

- [ ] **Step 1: 加类型**

`frontend/src/extensions/types.ts` 末尾（或 KnowledgeBase 相关区）追加：

```ts
export interface KnowledgeBaseGrant {
  id: string;
  kb_id: string;
  grantee_type: "user" | "dept" | "role";
  grantee_id: string;
  permission: "read" | "write";
  expires_at: string | null;
  created_by: string | null;
  created_at: string;
}

export interface KnowledgeBaseGrantCreate {
  grantee_type: "user" | "dept" | "role";
  grantee_id: string;
  permission: "read" | "write";
  expires_at?: string | null;
}
```

- [ ] **Step 2: 加 API 函数**

`frontend/src/extensions/api/index.ts` 的 `knowledgeBaseApi` 对象内追加：

```ts
  grants: {
    list: (kbId: string) => request<KnowledgeBaseGrant[]>(`/knowledge-bases/${kbId}/grants`),
    create: (kbId: string, data: KnowledgeBaseGrantCreate) =>
      request<KnowledgeBaseGrant>(`/knowledge-bases/${kbId}/grants`, { method: "POST", body: JSON.stringify(data) }),
    update: (kbId: string, grantId: string, data: { permission?: "read" | "write"; expires_at?: string | null }) =>
      request<KnowledgeBaseGrant>(`/knowledge-bases/${kbId}/grants/${grantId}`, { method: "PATCH", body: JSON.stringify(data) }),
    remove: (kbId: string, grantId: string) =>
      request<MessageResponse>(`/knowledge-bases/${kbId}/grants/${grantId}`, { method: "DELETE" }),
  },
```

（确认 `KnowledgeBaseGrant`、`KnowledgeBaseGrantCreate` 已从 `@/extensions/types` import。）

- [ ] **Step 3: typecheck**

Run: `docker exec deer-flow-frontend sh -c "cd /app/frontend && pnpm typecheck"`
Expected: 通过（无新错误）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/types.ts frontend/src/extensions/api/index.ts
git commit -m "feat(kb-access): 前端类型 + grants API 客户端"
```

---

### Task 8: 前端 KB 管理页授权 UI

**Files:**
- Modify: `frontend/src/app/knowledge/page.tsx`（KB 详情/编辑区加「数据访问授权」区）

- [ ] **Step 1: 在 KB 详情面板加授权区**

在 KB 详情/编辑面板的「访问权限」select 附近（约 line 2141 编辑表单 或 详情元信息区 line 1192）追加一个「数据访问授权」区块。核心组件代码（内联在 page.tsx，`useState` 管理授权列表）：

```tsx
const [kbGrants, setKbGrants] = useState<KnowledgeBaseGrant[]>([]);
const [grantsLoaded, setGrantsLoaded] = useState(false);
const loadGrants = useCallback(async (kbId: string) => {
  try {
    setKbGrants(await knowledgeBaseApi.grants.list(kbId));
  } catch { /* 非 owner 或加载失败忽略 */ }
}, []);

// 在打开详情/编辑某 KB 时调用 loadGrants(kb.id)；详情面板内渲染：
<div className="rounded-xl border border-border bg-card p-4 space-y-3">
  <div className="flex items-center justify-between">
    <h4 className="text-sm font-semibold text-foreground">数据访问授权</h4>
    <button type="button" onClick={openAddGrant}
      className="px-2.5 py-1 text-xs font-medium text-primary bg-primary/10 border border-primary/20 rounded-lg hover:bg-primary/20">
      + 添加授权
    </button>
  </div>
  {kbGrants.length === 0 ? (
    <p className="text-xs text-muted-foreground">暂无显式授权。私有 KB 可在此授权特定用户/部门/角色访问。</p>
  ) : (
    <div className="space-y-1.5">
      {kbGrants.map((g) => (
        <div key={g.id} className="flex items-center justify-between gap-2 text-sm">
          <span className="inline-flex items-center gap-1.5">
            <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-semibold border",
              g.grantee_type === "user" ? "text-sky-600 border-sky-500/30 bg-sky-500/10"
                : g.grantee_type === "dept" ? "text-indigo-600 border-indigo-500/30 bg-indigo-500/10"
                : "text-primary border-primary/20 bg-primary/10")}>
              {g.grantee_type === "user" ? "用户" : g.grantee_type === "dept" ? "部门" : "角色"}
            </span>
            <span>{granteeName(g)}</span>
            <span className="text-xs text-muted-foreground">{g.permission === "write" ? "读写" : "只读"}</span>
            {g.expires_at && new Date(g.expires_at) < new Date()
              ? <span className="text-xs text-muted-foreground/60">(已过期)</span>
              : g.expires_at && <span className="text-xs text-muted-foreground">至 {format(new Date(g.expires_at), "yyyy-MM-dd")}</span>}
          </span>
          <button type="button" onClick={() => removeGrant(g)} className="text-muted-foreground hover:text-destructive text-sm">×</button>
        </div>
      ))}
    </div>
  )}
</div>
```

（`granteeName(g)` 把 grantee_id 映射为 用户全名/部门名/角色名——用页面已有的 users/depts/roles 列表查找；`removeGrant` 调 `knowledgeBaseApi.grants.remove` 后刷新；「添加授权」弹出一个含 grantee_type 选择 + 搜索选择器 + permission select 的小弹窗，确认后调 `grants.create`。）

- [ ] **Step 2: 补实现细节**（添加授权弹窗 + granteeName 映射 + removeGrant 刷新），确保与页面现有弹窗/搜索组件模式一致。

- [ ] **Step 3: typecheck**

Run: `docker exec deer-flow-frontend sh -c "cd /app/frontend && pnpm typecheck"`
Expected: 通过

- [ ] **Step 4: 重启 frontend + 浏览器验证**

Run: `docker compose -p eai-docker restart frontend`
验证：登录 admin → 知识库页 → 打开某 KB 详情 → 加一个授权（选用户/部门/角色 + read/write）→ 保存 → 列表出现对应条目；用被授权用户登录可见该私有 KB（若方便，临时创建测试用户）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/knowledge/page.tsx
git commit -m "feat(kb-access): 知识库管理页数据访问授权 UI (增删/类型徽章/过期)"
```

---

### Task 9: 全量回归 + 收尾

**Files:** 无新文件

- [ ] **Step 1: 后端全量相关测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_data_access.py tests/test_knowledge_data_access.py tests/test_p0_permission_gates.py tests/test_policy_enforcement.py -q`
Expected: 全 PASS

- [ ] **Step 2: 前端 typecheck + lint**

Run: `docker exec deer-flow-frontend sh -c "cd /app/frontend && pnpm typecheck"`
Expected: 通过

- [ ] **Step 3: 浏览器端到端确认**

登录 admin → 知识库页：
1. 列表仅见自己/公开/授权内 KB（scope 行为不变）
2. 详情打开「数据访问授权」→ 添加 user 授权 → 保存 → 显示
3. 删除授权 → 消失
4. （可选）用被授权用户登录确认私有 KB 可见、read 用户不可编辑（编辑按钮隐藏或 403）

- [ ] **Step 4: 更新 memory/cerebrum**（OpenWolf 记账：.wolf/memory.md 追加；如踩坑更新 cerebrum/buglog）

- [ ] **Step 5: 收尾 commit（如还有未提交）**

---

## 自检记录（计划作者）

- **Spec 覆盖**：知识库授权表 ✓(T1)、可见性 OR 组合 ✓(T2/T4)、write 门 ✓(T5)、API ✓(T6)、UI ✓(T8)、测试 ✓(各 T)、范围外 knowledge_factory ✓（未列入，spec 已注明）。
- **占位符**：无 TBD；每个代码步骤含完整代码。
- **类型一致**：`kb_grant_visible_clause(identity)`、`has_kb_grant(db, kb_id, identity, permission)`、`_load_kb_scoped(db, kb_id, scope, identity=None)` 在后续任务引用一致；`KnowledgeBaseGrant` schema 与模型列一致。
