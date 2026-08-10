# Phase 2：数据域引擎 + ABAC 策略接入 — 实现计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 执行。步骤使用 checkbox (`- [ ]`) 追踪。

**目标：** 实现 FilterRule → SQLAlchemy 转换、`with_data_scope` 依赖注入、ABAC 策略 DB 表 + API、请求级缓存、首批模块数据域迁移。

**依赖：** Phase 1（已完成）— PermissionRegistry、IdentityProvider、UnifiedPermissionEngine、middleware 改造。

**设计文档：** `docs/superpowers/specs/2026-07-30-abac-rbac-redesign-design.md`
**Phase 1 计划：** `docs/superpowers/plans/2026-07-30-abac-rbac-redesign-plan.md`

---

### Task 1: `FilterRule.to_sqlalchemy()` — YAML 规则 → SQL WHERE

**文件：**
- Modify: `backend/app/extensions/auth/engine.py`
- Test: 追加到 `backend/tests/test_permission_engine.py`

- [ ] **Step 1: 写测试**

```python
# 追加到 TestFilterRule 类

def test_to_sqlalchemy_eq(self):
    from sqlalchemy import Column, String, select
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    class MockModel(Base):
        __tablename__ = "mock"
        owner_id = Column(String)
    rule = FilterRule(operator="eq", field="owner_id", value="user-1")
    column_map = {"owner_id": MockModel.owner_id}
    expr = rule.to_sqlalchemy(MockModel, column_map)
    # Build a query and check the WHERE clause renders
    stmt = select(MockModel).where(expr)
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "owner_id" in sql
    assert "user-1" in sql

def test_to_sqlalchemy_in(self):
    from sqlalchemy import Column, String
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    class MockModel(Base):
        __tablename__ = "mock"
        dept_id = Column(String)
    rule = FilterRule(operator="in", field="dept_id", value=["d1", "d2"])
    column_map = {"dept_id": MockModel.dept_id}
    expr = rule.to_sqlalchemy(MockModel, column_map)
    assert expr is not None

def test_to_sqlalchemy_and(self):
    from sqlalchemy import Column, String
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    class MockModel(Base):
        __tablename__ = "mock"
        owner_id = Column(String)
        dept_id = Column(String)
    inner1 = FilterRule(operator="eq", field="owner_id", value="u1")
    inner2 = FilterRule(operator="in", field="dept_id", value=["d1"])
    rule = FilterRule(operator="and", children=[inner1, inner2])
    column_map = {"owner_id": MockModel.owner_id, "dept_id": MockModel.dept_id}
    expr = rule.to_sqlalchemy(MockModel, column_map)
    assert expr is not None

def test_to_sqlalchemy_honors_column_map_and_auto_maps(self):
    """Columns in column_map use the provided mapping; other columns auto-resolve from model."""
    from sqlalchemy import Column, String
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    class MockModel(Base):
        __tablename__ = "mock"
        owner_id = Column(String)
        access_type = Column(String)
    rule = FilterRule(operator="eq", field="access_type", value="public")
    # No column_map needed if field name matches model attribute
    expr = rule.to_sqlalchemy(MockModel, column_map=None)
    assert expr is not None
```

- [ ] **Step 2: 实现 `FilterRule.to_sqlalchemy()`**

```python
# 在 engine.py 的 FilterRule 类中添加

def to_sqlalchemy(self, model, column_map: dict[str, Column] | None = None):
    """Convert FilterRule to SQLAlchemy BinaryExpression.

    Uses column_map for explicit field→column mapping; falls back to
    getattr(model, field) for auto-resolution.
    """
    from sqlalchemy import and_, or_

    column_map = column_map or {}

    if self.operator == "none_allow":
        return sqlalchemy_false()  # WHERE FALSE

    if self.operator == "eq":
        col = column_map.get(self.field) or getattr(model, self.field)
        return col == self.value

    if self.operator == "in":
        col = column_map.get(self.field) or getattr(model, self.field)
        if not self.value:
            return sqlalchemy_false()
        return col.in_(self.value)

    if self.operator == "and" and self.children:
        return and_(*[c.to_sqlalchemy(model, column_map) for c in self.children])

    if self.operator == "or" and self.children:
        return or_(*[c.to_sqlalchemy(model, column_map) for c in self.children])

    return sqlalchemy_false()
```

需要在文件顶部添加：
```python
from sqlalchemy import false as sqlalchemy_false
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_permission_engine.py -v
```

- [ ] **Step 4: 提交**

```bash
git commit -m "feat(permissions): add FilterRule.to_sqlalchemy() for SQL WHERE generation"
```

---

### Task 2: `DataScopeEngine` + `with_data_scope` 依赖注入

**文件：**
- Create: `backend/app/extensions/auth/datascope.py`
- Modify: `backend/app/extensions/auth/middleware.py`（新增 `with_data_scope`）
- Test: `backend/tests/test_datascope.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_datascope.py
import pytest
from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.registry import DataScope as RegDataScope


class TestDataScopeEngine:
    def test_get_data_scope_returns_filter_rule(self):
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="dept_head", dept_ids=["d1", "d2"])
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_owner", display_name="仅自己的",
                             rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
                RegDataScope(id="knowledge_dept", display_name="本部门",
                             rule_template={"dept_id IN": "$identity.dept_ids"}, module="knowledge"),
                RegDataScope(id="knowledge_public", display_name="公开",
                             rule_template={"access_type": "public"}, module="knowledge"),
            ]
        }
        engine = DataScopeEngine(scopes, role_data_scopes={"dept_head": ["knowledge_dept"]})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule is not None
        # dept_head gets knowledge_dept scope
        # rule should be an OR: owner_id == u1 OR dept_id IN [d1, d2]

    def test_unknown_resource_returns_none_allow(self):
        idn = AttributeSet(user_id="u1", username="test")
        engine = DataScopeEngine({}, {})
        rule = engine.get_data_scope(idn, "nonexistent")
        assert rule.operator == "none_allow"

    def test_role_without_data_scope_returns_none_allow(self):
        idn = AttributeSet(user_id="u1", username="test", role_code="no_scope_role")
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_public", display_name="公开",
                             rule_template={"access_type": "public"}, module="knowledge"),
            ]
        }
        engine = DataScopeEngine(scopes, role_data_scopes={})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule.operator == "none_allow"

    def test_or_multiple_scopes_combined(self):
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="admin", dept_ids=["d1"])
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_owner", display_name="仅自己的",
                             rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
                RegDataScope(id="knowledge_dept", display_name="本部门",
                             rule_template={"dept_id IN": "$identity.dept_ids"}, module="knowledge"),
            ]
        }
        # Role has BOTH scopes — combined with OR
        engine = DataScopeEngine(scopes, role_data_scopes={"admin": ["knowledge_owner", "knowledge_dept"]})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule.operator == "or"
        assert len(rule.children) == 2  # one for owner, one for dept
```

- [ ] **Step 2: 实现 `DataScopeEngine`**

```python
# backend/app/extensions/auth/datascope.py
"""Data scope engine — resolves role data_scopes to FilterRules."""
from __future__ import annotations

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import DataScope, get_permission_registry


class DataScopeEngine:
    """Resolves data scope configurations to executable FilterRules."""

    def __init__(
        self,
        scopes_by_resource: dict[str, list[DataScope]] | None = None,
        role_data_scopes: dict[str, list[str]] | None = None,
    ):
        self._scopes_by_resource = scopes_by_resource or {}
        self._role_data_scopes = role_data_scopes or {}

    @classmethod
    def from_registry(cls) -> "DataScopeEngine":
        """Build engine from PermissionRegistry."""
        registry = get_permission_registry()
        scopes_by_resource: dict[str, list[DataScope]] = {}
        for module_key, mp in registry.list_modules():
            if mp.data_scopes:
                scopes_by_resource[module_key] = mp.data_scopes

        role_data_scopes: dict[str, list[str]] = {}
        for code in registry._role_defaults:
            defaults = registry.get_role_defaults(code)
            if defaults and defaults.get("data_scopes"):
                role_data_scopes[code] = defaults["data_scopes"]

        return cls(scopes_by_resource, role_data_scopes)

    def get_data_scope(self, identity: AttributeSet, resource_type: str) -> FilterRule:
        """Return a FilterRule for what this identity can see of resource_type."""
        scopes = self._scopes_by_resource.get(resource_type)
        if not scopes:
            return FilterRule(operator="none_allow")

        role_code = identity.role_code or ""
        allowed_scope_ids = self._role_data_scopes.get(role_code, [])

        applicable = [s for s in scopes if s.id in allowed_scope_ids]
        if not applicable:
            return FilterRule(operator="none_allow")

        if len(applicable) == 1:
            return FilterRule.from_template(applicable[0].rule_template, identity)

        # Multiple scopes → OR them together
        children = [FilterRule.from_template(s.rule_template, identity) for s in applicable]
        children = [c for c in children if c.operator != "none_allow"]
        if not children:
            return FilterRule(operator="none_allow")
        if len(children) == 1:
            return children[0]
        return FilterRule(operator="or", children=children)
```

- [ ] **Step 3: 实现 `with_data_scope` 依赖注入**

在 `middleware.py` 末尾添加：

```python
# backend/app/extensions/auth/middleware.py 尾部追加

from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.engine import FilterRule


def with_data_scope(resource_type: str):
    """FastAPI dependency: inject a FilterRule for data-level access control.

    Usage:
        @router.get("/knowledge-bases")
        async def list_kbs(
            db: AsyncSession = Depends(get_db),
            scope: FilterRule = Depends(with_data_scope("knowledge")),
        ):
            query = select(KnowledgeBase).where(scope.to_sqlalchemy(KnowledgeBase))
            ...
    """
    async def _scope(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> FilterRule:
        from app.extensions.auth.identity import get_identity_provider

        engine = DataScopeEngine.from_registry()
        provider = get_identity_provider()
        identity = await provider.resolve(current_user.id, db)
        return engine.get_data_scope(identity, resource_type)

    return _scope
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_datascope.py -v
```

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(permissions): add DataScopeEngine + with_data_scope dependency"
```

---

### Task 3: 请求级缓存（减少 5x 查询开销）

**文件：**
- Create: `backend/app/extensions/auth/cache.py`
- Modify: `backend/app/extensions/auth/middleware.py`

**问题：** 每次 `require_permission` 调用执行 5+ 个 DB 查询（select all roles + IdentityProvider 的 4 个查询）。同一请求中多个 `require_permission` 依赖链式触发 → 查询数翻倍。

**方案：** 用 `ContextVar` 实现请求级缓存，存储 engine + identity。同一请求内多次调用共享缓存。

- [ ] **Step 1: 实现请求级缓存**

```python
# backend/app/extensions/auth/cache.py
"""Request-scoped caching for permission engine and identity."""
from __future__ import annotations

from contextvars import ContextVar

from app.extensions.auth.engine import UnifiedPermissionEngine
from app.extensions.auth.identity import AttributeSet

_request_engine: ContextVar[UnifiedPermissionEngine | None] = ContextVar("_perm_engine", default=None)
_request_identity: ContextVar[AttributeSet | None] = ContextVar("_perm_identity", default=None)


def get_cached_engine() -> UnifiedPermissionEngine | None:
    return _request_engine.get(None)


def set_cached_engine(engine: UnifiedPermissionEngine) -> None:
    _request_engine.set(engine)


def get_cached_identity() -> AttributeSet | None:
    return _request_identity.get(None)


def set_cached_identity(identity: AttributeSet) -> None:
    _request_identity.set(identity)


def clear_permission_cache() -> None:
    _request_engine.set(None)
    _request_identity.set(None)
```

- [ ] **Step 2: 在 middleware 中使用缓存**

在 `require_permission` 的 `check_permission` 中，优先读缓存：

```python
# 在 check_permission 内部，替换原来的直接构建逻辑

from app.extensions.auth.cache import get_cached_engine, set_cached_engine
from app.extensions.auth.cache import get_cached_identity, set_cached_identity

engine = get_cached_engine()
if engine is None:
    # 首次调用：构建 engine + identity
    result = await db.execute(sa_select(Role))
    roles = result.scalars().all()
    role_permissions = {r.code: set(r.permissions or []) for r in roles}
    all_ids = {p.id for p in get_permission_registry().list_all_permissions()}
    engine = UnifiedPermissionEngine(
        role_permissions=role_permissions,
        all_permission_ids=all_ids,
    )
    set_cached_engine(engine)

identity = get_cached_identity()
if identity is None:
    identity = await get_identity_provider().resolve(current_user.id, db)
    set_cached_identity(identity)
```

- [ ] **Step 3: 验证性能**

在 `require_permission` 中添加 debug 日志，确认同请求内第二次调用命中缓存。

- [ ] **Step 4: 提交**

```bash
git commit -m "perf(permissions): add request-scoped ContextVar cache for engine and identity"
```

---

### Task 4: ABAC 策略 DB 表 + CRUD API

**文件：**
- Create: `backend/app/extensions/auth/models.py`（Policy 模型）
- Modify: `backend/app/extensions/database.py`（migrate 加 policies 表）
- Create: `backend/app/extensions/auth/policy_routers.py`
- Modify: `backend/app/extensions/auth/middleware.py`（engine 加载 policies）
- Test: `backend/tests/test_policy_crud.py`

- [ ] **Step 1: 创建 Policy 模型 + DB 迁移**

```python
# backend/app/extensions/auth/models.py
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.extensions.database import Base
import uuid
from datetime import UTC, datetime


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    conditions = Column(JSONB, nullable=False)
    grants = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
```

在 `database.py` 的 `migrate_db()` 末尾追加：
```python
# ABAC policies table
await conn.execute(text("""
    CREATE TABLE IF NOT EXISTS policies (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(200) NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        priority INT NOT NULL DEFAULT 0,
        conditions JSONB NOT NULL DEFAULT '{}',
        grants JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""))
```

- [ ] **Step 2: 实现 Policy CRUD API**

```python
# backend/app/extensions/auth/policy_routers.py
"""ABAC policy CRUD endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.auth.models import Policy
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser
from pydantic import BaseModel

router = APIRouter(prefix="/api/policies", tags=["policies"])


class PolicyCreate(BaseModel):
    name: str
    priority: int = 0
    conditions: dict = {}
    grants: dict = {}


class PolicyUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    conditions: dict | None = None
    grants: dict | None = None


@router.get("")
async def list_policies(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    result = await db.execute(select(Policy).order_by(Policy.priority))
    policies = result.scalars().all()
    return {"policies": [
        {
            "id": str(p.id), "name": p.name, "enabled": p.enabled,
            "priority": p.priority, "conditions": p.conditions, "grants": p.grants,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in policies
    ]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:create")),
):
    policy = Policy(
        name=data.name, priority=data.priority,
        conditions=data.conditions, grants=data.grants,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return {"id": str(policy.id), "name": policy.name}


@router.put("/{policy_id}")
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:update")),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if data.name is not None:
        policy.name = data.name
    if data.enabled is not None:
        policy.enabled = data.enabled
    if data.priority is not None:
        policy.priority = data.priority
    if data.conditions is not None:
        policy.conditions = data.conditions
    if data.grants is not None:
        policy.grants = data.grants
    await db.commit()
    return {"id": str(policy.id), "name": policy.name}


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:delete")),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(policy)
    await db.commit()
    return {"message": "Policy deleted"}
```

注册路由：在 `backend/app/gateway/app.py` 中添加 `from app.extensions.auth.policy_routers import router as policy_router` 并 `app.include_router(policy_router)`。

- [ ] **Step 3: 在 engine 中加载 policies**

修改 `middleware.py` 中 engine 构建，从 DB 加载 policies：

```python
# 在 _build_engine 或 check_permission 中添加
from app.extensions.auth.models import Policy as PolicyModel
from app.extensions.auth.engine import Policy as EnginePolicy

policy_result = await db.execute(
    select(PolicyModel).where(PolicyModel.enabled == True).order_by(PolicyModel.priority)
)
policies = [
    EnginePolicy(name=p.name, priority=p.priority, conditions=p.conditions, grants=p.grants)
    for p in policy_result.scalars().all()
]
engine = UnifiedPermissionEngine(
    role_permissions=role_permissions,
    all_permission_ids=all_ids,
    policies=policies,
)
```

- [ ] **Step 4: 写测试 + 验证**

```bash
cd backend && uv run pytest tests/test_policy_crud.py -v
```

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(permissions): add Policy DB model + CRUD API + engine policy loading"
```

---

### Task 5: 知识库模块数据域迁移（示例）

**文件：**
- Modify: `backend/app/extensions/knowledge/routers.py`

**目标：** 将 `list_kbs` 从硬编码 `WHERE owner_id = ? OR access_type = 'public'` 改为 `with_data_scope("knowledge")`。

- [ ] **Step 1: 替换 list_kbs 的过滤逻辑**

在 `knowledge/routers.py` 的 `list_knowledge_bases` 中：

```python
# 旧代码（service 层过滤）
kbs, total = await KnowledgeBaseService.list_kbs(db, current_user.id, ...)

# 新代码
@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    query = select(KnowledgeBase).where(scope.to_sqlalchemy(KnowledgeBase, {
        "dept_id": KnowledgeBase.dept_id,
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
    }))
    # 管理员放行全部
    if current_user.role_name in ("Super Admin",):
        query = select(KnowledgeBase)
    query = query.offset(skip).limit(limit).order_by(KnowledgeBase.created_at.desc())
    result = await db.execute(query)
    kbs = result.scalars().all()
    ...
```

- [ ] **Step 2: 确认 behavior 一致**

用 admin 和 dept_head 两个用户分别调用 `GET /api/extensions/knowledge-bases`，确认返回数据不变。

- [ ] **Step 3: 提交**

```bash
git commit -m "refactor(knowledge): use with_data_scope for knowledge base list filtering"
```

---

## 任务总览

| Task | 产出 | 预估 |
|------|------|------|
| 1 | `FilterRule.to_sqlalchemy()` | 1 file + 4 tests |
| 2 | `DataScopeEngine` + `with_data_scope` | 2 files + 4 tests |
| 3 | 请求级 ContextVar 缓存 | 1 file |
| 4 | ABAC Policy 模型 + CRUD + engine 加载 | 3 files + tests |
| 5 | 知识库数据域迁移示例 | 1 file |

**总新增/修改文件：** ~8 个 | **新增测试：** ~12 个

---

## 附录：列映射参考

基于探索结果，各模块接入数据域时的 `column_map`：

### KnowledgeBase（`knowledge_bases` 表）

| 权限字段 | 模型属性 | 用途 |
|---------|---------|------|
| `owner_id` | `KnowledgeBase.owner_id` | 所有者过滤 |
| `access_type` | `KnowledgeBase.access_type` | private/dept/public |
| `dept_id` | `KnowledgeBase.allowed_depts` | PostgreSQL ARRAY，需 `contains()` |

```python
KB_COLUMN_MAP = {
    "owner_id": KnowledgeBase.owner_id,
    "access_type": KnowledgeBase.access_type,
    "dept_id": KnowledgeBase.allowed_depts,  # 注意：是数组，不是标量
}
```

**注意：** `dept_id IN: [...]` 的 FilterRule 默认生成 `col.in_(values)`，对数组列需要特殊处理 → 改用 `col.contains([value])` 或自定义 `operator="array_contains"`。Phase 2 先处理 owner_id + access_type，数组列后续处理。

### ReportProject（`report_projects` 表）

| 权限字段 | 来源 | 用途 |
|---------|------|------|
| `id IN` | `identity.member_projects` | 项目成员过滤 |
| `created_by` | `ReportProject.created_by` | 创建者过滤 |

```python
PROJECT_COLUMN_MAP = {
    "owner_id": ReportProject.created_by,  # 语义映射
    "id": ReportProject.id,
}
```

### CPA（`cpa_*` 表）

CPA 数据无用户隔离字段。数据域只有两级：`cpa_all`（全量）和 `cpa_dept`（暂无实现列）。接入时需要先扩展模型加 `dept_id`/`created_by` 列，或保持全量访问。

### `with_data_scope` 使用模式

```python
# 模式 1：直接 where
@router.get("/items")
async def list_items(
    db: AsyncSession = Depends(get_db),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    query = select(KnowledgeBase).where(scope.to_sqlalchemy(KnowledgeBase, KB_COLUMN_MAP))

# 模式 2：与业务过滤组合
@router.get("/items")
async def list_items(
    db: AsyncSession = Depends(get_db),
    scope: FilterRule = Depends(with_data_scope("project")),
    status: str | None = None,
):
    query = select(ReportProject).where(scope.to_sqlalchemy(ReportProject, PROJECT_COLUMN_MAP))
    if status:
        query = query.where(ReportProject.status == status)

# 模式 3：管理员旁路
if is_admin:
    scope = FilterRule(operator="none_allow")  # 空规则 = 不过滤（需要特殊语义）
    # 或直接用不带 scope 的 query
```
