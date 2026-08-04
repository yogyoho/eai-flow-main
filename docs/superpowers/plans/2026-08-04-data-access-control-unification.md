# 数据访问控制统一 + ABAC deny 原语 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把知识库/项目/文档空间的行级可见性统一到 `DataScopeEngine`+`FilterRule`,补齐 scope 表达力(数组重叠),闭合 IDOR,并加上 ABAC deny 原语(权限点 + 数据范围),修 `/me` 一致性 bug。

**Architecture:** 两层正交——可见性(`DataScopeEngine`+`FilterRule`,行级过滤)与权限(权限点 / 项目内 `unified_permissions`)。本计划先做引擎层(FilterRule `overlap`/`not` 算子、`DataScopeEngine` deny 组合、`with_data_scope` 注入策略+超管旁路、权限点 deny、`/me` 一致性、共享 policy loader),再把三模块的 list/by-id 统一到 scope 引擎、闭合项目 IDOR,最后前端策略编辑器加 deny 区。

**Tech Stack:** Python 3.12 / SQLAlchemy 2.0 (async) / FastAPI / Pydantic / PostgreSQL ARRAY / pytest;Next.js+React 前端。后端测试命令:`cd backend && PYTHONPATH=. uv run pytest tests/<file>.py -v`;lint:`cd backend && make lint`。

**Spec:** `docs/superpowers/specs/2026-08-04-abac-deny-primitive-design.md`

**Conventions:** 改 `app/` EAI 定制代码无需 EAI-CUSTOM 三重规范(非 harness 上游);改 `packages/harness/` 才需要(本计划不触及 harness)。ruff 行宽 240。提交到 `main-dev-fork`。

---

## File Structure

**Create:**
- `backend/app/extensions/auth/policy_loader.py` — `load_active_policies(db)` 共享策略加载器(消除 `require_permission` 与 `/me` 漂移)。
- `backend/tests/test_filterrule_operators.py` — `overlap`/`not` 算子单元测试。
- `backend/tests/test_policy_enforcement.py` — deny 端到端集成测试。
- `backend/tests/test_knowledge_data_access.py` — 知识库可见性(list/by-id 统一、dept 共享)测试。
- `backend/tests/test_project_idor.py` — 项目 IDOR 闭合测试。

**Modify:**
- `backend/app/extensions/auth/engine.py` — `FilterRule` 加 `overlap`/`not`;提取 `evaluate_policy_conditions`;`check`/`list_permissions` 加 deny。
- `backend/app/extensions/auth/datascope.py` — `get_data_scope` 加 `deny_scope_ids`;抽 `build_scope_union`。
- `backend/app/extensions/auth/middleware.py` — `with_data_scope` 改造(策略+超管+deny);`require_permission` 用共享 loader + deny 日志。
- `backend/app/extensions/auth/permission_routers.py` — `/me` 传 `load_active_policies`。
- `backend/app/extensions/auth/policy_routers.py` — `PolicyCreate/Update` 校验 deny 字段。
- `config/permissions.yaml` — knowledge data_scopes 重写(overlap);docmgr 新增 data_scopes;project_member 补 `created_by`。
- `backend/app/extensions/knowledge/routers.py` — column_map 扩;by-id 用 scope;删 `_can_access_kb`。
- `backend/app/extensions/project/routers.py` — list 用 `with_data_scope`;闭合 6 个 IDOR 端点。
- `backend/app/extensions/project/service.py` — `list_projects` 接受 scope FilterRule(或保留 membership 但补成员复查)。
- `backend/app/extensions/docmgr/service.py` + `routers.py` — list/by-id 接 `with_data_scope("docmgr")`。
- `frontend/src/app/admin/roles/page.tsx` — 策略编辑器 deny 两栏 + 警示色;删 grant.data_scope 展示。

---

## Phase 1 — FilterRule 算子扩展(基础)

### Task 1: `overlap` 算子(数组重叠,知识库 allowed_depts)

**Files:**
- Modify: `backend/app/extensions/auth/engine.py`(FilterRule.from_template + to_sqlalchemy)
- Test: `backend/tests/test_filterrule_operators.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_filterrule_operators.py
import uuid
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet


def test_overlap_template_parses():
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[uuid.uuid4(), uuid.uuid4()])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    assert rule.operator == "overlap"
    assert rule.field == "allowed_depts"
    assert all(isinstance(x, uuid.UUID) for x in rule.value)  # str -> UUID coercion


def test_overlap_to_sqlalchemy_uses_array_overlap():
    from app.extensions.models import KnowledgeBase
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[uuid.uuid4()])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    expr = rule.to_sqlalchemy(KnowledgeBase, {"allowed_depts": KnowledgeBase.allowed_depts})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": False}))
    assert "allowed_depts" in compiled and "&&" in compiled
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_filterrule_operators.py -v`
Expected: FAIL(`overlap` 未实现 → `from_template` 落入 eq 分支或 to_sqlalchemy 返回 false)

- [ ] **Step 3: 实现**

In `engine.py` `from_template`,在 ` IN` 判断之后加 ` OVERLAP`:
```python
        for key, raw_value in template.items():
            if " IN" in key:
                field = key[:key.rfind(" IN")].strip()
                resolved = cls._resolve(raw_value, identity)
                if resolved is None:
                    return cls(operator="none_allow")
                return cls(operator="in", field=field, value=resolved if isinstance(resolved, list) else [resolved])
            if " OVERLAP" in key:
                import uuid as _uuid
                field = key[:key.rfind(" OVERLAP")].strip()
                resolved = cls._resolve(raw_value, identity)
                if not resolved:
                    return cls(operator="none_allow")  # identity 无该属性 → 交集必空 → deny
                coerced = [_uuid.UUID(x) for x in resolved] if resolved and isinstance(resolved[0], str) else list(resolved)
                return cls(operator="overlap", field=field, value=coerced)
            else:
                resolved = cls._resolve(raw_value, identity)
                return cls(operator="eq", field=key, value=resolved)
```
In `to_sqlalchemy`,在 `in` 分支后加:
```python
        if self.operator == "overlap":
            col = column_map.get(self.field) if column_map else None
            if col is None and self.field and hasattr(model, self.field):
                col = getattr(model, self.field)
            if col is None or not self.value:
                return sqlalchemy_false()
            return col.overlap(self.value)   # PG && ;col 须为 ARRAY 列
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_filterrule_operators.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/engine.py backend/tests/test_filterrule_operators.py
git commit -m "feat(rbac): FilterRule overlap operator for PG array columns (knowledge allowed_depts)"
```

### Task 2: `not` 算子(数据 deny)

**Files:** Modify `backend/app/extensions/auth/engine.py`;Test: `backend/tests/test_filterrule_operators.py`

- [ ] **Step 1: 写失败测试**(追加到同一文件)

```python
def test_not_template_and_sqlalchemy():
    from app.extensions.models import KnowledgeBase
    idn = AttributeSet(user_id="u1", username="u1")
    inner = FilterRule.from_template({"access_type": "public"}, idn)   # eq
    rule = FilterRule(operator="not", children=[inner])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    assert "NOT" in str(expr.compile(compile_kwargs={"literal_binds": False})).upper()
```

- [ ] **Step 2: 跑确认失败** — `cd backend && PYTHONPATH=. uv run pytest tests/test_filterrule_operators.py::test_not_template_and_sqlalchemy -v` → FAIL

- [ ] **Step 3: 实现** — `to_sqlalchemy` 的 `or` 分支后加:
```python
        if self.operator == "not" and self.children:
            from sqlalchemy import not_
            return not_(self.children[0].to_sqlalchemy(model, column_map))
```

- [ ] **Step 4: 跑确认通过** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat(rbac): FilterRule not operator for data-scope deny"`

---

## Phase 2 — DataScopeEngine deny + with_data_scope 改造

### Task 3: 提取 `evaluate_policy_conditions` + `load_active_policies`

**Files:** Create `backend/app/extensions/auth/policy_loader.py`;Modify `engine.py`,`middleware.py`

- [ ] **Step 1: 写失败测试**

```python
# append to test_filterrule_operators.py
def test_evaluate_policy_conditions_module_function():
    from app.extensions.auth.engine import evaluate_policy_conditions
    idn = AttributeSet(user_id="u1", username="u1", role_level=50)
    assert evaluate_policy_conditions({"attr": "role_level", "op": "gte", "value": 40}, idn) is True
    assert evaluate_policy_conditions({"attr": "role_level", "op": "gte", "value": 60}, idn) is False
    assert evaluate_policy_conditions({}, idn) is True   # empty = match all
```

- [ ] **Step 2: 跑确认失败**(函数不存在)

- [ ] **Step 3: 实现**

In `engine.py`:把 `UnifiedPermissionEngine._evaluate_conditions` 的方法体搬到模块级 `evaluate_policy_conditions(conditions, identity) -> bool`,方法体调用改为 `evaluate_policy_conditions(self, identity)` → `evaluate_policy_conditions(conditions, identity)`。保持原逻辑(and/or/attr/op/value + operators 字典)。

Create `backend/app/extensions/auth/policy_loader.py`:
```python
"""Shared loader for active ABAC policies — single source for require_permission + /me."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.extensions.auth.engine import Policy as EnginePolicy
from app.extensions.auth.models import Policy as PolicyModel


async def load_active_policies(db: AsyncSession) -> list[EnginePolicy]:
    rows = (await db.execute(
        select(PolicyModel).where(PolicyModel.enabled == True).order_by(PolicyModel.priority)  # noqa: E712
    )).scalars().all()
    return [EnginePolicy(name=r.name, priority=r.priority, conditions=r.conditions, grants=r.grants) for r in rows]
```

- [ ] **Step 4: 跑确认通过**

- [ ] **Step 5: Commit** — `git add backend/app/extensions/auth/policy_loader.py backend/app/extensions/auth/engine.py backend/tests/test_filterrule_operators.py && git commit -m "refactor(rbac): extract evaluate_policy_conditions + shared load_active_policies"`

### Task 4: `DataScopeEngine` deny 组合

**Files:** Modify `backend/app/extensions/auth/datascope.py`;Test: `backend/tests/test_datascope.py`

- [ ] **Step 1: 写失败测试**(追加到 `test_datascope.py`)

```python
def test_get_data_scope_with_deny_composes_and_not():
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.registry import DataScope
    scopes = {"knowledge": [DataScope(id="knowledge_owner", display_name="o", rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
                            DataScope(id="knowledge_public", display_name="p", rule_template={"access_type": "public"}, module="knowledge")]}
    idn = AttributeSet(user_id="u1", username="u1")
    eng = DataScopeEngine(scopes, role_data_scopes={"r": ["knowledge_owner", "knowledge_public"]})
    rule = eng.get_data_scope(idn, "knowledge", deny_scope_ids={"knowledge_public"})
    assert rule.operator == "and"
    assert rule.children[1].operator == "not"   # AND NOT public

def test_get_data_scope_no_deny_returns_allow_unchanged():
    # deny_scope_ids empty or not applicable → deny_rule none_allow → return allow_rule
    ...
```
(import `AttributeSet` at top of test file)

- [ ] **Step 2: 跑确认失败**(`get_data_scope` 不接受 `deny_scope_ids`)

- [ ] **Step 3: 实现** — 重构 `datascope.py`:
```python
    def get_data_scope(self, identity, resource_type, deny_scope_ids=None):
        deny_scope_ids = deny_scope_ids or set()
        allow_rule = self.build_scope_union(identity, resource_type,
                                            self._role_data_scopes.get(identity.role_code or "", []))
        deny_rule = self.build_scope_union(identity, resource_type, deny_scope_ids)
        if deny_rule.operator == "none_allow":
            return allow_rule
        if deny_rule.operator == "allow_all":
            return FilterRule(operator="none_allow")
        return FilterRule(operator="and", children=[allow_rule, FilterRule(operator="not", children=[deny_rule])])

    def build_scope_union(self, identity, resource_type, scope_ids):
        """OR-union of the rule_templates of the given scope ids for resource_type. (抽出原 get_data_scope 主体)"""
        scopes = self._scopes_by_resource.get(resource_type)
        if not scopes:
            return FilterRule(operator="none_allow")
        applicable = [s for s in scopes if s.id in scope_ids]
        if not applicable:
            return FilterRule(operator="none_allow")
        if len(applicable) == 1:
            return FilterRule.from_template(applicable[0].rule_template, identity)
        children = [FilterRule.from_template(s.rule_template, identity) for s in applicable]
        if any(c.operator == "allow_all" for c in children):
            return FilterRule(operator="allow_all")
        children = [c for c in children if c.operator != "none_allow"]
        if not children:
            return FilterRule(operator="none_allow")
        if len(children) == 1:
            return children[0]
        return FilterRule(operator="or", children=children)
```
(保留 `from app.extensions.auth.engine import FilterRule` 导入;原 `get_data_scope` 主体替换为 `build_scope_union`。)

- [ ] **Step 4: 跑确认通过**(含原有 `test_datascope.py` 全绿——`build_scope_union` 保留了原语义,`get_data_scope` 默认 `deny_scope_ids=None` 时 deny_rule=none_allow→返回 allow_rule,等价旧行为)

- [ ] **Step 5: Commit** — `git commit -am "feat(rbac): DataScopeEngine composes AND NOT deny; extract build_scope_union"`

### Task 5: `with_data_scope` 改造(策略 + 超管旁路 + deny)

**Files:** Modify `backend/app/extensions/auth/middleware.py:339-362`

- [ ] **Step 1: 写失败测试** — 集成级,放 `test_policy_enforcement.py`(Task 11 一起写);此处先实现。

- [ ] **Step 2: 实现** — 替换 `with_data_scope` 内部 `_scope`:
```python
def with_data_scope(resource_type: str):
    async def _scope(current_user: CurrentUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)) -> FilterRule:
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.registry import get_permission_registry
        from app.extensions.auth.policy_loader import load_active_policies
        from app.extensions.auth.engine import evaluate_policy_conditions
        identity = await get_identity_provider().resolve(current_user.id, db)
        reg = get_permission_registry()
        defaults = reg.get_role_defaults(identity.role_code)
        resolved = reg.resolve_role_permissions(identity.role_code or "")
        if (defaults and defaults.get("is_system")) or "*" in resolved:
            return FilterRule(operator="allow_all")   # 超管双豁免,内建
        deny_ids = set()
        for p in await load_active_policies(db):
            if evaluate_policy_conditions(p.conditions, identity):
                deny_ids.update(p.grants.get("deny_data_scopes") or [])
        return DataScopeEngine.from_registry().get_data_scope(identity, resource_type, deny_ids)
    return _scope
```

- [ ] **Step 3: 跑现有 datascope/知识库测试不回归** — `cd backend && PYTHONPATH=. uv run pytest tests/test_datascope.py -v` → PASS

- [ ] **Step 4: Commit** — `git commit -am "feat(rbac): with_data_scope injects policies + superadmin bypass + data deny"`

---

## Phase 3 — 权限点 deny + /me 一致性

### Task 6: `engine.check` deny(精确 + 模块通配)

**Files:** Modify `engine.py`;Test: `backend/tests/test_filterrule_operators.py`(或新建 `test_unified_engine.py`)

- [ ] **Step 1: 写失败测试**

```python
def test_check_deny_overrides_role_grant():
    from app.extensions.auth.engine import UnifiedPermissionEngine, Policy, EnginePolicy if False else Policy
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    eng = UnifiedPermissionEngine(role_permissions={"r": {"kb:delete"}},
                                  policies=[Policy(name="d", priority=0,
                                                   conditions={},
                                                   grants={"deny_permissions": ["kb:delete"]})])
    assert eng.check(idn, "kb:delete") is False   # 角色有,但 deny 压过

def test_check_deny_module_wildcard():
    eng = UnifiedPermissionEngine(role_permissions={"r": {"kb:read", "kb:create"}},
                                  policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:*"]})])
    assert eng.check(idn, "kb:read") is False and eng.check(idn, "kb:create") is False

def test_check_superadmin_immune_to_deny():
    eng = UnifiedPermissionEngine(role_permissions={"super": {"*"}},
                                  policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:read"]})])
    sup = AttributeSet(user_id="s", username="s", role_code="super")
    assert eng.check(sup, "kb:read") is True
```

- [ ] **Step 2: 跑确认失败**

- [ ] **Step 3: 实现** — 改 `check`(用 §4.8 伪码):wildcard→allow;collect allow(角色+策略 allow);不命中→False;再遍历策略,`permission in denied or f"{prefix}:*" in denied` → False;else True。`denied = p.grants.get("deny_permissions") or []`。

- [ ] **Step 4: 跑确认通过**

- [ ] **Step 5: Commit** — `git commit -am "feat(rbac): engine.check deny-overrides (exact + module-wildcard); superadmin immune"`

### Task 7: `engine.list_permissions` 全量展开 + deny

**Files:** Modify `engine.py`;Test 同上

- [ ] **Step 1: 写失败测试**

```python
def test_list_permissions_expands_and_subtracts_deny():
    eng = UnifiedPermissionEngine(role_permissions={"r": {"kb:*"}},
                                  all_permission_ids={"kb:read", "kb:create", "kb:delete"},
                                  policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:delete"]})])
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    perms = eng.list_permissions(idn)
    assert "kb:read" in perms and "kb:create" in perms and "kb:delete" not in perms
```

- [ ] **Step 2: 跑确认失败**

- [ ] **Step 3: 实现** — `list_permissions`:`*`→`set(_all_permission_ids)`;else `expand(role_perms ∪ 策略 allow) − expand(策略 deny)`,`expand` 用 §4.5 伪码(`*`/`prefix:*`/exact)。

- [ ] **Step 4: 跑确认通过**

- [ ] **Step 5: Commit** — `git commit -am "feat(rbac): list_permissions expands to concrete points and subtracts deny"`

### Task 8: `/me` 一致性修复 + require_permission 用共享 loader

**Files:** Modify `permission_routers.py:79`,`middleware.py:205-231`

- [ ] **Step 1: 写失败测试** — 放 `test_policy_enforcement.py`(Task 11);此处先实现。

- [ ] **Step 2: 实现**

`permission_routers.py` `/me`:把
```python
    engine = UnifiedPermissionEngine(role_permissions=role_permissions, all_permission_ids=all_ids)
```
改为
```python
    from app.extensions.auth.policy_loader import load_active_policies
    engine = UnifiedPermissionEngine(role_permissions=role_permissions, all_permission_ids=all_ids,
                                     policies=await load_active_policies(db))
```
`middleware.py` `require_permission`(205-231):把内联的 `select(PolicyModel)...` 策略加载块替换为 `policies = await load_active_policies(db)`(import 共享 loader)。deny 命中时(257-265)日志补 `denied by policy <name>`——需在 `engine.check` 命中 deny 时返回 policy 名(简单做法:`check` 返回 `(bool, str|None)`,或新增 `check_with_reason`;为最小侵入,在 `require_permission` 内 deny 判定后重查一次拿名,或 `check` 接受可选 `deny_reason` out-param)。**取舍**:`check` 增加 `deny_policy_name: list[str] | None = None` out-param(默认 None),命中 deny 时 append 名;`require_permission` 读它写日志。

- [ ] **Step 3: 跑确认** — `cd backend && PYTHONPATH=. uv run pytest tests/ -k "permission or me or engine" -v` → PASS,无回归

- [ ] **Step 4: Commit** — `git commit -am "fix(rbac): /me loads policies via shared loader; require_permission deny audit log"`

### Task 9: `policy_routers` deny 字段校验

**Files:** Modify `backend/app/extensions/auth/policy_routers.py`

- [ ] **Step 1: 写失败测试**

```python
# test_policy_enforcement.py
def test_create_policy_rejects_unknown_deny_data_scope(client_or_db_fixture):
    # POST /api/policies with grants.deny_data_scopes=["nonexistent"] → 400
    ...
```

- [ ] **Step 2: 跑确认失败**

- [ ] **Step 3: 实现** — 在 `create_policy`/`update_policy` 写库前加校验函数:
```python
def _validate_grants(grants: dict, registry) -> None:
    for key in ("permissions", "deny_permissions"):
        v = grants.get(key)
        if v is not None and (not isinstance(v, list) or not all(isinstance(x, str) for x in v)):
            raise HTTPException(400, f"{key} must be a list of strings")
    for sid in grants.get("deny_data_scopes") or []:
        if registry.get_data_scope(sid) is None:
            raise HTTPException(400, f"Unknown data scope id: {sid}")
```
`create_policy`/`update_policy` 顶部调 `_validate_grants(data.grants, get_permission_registry())`。

- [ ] **Step 4: 跑确认通过**

- [ ] **Step 5: Commit** — `git commit -am "feat(rbac): validate policy grants deny_permissions/deny_data_scopes"`

---

## Phase 4 — 知识库模块(核心目的)

### Task 10: 重写 knowledge data_scopes + list column_map

**Files:** Modify `config/permissions.yaml`(knowledge.data_scopes),`backend/app/extensions/knowledge/routers.py:99-105`

- [ ] **Step 1: 写失败测试** — `test_knowledge_data_access.py`:
```python
@pytest.mark.asyncio
async def test_dept_role_sees_dept_shared_kb(test_db, ...):
    # 建 KB: access_type="dept", allowed_depts=[用户的 dept]
    # 用户角色 data_scopes 含 knowledge_owner+knowledge_dept+knowledge_public
    # 调 GET /api/extensions/knowledge-bases → 该 KB 出现在结果里(修复前看不到)
    ...
```

- [ ] **Step 2: 跑确认失败**

- [ ] **Step 3: 实现**

`permissions.yaml` knowledge.data_scopes 改为(spec §4.3):
```yaml
    data_scopes:
      - { id: "knowledge_owner",  display_name: "仅自己的知识库", rule_template: { owner_id: "$identity.user_id" } }
      - { id: "knowledge_public", display_name: "所有公开知识库", rule_template: { access_type: "public" } }
      - { id: "knowledge_dept",   display_name: "本部门的知识库", rule_template: { and: [ { access_type: "dept" }, { allowed_depts OVERLAP: "$identity.dept_ids" } ] } }
```
`routers.py:99-105` column_map:
```python
        column_map = {
            "owner_id": KnowledgeBase.owner_id,
            "access_type": KnowledgeBase.access_type,
            "allowed_depts": KnowledgeBase.allowed_depts,
        }
```
(保留 admin 走 `is_superadmin` 分支或改用 `with_data_scope` 内建超管——本步先保留 `is_superadmin` 分支不变,Task 12 统一收掉。)

- [ ] **Step 4: 跑确认通过**(dept 角色看到 dept 共享库)

- [ ] **Step 5: Commit** — `git commit -am "fix(knowledge): dept scope uses allowed_depts overlap; column_map includes array"`

### Task 11: 知识库 by-id 统一(删 `_can_access_kb`)

**Files:** Modify `backend/app/extensions/knowledge/routers.py`(57-64 删除;所有 by-id 端点改用 scope)

- [ ] **Step 1: 写失败测试** — `test_knowledge_data_access.py`:
```python
async def test_by_id_unauthorized_returns_404_not_403(test_db, ...):
    # 非所有者、非 public、非本部门的 KB → GET /knowledge-bases/{id} → 404(不泄露存在性)
async def test_by_id_owner_succeeds(...): ...
```

- [ ] **Step 2: 跑确认失败**

- [ ] **Step 3: 实现** — 新增 helper:
```python
async def _load_kb_scoped(db, kb_id, scope: FilterRule):
    from sqlalchemy import select as sa_select
    colmap = {"owner_id": KnowledgeBase.owner_id, "access_type": KnowledgeBase.access_type, "allowed_depts": KnowledgeBase.allowed_depts}
    q = sa_select(KnowledgeBase).where(KnowledgeBase.id == kb_id).where(scope.to_sqlalchemy(KnowledgeBase, colmap))
    return (await db.execute(q)).scalar_one_or_none()
```
每个原 `_can_access_kb(kb, current_user)` 调用点(GET/PUT/DELETE/documents/search)改为:先 `kb = await _load_kb_scoped(db, kb_id, scope)`,`if kb is None: raise HTTPException(404)`。`scope` 由各端点 `Depends(with_data_scope("knowledge"))` 注入。删除 `_can_access_kb` 函数。
PUT/DELETE 的 admin 字符串旁路(`role_name in ["超级管理员","admin"]`,163/178)删除——admin 经 `with_data_scope` 内建超管分支拿 `allow_all`,自然放行。

- [ ] **Step 4: 跑确认通过**(含知识库全部端点回归)

- [ ] **Step 5: Commit** — `git commit -am "refactor(knowledge): by-id reuses list scope (404 on no-access); drop _can_access_kb + role_name bypass"`

---

## Phase 5 — 项目模块(闭合 IDOR)

### Task 12: project list 用 scope + 6 个 IDOR 端点闭合

**Files:** Modify `config/permissions.yaml`(project_member scope),`project/routers.py`,`project/service.py`

- [ ] **Step 1: 写失败测试** — `test_project_idor.py`:
```python
async def test_non_member_cannot_finalize_doc(...):
    # 用户 A 不是 project P 成员;POST /projects/{P}/finalize-doc → 403
async def test_non_member_cannot_see_activities(...):
    # GET /projects/{P}/activities → 403(非成员)
```

- [ ] **Step 2: 跑确认失败**(当前返回 200)

- [ ] **Step 3: 实现**

`permissions.yaml` project.data_scopes 的 `project_member`:
```yaml
      - { id: "project_member", display_name: "参与的项目", rule_template: { or: [ { id IN: "$identity.member_projects" }, { created_by: "$identity.user_id" } ] } }
```
新增成员资格复查依赖(放 `unified_permissions.py` 或 `middleware.py`):
```python
def require_project_member():
    async def _check(current_user=Depends(get_current_user), db=Depends(get_db),
                    project_id: uuid.UUID = None):  # project_id 从 path 注入,见下
        from app.extensions.auth.admin import is_superadmin
        if await is_superadmin(db, current_user.id): return current_user
        from app.extensions.models import ProjectMember
        exists = await db.execute(select(ProjectMember).where(ProjectMember.project_id==project_id, ProjectMember.user_id==current_user.id))
        if not exists.scalar_one_or_none():
            raise HTTPException(403, "Not a project member")
        return current_user
    return _check
```
(项目路由用 `project_id` path param;`require_resource_permission` 已有从 `request.path_params` 取 project_id 的模式——复用同一方式取参。)
闭合端点(加成员复查):
- `/projects/{project_id}/documents/{doc_id}/status`(`routers.py:1000`)
- `/projects/{project_id}/finalize-doc`(`1185`)
- `/projects/{project_id}/merge-docs`(`1029`)
- `/projects/{project_id}/activities`(`735`)
- `/projects/{project_id}/stats`(`1101`)
- `/projects/{project_id}/files`(`300`)
- phase board/readiness(`599,613`)、`/phase-status`(`911`)
(list 可见性:本步保留 `service.list_projects` 手写过滤不动——统一到 `with_data_scope("projects")` 列为后续优化,优先级低于 IDOR 修复;若需统一,在 list 端点叠加 `Depends(with_data_scope("projects"))` 并替换 service 内的 created_by/member 查询。**本任务聚焦 IDOR 闭合**,scope 统一记入 §风险。)

- [ ] **Step 4: 跑确认通过**(非成员 6 端点 403;成员正常)

- [ ] **Step 5: Commit** — `git commit -am "fix(project): close IDOR on doc-status/finalize/merge/activities/stats/files + member recheck"`

---

## Phase 6 — 文档空间模块

### Task 13: docmgr 声明 scope + 接线

**Files:** Modify `config/permissions.yaml`(docmgr.data_scopes),`docmgr/service.py`,`docmgr/routers.py`

- [ ] **Step 1: 写失败测试** — `test_docmgr` 或现有:验证 list 行为不变(我的 + 项目成员的文档可见)。

- [ ] **Step 2: 实现**

`permissions.yaml` docmgr 加:
```yaml
  docmgr:
    ...pages...
    data_scopes:
      - { id: "doc_owner",          display_name: "我的文档",   rule_template: { user_id: "$identity.user_id" } }
      - { id: "doc_project_member", display_name: "项目内文档", rule_template: { project_id IN: "$identity.member_projects" } }
```
`docmgr/routers.py` `GET /documents`:`scope: FilterRule = Depends(with_data_scope("docmgr"))`,service 用 `scope.to_sqlalchemy(AIDocument, {"user_id": AIDocument.user_id, "project_id": AIDocument.project_id})` 叠加到查询,替代手写 `user_id == caller OR project_id IN ...`。`get_by_id` 同样用 scope(§4.6 通用原则)。
(docmgr 现 IDOR 已闭合;本步是机制统一,行为不变。若与 `project_scope`/`folder_id` 等业务过滤器叠加复杂,**最小做法**:保留 service 现有逻辑,仅把 owner/membership 谓词换成 scope FilterRule,其余 filter 不变。)

- [ ] **Step 3: 跑确认**(docmgr 现有测试全绿,行为等价)

- [ ] **Step 4: Commit** — `git commit -am "refactor(docmgr): declare data_scopes + wire list/by-id to scope engine"`

---

## Phase 7 — 前端策略编辑器

### Task 14: 策略编辑器 deny 两栏 + 清理

**Files:** Modify `frontend/src/app/admin/roles/page.tsx`

- [ ] **Step 1: 实现**(前端无单测门槛,靠 typecheck + 人工)
- 在 `PolicyEditorForm` 现有"授权(grant)"区下方加**"拒绝(deny)"区**:权限点选择器(写入 `deny_permissions`)+ 数据范围选择器(从 registry modules 的 data_scopes 取选项,写入 `deny_data_scopes`)。deny 区用警示色底(如 `bg-amber-50` / `border-amber-300`)。
- `toEngineGrants`:`{permissions, deny_permissions, deny_data_scopes}`;`toGrantArray` 反向。
- `PolicyRow`:展示"拒绝权限: …" / "拒绝范围: …"。
- 删 `page.tsx:1086` grant 上 `data_scope` 残留展示。
- 空条件展示"（全局·所有非超管用户）"。

- [ ] **Step 2: typecheck** — `cd frontend && pnpm typecheck` → 0 error

- [ ] **Step 3: 人工验证** — 启前端,策略编辑器能存含 deny_permissions/deny_data_scopes 的策略(后端 Task 9 校验生效)。

- [ ] **Step 4: Commit** — `git commit -am "feat(roles-ui): policy editor deny (permissions + data scopes) section; drop grant.data_scope"`

---

## Phase 8 — 集成测试 + 回归

### Task 15: 端到端集成测试

**Files:** `backend/tests/test_policy_enforcement.py`

- [ ] **Step 1: 写测试**

```python
@pytest.mark.asyncio
async def test_permission_deny_blocks_endpoint(test_client, db_with_policy):
    # 插 Policy{conditions:{attr:user_id,op:eq,value:Y}, grants:{deny_permissions:["kb:read"]}}
    # 以 Y 调需 kb:read 的端点 → 403;以 Z → 200

@pytest.mark.asyncio
async def test_me_includes_policy_grants_and_respects_deny(test_client, ...):
    # /me:Y 不含 kb:read(被 deny),Z 含(被 grant)
    # 超管 /me 全集 + 接口 200

@pytest.mark.asyncio
async def test_data_deny_on_knowledge(test_client, ...):
    # Policy{deny_data_scopes:["knowledge_public"]} → 非 public 角色查 KB list 时 public KB 被排除
```

- [ ] **Step 2: 跑** — `cd backend && PYTHONPATH=. uv run pytest tests/test_policy_enforcement.py tests/test_knowledge_data_access.py tests/test_project_idor.py -v` → 全绿

- [ ] **Step 3: 全量回归** — `cd backend && make test` → 全绿;`cd backend && make lint` → 通过

- [ ] **Step 4: Commit** — `git commit -am "test(rbac): policy enforcement + /me consistency + data deny integration tests"`

### Task 16: 上线前 behavior-flip 核对(人工)

- [ ] **Step 1: diff 现有角色 data_scopes 绑定 vs 新 yaml**(脚本或人工):确认修好的 `knowledge_dept` 不会让某个角色意外多看/少看库。重点:dept_head/project_manager 现在会新看到 dept 共享库(正确收敛,需预告业务方)。
- [ ] **Step 2: 核对前端是否依赖 by-id 的 403**(知识库 by-id 现统一 404)。grep 前端 `.status === 403` 在 KB 相关调用。
- [ ] **Step 3: 记录核对结果到 `.wolf/memory.md`。**

---

## Self-Review

**Spec coverage:**
- §4.2 overlap/not 算子 → Task 1,2 ✓
- §4.3 知识库 scope 重写 + column_map → Task 10 ✓;by-id 统一 → Task 11 ✓
- §4.4 项目 IDOR 闭合 → Task 12 ✓(list scope 统一列为 follow-up,见风险)
- §4.5 docmgr scope → Task 13 ✓
- §4.6 by-id 统一原则 → Task 11(knowledge)✓;docmgr Task 13 ✓;project list 统一 deferred
- §4.7 数据 deny → Task 4,5 ✓
- §4.8 权限点 deny + /me → Task 6,7,8 ✓
- §4.9 超管双豁免 → Task 5(with_data_scope)+ Task 6(check)✓
- §4.10 with_data_scope 改造 → Task 5 ✓
- §4.11 前端/priority/空条件/审计 → Task 14(前端)+ Task 8(审计)✓;priority 文档化(无需任务)
- §3 缺陷 1/2/3 → Task 10/11 ✓

**Placeholder scan:** Task 5/8/15 的集成测试用了 `...`/`fixture` 占位——这些是测试 fixture 依赖具体 test_db 搭建模式,需实现者按仓库现有 `conftest.py` 的 async db fixture 填(参考 `test_role_calibration.py` 的 `conn` fixture 模式)。已标注参考位置,非空泛 TBD。

**Type consistency:** `build_scope_union`、`evaluate_policy_conditions`、`load_active_policies`、`_load_kb_scoped`、`require_project_member`、`_validate_grants` 命名一致;`FilterRule` 新算子 `overlap`/`not` 在 from_template 与 to_sqlalchemy 两侧对齐。

**风险(实现者注意):**
- 项目 list 统一到 `with_data_scope("projects")` 本计划**未强制**(Task 12 只闭合 IDOR + 补 scope 声明)。若要彻底统一,需把 `service.list_projects` 的 `created_by OR member` 改用 scope FilterRule + 保留 `archived_at IS NULL` 基础条件——列为可选后续。
- `overlap` 的 UUID 类型对齐:`identity.dept_ids` 是 str 列表,Task 1 已做 `uuid.UUID(x)` 强制;实现时用真实 PG ARRAY 跑一遍集成测试确认 `&&` 生成正确。
- by-id 统一为 404:Task 16 已列前端 403 依赖核对。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-04-data-access-control-unification.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个 fresh subagent,任务间两阶段 review,迭代快、上下文干净。

**2. Inline Execution** — 本会话内用 executing-plans 批量执行,带 checkpoint 复审。

Which approach?

---

## Known Limitations (from final holistic review — 2026-08-05)

The final review found **zero Critical** issues. These three "Important" items are **deferrals explicitly made during planning or by-design separations**, recorded here so they're not lost:

- **L1 — project list/by-id not yet on `with_data_scope`** (`project/routers.py:47-96`, `service.py:147-172`): project visibility still uses the hand-rolled `created_by OR ProjectMember` filter, which is **equivalent** for base visibility but means `deny_data_scopes` does NOT narrow project list/by-id. The plan deliberately deferred this ("统一到 with_data_scope('projects') 列为后续优化,优先级低于 IDOR 修复"). **Follow-up:** wire `with_data_scope("projects")` into list + `get_project` when project-level data-deny is needed.

- **L2 — docmgr by-id not yet on the scope engine** (`docmgr/service.py` `get_by_id`): list is wired (Task 13), by-id still uses the hand-rolled owner/member clause. by-id still enforces base visibility (no IDOR), but `deny_data_scopes` won't narrow a by-id fetch. Task 13 deferred this ("deny on by-id is a future refinement"). Only matters once a docmgr `deny_data_scopes` policy exists (none today). **Follow-up:** thread scope into `get_by_id` mirroring `_load_kb_scoped`.

- **L3 — `require_resource_permission` base gate checks `system:access` against role perms only** (`unified_permissions.py:214-221`): it does not route through `UnifiedPermissionEngine`, so a policy that *denies* `system:access` wouldn't be honored at the 5 project-mutation endpoints. By design, project-role *actions* (chapter:write_any etc.) are evaluated via `project_roles`, separate from the ABAC engine (spec §4.1/§2). The gap is narrow (policy-denied `system:access` is an unusual case; the action check still applies). **Follow-up:** route the `system:access` base check through `engine.check` if global system:access deny policies become a real need.

**Minor follow-ups:** M1 `user` role lacks `knowledge_owner` (can't see own private KB — pre-existing); M2 redundant `is_superadmin` branch in knowledge list (`with_data_scope` already bypasses superadmin); M3 defensive try/except around overlap UUID coercion; M4 validate `deny_permissions` ids against registry (like deny_data_scopes); M5 add an end-to-end visibility-matrix test for knowledge; M6 project `get_project` returns 403 to non-members (existence leak — pre-existing).

**Net:** branch is ship-ready for the in-scope goals (deny engine, /me fix, knowledge dept-sharing + by-id unification, project IDOR closures, docmgr scope declaration). L1–L3 are documented scope edges, not regressions.
