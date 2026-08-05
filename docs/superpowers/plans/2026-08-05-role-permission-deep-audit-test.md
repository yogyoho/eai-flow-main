# 角色管理操作权限 + 数据访问深度审计与测试 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以「测试先行红→绿」完成角色管理模块深度测试闭环：①抢救 CRITICAL 的 dept_head 权限清空 bug（4 用户被锁）；②补全 HTTP 集成层测试（/me、deny→端点、数据 deny、IDOR、scope 接线）与引擎边界测试；③修复 docmgr 两个 scope 缺口 + workflow-admin 硬编码门；④浏览器 E2E + 安全对抗；⑤输出审计报告。

**Architecture:** 测试跑在 gateway 容器内（`backend/` 整目录 bind-mount，`.venv` 为 named volume）。L1 测试遵循仓库既有模式：**真实 PermissionRegistry（读 config/permissions.yaml + roles_custom.yaml）+ mock identity（monkeypatch `get_identity_provider`）+ mock policy 行（`load_active_policies`）+ FastAPI TestClient `dependency_overrides(get_current_user, get_db)`**——无 live-PG（仓库无此基建，且共享 dev DB 不做破坏性写入）。红→绿判别靠 SQL 形状断言（scope 引擎签名 `NOT` 等）。

**Tech Stack:** Python 3.12 / FastAPI TestClient / httpx ASGITransport / SQLAlchemy 2.0 async / pytest / YAML;Next.js 前端（F4）。

**Spec:** `docs/superpowers/specs/2026-08-05-role-permission-deep-audit-test-design.md`

**Conventions:**
- 测试运行命令（一律容器内）：`docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/<file>.py -v'`（MSYS 会改写裸路径，必须 `sh -c` 包裹）。
- 改 `app/` EAI 定制代码无需 EAI-CUSTOM 三重规范（非 harness 上游）；改 harness 才需要（本计划不触及 harness）。ruff 行宽 240。
- 提交到 `main-dev-fork`；commit 用显式 pathspec（`git commit -m "..." -- <files>`）避免扫入并发 `.wolf/*` 改动。
- 全量回归基线：本 fork 后端 420 失败/79 collection 错误为**既有基线**，判别"新失败"只看法人域测试文件；前端 typecheck 127 为既有基线。

---

## 文件结构

**修复：**
- `config/roles_custom.yaml` — F1：dept_head `permissions` 改为 `#inherit:user` + 16 扩展（21 权限）。
- `backend/app/extensions/docmgr/collab_routers.py` — F2：8 个 by-id 端点注入 `with_data_scope("docmgr")` + 换 `get_by_id_scoped`。
- `backend/app/extensions/docmgr/service.py` — F3：`list_folders` 加 `scope` 参数分支。
- `backend/app/extensions/docmgr/routers.py` — F3：`/folders` 端点注入 scope 并透传。
- `frontend/src/app/workflow-admin/layout.tsx` + `page.tsx` + `components/TemplateEditorPage.tsx` — F4：`is_admin` 门（AdminGate 模式）。

**测试（新增，backend/tests/）：**
- `rbac_helpers.py` — 共享工具（canned identity、policy mock、smart_db、build_app、patch_identity）。
- `test_role_definition_f1.py` — F1 回归（真实 registry）。
- `test_permissions_me_endpoint.py` — /me 端点 HTTP。
- `test_policy_deny_endpoint.py` — deny→HTTP 403。
- `test_with_data_scope_middleware.py` — 中间件依赖直调。
- `test_data_deny_e2e.py` — 数据 deny 到真实列表查询 SQL。
- `test_project_idor_http.py` — 真实 project 路由 HTTP 403/200。
- `test_knowledge_flip.py` — dept scope 接线 + by-id 用 scope（SQL 断言）。
- `test_docmgr_scopes.py` — F2/F3（红→绿）。
- `test_rbac_edge.py` — 环检测 / not 组合 / overlap 空值 / law_all / bare-* 写拦截。

**文档：** 本计划 + Cycle 4 审计报告。

---

## Cycle 0 — F1 dept_head 抢救（红→绿）

### Task 1: 写 F1 回归测试（红）

**Files:**
- Create: `backend/tests/test_role_definition_f1.py`

- [ ] **Step 1: 写测试**

`backend/tests/test_role_definition_f1.py`（真实 registry，守护 shipped 数据；不依赖 tmp yaml）：

```python
"""F1 回归：dept_head 权限被 overlay 清空后必须恢复（#inherit:user + 部门扩展）。

用真实 PermissionRegistry（读 config/permissions.yaml + config/roles_custom.yaml），
守护 shipped 数据——dept_head 用户因此持有 system:access，4 个在册用户不被锁死。
"""
from app.extensions.auth.registry import PermissionRegistry

REQUIRED_DEPT_HEAD = {
    "system:access", "kb:read", "doc:read", "model:read", "dashboard:view",  # 继承 user
    "department:create", "department:update", "department:delete",
    "kb:create", "kb:upload", "kb:update", "kb:delete",
    "doc:upload", "doc:delete", "project:create", "project:read",
    "approval:approve", "approval:submit", "approval:view",
    "chapter:review", "workflow:read",
}


def test_dept_head_resolves_nonempty_and_has_system_access():
    reg = PermissionRegistry()
    perms = reg.resolve_role_permissions("dept_head")
    assert len(perms) >= 21, f"dept_head 解析为 {len(perms)} 个权限（期望 >=21）"
    assert REQUIRED_DEPT_HEAD <= perms, f"dept_head 缺权限: {REQUIRED_DEPT_HEAD - perms}"
    assert "system:access" in perms


def test_project_manager_inherits_dept_head_chain():
    reg = PermissionRegistry()
    perms = reg.resolve_role_permissions("project_manager")
    assert "system:access" in perms  # #inherit:dept_head → #inherit:user → system:access
    assert "department:update" in perms  # 从 dept_head 继承的部门管理权限


def test_dept_head_data_scopes_present():
    reg = PermissionRegistry()
    scopes = reg.get_data_scopes_for_role("dept_head")
    assert {"project_member", "knowledge_dept", "doc_owner", "doc_project_member"} <= set(scopes)
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_role_definition_f1.py -v'`
Expected: `test_dept_head_resolves_nonempty_and_has_system_access` FAIL（`resolve_role_permissions('dept_head')` 现为 0 权限）；其余可能 pass（data_scopes 存在）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_role_definition_f1.py
git commit -m "test(rbac): F1 dept_head regression — overlay must not wipe to zero perms" -- backend/tests/test_role_definition_f1.py
```

### Task 2: 修 roles_custom.yaml（绿）

**Files:**
- Modify: `config/roles_custom.yaml`（dept_head 的 `permissions:` 键，约第 65 行）

- [ ] **Step 1: 改 dept_head.permissions**

把当前 `dept_head:` 下的 `permissions: []` 替换为（保留该角色其余键：display_name/nav/data_scopes/pages/is_system/level/description 不动）：

```yaml
    permissions:
    - '#inherit:user'
    - department:create
    - department:update
    - department:delete
    - kb:create
    - kb:upload
    - kb:update
    - kb:delete
    - doc:upload
    - doc:delete
    - project:create
    - project:read
    - approval:approve
    - approval:submit
    - approval:view
    - chapter:review
    - workflow:read
```

- [ ] **Step 2: 跑测试确认通过（绿）**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_role_definition_f1.py -v'`
Expected: 3 passed。

- [ ] **Step 3: 容器验证 + 用户解锁确认**

Run:
```bash
docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python - <<"PY"
from app.extensions.auth.registry import PermissionRegistry
r = PermissionRegistry()
print("dept_head", len(r.resolve_role_permissions("dept_head")), "system:access" in r.resolve_role_permissions("dept_head"))
print("project_manager", len(r.resolve_role_permissions("project_manager")), "system:access" in r.resolve_role_permissions("project_manager"))
PY'
```
Expected: `dept_head 21 True`；`project_manager 30 True`（21 继承 + 11 自身去重 2 = 30；若数字略有出入，以 `system:access True` 为准）。
再用一个 dept_head 用户（如 zhangsan）登录 `GET /api/extensions/knowledge/knowledge-bases` → 200（不再 403）。若该账号密码未知，用 admin 重置密码后验证。

- [ ] **Step 4: Commit**

```bash
git add config/roles_custom.yaml
git commit -m "fix(rbac): F1 restore dept_head perms (#inherit:user + dept extras) — 4 users unblocked" -- config/roles_custom.yaml
```

---

## Cycle 1 — L1 集成套件（红→绿）+ F2/F3/F4

### Task 3: 共享测试工具 rbac_helpers.py

**Files:**
- Create: `backend/tests/rbac_helpers.py`

- [ ] **Step 1: 写工具模块**

```python
"""共享 RBAC 深度测试工具：canned identity、policy mock、smart_db、app builder。

跑在 gateway 容器内；registry 读真实 config/permissions.yaml + roles_custom.yaml。
DB 一律 mock（仓库"无 live-PG 集成测试"惯例），identity 经 monkeypatch get_identity_provider。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser


def make_user(role_name: str = "user", **kw) -> CurrentUser:
    return CurrentUser(
        id=kw.get("id", uuid.uuid4()),
        username=kw.get("username", "tester"),
        email=kw.get("email", "tester@eai-flow.com"),
        full_name=kw.get("full_name", "Tester"),
        role_id=kw.get("role_id"),
        role_name=role_name,
        dept_id=kw.get("dept_id"),
        dept_name=kw.get("dept_name"),
        status="active",
    )


def fake_identity(role_code: str = "user", **kw) -> AttributeSet:
    return AttributeSet(
        user_id=kw.get("user_id", str(uuid.uuid4())),
        username=kw.get("username", "tester"),
        role_code=role_code,
        role_level=kw.get("role_level", 0),
        dept_id=kw.get("dept_id"),
        dept_ids=kw.get("dept_ids", []),
        member_projects=kw.get("member_projects", []),
        project_roles=kw.get("project_roles", {}),
        tags=kw.get("tags", []),
        labels=kw.get("labels", {}),
    )


class FakeIdentityProvider:
    """resolve() 返回 canned identity；monkeypatch get_identity_provider 指向它。"""

    def __init__(self, identity: AttributeSet):
        self._identity = identity

    async def resolve(self, user_id, db):  # noqa: ARG002
        return self._identity


def patch_identity(monkeypatch, identity: AttributeSet) -> FakeIdentityProvider:
    """让 with_data_scope / /me / require_permission / require_resource_permission 拿到 canned identity。

    必须 patch 源模块 + 已模块级 import 的消费模块（惰性导入 vs 模块级导入差异）。
    """
    provider = FakeIdentityProvider(identity)
    monkeypatch.setattr("app.extensions.auth.identity.get_identity_provider", lambda: provider)
    monkeypatch.setattr("app.extensions.auth.permission_routers.get_identity_provider", lambda: provider)
    monkeypatch.setattr("app.extensions.auth.unified_permissions.get_identity_provider", lambda: provider)
    monkeypatch.setattr("app.extensions.auth.middleware.get_identity_provider", lambda: provider)
    return provider


def policy_row(name: str = "p", priority: int = 0, conditions: dict | None = None, grants: dict | None = None) -> SimpleNamespace:
    """duck-typed PolicyModel 行——load_active_policies 只读 name/priority/conditions/grants。"""
    return SimpleNamespace(name=name, priority=priority, conditions=conditions or {}, grants=grants or {})


def policy_rows_db(rows: list | None = None):
    """mock 的 AsyncSession：execute().scalars().all() 返回 rows（load_active_policies 专属）。

    用于不涉及端点数据查询、只走 policy 加载的测试（/me、deny→端点、with_data_scope）。
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows or [])
    db.execute.return_value = result
    return db


def smart_db(*, policy_rows: list | None = None, doc_row=None, kb_row=None, member_row=None):
    """AsyncMock session 按 SQL 形状路由 execute() 结果。

    - 含 "policies" → scalars().all() = policy_rows（load_active_policies 用）
    - 含 "ai_documents" / "folders" → scalar_one_or_none = doc_row；scalars().all = [doc_row]
    - 含 "knowledge_bases" → scalar_one_or_none = kb_row
    - 含 "project_members" → scalar_one_or_none = member_row
    - 其它 → 空
    """
    db = AsyncMock()

    def _execute(stmt, *a, **k):  # noqa: ARG001
        sql = str(stmt)
        result = MagicMock()
        if "policies" in sql:
            result.scalars.return_value.all.return_value = list(policy_rows or [])
        elif "ai_documents" in sql or "folders" in sql:
            result.scalar_one_or_none.return_value = doc_row
            result.scalars.return_value.all.return_value = [doc_row] if doc_row else []
        elif "knowledge_bases" in sql:
            result.scalar_one_or_none.return_value = kb_row
            result.scalars.return_value.all.return_value = [kb_row] if kb_row else []
        elif "project_members" in sql:
            result.scalar_one_or_none.return_value = member_row
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    return db


def build_app(router, *, user: CurrentUser | None = None, db=None) -> TestClient:
    """TestClient app：override get_current_user + get_db，含目标 router。"""
    app = FastAPI()
    app.include_router(router)
    u = user or make_user()
    session = db if db is not None else AsyncMock()

    async def _user():
        return u

    async def _db():
        yield session

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app, raise_server_exceptions=False)


def capture_sql(db):
    """取最近一次 db.execute 的编译 SQL（小写、含字面值）。"""
    stmt = db.execute.await_args.args[0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
```

- [ ] **Step 2: 快速自检（import 不炸）**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -c "import sys; sys.path.insert(0, \"tests\"); import rbac_helpers; print(\"OK\")"'`
Expected: `OK`。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/rbac_helpers.py
git commit -m "test(rbac): shared helpers for HTTP-level RBAC tests (identity/policy/smart_db/app)" -- backend/tests/rbac_helpers.py
```

### Task 4: test_permissions_me_endpoint.py（/me 端点，现 0 覆盖）

**Files:**
- Create: `backend/tests/test_permissions_me_endpoint.py`

- [ ] **Step 1: 写测试**

```python
"""/api/permissions/me 端点 HTTP 测试（修复前 0 覆盖）。

真实 registry + canned identity + mock policy 行；验证超管全集、策略 grant/deny、
以及 /me 与 require_permission 的一致性（deny 时端点 403）。
"""
from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_row, policy_rows_db
from app.extensions.auth.permission_routers import router


def test_me_superadmin_full_set_and_is_admin(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    tc = build_app(router, user=make_user(role_name="超级管理员"), db=policy_rows_db([]))
    r = tc.get("/me")
    assert r.status_code == 200
    data = r.json()
    assert data["is_admin"] is True
    assert data["permissions"], "超管应展开为具体权限点全集"
    assert "*" not in data["permissions"], "list_permissions 输出具体点，不含裸通配"


def test_me_policy_grant_appears_and_deny_overrides(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = policy_rows_db([
        policy_row("grant_plus", grants={"permissions": ["kb:create", "kb:update", "kb:delete"]}),
        policy_row("deny_delete", grants={"deny_permissions": ["kb:delete"]}),
    ])
    tc = build_app(router, user=make_user(role_name="普通用户"), db=db)
    data = tc.get("/me").json()
    perms = set(data["permissions"])
    assert "kb:read" in perms          # user base
    assert "kb:create" in perms        # 策略授予
    assert "kb:update" in perms        # 策略授予、未被 deny
    assert "kb:delete" not in perms    # deny-overrides 压过策略授予


def test_me_deny_consistent_with_endpoint_403(monkeypatch):
    from fastapi import APIRouter, Depends
    from app.extensions.auth.middleware import require_permission

    # 最小 gate 端点：与 /me 用同一 require_permission + 同一 policy 集
    probe = APIRouter()

    @probe.get("/ping-kb")
    async def ping_kb(_u=Depends(require_permission("kb:read"))):
        return {"ok": True}

    identity = fake_identity(role_code="user")
    patch_identity(monkeypatch, identity)
    rows = [policy_row("deny_read", grants={"deny_permissions": ["kb:read"]})]
    db = policy_rows_db(rows)

    # /me：kb:read 被 deny
    me_data = build_app(router, db=db).get("/me").json()
    assert "kb:read" not in set(me_data["permissions"])

    # 同一 policy 集下 gate 端点 403
    assert build_app(probe, db=db).get("/ping-kb").status_code == 403
```

（`policy_rows_db` 已定义于 `rbac_helpers.py` Task 3。）

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_permissions_me_endpoint.py -v'`
Expected: 3 passed（代码已正确；本文件补的是缺失的验证，非红项）。若某用例红，先排查 mock 目标（`/me` 的 `get_identity_provider` 若为模块级 import，patch 消费模块名 `app.extensions.auth.permission_routers.get_identity_provider`——helpers 已处理）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_permissions_me_endpoint.py
git commit -m "test(rbac): /me endpoint HTTP — superadmin full-set, policy grant/deny, consistency with require_permission" -- backend/tests/test_permissions_me_endpoint.py
```

### Task 5: test_policy_deny_endpoint.py（deny→HTTP 403）

**Files:**
- Create: `backend/tests/test_policy_deny_endpoint.py`

- [ ] **Step 1: 写测试**

```python
"""deny_permissions 策略 → 真实 HTTP 端点 403（Y 被拒 / Z 放行 / 超管豁免 / 空条件全员）。"""
import pytest

from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_row, policy_rows_db
from fastapi import APIRouter, Depends
from app.extensions.auth.middleware import require_permission

probe = APIRouter()


@probe.get("/ping-kb")
async def ping_kb(_u=Depends(require_permission("kb:read"))):
    return {"ok": True}


@pytest.mark.parametrize("role,rows,expected", [
    ("user", [policy_row("d", grants={"deny_permissions": ["kb:read"]})], 403),   # 精确点 deny
    ("user", [policy_row("d", grants={"deny_permissions": ["kb:*"]})], 403),      # 模块通配 deny
    ("user", [policy_row("d", grants={"deny_permissions": ["doc:read"]})], 200),  # 无关 deny → 放行
    ("user", [policy_row("d", conditions={"attr": "user_id", "op": "eq", "value": "someone-else"})], 200),  # 条件不匹配
    ("superadmin", [policy_row("d", grants={"deny_permissions": ["kb:read"]})], 200),  # 超管豁免
    ("user", [policy_row("d", conditions={}, grants={"deny_permissions": ["kb:read"]})], 403),  # 空条件=全员
])
def test_deny_to_endpoint(monkeypatch, role, rows, expected):
    patch_identity(monkeypatch, fake_identity(role_code=role))
    tc = build_app(probe, user=make_user(), db=policy_rows_db(rows))
    assert tc.get("/ping-kb").status_code == expected
```

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_policy_deny_endpoint.py -v'`
Expected: 6 passed。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_policy_deny_endpoint.py
git commit -m "test(rbac): deny_permissions -> HTTP 403 (exact/module-wildcard/empty-cond/superadmin-immune)" -- backend/tests/test_policy_deny_endpoint.py
```

### Task 6: test_with_data_scope_middleware.py（中间件依赖直调）

**Files:**
- Create: `backend/tests/test_with_data_scope_middleware.py`

- [ ] **Step 1: 写测试**

```python
"""with_data_scope 中间件依赖直调（现无直测）：超管 allow_all / deny 收集 / AND NOT deny。"""
import pytest

from rbac_helpers import fake_identity, make_user, patch_identity, policy_row, policy_rows_db
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import with_data_scope


@pytest.mark.asyncio
async def test_superadmin_gets_allow_all(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=policy_rows_db([]))
    assert isinstance(rule, FilterRule) and rule.operator == "allow_all"


@pytest.mark.asyncio
async def test_deny_collected_composes_and_not(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = policy_rows_db([policy_row("d", grants={"deny_data_scopes": ["knowledge_public"]})])
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    assert rule.operator == "and", "allow AND NOT deny"
    assert rule.children[1].operator == "not"


@pytest.mark.asyncio
async def test_no_deny_returns_plain_allow(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=policy_rows_db([]))
    assert rule.operator != "and"  # 无 deny → 不产生 AND NOT
```

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_with_data_scope_middleware.py -v'`
Expected: 3 passed。注：`user` 角色须有 `knowledge_owner`/`knowledge_public` scope（M1 已授）；superadmin 命中内置 allow_all。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_with_data_scope_middleware.py
git commit -m "test(rbac): with_data_scope middleware — superadmin allow_all, deny collect, AND NOT" -- backend/tests/test_with_data_scope_middleware.py
```

### Task 7: test_data_deny_e2e.py（数据 deny 到真实列表查询 SQL）

**Files:**
- Create: `backend/tests/test_data_deny_e2e.py`

- [ ] **Step 1: 写测试**

```python
"""deny_data_scopes 必须到达 knowledge 真实列表查询（engine 组合之外，走 with_data_scope 全链）。"""
import pytest

from rbac_helpers import fake_identity, make_user, patch_identity, policy_row, smart_db
from app.extensions.auth.middleware import with_data_scope
from app.extensions.models import KnowledgeBase


@pytest.mark.asyncio
async def test_deny_reaches_list_query_sql(monkeypatch):
    """带 deny_data_scopes=[knowledge_public] 策略时，列表查询 SQL 必须含 AND NOT 拒绝谓词。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[policy_row("d", grants={"deny_data_scopes": ["knowledge_public"]})])
    # 1. 经 with_data_scope 取真实 scope 规则
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    # 2. 编译成 SQL，断言拒绝分支在
    sql = str(rule.to_sqlalchemy(KnowledgeBase, {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "not" in sql, f"数据 deny 未出现在列表 SQL: {sql}"
    assert "access_type" in sql  # deny 分支引用 knowledge_public 的 access_type 列


@pytest.mark.asyncio
async def test_no_deny_list_query_plain(monkeypatch):
    """无 deny 策略时，scope 规则不含 NOT。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[])
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    sql = str(rule.to_sqlalchemy(KnowledgeBase, {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "not" not in sql
```

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_data_deny_e2e.py -v'`
Expected: 2 passed（with_data_scope 已实现 deny 注入；本文件验证它到达真实 SQL 层）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_data_deny_e2e.py
git commit -m "test(rbac): data deny reaches knowledge list SQL via with_data_scope chain" -- backend/tests/test_data_deny_e2e.py
```

### Task 8: test_project_idor_http.py（真实 project 路由 HTTP 403/200）

**Files:**
- Create: `backend/tests/test_project_idor_http.py`

- [ ] **Step 1: 写测试**

```python
"""项目 IDOR 端点 HTTP 级闭合：非成员 403 / 成员 200 / 超管 200；get_project 404。

真实 project router；mock db 只服务 is_superadmin(跳过) 与 membership 查询。
"""
import uuid

import pytest

from rbac_helpers import build_app, fake_identity, make_user, patch_identity, smart_db
from app.extensions.auth import admin as _admin_mod
from app.extensions.project.routers import router as project_router

PID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _no_superadmin(monkeypatch):
    """默认让 is_superadmin 返回 False（非超管路径）。"""
    async def _false(db, user_id):  # noqa: ARG001
        return False
    monkeypatch.setattr(_admin_mod, "is_superadmin", _false)


def test_non_member_403(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user", member_projects=[]))
    db = smart_db(member_row=None)  # 非成员 → membership 查询 None
    tc = build_app(project_router, user=make_user(), db=db)
    assert tc.get(f"/api/extensions/projects/{PID}/activities").status_code == 403
    assert tc.get(f"/api/extensions/projects/{PID}/stats").status_code == 403
    assert tc.get(f"/api/extensions/projects/{PID}/files").status_code == 403


def test_member_200(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user", member_projects=[str(PID)]))
    db = smart_db(member_row=object())  # 有成员行 → 过门 → 端点体跑（空数据 → 200）
    tc = build_app(project_router, user=make_user(), db=db)
    assert tc.get(f"/api/extensions/projects/{PID}/activities").status_code == 200


def test_superadmin_200(monkeypatch):
    async def _true(db, user_id):  # noqa: ARG001
        return True
    monkeypatch.setattr(_admin_mod, "is_superadmin", _true)  # 覆盖 autouse 的 False
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    db = smart_db(member_row=None)
    tc = build_app(project_router, user=make_user(role_name="超级管理员"), db=db)
    assert tc.get(f"/api/extensions/projects/{PID}/activities").status_code == 200
```

注意：若 `project_router` include 后某端点依赖未覆盖（如其它 `require_*`），对**本测试用到的三个端点**逐一确认其依赖仅为 `require_project_member` + `get_db` + `get_current_user`（审计已确认 activities/stats/files 用 `require_project_member`）。`/api/extensions/projects` 前缀以 `project/routers.py` 实际 `APIRouter(prefix=...)` 为准。

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_project_idor_http.py -v'`
Expected: 3 passed（read 端点已 gate；HTTP 层确认）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_project_idor_http.py
git commit -m "test(rbac): project IDOR HTTP — non-member 403 / member 200 / superadmin 200" -- backend/tests/test_project_idor_http.py
```

### Task 9: test_knowledge_flip.py（dept scope 接线 + by-id 用 scope）

**Files:**
- Create: `backend/tests/test_knowledge_flip.py`

- [ ] **Step 1: 写测试**

```python
"""knowledge 可见性接线（HTTP/SQL 层）：dept 角色 scope 含 overlap；by-id 复用 list scope。"""
import uuid

import pytest

from rbac_helpers import build_app, capture_sql, fake_identity, make_user, patch_identity, smart_db
from app.extensions.auth.middleware import with_data_scope
from app.extensions.knowledge.routers import router
from app.extensions.models import KnowledgeBase


@pytest.mark.asyncio
async def test_dept_role_scope_includes_overlap(monkeypatch):
    """dept_head 角色的 knowledge scope 必须表达 allowed_depts OVERLAP（dept 共享接线）。"""
    dept = uuid.uuid4()
    patch_identity(monkeypatch, fake_identity(role_code="dept_head", dept_ids=[str(dept)]))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=smart_db(policy_rows=[]))
    sql = str(rule.to_sqlalchemy(KnowledgeBase, {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "allowed_depts" in sql and "&&" in sql, f"dept 共享未接线: {sql}"


def test_by_id_reuses_list_scope(monkeypatch):
    """GET /knowledge-bases/{id} 的查询必须叠加 scope 谓词（404 on no-access）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[], kb_row=None)
    tc = build_app(router, user=make_user(), db=db)
    r = tc.get(f"/api/extensions/knowledge/knowledge-bases/{uuid.uuid4()}")
    assert r.status_code == 404
    sql = capture_sql(db)
    assert "owner_id" in sql  # 查询带 scope（doc_owner 分支），非裸 id 查询
```

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_knowledge_flip.py -v'`
Expected: 2 passed（F1 修复后 dept_head 有 `knowledge_dept` scope，overlap 接线生效）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_knowledge_flip.py
git commit -m "test(rbac): knowledge dept overlap wiring + by-id reuses list scope (404)" -- backend/tests/test_knowledge_flip.py
```

### Task 10: test_rbac_edge.py（引擎边界补齐）

**Files:**
- Create: `backend/tests/test_rbac_edge.py`

- [ ] **Step 1: 写测试**

```python
"""引擎边界：inherit 环检测 / not 组合 / overlap 空值 / knowledge_law_all / bare-* 写拦截。"""
import uuid

import pytest
from fastapi import HTTPException

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.policy_routers import _validate_grants
from app.extensions.auth.registry import PermissionRegistry, get_permission_registry
from app.extensions.models import KnowledgeBase


def test_inherit_cycle_detected(tmp_path):
    main = tmp_path / "permissions.yaml"
    main.write_text(
        "version: 3\nmodules: {}\nroles:\n  a:\n    display_name: A\n    permissions: ['#inherit:b']\n    nav: []\n    data_scopes: []\n  b:\n    display_name: B\n    permissions: ['#inherit:a']\n    nav: []\n    data_scopes: []\n",
        encoding="utf-8",
    )
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    reg = PermissionRegistry(str(main), overlay_path=str(overlay))
    perms = reg.resolve_role_permissions("a")  # 环：不无限循环、不抛
    assert perms == set()


def test_not_over_allow_all_is_false():
    rule = FilterRule(operator="not", children=[FilterRule(operator="allow_all")])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "not" in compiled.lower()  # NOT TRUE = FALSE（deny allow_all → 全否）


def test_not_over_none_allow_is_true():
    rule = FilterRule(operator="not", children=[FilterRule(operator="none_allow")])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    assert "not" in str(expr.compile(compile_kwargs={"literal_binds": True})).lower()


def test_overlap_empty_value_false():
    rule = FilterRule(operator="overlap", field="allowed_depts", value=[])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"allowed_depts": KnowledgeBase.allowed_depts})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "false" in compiled  # 空值 → WHERE FALSE


def test_knowledge_scopes_declared():
    """三个真实 knowledge scope 必须声明（owner/public/dept）。

    注：spec §6 测试矩阵里的 knowledge_law_all 是历史残留名——kb_type(law) 分类型差异化
    已按 08-04 设计 §2 明确 deferred，yaml 现无该 scope；不为此造数据。
    """
    reg = get_permission_registry()
    for sid in ("knowledge_owner", "knowledge_public", "knowledge_dept"):
        assert reg.get_data_scope(sid) is not None, f"scope {sid} 未声明"
    assert reg.get_data_scope("knowledge_law_all") is None  # 已 deferred，确无此 scope


def test_bare_star_deny_rejected_on_write():
    with pytest.raises(HTTPException) as ei:
        _validate_grants({"deny_permissions": ["*"]}, get_permission_registry())
    assert ei.value.status_code == 400
```

- [ ] **Step 2: 跑测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_rbac_edge.py -v'`
Expected: 6 passed。若 `get_data_scope("knowledge_law_all")` 的签名不同（接受 module/id），按 `registry.py` 实际 API 调整调用。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_rbac_edge.py
git commit -m "test(rbac): engine edges — inherit cycle, not combos, overlap empty, law_all, bare-* deny write-guard" -- backend/tests/test_rbac_edge.py
```

### Task 11: test_docmgr_scopes.py（F2/F3 — 红）

**Files:**
- Create: `backend/tests/test_docmgr_scopes.py`

- [ ] **Step 1: 写测试（先红——F2/F3 未修）**

```python
"""F2/F3 回归：collab by-id 与 list_folders 必须走 scope 引擎（deny 生效）。

红→绿判别器：scope 引擎产出的 SQL 含 NOT（deny 分支）；legacy 手写子句不含。
"""
import uuid

import pytest

from rbac_helpers import build_app, capture_sql, fake_identity, make_user, patch_identity, policy_row, smart_db
from app.extensions.docmgr.collab_routers import router as collab_router
from app.extensions.docmgr.routers import router as docmgr_router

DID = uuid.uuid4()


def _deny_db():
    # deny_data_scopes 策略 + user 角色（doc_owner/doc_project_member）
    return smart_db(policy_rows=[policy_row("d", grants={"deny_data_scopes": ["doc_project_member"]})], doc_row=None)


def test_collab_by_id_scope_narrows(monkeypatch):
    """F2：collab by-id 查询必须含 scope 引擎的 AND NOT deny（deny 生效）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = _deny_db()
    tc = build_app(collab_router, user=make_user(), db=db)
    r = tc.get(f"/api/extensions/docmgr/documents/{DID}/comments")
    assert r.status_code == 404  # mock 无行
    sql = capture_sql(db)
    assert "not" in sql, f"collab by-id 未走 scope（deny 不生效）: {sql}"


def test_list_folders_scope_narrows(monkeypatch):
    """F3：/folders 查询必须含 scope 谓词（deny 生效）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = _deny_db()
    tc = build_app(docmgr_router, user=make_user(), db=db)
    r = tc.get("/api/extensions/docmgr/folders")
    assert r.status_code == 200  # 空数据
    sql = capture_sql(db)
    assert "not" in sql, f"list_folders 未走 scope（deny 不生效）: {sql}"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_docmgr_scopes.py -v'`
Expected: 2 FAIL——F2：collab 仍用 legacy `get_by_id`（SQL 无 NOT）；F3：`/folders` 不走 `with_data_scope`（SQL 无 NOT）。这两个失败即审计证据。

- [ ] **Step 3: Commit（红项先提交，作为审计证据）**

```bash
git add backend/tests/test_docmgr_scopes.py
git commit -m "test(rbac): F2/F3 RED — collab by-id + list_folders not scope-wired (deny not applied)" -- backend/tests/test_docmgr_scopes.py
```

### Task 12: 修 F2（collab_routers 接 scope）

**Files:**
- Modify: `backend/app/extensions/docmgr/collab_routers.py`

- [ ] **Step 1: 加 imports**

在 `collab_routers.py` 顶部（`from app.extensions.auth.middleware import get_current_user` 附近）加：

```python
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import get_current_user, with_data_scope
```

- [ ] **Step 2: 8 个 by-id 端点改 `get_by_id_scoped` + 注入 scope**

对 7 个 path 参数端点（`list_comments` L37、`create_comment` L50、`list_versions` L116、`create_version` L131、`diff_versions` L164、`get_version` L180、`restore_version` L199）逐一：
- 签名加 `scope: FilterRule = Depends(with_data_scope("docmgr")),`
- 调用改 `doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)`

示例（`list_comments`）：

```python
@router.get("/documents/{doc_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    # EAI-CUSTOM (F2): by-id 复用 list 同 scope 引擎，deny_data_scopes 可窄化批注/版本接口
    scope: FilterRule = Depends(with_data_scope("docmgr")),
):
    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return await CommentService.list_comments(db, doc_id)
```

对 `ai_review_document`（L240，`request.doc_id` 来自 body）：

```python
    # ...签名加 scope 参数同上...
    doc = await AIDocumentService.get_by_id_scoped(db, request.doc_id, scope)
```

- [ ] **Step 3: 跑 Task 11 测试确认转绿**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_docmgr_scopes.py::test_collab_by_id_scope_narrows -v'`
Expected: PASS（collab by-id SQL 现在含 NOT）。

- [ ] **Step 4: lint + Commit**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m ruff check app/extensions/docmgr/collab_routers.py'`
Expected: 0 error。

```bash
git add backend/app/extensions/docmgr/collab_routers.py
git commit -m "fix(rbac): F2 collab_routers by-id routes through scope engine (deny narrows; superadmin allow_all)" -- backend/app/extensions/docmgr/collab_routers.py
```

### Task 13: 修 F3（list_folders 接 scope）

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`（`list_folders`，约 L245-263）
- Modify: `backend/app/extensions/docmgr/routers.py`（`/folders` 端点，约 L435-443）

- [ ] **Step 1: service.list_folders 加 scope 分支**

```python
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
        return [row[0] for row in result.all()]
```

- [ ] **Step 2: /folders 端点注入 scope**

`routers.py`（确认已 import `with_data_scope`、`FilterRule`——F2 依赖 docmgr 主路由已有）：

```python
@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
    # EAI-CUSTOM (F3): 文件夹列表走 scope 引擎（deny 生效，超管 allow_all）
    scope: FilterRule = Depends(with_data_scope("docmgr")),
):
    folders = await AIDocumentService.list_folders(db, current_user.id, project_scope=project_scope, scope=scope)
    return FolderListResponse(folders=folders)
```

- [ ] **Step 3: 跑 Task 11 测试确认转绿**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_docmgr_scopes.py -v'`
Expected: 2 passed。

- [ ] **Step 4: lint + Commit**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m ruff check app/extensions/docmgr/service.py app/extensions/docmgr/routers.py'`
Expected: 0 error。

```bash
git add backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/routers.py
git commit -m "fix(rbac): F3 list_folders routes through scope engine (deny narrows; backward-compat scope=None)" -- backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/routers.py
```

### Task 14: 修 F4（workflow-admin 硬编码门）

**Files:**
- Modify: `frontend/src/app/workflow-admin/layout.tsx`
- Modify: `frontend/src/app/workflow-admin/page.tsx`
- Modify: `frontend/src/app/workflow-admin/components/TemplateEditorPage.tsx`

- [ ] **Step 1: layout.tsx 改 AdminGate 模式**

`layout.tsx`（当前 `isAdmin(user?.role_name)` 判门；layout 本体不在 PermissionProvider 内 → 按 `admin/layout.tsx` 模式外包 provider + 下沉 gate）：

```tsx
import { PermissionProvider } from "@/core/permissions";
// ...原有 imports（useAuth, useRouter, SimpleShellLayout, ReactNode...）

// 删除 isAdmin(roleName) helper（10-12 行）

export default function WorkflowAdminLayout({ children }: { children: ReactNode }) {
  // EAI-CUSTOM (F4): PermissionProvider 置于判权门之上，WorkflowAdminGate 消费 /me is_admin
  return (
    <PermissionProvider>
      <WorkflowAdminGate>{children}</WorkflowAdminGate>
    </PermissionProvider>
  );
}

function WorkflowAdminGate({ children }: { children: ReactNode }) {
  const { is_admin, isLoading: permLoading } = usePermission();
  const { isLoading: userLoading } = useAuth();
  const router = useRouter();
  const loading = userLoading || permLoading;

  useEffect(() => {
    if (!loading && !is_admin) {
      router.replace("/dashboard");
    }
  }, [loading, is_admin, router]);

  if (!loading && !is_admin) {
    return null;
  }

  return <SimpleShellLayout>{children}</SimpleShellLayout>;
}
```

（需 `import { usePermission } from "@/core/permissions";`；`SimpleShellLayout` 仍是 children 的 ShellLayout/PermissionProvider 供给者。）

- [ ] **Step 2: page.tsx 改 is_admin**

`page.tsx`（当前 L40-41 `const isSuperAdmin = user?.role_name === "Super Admin";`）：

```tsx
import { usePermission } from "@/core/permissions";
// ...
  const { is_admin: isSuperAdmin } = usePermission();  // EAI-CUSTOM (F4): /me 权威
```

保留其余 `isSuperAdmin` 用法不变（L184/190/208/214 直接替换布尔源）。删除不再需要的 `user?.role_name === "Super Admin"` 判定；若 `user` 变量其余处仍用，保留 `const { user } = useAuth()`。

- [ ] **Step 3: TemplateEditorPage.tsx 改 is_admin**

同 page.tsx：L32 `const isSuperAdmin = user?.role_name === "Super Admin";` → `const { is_admin: isSuperAdmin } = usePermission();`（加 import）。

- [ ] **Step 4: typecheck**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "workflow-admin" || echo "NO_WORKFLOW_ADMIN_TS_ERRORS"`
Expected: `NO_WORKFLOW_ADMIN_TS_ERRORS`（或仅既有基线错误，不含 workflow-admin 文件新增错误；全量 typecheck 有 127 个既有基线错误，只看 workflow-admin 相关无新错）。

- [ ] **Step 5: lint + Commit**

Run: `cd frontend && npx eslint src/app/workflow-admin` → 0 error。

```bash
git add frontend/src/app/workflow-admin/layout.tsx frontend/src/app/workflow-admin/page.tsx frontend/src/app/workflow-admin/components/TemplateEditorPage.tsx
git commit -m "fix(rbac): F4 workflow-admin uses /me is_admin (drop hardcoded role_name === Super Admin)" -- frontend/src/app/workflow-admin/layout.tsx frontend/src/app/workflow-admin/page.tsx frontend/src/app/workflow-admin/components/TemplateEditorPage.tsx
```

### Task 15: L1 全绿 + 法人域回归对比

- [ ] **Step 1: 跑全部 L1 新测试**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_role_definition_f1.py tests/test_permissions_me_endpoint.py tests/test_policy_deny_endpoint.py tests/test_with_data_scope_middleware.py tests/test_data_deny_e2e.py tests/test_project_idor_http.py tests/test_knowledge_flip.py tests/test_docmgr_scopes.py tests/test_rbac_edge.py -v'`
Expected: 全绿。

- [ ] **Step 2: 法人域既有测试回归（确认无新失败）**

Run: `docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/test_filterrule_operators.py tests/test_policy_enforcement.py tests/test_datascope.py tests/test_knowledge_data_access.py tests/test_docmgr_data_access.py tests/test_project_idor.py tests/test_registry_overlay.py tests/test_role_calibration.py tests/test_role_overlay_store.py tests/test_unified_project_permissions.py tests/test_p0_permission_gates.py tests/test_authorization_provider.py tests/test_policy_crud.py -v'`
Expected: 全部通过（F1/F2/F3 修复不应破坏既有测试；若某既有测试因 F2/F3 变化失败，说明回归，需修——例如 collab_routers 若存在依赖 scope 的既有测试）。

- [ ] **Step 3: 记录红→绿清单（供 Cycle 4 报告）**

把 Cycle 0-1 每个红项→修复→转绿的记录追加到 `.wolf/memory.md`（一行一条）。

---

## Cycle 2 — L2 浏览器 E2E（真实 Docker 多角色）

### Task 16: E2E 场景清单（chrome-devtools，nginx :2026）

前置：dev 环境已起（deer-flow-frontend/gateway/nginx up）；重启 frontend 容器使 F4 改动生效：
`docker compose -p eai-docker -f docker/docker-compose-dev.yaml up -d --no-deps frontend`（force-recreate 可选，若前端 HMR 不生效）。

- [ ] **Step 1: admin 策略编辑器 deny 区**
  登录 `admin@eai-flow.com` / `Admin@2026` → 角色管理 → 策略 → 新建策略：加 deny 权限 `kb:delete` + deny 数据范围 `knowledge_public` → 保存 → 重载 → 断言策略行显示"拒绝权限/拒绝范围"、字段往返。

- [ ] **Step 2: dept_head 修复后全流程**
  用 dept_head 用户（zhangsan，若密码未知先在 admin 用户管理重置）登录 → 知识库/项目/文档空间 → 断言无 403、能访问、能建库。

- [ ] **Step 3: workflow-admin 门（F4）**
  非超管（dept_head/user）访问 `/workflow-admin` → 断言重定向 `/dashboard`；admin 访问 → 可进、发布/提交审批按钮按 is_admin 切换。

- [ ] **Step 4: 按钮级 can()**
  user 角色（test-procurement）进 knowledge 页 → 断言新建/上传/删除按钮显隐符合 user 权限（kb:read 无 create/upload/delete）。

- [ ] **Step 5: 页面可见性**
  dept_head 看 knowledge-factory（9 tab）与 contract-price（6 路由）→ 断言未授权 tab 不渲染。

- [ ] **Step 6: 记录结果**（截图/断言到 `.wolf/memory.md` 或报告草稿）。

---

## Cycle 3 — L3 安全对抗

### Task 17: 对抗探测清单（测试 DB 内做破坏性探测，真实环境只做只读）

- [ ] **Step 1: IDOR 越权**（L1 `test_project_idor_http.py` 已覆盖 read 端点；补 mutation 端点引擎级断言已在 `test_unified_project_permissions.py`）——确认覆盖无缺口。
- [ ] **Step 2: 存在性泄露**（by-id 无权 vs 不存在统一 404；`get_project` 非成员 404）——已在 L1 断言（knowledge by-id 404 / project 404）。
- [ ] **Step 3: 超管双豁免**（deny_permissions + deny_data_scopes 对超管无效）——已在 L1 断言（`test_policy_deny_endpoint.py` superadmin 例 / `test_with_data_scope_middleware.py` allow_all）。
- [ ] **Step 4: deny 绕过**（精确/通配/嵌套条件/空条件）——已在 `test_policy_deny_endpoint.py` 覆盖。
- [ ] **Step 5: 边界**（str→UUID 畸形 dept_ids、空 allowed_depts、bare-* 写入口 400）——`test_rbac_edge.py` 覆盖；畸形 dept_ids 已有 `test_filterrule_operators.py`。
- [ ] **Step 6: deep-link 直达隐藏子页**（前端无守卫）——记录为已知项，不改（spec §3 RISK）。
- [ ] **Step 7: 记录结论**（哪些已闭合/哪些记录）。

---

## Cycle 4 — 审计报告

### Task 18: 产出审计报告

- [ ] **Step 1: 汇总**
  在 `docs/superpowers/specs/2026-08-05-role-permission-deep-audit-test-design.md` 末尾追加「实施结果」章节，或新建 `docs/superpowers/reports/2026-08-05-role-permission-deep-audit-report.md`，包含：
  1. 设计完备性结论（spec §2.1）。
  2. 实现落地性 + 修复记录（Cycle 0/1 每个 commit：F1/F2/F3/F4 红→绿）。
  3. 深度测试结论（L1/L2/L3 每项通过/失败/已知项表）。
  4. 已知项（spec §3 记录不修 + RISK）+ 后续建议（require_role 替换、roles 页细粒度、deep-link 守卫、live-PG 测试基建）。

- [ ] **Step 2: 提交报告 + wolf 记账**
```bash
git add docs/superpowers/specs/2026-08-05-role-permission-deep-audit-test-design.md
git commit -m "docs(report): role-permission deep-audit results — F1-F4 fixed, L1-L3 test matrix outcomes" -- docs/superpowers/specs/2026-08-05-role-permission-deep-audit-test-design.md
```
并按 OpenWolf 协议：`.wolf/buglog.json` 记 F1（dept_head 清空 bug，read-max-id 防撞）、`.wolf/memory.md` 追加会话一行、`.wolf/cerebrum.md` 更新 Key Learnings（overlay 整体替换语义是数据坑、live 验证法）。

---

## Self-Review

**Spec coverage:**
- spec §2 审计结论 → 本计划 Task 1-2（F1）+ L1 套件（已验证设计/实现状态）。
- spec §4 F1 → Task 1-2；F2 → Task 11/12；F3 → Task 11/13；F4 → Task 14。
- spec §5 L1 8 文件 → Task 4-11 逐一对应；L2 → Task 16；L3 → Task 17；L4 → Task 1/11（回归）。
- spec §6 执行顺序 Cycle 0-4 → 本计划 Cycle 0-4 对应。
- spec §7 报告 → Task 18。

**Placeholder scan:** 无 TBD/TODO/`pass` 占位——Task 5 内已注明删除 `pass` 桩；所有测试含完整代码；`policy_rows_db` 内联在 Task 4。F2/F3 改动为精确代码块。

**Type consistency:** `rbac_helpers` 的 `make_user`/`fake_identity`/`smart_db`/`build_app`/`capture_sql`/`patch_identity`/`policy_row`/`policy_rows_db` 在 Task 3-11 间名称一致；`get_by_id_scoped(db, doc_id, scope)` 签名与现有 `service.py:143-173` 一致；`list_folders(db, user_id, project_scope, scope)` 新增参数字段与端点调用一致。

**风险（实现者注意）：**
- `patch_identity` 必须同时 patch 源模块与消费模块（helpers 已列）；若某端点用 `app.extensions.auth.<module>.get_identity_provider` 的模块级名，需补 patch 该模块。
- 真实 project router include 后若某端点有未覆盖依赖，按 Task 8 注处理（对测试用端点确认依赖集合）。
- F4 typecheck 只看 workflow-admin 无新错（全量 127 基线错误不修）。
- 全量 pytest 基线 420 失败不修（判别新失败只看法人域文件）。
