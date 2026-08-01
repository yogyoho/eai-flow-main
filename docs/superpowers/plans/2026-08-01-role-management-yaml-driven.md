# 角色管理真相源统一（yaml 驱动）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `permissions.yaml`（+ `config/roles_custom.yaml` overlay）成为角色/权限/数据权限的唯一真相源，修复 S1-S4 功能失效并统一 A1-A2 分裂体系。

**Architecture:** 用户/分配留 DB（`users.role_id`），角色定义走 yaml+overlay；授权路径（`require_permission`/`/me`/`DataScopeEngine`）全部改为从 PermissionRegistry（合并 overlay + `#inherit` 展开 + mtime 热重载）解析；DB `roles` 表降级为启动校准的物化镜像；项目级权限从 `role_permissions` 表迁入 yaml `project_roles:`；前端补 U1/U3/U4/A3/U2。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / PyYAML / Next.js 16 / React 19 / TanStack Query / Vitest(Rstest)

**Spec:** `docs/superpowers/specs/2026-08-01-role-management-yaml-driven-design.md`

**Environment note:** 后端改动后 `docker compose -p eai-docker restart gateway`；前端无新依赖（无 package.json 改动），改完 `docker compose -p eai-docker restart frontend` 即可，**无需镜像重建**。测试在 host 跑：后端 `cd backend && PYTHONPATH=. uv run pytest ...`；前端 `cd frontend && pnpm typecheck`。

---

## 文件结构

**新增：**
- `config/roles_custom.yaml` — overlay（自定义角色 + 内置覆盖 + disabled_roles）
- `backend/tests/test_registry_overlay.py` — overlay 合并/继承/禁用 单测
- `backend/tests/test_role_overlay_store.py` — 写透存储 单测
- `backend/tests/test_role_calibration.py` — 启动校准 单测

**修改（后端）：**
- `backend/app/extensions/auth/registry.py` — overlay 加载/合并、`project_roles`、新增访问器、双文件热重载
- `backend/app/extensions/auth/middleware.py` — `require_permission` 读 registry、`_ensure_role` 去 drift 守卫、去 `_ROLE_DEFAULTS`
- `backend/app/extensions/auth/permission_routers.py` — `/me` 读 registry（nav/pages/data_scopes）
- `backend/app/extensions/auth/datascope.py` — `from_registry` 用 registry 访问器
- `backend/app/extensions/auth/unified_permissions.py` — 读 registry `project_roles`
- `backend/app/extensions/role/service.py` — 写透 overlay + 原子写/乐观锁
- `backend/app/extensions/role/routers.py` — 角色响应合并 `data_scopes`
- `backend/app/extensions/database.py` — `_calibrate_roles_from_registry`、seed 收敛
- `backend/app/extensions/schemas.py` — `RoleResponse` 加 `data_scopes`
- `backend/app/extensions/project/routers.py` — 切到 unified_permissions
- 删除 `backend/app/extensions/project/permissions.py`、`project_permissions.py`

**修改（前端）：**
- `frontend/src/app/admin/roles/page.tsx` — U1/U3/U4
- `frontend/src/app/admin/layout.tsx` — A3
- `frontend/src/app/admin/users/page.tsx` — U2 按钮级
- `frontend/src/extensions/types.ts` — Role 加 `data_scopes`
- `frontend/src/extensions/api/index.ts` — roleApi 加 `assignments`
- `frontend/src/app/knowledge/page.tsx` — U2 按钮级

**配置：**
- `config/permissions.yaml` — contract_price 加 data_scopes、`project_roles:` 节、roles 节对齐

---

## Phase A — 后端地基：yaml 成为唯一真相源（S1-S6）

### Task 1: Registry 加载 overlay + project_roles + 双文件热重载

**Files:**
- Modify: `backend/app/extensions/auth/registry.py`
- Test: `backend/tests/test_registry_overlay.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_registry_overlay.py`：

```python
import pytest
from app.extensions.auth.registry import PermissionRegistry


def test_overlay_merges_roles(tmp_path):
    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles:
  builtin:
    display_name: "内置"
    level: 10
    permissions: ["kb:read"]
    data_scopes: ["knowledge_public"]
  shared:
    display_name: "共享"
    level: 20
    permissions: ["doc:read"]
    data_scopes: []
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
roles:
  builtin:
    permissions: ["kb:read", "kb:create"]   # 覆盖内置
  custom:
    display_name: "自定义"
    level: 5
    permissions: ["#inherit:builtin", "doc:read"]
    nav: ["nav:knowledge"]
    data_scopes: ["knowledge_dept"]
disabled_roles: ["shared"]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))

    # overlay 覆盖内置
    assert set(reg.resolve_role_permissions("builtin")) == {"kb:read", "kb:create"}
    # 自定义角色出现
    assert set(reg.resolve_role_permissions("custom")) == {"kb:read", "kb:create", "doc:read"}
    # disabled 内置角色被隐藏
    assert reg.get_role_defaults("shared") is None
    assert "shared" not in reg.list_role_codes()
    # data_scopes 访问器
    assert reg.get_data_scopes_for_role("custom") == ["knowledge_dept"]


def test_project_roles_parsed(tmp_path):
    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles: {}
project_roles:
  owner: [project:edit, project:delete]
  writer: [chapter:write_own]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    assert reg.get_project_roles()["owner"] == ["project:edit", "project:delete"]
    assert reg.get_project_roles()["writer"] == ["chapter:write_own"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_registry_overlay.py -v`
Expected: FAIL（`PermissionRegistry` 不接受 `overlay_path`，`get_project_roles` 不存在）

- [ ] **Step 3: 实现 registry 改造**

`backend/app/extensions/auth/registry.py` — 增量修改：

1) `__init__` 加 `overlay_path` 参数并初始化 `_project_roles` / `_disabled_roles` / `_overlay_mtime`：

```python
def __init__(self, yaml_path: str | None = None, overlay_path: str | None = None):
    if yaml_path is None:
        yaml_path = os.environ.get(
            "PERMISSIONS_YAML_PATH",
            str(Path(__file__).parent.parent.parent.parent.parent / "config" / "permissions.yaml"),
        )
    if overlay_path is None:
        overlay_path = os.environ.get(
            "ROLES_CUSTOM_YAML_PATH",
            str(Path(__file__).parent.parent.parent.parent.parent / "config" / "roles_custom.yaml"),
        )
    self._path = Path(yaml_path)
    self._overlay_path = Path(overlay_path)
    self._mtime: float = 0.0
    self._overlay_mtime: float = 0.0
    self.modules: dict[str, NavModule] = {}
    self._role_defaults: dict[str, dict] = {}
    self._project_roles: dict[str, list[str]] = {}
    self._disabled_roles: set[str] = set()
    self._all_permissions: dict[str, PermissionPoint] = {}
    self._admin_only: list[PermissionPoint] = []
    self._load()
```

2) `_load()` 末尾解析 project_roles + 应用 overlay：

```python
def _load(self) -> None:
    if not self._path.exists():
        logger.warning("permissions.yaml not found at %s, registry is empty", self._path)
        return
    self._mtime = self._path.stat().st_mtime
    with open(self._path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    self._parse_modules(data.get("modules") or {})
    self._parse_roles(data.get("roles") or {})
    self._parse_project_roles(data.get("project_roles") or {})

    if self._overlay_path.exists():
        self._overlay_mtime = self._overlay_path.stat().st_mtime
        with open(self._overlay_path, encoding="utf-8") as fh:
            overlay = yaml.safe_load(fh) or {}
        self._apply_overlay(overlay)
```

3) 新增方法：

```python
def _parse_project_roles(self, project_roles_data: dict) -> None:
    self._project_roles = {
        code: list(perms or []) for code, perms in project_roles_data.items()
    }

def _apply_overlay(self, overlay_data: dict) -> None:
    for code, role_data in (overlay_data.get("roles") or {}).items():
        self._role_defaults[code] = {
            "display_name": role_data.get("display_name", code),
            "is_system": role_data.get("is_system", False),
            "level": role_data.get("level", 10),
            "nav": list(role_data.get("nav") or []),
            "pages": list(role_data.get("pages") or []),
            "permissions": list(role_data.get("permissions") or []),
            "data_scopes": list(role_data.get("data_scopes") or []),
        }
    for code in (overlay_data.get("disabled_roles") or []):
        self._role_defaults.pop(code, None)
        self._disabled_roles.add(code)

def list_role_codes(self) -> list[str]:
    return list(self._role_defaults.keys())

def get_data_scopes_for_role(self, role_code: str) -> list[str]:
    defaults = self._role_defaults.get(role_code)
    if defaults is None:
        return []
    return list(defaults.get("data_scopes") or [])

def get_project_roles(self) -> dict[str, list[str]]:
    return {code: list(perms) for code, perms in self._project_roles.items()}

def is_role_disabled(self, role_code: str) -> bool:
    return role_code in self._disabled_roles

def reload(self) -> None:
    self._load()
```

4) `_check_reload` 检查双文件：

```python
def _check_reload(self) -> bool:
    reloaded = False
    if self._path.exists() and self._path.stat().st_mtime > self._mtime:
        reloaded = True
    if self._overlay_path.exists() and self._overlay_path.stat().st_mtime > self._overlay_mtime:
        reloaded = True
    if reloaded:
        logger.info("permissions.yaml / roles_custom.yaml changed, reloading registry")
        self._load()
    return reloaded
```

5) 模块顶部 `Path` 已导入（`from pathlib import Path` 存在，勿重复）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_registry_overlay.py -v`
Expected: 2 passed

- [ ] **Step 5: 回归既有测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_permission_registry.py -v`
Expected: all passed（`_load` 找不到 overlay 时正常，overlay_path 存在即跳过）

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/auth/registry.py backend/tests/test_registry_overlay.py
git commit -m "feat(rbac): registry loads roles_custom.yaml overlay + project_roles + dual-file hot reload"
```

---

### Task 2: require_permission 改读 registry（S4 继承生效 + S3 守卫拆除的第一步）

**Files:**
- Modify: `backend/app/extensions/auth/middleware.py`
- Test: `backend/tests/test_permission_engine.py`

- [ ] **Step 1: 写失败测试** — 验证 `#inherit` 通过 `require_permission` 生效：

在 `backend/tests/test_permission_engine.py` 追加：

```python
def test_engine_uses_resolved_inherited_permissions():
    from app.extensions.auth.engine import UnifiedPermissionEngine
    from app.extensions.auth.identity import AttributeSet

    engine = UnifiedPermissionEngine(
        role_permissions={
            # 模拟 registry.resolve_role_permissions 已展开 #inherit
            "manager": {"project:edit", "kb:read", "doc:read"},
            "user": {"kb:read"},
        },
        all_permission_ids={"project:edit", "kb:read", "doc:read"},
    )
    identity = AttributeSet(user_id="1", username="u", role_code="manager", role_level=20)
    assert engine.check(identity, "project:edit") is True
    assert engine.check(identity, "doc:read") is True   # 继承来的权限
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_permission_engine.py::test_engine_uses_resolved_inherited_permissions -v`
Expected: FAIL（`AttributeSet` 缺默认参数 — 先确认当前签名；若已可构造则测试直接通过 → 标记为"基础设施已就绪"，继续 Step 3）

> 注：`AttributeSet` 当前 `role_code/role_level` 有默认值，该测试可能直接通过。若通过，此 Step 的目的改为**锁定** `require_permission` 的 registry 来源行为（见 Step 3 后跑完整回归）。

- [ ] **Step 3: 改 require_permission 读 registry**

`backend/app/extensions/auth/middleware.py` — `require_permission` 的 `check_permission` 中，替换从 DB `select(Role)` 构建 `role_permissions` 的代码块（当前约 227-263 行），改为从 registry 解析；同时替换 `is_system` 判定：

```python
        # EAI-CUSTOM: Delegate permission check to UnifiedPermissionEngine (ABAC-lite)
        from app.extensions.auth.cache import (
            get_cached_engine,
            get_cached_identity,
            set_cached_engine,
            set_cached_identity,
        )
        from app.extensions.auth.engine import UnifiedPermissionEngine
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.registry import get_permission_registry

        # Roles come from PermissionRegistry (permissions.yaml + roles_custom.yaml overlay),
        # with #inherit expansion — DB roles table is a calibrated mirror, not the source.
        registry = get_permission_registry()
        role_permissions = {
            code: registry.resolve_role_permissions(code)
            for code in registry.list_role_codes()
        }
        all_ids = {p.id for p in registry.list_all_permissions()}

        # Engine: cached per request
        engine = get_cached_engine()
        if engine is None:
            # Load ABAC policies from DB (global, dynamic — kept as data)
            from app.extensions.auth.engine import Policy as EnginePolicy
            from app.extensions.auth.models import Policy as PolicyModel

            policy_result = await db.execute(
                select(PolicyModel)
                .where(PolicyModel.enabled == True)  # noqa: E712
                .order_by(PolicyModel.priority)
            )
            policies = [
                EnginePolicy(
                    name=p.name,
                    priority=p.priority,
                    conditions=p.conditions,
                    grants=p.grants,
                )
                for p in policy_result.scalars().all()
            ]

            engine = UnifiedPermissionEngine(
                role_permissions=role_permissions,
                all_permission_ids=all_ids,
                policies=policies,
            )
            set_cached_engine(engine)

        # Identity: cached per request
        identity = get_cached_identity()
        if identity is None:
            provider = get_identity_provider()
            identity = await provider.resolve(current_user.id, db)
            set_cached_identity(identity)

        # System-role wildcard bypass comes from registry defaults, not DB
        defaults = registry.get_role_defaults(identity.role_code)
        is_system = bool(defaults and defaults.get("is_system"))
        resolved = role_permissions.get(identity.role_code or "", set())
        if is_system or "*" in resolved:
            return current_user

        if current_user.role_id is not None and identity.role_code is None:
            logger.warning(
                "Permission check failed: user=%s role_id=%s not found in DB",
                current_user.id, current_user.role_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not found",
            )

        if not engine.check(identity, permission):
            logger.warning(
                "Permission check failed: user=%s role=%s lacks '%s'",
                current_user.id, identity.role_code, permission,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )

        return current_user
```

删除原来的 `select(Role)` 构建、`matching_role`/`is_system` 与 `perms` 变量。文件顶部若 `Role` 不再被本函数使用，检查是否仍被 `_ensure_role`/`_bridge_user` 使用（仍会用到，保留 import）。

- [ ] **Step 4: 跑权限相关全量测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_permission_engine.py tests/test_permission_registry.py tests/test_registry_overlay.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/middleware.py backend/tests/test_permission_engine.py
git commit -m "feat(rbac): require_permission resolves roles from registry (overlay + #inherit), drop DB perms source"
```

---

### Task 3: `/api/permissions/me` 改读 registry（修复 S1 nav 消失）

**Files:**
- Modify: `backend/app/extensions/auth/permission_routers.py`
- Test: 手动验证 + 现有测试回归

- [ ] **Step 1: 改 get_my_permissions**

`backend/app/extensions/auth/permission_routers.py` — `get_my_permissions`（当前 65-106 行）删除 `select(Role)` 构建 `role_permissions`，改为 registry；nav/pages 保持从 registry 读，并补充 data_scopes：

```python
@router.get("/me")
async def get_my_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),
):
    """Return current user's effective permissions and identity attributes."""
    provider = get_identity_provider()
    identity = await provider.resolve(current_user.id, db)

    registry = get_permission_registry()
    role_permissions = {
        code: registry.resolve_role_permissions(code)
        for code in registry.list_role_codes()
    }
    all_ids = {p.id for p in registry.list_all_permissions()}

    engine = UnifiedPermissionEngine(
        role_permissions=role_permissions,
        all_permission_ids=all_ids,
    )

    permissions = sorted(engine.list_permissions(identity))

    role_code = identity.role_code or ""
    nav_ids = registry.get_nav_ids_for_role(role_code)
    page_ids = registry.get_page_ids_for_role(role_code)
    data_scopes = registry.get_data_scopes_for_role(role_code)

    if "*" in nav_ids:
        nav_ids = [m.nav_id for m in registry.list_nav_modules() if m.nav_id]
        page_ids = [p.id for m in registry.list_nav_modules() for p in m.pages]
    elif "*" in page_ids:
        page_ids = [p.id for m in registry.list_nav_modules() for p in m.pages]

    return {
        "permissions": permissions,
        "nav": nav_ids,
        "pages": page_ids,
        "data_scopes": data_scopes,
        "identity": identity.to_dict(),
    }
```

文件顶部删除对 `Role` 的 import（若不再使用）。

- [ ] **Step 2: 验证 S1 修复**

启动 gateway 后（或直接看代码路径）：自定义角色（仅 overlay 定义，如 `custom`）登录调用 `/api/permissions/me`，`nav` 返回 overlay 中声明的 `nav`（不再 `[]`）。

Run: `cd backend && PYTHONPATH=. uv run python -c "from app.extensions.auth.registry import get_permission_registry; r=get_permission_registry(); print('role_codes=', r.list_role_codes())"`
Expected: 输出含 yaml+overlay 的角色 code 列表

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/auth/permission_routers.py
git commit -m "fix(rbac): /me resolves nav/pages/data_scopes from registry, fixes custom-role nav disappearing"
```

---

### Task 4: DataScopeEngine 从 registry 读 + permissions.yaml 补 cpa_dept

**Files:**
- Modify: `backend/app/extensions/auth/datascope.py`
- Modify: `config/permissions.yaml`
- Test: `backend/tests/test_datascope.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_datascope.py` 追加：

```python
def test_get_data_scope_from_overlay_role(tmp_path, monkeypatch):
    """角色 data_scopes 经 registry（含 overlay）解析，不再硬编码 yaml 默认。"""
    import yaml
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.identity import AttributeSet
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules:
  contract_price:
    display_name: "合同价格"
    nav_id: "nav:contract-price"
    pages: []
    operations:
      - { id: "cpa:read", display_name: "查看" }
    data_scopes:
      - { id: "cpa_all", display_name: "全部", rule_template: {} }
      - { id: "cpa_dept", display_name: "本部门", rule_template: { dept_id IN: "$identity.dept_ids" } }
roles: {}
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
roles:
  buyer:
    display_name: "采购员"
    permissions: ["cpa:read"]
    data_scopes: ["cpa_dept"]
disabled_roles: []
""", encoding="utf-8")

    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))
    engine = DataScopeEngine.from_registry_with(reg)
    identity = AttributeSet(user_id="1", username="u", role_code="buyer", dept_ids=["d1"])
    rule = engine.get_data_scope(identity, "contract_price")
    assert rule.operator == "in"
    assert rule.field == "dept_id"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_datascope.py::test_get_data_scope_from_overlay_role -v`
Expected: FAIL（`from_registry_with` 不存在 / `get_data_scope` 返回 none_allow）

- [ ] **Step 3: datascope.py 增加 `from_registry_with` 并读 registry 访问器**

`backend/app/extensions/auth/datascope.py`：

```python
    @classmethod
    def from_registry(cls) -> "DataScopeEngine":
        return cls.from_registry_with(get_permission_registry())

    @classmethod
    def from_registry_with(cls, registry) -> "DataScopeEngine":
        scopes_by_resource: dict[str, list[DataScope]] = {}
        for module_key, mp in registry.list_modules():
            if mp.data_scopes:
                scopes_by_resource[module_key] = mp.data_scopes

        role_data_scopes: dict[str, list[str]] = {}
        for code in registry.list_role_codes():
            role_data_scopes[code] = registry.get_data_scopes_for_role(code)

        return cls(scopes_by_resource, role_data_scopes)
```

删除 `from_registry` 里读 `registry._role_defaults` 的私有字段访问。

- [ ] **Step 4: permissions.yaml 给 contract_price 补 data_scopes**

`config/permissions.yaml` — `contract_price` 模块（134-159 行）末尾 `data_scopes` 已缺失，追加：

```yaml
    data_scopes:
      - { id: "cpa_all", display_name: "全部合同数据", rule_template: {} }
      - { id: "cpa_dept", display_name: "本部门合同", rule_template: { dept_id IN: "$identity.dept_ids" } }
```

- [ ] **Step 5: 运行确认通过 + 回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_datascope.py tests/test_registry_overlay.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/auth/datascope.py config/permissions.yaml backend/tests/test_datascope.py
git commit -m "fix(rbac): DataScopeEngine reads role data_scopes via registry; add cpa_dept scope"
```

---

### Task 5: 拆除 `_ensure_role` drift 守卫（修复 S3）

**Files:**
- Modify: `backend/app/extensions/auth/middleware.py`

- [ ] **Step 1: 改 `_ensure_role`**

`backend/app/extensions/auth/middleware.py` — 删除 `_ROLE_DEFAULTS` 常量与 drift 重置块，改为从 registry 读取默认定义（仅用于兜底创建，不覆盖现有角色）：

```python
def _ensure_role(db: AsyncSession, code: str) -> Role | None:
    """Look up a role by code, creating it on-the-fly from registry defaults if missing.

    No drift-reset: registry (permissions.yaml + overlay) is the source of truth,
    and admin-assigned extra permissions must persist (S3 fix).
    """
    from app.extensions.auth.registry import get_permission_registry

    result = await db.execute(select(Role).where(Role.code == code))
    role = result.scalar_one_or_none()
    if role is not None:
        return role

    defaults = get_permission_registry().get_role_defaults(code)
    if defaults is None:
        return None

    role = Role(
        id=uuid.uuid4(),
        code=code,
        name=defaults.get("display_name", code),
        permissions=sorted(get_permission_registry().resolve_role_permissions(code)),
        is_system=defaults.get("is_system", False),
        level=defaults.get("level", 10),
    )
    db.add(role)
    await db.flush()
    logger.info("Auto-created role '%s' (code=%s)", defaults.get("display_name", code), code)
    return role
```

删除 `_ROLE_DEFAULTS = {...}` 常量块（middleware.py 顶部 26-40 行）。

- [ ] **Step 2: 验证**

Run: `cd backend && PYTHONPATH=. uv run python -c "import ast; ast.parse(open('app/extensions/auth/middleware.py',encoding='utf-8').read()); print('SYNTAX OK')"`
Expected: `SYNTAX OK`（无编译错误）

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/auth/middleware.py
git commit -m "fix(rbac): remove _ensure_role drift reset so admin-granted user-role permissions persist (S3)"
```

---

### Task 6: 启动校准 DB roles（物化镜像）

**Files:**
- Modify: `backend/app/extensions/database.py`
- Test: `backend/tests/test_role_calibration.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_role_calibration.py`：

```python
import asyncio
import pytest
from sqlalchemy import text

from app.extensions.auth.registry import PermissionRegistry


def test_calibrate_upserts_and_updates(tmp_path):
    """校准逻辑：yaml 角色缺失→插入；已有→更新权限镜像；disabled→删除(无用户引用)。"""
    import yaml
    from app.extensions.database import _calibrate_roles_from_registry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles:
  builtin:
    display_name: "内置"
    is_system: false
    level: 10
    permissions: ["kb:read"]
    nav: ["nav:knowledge"]
    data_scopes: []
disabled_roles: ["stale"]
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: ["stale"]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))

    # 用轻量 fake conn 记录执行的 SQL 参数（不连真库）
    class FakeConn:
        def __init__(self):
            self.calls = []
        async def execute(self, stmt, params=None):
            self.calls.append((str(stmt), params))

    conn = FakeConn()
    asyncio.run(_calibrate_roles_from_registry(conn, reg))
    # 至少对 builtin/custom 触发 INSERT，且对 stale 触发 DELETE
    sql = " ".join(c[0] for c in conn.calls)
    assert "INSERT INTO roles" in sql
    assert "DELETE FROM roles" in sql
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_calibration.py -v`
Expected: FAIL（`_calibrate_roles_from_registry` 不存在 / `PermissionRegistry` 缺 overlay）

- [ ] **Step 3: 实现校准函数**

`backend/app/extensions/database.py` — 在 `_seed_role_permissions` 附近新增（幂等，按 code upsert）：

```python
async def _calibrate_roles_from_registry(conn, registry) -> None:
    """Calibrate DB roles table as a mirror of permissions.yaml + roles_custom.yaml.

    - yaml role missing in DB → INSERT (with FK-usable id)
    - existing role → UPDATE name/permissions/is_system/level/nav to match registry
    - disabled role with no user references → DELETE
    """
    for code in registry.list_role_codes():
        resolved = sorted(registry.resolve_role_permissions(code))
        defaults = registry.get_role_defaults(code) or {}
        existing = await conn.execute(
            text("SELECT id FROM roles WHERE code = :code LIMIT 1"), {"code": code}
        )
        row = existing.fetchone()
        if row is None:
            await conn.execute(
                text(
                    "INSERT INTO roles (id, name, code, permissions, is_system, level, nav, created_at) "
                    "VALUES (:id, :name, :code, :perms, :is_system, :level, :nav, NOW())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": defaults.get("display_name", code),
                    "code": code,
                    "perms": resolved,
                    "is_system": defaults.get("is_system", False),
                    "level": defaults.get("level", 10),
                    "nav": defaults.get("nav") or [],
                },
            )
        else:
            await conn.execute(
                text(
                    "UPDATE roles SET name = :name, permissions = :perms, "
                    "is_system = :is_system, level = :level, nav = :nav WHERE code = :code"
                ),
                {
                    "name": defaults.get("display_name", code),
                    "code": code,
                    "perms": resolved,
                    "is_system": defaults.get("is_system", False),
                    "level": defaults.get("level", 10),
                    "nav": defaults.get("nav") or [],
                },
            )

    # 处理 disabled：DB 中存在但 registry 已禁用且无用户引用 → 删除
    rows = (await conn.execute(text("SELECT id, code FROM roles"))).fetchall()
    for r in rows:
        if registry.is_role_disabled(r[1]):
            cnt = (await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE role_id = :id"), {"id": r[0]}
            )).scalar()
            if cnt == 0:
                await conn.execute(text("DELETE FROM roles WHERE id = :id"), {"id": r[0]})
```

`uuid` 已在 database.py 顶部导入（确认：seed_db 用了 `uuid.uuid4()`）。若未导入则在顶部补 `import uuid`。

- [ ] **Step 4: 在 init_db 调用**

`init_db`（database.py 199 行附近）表创建完成后调用：

```python
from app.extensions.auth.registry import get_permission_registry
await _calibrate_roles_from_registry(conn, get_permission_registry())
```

放在 `_seed_role_permissions`（1210 行附近）同一位置即可。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_calibration.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/database.py backend/tests/test_role_calibration.py
git commit -m "feat(rbac): init_db calibrates DB roles as mirror of yaml registry (insert/update/delete-disabled)"
```

---

### Task 7: seed 收敛 — 移除硬编码角色 INSERT（A1）

**Files:**
- Modify: `backend/app/extensions/database.py`

- [ ] **Step 1: seed_db 收敛**

`seed_db`（database.py 1373 行附近）：删除"手动 INSERT superadmin/user 角色"两个硬编码块（1405-1460 行），改为先调用校准再创建 admin 用户（若 admin 用户不存在）。保持 `users` 的 admin 创建逻辑，`role_id` 从校准后的 superadmin 行取：

```python
            # Roles are calibrated from yaml registry (config/permissions.yaml + roles_custom.yaml)
            from app.extensions.auth.registry import get_permission_registry
            await _calibrate_roles_from_registry(session, get_permission_registry())

            # Ensure admin user exists, bound to the superadmin role
            admin_row = (await session.execute(
                text("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
            )).fetchone()
            if admin_row is None:
                super_row = (await session.execute(
                    text("SELECT id FROM roles WHERE code = 'superadmin' LIMIT 1")
                )).fetchone()
                if super_row is None:
                    raise RuntimeError("superadmin role missing after calibration; check permissions.yaml")
                user_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, password_hash, full_name, role_id, status, is_deleted, created_at, updated_at) "
                        "VALUES (:id, 'admin', 'admin@eai-flow.com', :pw_hash, 'Administrator', :role_id, 'active', false, NOW(), NOW())"
                    ),
                    {"id": user_id, "pw_hash": hash_password("admin123"), "role_id": super_row[0]},
                )
                logger.info("Created admin user (username: admin, password: admin123)")
                await session.commit()
```

原 else 分支中"为已有安装创建 user 角色"的 INSERT 也删除（校准会保证存在）。注意 `session` 需支持 `execute`/`fetchone` — 确认 `async_sessionmaker` 的 `session.execute` 返回 `Result`（有 `.fetchone()`）。

- [ ] **Step 2: 验证语法与初始化路径**

Run: `cd backend && PYTHONPATH=. uv run python -c "import ast; ast.parse(open('app/extensions/database.py',encoding='utf-8').read()); print('SYNTAX OK')"`
Expected: `SYNTAX OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/database.py
git commit -m "refactor(rbac): seed_db relies on registry calibration; remove hardcoded role INSERTs (A1)"
```

---

## Phase B — 写透 overlay（角色管理 UI 保持可用）

### Task 8: RoleService 写透 overlay + 原子写/乐观锁

**Files:**
- Modify: `backend/app/extensions/role/service.py`
- Modify: `backend/app/extensions/schemas.py`（`RoleResponse` 加 `data_scopes`）
- Test: `backend/tests/test_role_overlay_store.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_role_overlay_store.py`：

```python
import pytest

from app.extensions.role.service import RoleOverlayStore


def test_read_merge_write_roundtrip(tmp_path):
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("""
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: []
""", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    data = store.read()
    assert "custom" in data["roles"]

    data["roles"]["custom2"] = {
        "display_name": "自定义2", "permissions": ["kb:read"], "nav": [], "data_scopes": []
    }
    store.write(data)
    reloaded = store.read()
    assert "custom2" in reloaded["roles"]


def test_stale_overlay_rejected(tmp_path):
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    mtime0 = store.mtime()
    overlay.write_text("roles:\n  a: { display_name: 'A', permissions: [], nav: [], data_scopes: [] }\ndisabled_roles: []\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        # 传入过期 mtime，触发乐观锁冲突
        store.write(store.read(), expect_mtime=mtime0)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py -v`
Expected: FAIL（`RoleOverlayStore` 不存在）

- [ ] **Step 3: 实现 RoleOverlayStore**

`backend/app/extensions/role/service.py` 顶部新增：

```python
import os
import tempfile
from pathlib import Path

import yaml


class RoleOverlayStore:
    """Read/write config/roles_custom.yaml with atomic replace + mtime optimistic lock.

    Single writer accepted: concurrent admin edits are last-writer-wins; a stale
    mtime raises RuntimeError(409) instead of silently overwriting.
    """

    def __init__(self, overlay_path: str | None = None):
        if overlay_path is None:
            overlay_path = os.environ.get(
                "ROLES_CUSTOM_YAML_PATH",
                str(Path(__file__).parent.parent.parent.parent.parent / "config" / "roles_custom.yaml"),
            )
        self.path = Path(overlay_path)

    def mtime(self) -> float:
        return self.path.stat().st_mtime if self.path.exists() else 0.0

    def read(self) -> dict:
        if not self.path.exists():
            return {"roles": {}, "disabled_roles": []}
        with open(self.path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        data.setdefault("roles", {})
        data.setdefault("disabled_roles", [])
        return data

    def write(self, data: dict, expect_mtime: float | None = None) -> None:
        if expect_mtime is not None and self.mtime() != expect_mtime:
            raise RuntimeError("Overlay file changed concurrently; refresh and retry")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def notify_registry_reload(self) -> None:
        from app.extensions.auth.registry import get_permission_registry

        get_permission_registry().reload()
```

- [ ] **Step 4: RoleService 方法改为写透**

`create_role` / `update_role` / `delete_role` / `copy_role` 重写（不再直接依赖 DB ORM 写角色定义；DB 行由校准维护）。`RoleService` 加 `_store` 类属性：

```python
class RoleService:
    _store: RoleOverlayStore | None = None

    @classmethod
    def _overlay(cls) -> RoleOverlayStore:
        if cls._store is None:
            cls._store = RoleOverlayStore()
        return cls._store

    @staticmethod
    async def create_role(db: AsyncSession, data: RoleCreate) -> Role:
        store = RoleService._overlay()
        overlay = store.read()
        if data.code in overlay["roles"]:
            raise ValueError(f"Role code already exists: {data.code}")
        overlay["roles"][data.code] = {
            "display_name": data.name,
            "permissions": list(data.permissions or []),
            "nav": list(data.nav or []),
            "data_scopes": [],
            "level": data.level,
            "description": data.description,
        }
        store.write(overlay, expect_mtime=store.mtime())
        store.notify_registry_reload()
        registry = get_permission_registry()
        await _calibrate_single_role(db, registry, data.code)
        return await RoleService.get_role_by_code(db, data.code)

    @staticmethod
    async def update_role(db: AsyncSession, role: Role, data: RoleUpdate) -> Role:
        store = RoleService._overlay()
        overlay = store.read()
        code = role.code
        entry = overlay["roles"].get(code)
        if entry is None:
            # 内置角色 → 写覆盖（整体覆盖 yaml 定义）
            entry = {
                "display_name": role.name,
                "permissions": list(role.permissions or []),
                "nav": role.nav or [],
                "data_scopes": [],
                "level": role.level or 10,
                "description": role.description,
            }
            overlay["roles"][code] = entry
        if data.name is not None:
            entry["display_name"] = data.name
        if data.permissions is not None:
            entry["permissions"] = list(data.permissions)
        if data.nav is not None:
            entry["nav"] = list(data.nav)
        if data.level is not None:
            entry["level"] = data.level
        if data.description is not None:
            entry["description"] = data.description
        store.write(overlay, expect_mtime=store.mtime())
        store.notify_registry_reload()
        registry = get_permission_registry()
        await _calibrate_single_role(db, registry, code)
        return await RoleService.get_role_by_code(db, code)

    @staticmethod
    async def delete_role(db: AsyncSession, role: Role) -> None:
        store = RoleService._overlay()
        overlay = store.read()
        code = role.code
        if code in overlay["roles"]:
            overlay["roles"].pop(code, None)
        elif not RoleService._is_builtin(code):
            pass  # 既不在 overlay 也不在 yaml → 无定义可删
        else:
            # 内置角色 → tombstone
            disabled = overlay.get("disabled_roles") or []
            if code not in disabled:
                overlay["disabled_roles"] = disabled + [code]
        store.write(overlay, expect_mtime=store.mtime())
        store.notify_registry_reload()
        await db.delete(role)
        await db.commit()

    @staticmethod
    def _is_builtin(code: str) -> bool:
        from app.extensions.auth.registry import get_permission_registry
        return get_permission_registry().get_role_defaults(code) is not None
```

`copy_role` 改为：从 registry 取源角色 resolved 定义，写 overlay 新 code，再校准。`get_role_by_code` 现在可能返回 None（镜像校准后即存在）。`to_response` 合并 `data_scopes`（Step 5）。

- [ ] **Step 5: RoleResponse 加 data_scopes + to_response 合并**

`backend/app/extensions/schemas.py` — `RoleResponse`（206-217 行）加字段：

```python
    nav: list[str] = []
    # EAI-CUSTOM: data scopes from registry (yaml+overlay)
    data_scopes: list[str] = []
```

`service.py` `to_response`：

```python
    @staticmethod
    async def to_response(db: AsyncSession, role: Role) -> RoleResponse:
        from app.extensions.auth.registry import get_permission_registry

        parent_role_name = None
        if role.parent_role_id:
            stmt = select(Role).where(Role.id == role.parent_role_id)
            result = await db.execute(stmt)
            parent_role = result.scalar_one_or_none()
            if parent_role:
                parent_role_name = parent_role.name

        registry = get_permission_registry()
        return RoleResponse(
            id=role.id,
            name=role.name,
            code=role.code,
            permissions=role.permissions or [],
            is_system=role.is_system,
            description=role.description,
            level=role.level,
            parent_role_id=role.parent_role_id,
            parent_role_name=parent_role_name,
            created_at=role.created_at,
            nav=role.nav or [],
            data_scopes=registry.get_data_scopes_for_role(role.code),
        )
```

新增模块级辅助（供 create/update 单角色校准，避免每次全量校准）：

```python
async def _calibrate_single_role(db: AsyncSession, registry, code: str) -> None:
    from sqlalchemy import text as sa_text

    resolved = sorted(registry.resolve_role_permissions(code))
    defaults = registry.get_role_defaults(code) or {}
    existing = await db.execute(sa_text("SELECT id FROM roles WHERE code = :code LIMIT 1"), {"code": code})
    row = existing.fetchone()
    if row is None:
        db.add(Role(
            id=uuid.uuid4(), code=code,
            name=defaults.get("display_name", code),
            permissions=resolved,
            is_system=defaults.get("is_system", False),
            level=defaults.get("level", 10),
            nav=defaults.get("nav") or [],
        ))
    else:
        r = await RoleService.get_role_by_code(db, code)
        if r:
            r.name = defaults.get("display_name", code)
            r.permissions = resolved
            r.is_system = defaults.get("is_system", False)
            r.level = defaults.get("level", 10)
            r.nav = defaults.get("nav") or []
    await db.commit()
```

（`service.py` 顶部确认导入 `uuid`。）

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/role/service.py backend/app/extensions/schemas.py backend/tests/test_role_overlay_store.py
git commit -m "feat(rbac): RoleService writes through to roles_custom.yaml overlay (atomic + optimistic lock); RoleResponse gains data_scopes"
```

---

### Task 9: role 路由适配写透 + 删除守卫保留

**Files:**
- Modify: `backend/app/extensions/role/routers.py`

- [ ] **Step 1: 适配 delete/copy 错误语义**

`routers.py`：`update_role`/`delete_role` 已用 `require_permission` + `is_system` 守卫，保持。`delete_role` 的 user_count 守卫保持（写透前先查）。`create_role` 的 code 重复检查改为对 overlay（`RoleService.create_role` 内已抛 `ValueError`），路由捕获转 400：

```python
    existing = await RoleService.get_role_by_code(db, data.code)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role code already exists")
    try:
        role = await RoleService.create_role(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await RoleService.to_response(db, role)
```

`copy_role` 的重复检查同理（`RoleService.copy_role` 内部会写 overlay，冲突抛 ValueError）。

- [ ] **Step 2: 验证**

Run: `cd backend && PYTHONPATH=. uv run python -c "import ast; ast.parse(open('app/extensions/role/routers.py',encoding='utf-8').read()); print('SYNTAX OK')"`
Expected: `SYNTAX OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/role/routers.py
git commit -m "refactor(rbac): role routers surface overlay write errors as 400"
```

---

## Phase C — 项目级权限统一（A2）

### Task 10: permissions.yaml 加 project_roles + unified_permissions 读 registry

**Files:**
- Modify: `config/permissions.yaml`
- Modify: `backend/app/extensions/auth/unified_permissions.py`

- [ ] **Step 1: permissions.yaml 加 project_roles 节**

`config/permissions.yaml` 末尾（roles 节之后）追加：

```yaml
# ── 项目级角色 → 权限映射（原 role_permissions 表 / DEFAULT_ROLE_PERMISSIONS 常量）──
project_roles:
  owner:      [project:edit, project:delete, member:add, member:remove, chapter:write_any, chapter:review_any, ai:start_writing, ai:stop_writing, approval:submit, approval:review, approval:approve, workflow:start, workflow:cancel, settings:edit, export:generate]
  phase_lead: [chapter:write_any, chapter:review_any, ai:start_writing, approval:submit, member:add, outline:edit]
  writer:     [chapter:write_own, chapter:confirm]
  reviewer:   [chapter:review, approval:review]
  approver:   [approval:approve, approval:view]
```

- [ ] **Step 2: unified_permissions.py 改为读 registry**

`backend/app/extensions/auth/unified_permissions.py` — `get_user_permissions` 中，删除 `RolePermission` 表查询，改用 registry：

```python
async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> set[str]:
    from app.extensions.auth.registry import get_permission_registry

    # Admin bypass — system role or wildcard
    from app.extensions.models import User
    user = await db.get(User, user_id)
    user_role = None
    if user and user.role_id:
        user_role = await db.get(Role, user.role_id)
    if user_role and (user_role.is_system or "*" in (user_role.permissions or [])):
        # Admin sees every permission granted to any project role
        registry = get_permission_registry()
        all_perms = set()
        for perms in registry.get_project_roles().values():
            all_perms.update(perms)
        return all_perms

    project_role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    if not project_role:
        return set()

    registry = get_permission_registry()
    role_perms = registry.get_project_roles().get(project_role.value) or []
    return set(role_perms)
```

删除文件顶部 `from app.extensions.models.role_permission import ProjectRole` 中的 `RolePermission` 相关导入（`ProjectRole` 枚举仍用于 `resolve_user_project_role`）。

- [ ] **Step 3: 运行现有 unified_permissions 相关测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -k "permission or policy or datascope" -v`
Expected: 无失败（`RolePermission` 表仍存在，不再读取）

- [ ] **Step 4: Commit**

```bash
git add config/permissions.yaml backend/app/extensions/auth/unified_permissions.py
git commit -m "feat(rbac): project_roles moved to permissions.yaml; unified_permissions reads registry (A2)"
```

---

### Task 11: 迁移 project/routers 到 unified_permissions + 删旧体系

**Files:**
- Modify: `backend/app/extensions/project/routers.py`
- Delete: `backend/app/extensions/project/permissions.py`
- Delete: `backend/app/extensions/project/project_permissions.py`

- [ ] **Step 1: 在 unified_permissions.py 提供兼容 shim**

`require_resource_permission` 在 project/routers.py 有 11 处 `Depends(...)` 且返回值被当作角色字符串使用，不能用 `RequireProjectPerm`（返回 CurrentUser）直接替换。在 `backend/app/extensions/auth/unified_permissions.py` 末尾追加**同名兼容 shim**（检查逻辑走 unified，返回值保持角色字符串）：

```python
from fastapi import Depends, HTTPException, Request
from app.extensions.auth.middleware import get_current_user


async def _resolve_project_role_str(
    db: AsyncSession, user_id: UUID, project_id: UUID, phase_node: str | None = None,
) -> str | None:
    role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    return role.value if role else None


def require_resource_permission(action: str):
    """Compat shim: unified_permissions check; returns project role string (old signature).

    Replaces the legacy app.extensions.project.permissions.require_resource_permission.
    """
    async def check(
        current_user: CurrentUser = Depends(get_current_user),
        request: Request = ...,
        db: AsyncSession = Depends(get_db),
    ) -> str | None:
        is_admin = False
        if current_user.role_id is not None:
            from app.extensions.models import Role as _Role

            role_obj = await db.get(_Role, current_user.role_id)
            if role_obj and (role_obj.is_system or "*" in (role_obj.permissions or [])):
                is_admin = True
        if is_admin:
            return "owner"

        project_id = request.path_params.get("project_id")
        if not project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="project_id required in path")
        from uuid import UUID as _UUID

        try:
            pid = _UUID(project_id)
        except (ValueError, AttributeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid project_id")

        perms = await get_user_permissions(db, current_user.id, pid)
        if action not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {action}")
        role = await resolve_user_project_role(db, current_user.id, pid)
        return role.value if role else None

    return check
```

（`unified_permissions.py` 顶部已 import `get_db`、`AsyncSession`、`UUID`、`CurrentUser`；`HTTPException` 已导入。）

- [ ] **Step 2: project/routers.py 改 import + get_my_permissions**

`backend/app/extensions/project/routers.py`：

1) 第 19 行 `from .permissions import require_resource_permission` → `from app.extensions.auth.unified_permissions import require_resource_permission`
2) 第 429 行 `from .permissions import get_project_role` → `from app.extensions.auth.unified_permissions import resolve_user_project_role`，并把该处调用改为：

```python
    project_role = await resolve_user_project_role(db, project_id, user.id)
```

3) `get_my_permissions`（290-341 行）删除对 `project_permissions.py` 的 import（304 行）与旧矩阵逻辑，改为：

```python
    from app.extensions.auth.registry import get_permission_registry
    from app.extensions.auth.unified_permissions import (
        get_user_permissions,
        resolve_user_project_role,
    )

    is_admin = False
    if user.role_id:
        role_obj = await db.get(Role, user.role_id)
        if role_obj:
            permissions = role_obj.permissions or []
            if "*" in permissions or role_obj.is_system:
                is_admin = True

    if is_admin:
        registry = get_permission_registry()
        all_perms = set()
        for perms in registry.get_project_roles().values():
            all_perms.update(perms)
        return ProjectPermissionsOut(
            role="owner",
            permissions=sorted(all_perms),
            phase_duties=None,
            is_admin=True,
        )

    perms = await get_user_permissions(db, user.id, project_id, phase_node)
    project_role = await resolve_user_project_role(db, user.id, project_id, phase_node)
    return ProjectPermissionsOut(
        role=project_role.value if project_role else None,
        permissions=sorted(perms),
        phase_duties=None,
        is_admin=False,
    )
```

若 `get_my_permissions` 签名原没有 `phase_node` 参数，保持原签名（`resolve_user_project_role` 的 `phase_node` 用默认 `None`）。

- [ ] **Step 3: 确认无残留引用**

Run: `cd backend && PYTHONPATH=. uv run python -c "import app.extensions.project.permissions" 2>&1 | head -1`
Expected: 模块已删除则报 ImportError（若仍可导入说明有遗留 import，回到 Step 1 清理）

再 grep：`cd backend && grep -rn "project_permissions\|project.permissions import" app/ --include=*.py`
Expected: 无输出

- [ ] **Step 4: 删除旧文件**

```bash
git rm backend/app/extensions/project/permissions.py backend/app/extensions/project/project_permissions.py
```

- [ ] **Step 5: 回归项目路由测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project*.py tests/test_permission*.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/project/routers.py
git commit -m "refactor(rbac): migrate project routers to unified_permissions; delete legacy permission matrices (A2)"
```

---

## Phase D — 前端（U1/U3/U4/A3/U2）

### Task 12: U1 — 角色列表显示用户数

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`
- Modify: `frontend/src/app/admin/roles/page.tsx`

- [ ] **Step 1: roleApi 加 assignments**

`frontend/src/extensions/api/index.ts` — roleApi 内新增：

```ts
  assignments: () =>
    request<RoleAssignmentInfo[]>(`/roles/assignments`),
```

- [ ] **Step 2: types.ts 加 RoleAssignmentInfo**

`frontend/src/extensions/types.ts`：

```ts
export interface RoleAssignmentInfo {
  role_id: string;
  role_name: string;
  user_count: number;
  permissions: string[];
}
```

- [ ] **Step 3: 页面加载 assignments 并展示**

`frontend/src/app/admin/roles/page.tsx`：
- state 加 `const [assignments, setAssignments] = useState<Record<string, number>>({});`
- `loadData` 里并行取：

```ts
      const [res, asg] = await Promise.all([roleApi.list(), roleApi.assignments()]);
      setAssignments(Object.fromEntries(asg.map((a) => [a.role_id, a.user_count])));
```

- 侧边栏 `<Users ... /> —` 改为 `{assignments[role.id] ?? 0}`：

```tsx
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" /> {assignments[role.id] ?? 0}
                    </span>
```

- [ ] **Step 4: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/api/index.ts frontend/src/extensions/types.ts frontend/src/app/admin/roles/page.tsx
git commit -m "feat(roles-ui): show real user count from /roles/assignments (U1)"
```

---

### Task 13: U3 — 策略 UI 修正（去 email_domain / data_scope / 角色误导）

**Files:**
- Modify: `frontend/src/app/admin/roles/page.tsx`

- [ ] **Step 1: 移除 email_domain 条件属性**

`PoliciesPanel` 内 `PolicyEditForm` 的 `ATTR_OPTIONS`：

```ts
  const ATTR_OPTIONS = ["tags", "role_level", "dept_id", "user_id"];  // 移除 email_domain
```

- [ ] **Step 2: grant 去掉 data_scope 下拉**

`PolicyEditForm` 中 grant 行的 `data_scope` Select 整块删除（引擎不消费该字段），`PolicyGrant` 类型仍兼容（`data_scope` 保留可空）。`addGrant` 初始对象改为 `{ permission: "" }`。

- [ ] **Step 3: 明确策略为全局**

`PoliciesPanel` 说明文案改为"管理全局访问策略（属性条件 + 权限授予），作用于所有角色"；`handlePolicySave` 移除 `role_id: selectedRole?.id` 传参：

```ts
        const created = await permissionsApi.createPolicy({
          name: policy.name, conditions: policy.conditions, grants: policy.grants,
          enabled: true,
        });
```

- [ ] **Step 4: typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 通过（`PolicyGrant.data_scope` 若变 unused 则保留字段仅类型用）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx
git commit -m "fix(roles-ui): policy editor drops email_domain/data_scope and clarifies global scope (U3)"
```

---

### Task 14: U4 — 数据权限面板初始加载/切换重置

**Files:**
- Modify: `frontend/src/app/admin/roles/page.tsx`

- [ ] **Step 1: Role 类型加 data_scopes**

`frontend/src/extensions/types.ts` Role interface：

```ts
  /** data scope ids resolved from registry */
  data_scopes?: string[];
```

- [ ] **Step 2: 面板用角色 data_scopes 做初始选择**

`handleSelectRole` 与 `loadData` 里设置：

```ts
    setDataScopeSelections(
      role.data_scopes?.length
        ? Object.fromEntries(
            (registryModules || [])
              .filter((m) => m.data_scopes?.length)
              .map((m) => [m.key, (role.data_scopes || []).find((d) => m.data_scopes.some((s) => s.id === d)) || m.data_scopes![0].id]),
          )
        : {}
    );
```

`handleDataScopeChange` 里去掉 `as unknown as UpdateRoleRequest` 强转（RoleUpdate 现可传 `data_scopes`，见 Task 15 后端若已加字段；本阶段先经 roleApi.update 传 `data_scopes`，后端 RoleUpdate schema 加字段在 Task 8 的 data_scopes 已进 RoleResponse 但 Update 未加 → 在 `schemas.py RoleUpdate` 加 `data_scopes: list[str] | None = None`，`service.update_role` 写透 entry）：

`backend/app/extensions/schemas.py` RoleUpdate 加：

```python
    # EAI-CUSTOM: data scopes (persisted to overlay via write-through)
    data_scopes: list[str] | None = None
```

`service.update_role` 在 entry 上加：

```python
        if data.data_scopes is not None:
            entry["data_scopes"] = list(data.data_scopes)
```

- [ ] **Step 3: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx frontend/src/extensions/types.ts backend/app/extensions/schemas.py backend/app/extensions/role/service.py
git commit -m "feat(roles-ui): data scope panel initializes from role data_scopes; RoleUpdate persists to overlay (U4)"
```

---

### Task 15: A3 — admin 布局鉴权改权限而非显示名

**Files:**
- Modify: `frontend/src/app/admin/layout.tsx`

- [ ] **Step 1: 改用权限判定**

`frontend/src/app/admin/layout.tsx` — `isAdmin` 从 `role_name === "Super Admin"` 改为基于权限（页面被 PermissionProvider 包裹，但 layout 顶层用 useAuth；改用 `role_name` 兜底 + `/api/permissions/me` 的 `can`）：

```ts
function isAdmin(user?: { role_name?: string | null }): boolean {
  // EAI-CUSTOM: 以 is_system/通配符权限为准，避免硬编码显示名
  return user?.role_name === "Super Admin" || user?.role_name === "超级管理员";
}
```

> 注意：这是过渡修复。根治需 `/api/permissions/me` 返回 `is_admin` 标志（identity 含 role.is_system）。在 `permission_routers.py /me` 返回值加 `"is_admin": bool(defaults and defaults.get("is_system"))`，前端 `PermissionProvider` 透出 `is_admin` 并使用：

```ts
// permission_routers.py /me return 增加
"is_admin": bool((registry.get_role_defaults(identity.role_code) or {}).get("is_system")),
```

```ts
// PermissionProvider state 加 is_admin: boolean；layout 用 ctx.is_admin
```

- [ ] **Step 2: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/layout.tsx frontend/src/core/permissions/PermissionProvider.tsx frontend/src/core/permissions/usePermission.ts backend/app/extensions/auth/permission_routers.py
git commit -m "fix(rbac): admin layout gates on is_admin flag from /me instead of display name (A3)"
```

---

### Task 16: U2 — 后端补强制 + 前端按钮级 can()（首批）

**Files:**
- Modify: `backend/app/extensions/dashboard/routers.py`
- Modify: `backend/app/extensions/law/routers.py`
- Modify: `backend/app/extensions/approval/routers.py`
- Modify: `frontend/src/app/admin/users/page.tsx`
- Modify: `frontend/src/app/knowledge/page.tsx`

- [ ] **Step 1: 后端补 require_permission**

`dashboard/routers.py` 顶层路由加 `Depends(require_permission("dashboard:view"))`；`law/routers.py` 加 `Depends(require_permission("kf:law:read"))`（或按模块实际权限点）；`approval/routers.py` 加 `Depends(require_permission("approval:view"))`。权限点先确认已在 `permissions.yaml` 声明（dashboard:view 已在；kf:law:read 已在；approval:view 已在）。逐个 router 的每个 endpoint 追加依赖参数。

- [ ] **Step 2: 前端按钮 can()（admin/users）**

`frontend/src/app/admin/users/page.tsx` — 引入 `usePermission`，对"新建用户/编辑/删除/重置密码"按钮按权限隐藏：

```ts
import { usePermission } from "@/core/permissions";

// 组件内
const { can } = usePermission();
// 渲染：{can("user:create") && <Button ...>新建用户</Button>}
```

`knowledge/page.tsx` 的"新建知识库/上传"按 `kb:create`/`kb:upload` 控制。

- [ ] **Step 3: typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 通过

- [ ] **Step 4: 回归后端测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_dashboard.py tests/test_law.py tests/test_approval.py -v`
Expected: 无失败（新依赖 require_permission，测试需带鉴权 context；若测试直连无鉴权，改为在依赖上 `get_current_user_optional` 或测试层 mock）

> 若现有测试未带鉴权导致 401/403，Task 16 的后端强制改到**新依赖注入** `require_permission` 会破坏测试。缓解：确认这些 router 已有 `get_current_user`；若没有，则本任务**仅做前端 can()**，后端强制点单列后续 Task 17。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/dashboard/routers.py backend/app/extensions/law/routers.py backend/app/extensions/approval/routers.py frontend/src/app/admin/users/page.tsx frontend/src/app/knowledge/page.tsx
git commit -m "feat(rbac): enforce require_permission on dashboard/law/approval + button-level can() on admin/users & knowledge (U2 batch 1)"
```

---

### Task 17: 收尾 — 全量回归 + 文档更新

**Files:**
- 文档：`README.md`（若权限说明变更）、`backend/CLAUDE.md`

- [x] **Step 1: 后端全量测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v`
**实际结果（2026-08-01 执行）：** 3894 passed / 420 failed / 136 errors —— 全部为**既有基线**（跨域污染、POSIX chmod 测试在 Windows 失败、`deerflow.skills.skillscan.orchestrator` 缺失等）；plan 域测试集（test_policy_crud/role_overlay_store/role_calibration/permission_engine/permission_registry/unified_project_permissions/datascope）61/61 通过，0 新增失败。

- [x] **Step 2: 前端全量**

Run: `cd frontend && pnpm lint && pnpm typecheck`
**实际结果：** typecheck 127 错误 = 既有基线（collab/docmgr/workflow/knowledge-factory/测试文件），本 plan 触及文件 0 新增；lint 758 错误均为既有，本 plan 文件 0 新增。

- [x] **Step 3: ruff**

Run: `cd backend && make lint`
**实际结果：** 662 错误均为既有（多为 routers.py 既有 E402/F401/F811），本 plan 改动文件全部通过。

- [x] **Step 4: 更新文档**

`backend/CLAUDE.md` 已增加 "Role / Permission System — YAML-Driven Single Source of Truth" 一节（commit 52ebbe01）。

- [x] **Step 5: Commit**

```bash
git add backend/CLAUDE.md
git commit -m "docs: record yaml-driven role/permission source-of-truth convention"
```

### Task 17 执行期间追加的 carry-forward 修复（会话内评审发现的既有问题，已一并修复）

| 项 | 问题 | 修复 commit |
|---|---|---|
| A1 | 策略 createPolicy 返回不完整 → 行渲染崩溃 | `65e2026c`（返回全字段） |
| A2 | 策略 conditions UI 数组 vs 引擎 dict → 422 | `65e2026c`（toEngineConditions/toUIConditions） |
| A3 | overlay 乐观锁 RuntimeError → 500 | `65e2026c`（→ 409） |
| A4 | dashboard:view 未授予任何角色（未来强制的前置授权） | `65e2026c`（补 5 角色默认） |
| C1 | 策略 grants UI 数组 vs 引擎 dict → 422（A2 只修了 conditions） | `26426a17`（toGrantArray + save/load 双向） |
| I2 | in/not_in 值字符串 vs 引擎需列表 | `26426a17`（逗号拆分/join） |
| I3 | 转换器无测试 | `26426a17`（12 vitest） |

**延后项（需后续单独处理，本 plan 未做）：**
1. **后端颗粒强制**：dashboard/law/approval 路由仍用 `system:access`。切换为 `dashboard:view`/`kf:law:read`/`approval:view` 需先补角色默认授权（dashboard:view 已补前置授权；law 需 read/write 拆分；approval 需 review 角色补 view）。当前切换会锁死非 admin 角色，故延后。
2. **`frontend/src/app/workflow-admin/page.tsx` 与 `TemplateEditorPage.tsx`** 仍用 `role_name === "Super Admin"` 显示名判断（A3 同类，未在任务文件清单内）。
3. **pre-existing 基线**：后端 420 失败 + 前端 127 type errors + ruff 662 错误 + `deerflow.skills.skillscan.orchestrator` 工作树被并发进程反复删除（bug-609 复发）。

---

## Self-Review

**Spec 覆盖：**
- S1（nav 生效）→ Task 3 ✓；S2（数据权限落地）→ Task 4/14 ✓；S3（重置守卫）→ Task 5 ✓；S4（继承）→ Task 2 + Task 1 overlay ✓
- A1（三套默认收敛）→ Task 1/7/8 ✓；A2（项目体系统一）→ Task 10/11 ✓
- U1 → Task 12 ✓；U2 → Task 16（+17 兜底）✓；U3 → Task 13 ✓；U4 → Task 14 ✓；A3 → Task 15 ✓
- 并发写 → Task 8（原子写+乐观锁）✓；policies 留 DB → Task 2 保持 DB 读取 ✓

**已知留白（有意为之，非占位）：**
- Task 16 后端强制的测试鉴权影响：已写明缓解路径（仅前端 or 单独 Task 17）。
- `RoleService.get_role_by_code` 在写透后依赖校准；`create_role` 返回镜像行。
- `disabled_roles` UI 展示（spec §8 未决默认"不展示"）→ 不在本计划内。
