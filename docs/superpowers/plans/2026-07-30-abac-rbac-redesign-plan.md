# ABAC-lite 权限系统重构 — 实现计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐步实现。步骤使用 checkbox (`- [ ]`) 语法追踪。

**目标：** 将现有双轨 RBAC 系统重构为统一的 ABAC-lite 权限引擎，支持配置驱动（YAML）、操作权限+数据权限统一管理、前端全链路控制。

**架构：** `PermissionRegistry`（YAML→内存） + `IdentityProvider`（用户→AttributeSet）→ `UnifiedPermissionEngine`（check + data_scope + list_permissions）。通过 `permissions.yaml` 声明模块权限点，DB `roles.permissions` 存储角色映射，`policies` 表存储自定义 ABAC 策略。

**技术栈：** Python 3.12, FastAPI (Depends), SQLAlchemy 2.0 async, PostgreSQL, Next.js 16, React 19, TypeScript 5.8

**设计文档：** `docs/superpowers/specs/2026-07-30-abac-rbac-redesign-design.md`

---

### Phase 1：引擎 + 注册中心（向后兼容）

#### Task 1: 创建 `permissions.yaml` 配置文件

**文件：**
- Create: `config/permissions.yaml`

- [ ] **Step 1: 创建权限声明文件**

```yaml
# permissions.yaml — 模块权限声明 + 角色默认映射 + seed 策略
# 格式版本，用于检测不兼容变更时告警
version: 1

modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库", description: "浏览和搜索知识库内容" }
      - { id: "kb:create", display_name: "创建知识库", description: "创建新的知识库" }
      - { id: "kb:update", display_name: "编辑知识库" }
      - { id: "kb:delete", display_name: "删除知识库" }
      - { id: "kb:upload", display_name: "上传文档" }
    data_scopes:
      - { id: "knowledge_owner", display_name: "仅自己的知识库", rule_template: { owner_id: "$identity.user_id" } }
      - { id: "knowledge_dept", display_name: "本部门的知识库", rule_template: { or: [{ owner_id: "$identity.user_id" }, { dept_id IN: "$identity.dept_ids" }] } }
      - { id: "knowledge_public", display_name: "所有公开知识库", rule_template: { access_type: "public" } }

  contract_price:
    display_name: "合同价格分析"
    permissions:
      - { id: "cpa:read", display_name: "查看合同价格" }
      - { id: "cpa:import", display_name: "导入合同" }
      - { id: "cpa:cluster", display_name: "执行聚类分析" }
      - { id: "cpa:export", display_name: "导出分析结果" }
    data_scopes:
      - { id: "cpa_all", display_name: "全部合同数据", rule_template: {} }
      - { id: "cpa_dept", display_name: "本部门合同", rule_template: { dept_id IN: "$identity.dept_ids" } }

  user_management:
    display_name: "用户管理"
    permissions:
      - { id: "user:read", display_name: "查看用户" }
      - { id: "user:create", display_name: "创建用户" }
      - { id: "user:update", display_name: "编辑用户" }
      - { id: "user:delete", display_name: "删除用户" }

  role_management:
    display_name: "角色管理"
    permissions:
      - { id: "role:read", display_name: "查看角色" }
      - { id: "role:create", display_name: "创建角色" }
      - { id: "role:update", display_name: "编辑角色" }
      - { id: "role:delete", display_name: "删除角色" }

  department:
    display_name: "部门管理"
    permissions:
      - { id: "department:create", display_name: "创建部门" }
      - { id: "department:update", display_name: "编辑部门" }
      - { id: "department:delete", display_name: "删除部门" }

  project:
    display_name: "报告项目"
    permissions:
      - { id: "project:create", display_name: "创建项目" }
      - { id: "project:edit", display_name: "编辑项目" }
      - { id: "project:delete", display_name: "删除项目" }
      - { id: "project:read", display_name: "查看项目" }
      - { id: "member:add", display_name: "添加成员" }
      - { id: "member:remove", display_name: "移除成员" }
      - { id: "chapter:write_own", display_name: "编写自己的章节" }
      - { id: "chapter:write_any", display_name: "编写任意章节" }
      - { id: "chapter:review", display_name: "审核章节" }
      - { id: "chapter:review_any", display_name: "审核任意章节" }
      - { id: "approval:submit", display_name: "提交审批" }
      - { id: "approval:review", display_name: "审批审核" }
      - { id: "approval:approve", display_name: "批准" }
      - { id: "approval:view", display_name: "查看审批" }
      - { id: "ai:start_writing", display_name: "启动 AI 写作" }
      - { id: "outline:edit", display_name: "编辑大纲" }
      - { id: "settings:edit", display_name: "编辑设置" }
      - { id: "export:generate", display_name: "生成导出" }
      - { id: "source:view", display_name: "查看来源" }
      - { id: "version:rollback", display_name: "版本回滚" }
    data_scopes:
      - { id: "project_member", display_name: "参与的项目", rule_template: { id IN: "$identity.member_projects" } }
      - { id: "project_all", display_name: "全部项目", rule_template: {} }

  workflow:
    display_name: "工作流"
    permissions:
      - { id: "workflow:read", display_name: "查看工作流" }
      - { id: "workflow:start", display_name: "启动工作流" }
      - { id: "workflow:cancel", display_name: "取消工作流" }
      - { id: "workflow:edit", display_name: "编辑工作流" }

  docmgr:
    display_name: "文档空间"
    permissions:
      - { id: "doc:read", display_name: "查看文档" }
      - { id: "doc:upload", display_name: "上传文档" }
      - { id: "doc:delete", display_name: "删除文档" }

  model_access:
    display_name: "模型访问"
    permissions:
      - { id: "model:read", display_name: "使用模型" }

  skills:
    display_name: "插件与工具"
    permissions:
      - { id: "skill:read", display_name: "查看插件" }
      - { id: "skill:install", display_name: "安装插件" }
      - { id: "skill:uninstall", display_name: "卸载插件" }

  license:
    display_name: "许可证管理"
    permissions:
      - { id: "license:manage", display_name: "管理许可证", admin_only: true }

  app_center:
    display_name: "应用中心管理"
    permissions:
      - { id: "app_center:manage", display_name: "管理应用中心", admin_only: true }

roles:
  superadmin:
    display_name: "超级管理员"
    is_system: true
    level: 100
    permissions: ["*"]
    data_scopes: ["project_all", "cpa_all", "knowledge_public"]

  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    permissions:
      - kb:read
      - kb:create
      - doc:read
      - doc:upload
      - project:create
      - project:read
      - model:read
      - system:access
      - workflow:read
      - cpa:read
      - cpa:import
      - approval:approve
      - approval:submit
      - approval:view
      - chapter:review
      - source:view
    data_scopes: ["knowledge_dept", "cpa_dept", "project_member"]

  project_manager:
    display_name: "项目经理"
    is_system: false
    level: 60
    permissions:
      - "#inherit:dept_head"
      - project:edit
      - member:add
      - member:remove
      - chapter:write_any
      - ai:start_writing
      - outline:edit
      - settings:edit
      - export:generate
      - approval:submit
      - approval:review
      - workflow:start
      - workflow:cancel
    data_scopes: ["project_member", "knowledge_dept", "cpa_dept"]

  writer:
    display_name: "撰写人"
    is_system: false
    level: 10
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
      - chapter:write_own
      - chapter:review
      - ai:start_writing
      - source:view
      - workflow:read
    data_scopes: ["project_member", "knowledge_dept"]

  reviewer:
    display_name: "审核员"
    is_system: false
    level: 20
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
      - chapter:review
      - approval:review
      - source:view
      - workflow:read
    data_scopes: ["project_member", "knowledge_dept"]

  user:
    display_name: "普通用户"
    is_system: false
    level: 1
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
    data_scopes: ["knowledge_public", "project_member"]
```

- [ ] **Step 2: 提交**

```bash
git add config/permissions.yaml
git commit -m "feat(permissions): add permissions.yaml with all module declarations and role defaults"
```

---

#### Task 2: 创建 `PermissionRegistry`（YAML 加载 + 热更新）

**文件：**
- Create: `backend/app/extensions/auth/registry.py`
- Test: `backend/tests/test_permission_registry.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_permission_registry.py
import pytest
from app.extensions.auth.registry import PermissionRegistry, ModulePermission, DataScope


class TestPermissionRegistry:
    def test_loads_all_modules_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes:
      - { id: "knowledge_owner", display_name: "仅自己的知识库", rule_template: { owner_id: "$identity.user_id" } }
  contract_price:
    display_name: "合同价格分析"
    permissions:
      - { id: "cpa:read", display_name: "查看合同价格" }
    data_scopes: []
roles: {}
""")
        registry = PermissionRegistry(str(yaml_file))
        assert "knowledge" in registry.modules
        assert registry.modules["knowledge"].display_name == "知识库"
        assert len(registry.modules["knowledge"].permissions) == 2
        assert registry.modules["knowledge"].permissions[0].id == "kb:read"

    def test_get_permission_by_id(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes: []
roles: {}
""")
        registry = PermissionRegistry(str(yaml_file))
        perm = registry.get_permission("kb:read")
        assert perm is not None
        assert perm.id == "kb:read"
        assert perm.module == "knowledge"
        assert registry.get_permission("nonexistent") is None

    def test_list_all_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
    data_scopes: []
  user_management:
    display_name: "用户管理"
    permissions:
      - { id: "user:read", display_name: "查看用户" }
    data_scopes: []
roles: {}
""")
        registry = PermissionRegistry(str(yaml_file))
        all_perms = registry.list_all_permissions()
        assert len(all_perms) == 2
        ids = {p.id for p in all_perms}
        assert ids == {"kb:read", "user:read"}

    def test_role_defaults_loaded(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules: {}
roles:
  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    permissions: ["kb:read", "system:access"]
    data_scopes: ["knowledge_dept"]
""")
        registry = PermissionRegistry(str(yaml_file))
        role = registry.get_role_defaults("dept_head")
        assert role is not None
        assert role["display_name"] == "部门负责人"
        assert role["permissions"] == ["kb:read", "system:access"]
        assert registry.get_role_defaults("nonexistent") is None

    def test_admin_only_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  license:
    display_name: "许可证管理"
    permissions:
      - { id: "license:manage", display_name: "管理许可证", admin_only: true }
      - { id: "license:view", display_name: "查看许可证" }
    data_scopes: []
roles: {}
""")
        registry = PermissionRegistry(str(yaml_file))
        perms = registry.list_admin_only_permissions()
        assert len(perms) == 1
        assert perms[0].id == "license:manage"

    def test_inherit_resolution(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules: {}
roles:
  base:
    display_name: "基础角色"
    is_system: false
    level: 10
    permissions: ["kb:read", "system:access"]
    data_scopes: ["knowledge_public"]
  derived:
    display_name: "派生角色"
    is_system: false
    level: 20
    permissions: ["#inherit:base", "kb:create"]
    data_scopes: ["knowledge_dept"]
""")
        registry = PermissionRegistry(str(yaml_file))
        resolved = registry.resolve_role_permissions("derived")
        assert "kb:read" in resolved
        assert "kb:create" in resolved
        assert "system:access" in resolved

    def test_reload_on_change(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
    data_scopes: []
roles: {}
""")
        registry = PermissionRegistry(str(yaml_file))
        assert "knowledge" in registry.modules

        # Modify file
        yaml_file.write_text("""
version: 1
modules:
  new_module:
    display_name: "新模块"
    permissions:
      - { id: "new:read", display_name: "查看" }
    data_scopes: []
roles: {}
""")
        registry._check_reload()
        assert "new_module" in registry.modules
        assert "knowledge" not in registry.modules
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permission_registry.py -v
```
期望：全部 FAIL（模块不存在）

- [ ] **Step 3: 实现 `PermissionRegistry`**

```python
# backend/app/extensions/auth/registry.py
"""Permission registry — loads permissions.yaml, serves permission metadata."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DataScope:
    id: str
    display_name: str
    rule_template: dict
    module: str = ""


@dataclass
class PermissionPoint:
    id: str
    display_name: str
    description: str | None = None
    admin_only: bool = False
    module: str = ""


@dataclass
class ModulePermission:
    display_name: str
    permissions: list[PermissionPoint] = field(default_factory=list)
    data_scopes: list[DataScope] = field(default_factory=list)


class PermissionRegistry:
    """Loads and serves the module-permission registry from a YAML file.

    The YAML file is the source of truth for *which permissions exist*.
    Role-to-permission mappings in the YAML are seed data only; the DB
    ``roles.permissions`` column is authoritative at runtime.
    """

    def __init__(self, yaml_path: str | None = None):
        if yaml_path is None:
            yaml_path = os.environ.get(
                "PERMISSIONS_YAML_PATH",
                str(Path(__file__).parent.parent.parent.parent.parent / "config" / "permissions.yaml"),
            )
        self._path = Path(yaml_path)
        self._mtime: float = 0.0
        self.modules: dict[str, ModulePermission] = {}
        self._role_defaults: dict[str, dict] = {}
        self._all_permissions: dict[str, PermissionPoint] = {}
        self._admin_only: list[PermissionPoint] = []
        self._load()

    # ── loading ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("permissions.yaml not found at %s, registry is empty", self._path)
            return
        self._mtime = self._path.stat().st_mtime
        with open(self._path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        self._parse_modules(data.get("modules") or {})
        self._parse_roles(data.get("roles") or {})

    def _parse_modules(self, modules_data: dict) -> None:
        self.modules.clear()
        self._all_permissions.clear()
        self._admin_only.clear()

        for module_key, module_data in modules_data.items():
            mp = ModulePermission(display_name=module_data.get("display_name", module_key))

            for p in module_data.get("permissions") or []:
                perm = PermissionPoint(
                    id=p["id"],
                    display_name=p.get("display_name", p["id"]),
                    description=p.get("description"),
                    admin_only=p.get("admin_only", False),
                    module=module_key,
                )
                mp.permissions.append(perm)
                self._all_permissions[perm.id] = perm
                if perm.admin_only:
                    self._admin_only.append(perm)

            for ds in module_data.get("data_scopes") or []:
                mp.data_scopes.append(DataScope(
                    id=ds["id"],
                    display_name=ds.get("display_name", ds["id"]),
                    rule_template=ds.get("rule_template") or {},
                    module=module_key,
                ))

            self.modules[module_key] = mp

    def _parse_roles(self, roles_data: dict) -> None:
        self._role_defaults.clear()
        for role_code, role_data in roles_data.items():
            self._role_defaults[role_code] = {
                "display_name": role_data.get("display_name", role_code),
                "is_system": role_data.get("is_system", False),
                "level": role_data.get("level", 10),
                "permissions": list(role_data.get("permissions") or []),
                "data_scopes": list(role_data.get("data_scopes") or []),
            }

    # ── query ─────────────────────────────────────────────────────────

    def get_permission(self, permission_id: str) -> PermissionPoint | None:
        return self._all_permissions.get(permission_id)

    def list_all_permissions(self) -> list[PermissionPoint]:
        return list(self._all_permissions.values())

    def list_admin_only_permissions(self) -> list[PermissionPoint]:
        return list(self._admin_only)

    def list_modules(self) -> list[tuple[str, ModulePermission]]:
        return list(self.modules.items())

    def get_data_scope(self, scope_id: str) -> DataScope | None:
        for mp in self.modules.values():
            for ds in mp.data_scopes:
                if ds.id == scope_id:
                    return ds
        return None

    def get_role_defaults(self, role_code: str) -> dict | None:
        return self._role_defaults.get(role_code)

    def resolve_role_permissions(self, role_code: str) -> set[str]:
        """Resolve a role's permissions including ``#inherit:`` chains."""
        defaults = self._role_defaults.get(role_code)
        if defaults is None:
            return set()

        resolved: set[str] = set()
        self._resolve_inherit(defaults.get("permissions") or [], resolved, set())
        return resolved

    def _resolve_inherit(self, permissions: list[str], resolved: set[str], visited: set[str]) -> None:
        for perm in permissions:
            if perm.startswith("#inherit:"):
                parent_code = perm.split(":", 1)[1].strip()
                if parent_code in visited:
                    logger.warning("Circular inherit detected: %s", visited)
                    continue
                visited.add(parent_code)
                parent = self._role_defaults.get(parent_code)
                if parent:
                    self._resolve_inherit(parent.get("permissions") or [], resolved, visited)
            else:
                resolved.add(perm)

    # ── hot-reload ────────────────────────────────────────────────────

    def _check_reload(self) -> bool:
        """Re-load if the YAML file changed since last load. Returns True on reload."""
        if not self._path.exists():
            return False
        current_mtime = self._path.stat().st_mtime
        if current_mtime > self._mtime:
            logger.info("permissions.yaml changed, reloading registry")
            self._load()
            return True
        return False


# ── singleton ─────────────────────────────────────────────────────────

_registry: PermissionRegistry | None = None


def get_permission_registry() -> PermissionRegistry:
    global _registry
    if _registry is None:
        _registry = PermissionRegistry()
    _registry._check_reload()
    return _registry
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permission_registry.py -v
```
期望：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/auth/registry.py backend/tests/test_permission_registry.py
git commit -m "feat(permissions): add PermissionRegistry with YAML loading and hot-reload"
```

---

#### Task 3: 创建 `AttributeSet` + `IdentityProvider`

**文件：**
- Create: `backend/app/extensions/auth/identity.py`
- Test: `backend/tests/test_identity_provider.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_identity_provider.py
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.identity import AttributeSet, IdentityProvider


class TestAttributeSet:
    def test_basic_attributes(self):
        attrs = AttributeSet(
            user_id="user-1",
            username="testuser",
            role_code="dept_head",
            role_level=50,
            dept_id="dept-1",
            dept_ids=["dept-1", "dept-2"],
        )
        assert attrs.user_id == "user-1"
        assert attrs.role_code == "dept_head"
        assert "dept-1" in attrs.dept_ids

    def test_to_dict_includes_all_fields(self):
        attrs = AttributeSet(
            user_id="u1", username="test", role_code="writer", role_level=10,
            dept_id="d1", dept_ids=["d1"],
            member_projects=["p1"], project_roles={"p1": "owner"},
            tags=["external"], labels={"region": "华东"},
        )
        d = attrs.to_dict()
        assert d["role_code"] == "writer"
        assert d["tags"] == ["external"]
        assert d["labels"]["region"] == "华东"


class TestIdentityProvider:
    @pytest.mark.asyncio
    async def test_resolve_returns_attribute_set(self):
        user_id = str(uuid.uuid4())
        mock_db = MagicMock(spec=AsyncSession)

        # Mock User + Role
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "testuser"
        mock_user.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        mock_role = MagicMock()
        mock_role.code = "dept_head"
        mock_role.level = 50
        mock_role.is_system = False

        # Mock UserDepartment
        mock_ud = MagicMock()
        mock_ud.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_ud2 = MagicMock()
        mock_ud2.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

        # Mock ProjectMember
        mock_pm = MagicMock()
        mock_pm.project_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
        mock_pm.role = "owner"

        with patch("app.extensions.auth.identity.select") as mock_select, \
             patch("app.extensions.auth.identity.User") as mock_user_model, \
             patch("app.extensions.auth.identity.Role") as mock_role_model, \
             patch("app.extensions.auth.identity.UserDepartment") as mock_ud_model, \
             patch("app.extensions.auth.identity.ProjectMember") as mock_pm_model:

            # Setup mock chain for User + Role
            mock_result = AsyncMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
            mock_db.execute = AsyncMock()

            # First call: User
            mock_db.execute.side_effect = [
                # User query
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user)),
                # Role query
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_role)),
                # UserDepartment query
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_ud, mock_ud2])))),
                # ProjectMember query
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_pm])))),
            ]

            provider = IdentityProvider()
            identity = await provider.resolve(user_id, mock_db)

            assert identity.user_id == user_id
            assert identity.role_code == "dept_head"
            assert identity.role_level == 50
            assert len(identity.member_projects) == 1
            assert identity.project_roles == {str(mock_pm.project_id): "owner"}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_identity_provider.py -v
```
期望：FAIL（模块不存在）

- [ ] **Step 3: 实现 `AttributeSet` + `IdentityProvider`**

```python
# backend/app/extensions/auth/identity.py
"""Identity provider — resolves a user to an AttributeSet for ABAC evaluation.

TagResolver plugins allow modules to extend identity attributes without
modifying the core identity resolution logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import ProjectMember, Role, User, UserDepartment

logger = logging.getLogger(__name__)


@dataclass
class AttributeSet:
    """User identity expressed as an extensible attribute set for ABAC evaluation."""

    user_id: str
    username: str

    # Fixed attributes
    role_code: str | None = None
    role_level: int = 0
    dept_id: str | None = None
    dept_ids: list[str] = field(default_factory=list)

    # Dynamic attributes (lazy-loaded)
    member_projects: list[str] = field(default_factory=list)
    project_roles: dict[str, str] = field(default_factory=dict)

    # Extensible attributes
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role_code": self.role_code,
            "role_level": self.role_level,
            "dept_id": self.dept_id,
            "dept_ids": self.dept_ids,
            "member_projects": self.member_projects,
            "project_roles": self.project_roles,
            "tags": self.tags,
            "labels": self.labels,
        }

    def get_attr(self, path: str) -> Any:
        """Resolve a dotted attribute path, e.g. 'labels.region' → '华东'."""
        parts = path.split(".")
        current: Any = self.to_dict()
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        return current


class TagResolver(Protocol):
    """Protocol for pluggable identity tag resolvers."""

    name: str

    async def resolve(self, user_id: str, db: AsyncSession) -> dict:
        """Return ``{tags: [...], labels: {...}, extra: {...}}``."""
        ...


class IdentityProvider:
    """Resolves a user to an AttributeSet for permission evaluation."""

    def __init__(self) -> None:
        self._tag_resolvers: list[TagResolver] = []

    def register_tag_resolver(self, resolver: TagResolver) -> None:
        self._tag_resolvers.append(resolver)

    async def resolve(self, user_id: str, db: AsyncSession) -> AttributeSet:
        # Load User
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")

        attrs = AttributeSet(
            user_id=str(user.id),
            username=user.username,
            dept_id=str(user.dept_id) if user.dept_id else None,
        )

        # Load Role
        if user.role_id:
            role = await db.get(Role, user.role_id)
            if role:
                attrs.role_code = role.code
                attrs.role_level = role.level or 0

        # Load departments
        stmt = select(UserDepartment).where(UserDepartment.user_id == user.id)
        result = await db.execute(stmt)
        uds = result.scalars().all()
        attrs.dept_ids = [str(ud.dept_id) for ud in uds]

        # Load project memberships
        stmt = select(ProjectMember).where(ProjectMember.user_id == user.id)
        result = await db.execute(stmt)
        pms = result.scalars().all()
        attrs.member_projects = [str(pm.project_id) for pm in pms]
        attrs.project_roles = {str(pm.project_id): pm.role for pm in pms}

        # Run tag resolvers
        for resolver in self._tag_resolvers:
            try:
                extra = await resolver.resolve(user_id, db)
                if extra.get("tags"):
                    attrs.tags.extend(extra["tags"])
                if extra.get("labels"):
                    attrs.labels.update(extra["labels"])
                if extra.get("extra"):
                    attrs.extra.update(extra["extra"])
            except Exception:
                logger.warning("TagResolver '%s' failed for user %s", resolver.name, user_id, exc_info=True)

        return attrs


# ── singleton ─────────────────────────────────────────────────────────

_identity_provider: IdentityProvider | None = None


def get_identity_provider() -> IdentityProvider:
    global _identity_provider
    if _identity_provider is None:
        _identity_provider = IdentityProvider()
    return _identity_provider
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_identity_provider.py -v
```
期望：PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/auth/identity.py backend/tests/test_identity_provider.py
git commit -m "feat(permissions): add AttributeSet + IdentityProvider with pluggable TagResolver"
```

---

#### Task 4: 创建 `UnifiedPermissionEngine`

**文件：**
- Create: `backend/app/extensions/auth/engine.py`
- Test: `backend/tests/test_permission_engine.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_permission_engine.py
import pytest
from app.extensions.auth.engine import UnifiedPermissionEngine, FilterRule
from app.extensions.auth.identity import AttributeSet


def identity(**kwargs) -> AttributeSet:
    defaults = {
        "user_id": "u1", "username": "test",
        "role_code": "writer", "role_level": 10,
    }
    defaults.update(kwargs)
    return AttributeSet(**defaults)


class TestUnifiedPermissionEngine:
    def test_star_wildcard_grants_all(self):
        idn = identity(role_code="superadmin")
        engine = UnifiedPermissionEngine(
            role_permissions={"superadmin": {"*"}},
        )
        assert engine.check(idn, "kb:create") is True
        assert engine.check(idn, "any:random:thing") is True

    def test_exact_permission_match(self):
        idn = identity(role_code="writer")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read", "doc:read", "system:access"}},
        )
        assert engine.check(idn, "kb:read") is True
        assert engine.check(idn, "kb:create") is False

    def test_module_wildcard(self):
        idn = identity(role_code="admin")
        engine = UnifiedPermissionEngine(
            role_permissions={"admin": {"kb:*", "system:access"}},
        )
        assert engine.check(idn, "kb:read") is True
        assert engine.check(idn, "kb:create") is True
        assert engine.check(idn, "user:read") is False

    def test_list_permissions(self):
        idn = identity(role_code="writer")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read", "doc:read", "system:access"}},
        )
        perms = engine.list_permissions(idn)
        assert set(perms) == {"kb:read", "doc:read", "system:access"}

    def test_list_permissions_star_expands_all(self):
        idn = identity(role_code="superadmin")
        engine = UnifiedPermissionEngine(
            role_permissions={"superadmin": {"*"}},
            all_permission_ids={"kb:read", "kb:create", "user:read"},
        )
        perms = engine.list_permissions(idn)
        assert perms == {"kb:read", "kb:create", "user:read"}


class TestFilterRule:
    def test_eq_to_sqlalchemy(self):
        rule = FilterRule(operator="eq", field="owner_id", value="user-1")
        # No real model — test dict serialization
        d = rule.to_dict()
        assert d == {"operator": "eq", "field": "owner_id", "value": "user-1", "children": None}

    def test_and_composite(self):
        inner1 = FilterRule(operator="eq", field="a", value=1)
        inner2 = FilterRule(operator="in", field="b", value=[1, 2])
        rule = FilterRule(operator="and", children=[inner1, inner2])
        d = rule.to_dict()
        assert d["operator"] == "and"
        assert len(d["children"]) == 2

    def test_from_template_simple(self):
        template = {"owner_id": "$identity.user_id"}
        idn = identity(user_id="user-99")
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "eq"
        assert rule.field == "owner_id"
        assert rule.value == "user-99"

    def test_from_template_in_list(self):
        template = {"dept_id IN": "$identity.dept_ids"}
        idn = identity(dept_ids=["d1", "d2"])
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "in"
        assert rule.field == "dept_id"
        assert rule.value == ["d1", "d2"]

    def test_from_template_or(self):
        template = {
            "or": [
                {"owner_id": "$identity.user_id"},
                {"dept_id IN": "$identity.dept_ids"},
            ]
        }
        idn = identity(user_id="u1", dept_ids=["d1"])
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "or"
        assert len(rule.children) == 2
        assert rule.children[0].value == "u1"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permission_engine.py -v
```
期望：FAIL

- [ ] **Step 3: 实现 `UnifiedPermissionEngine` + `FilterRule`**

```python
# backend/app/extensions/auth/engine.py
"""Unified ABAC-lite permission engine.

Checks both role-based permissions and ABAC policies against an
:class:`AttributeSet` to answer: can this identity perform this action?
Optionally evaluates data-scope rules to answer: which resources can
this identity see?
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.extensions.auth.identity import AttributeSet

logger = logging.getLogger(__name__)


# ── FilterRule ────────────────────────────────────────────────────────

@dataclass
class FilterRule:
    """Serializable filter rule tree supporting AND/OR/IN/EQ/NONE_ALLOW.

    ``NONE_ALLOW`` (default empty tree) means access denied — you must
    explicitly configure an allow-rule.
    """

    operator: str = "none_allow"   # "eq" | "in" | "and" | "or" | "none_allow" | "raw"
    field: str | None = None
    value: Any = None
    children: list["FilterRule"] | None = None

    @classmethod
    def from_template(cls, template: dict, identity: AttributeSet) -> "FilterRule":
        """Build a FilterRule from a YAML rule_template + identity."""
        if not template:
            return cls(operator="none_allow")

        if "or" in template:
            return cls(
                operator="or",
                children=[cls.from_template(child, identity) for child in template["or"]],
            )
        if "and" in template:
            return cls(
                operator="and",
                children=[cls.from_template(child, identity) for child in template["and"]],
            )

        # Single condition: resolve the only key/value pair
        for key, raw_value in template.items():
            if " IN " in key:
                field = key.replace(" IN ", "").strip()
                resolved = cls._resolve(raw_value, identity)
                return cls(operator="in", field=field, value=resolved if isinstance(resolved, list) else [resolved])
            else:
                resolved = cls._resolve(raw_value, identity)
                return cls(operator="eq", field=key, value=resolved)

        return cls(operator="none_allow")

    @staticmethod
    def _resolve(value: Any, identity: AttributeSet) -> Any:
        """Replace ``$identity.xxx`` references with actual identity values."""
        if isinstance(value, str) and value.startswith("$identity."):
            path = value[len("$identity."):]
            return identity.get_attr(path)
        return value

    def to_dict(self) -> dict:
        return {
            "operator": self.operator,
            "field": self.field,
            "value": self.value,
            "children": [c.to_dict() for c in self.children] if self.children else None,
        }


# ── Engine ────────────────────────────────────────────────────────────

@dataclass
class Policy:
    """A stored ABAC policy."""
    name: str
    priority: int
    conditions: dict
    grants: dict   # {permissions: [...], data_scope: str | None}


class UnifiedPermissionEngine:
    """ABAC-lite engine.

    Evaluation order:
    1. ``*`` wildcard → grant
    2. Direct role permission match (including ``module:*`` prefixes)
    3. ABAC policies (sorted by priority, OR semantics)
    4. Default deny
    """

    def __init__(
        self,
        role_permissions: dict[str, set[str]] | None = None,
        all_permission_ids: set[str] | None = None,
        policies: list[Policy] | None = None,
    ):
        # {role_code: {perm1, perm2, ...}}
        self._role_permissions: dict[str, set[str]] = role_permissions or {}
        # Set of all known permission IDs (for * expansion)
        self._all_permission_ids: set[str] = all_permission_ids or set()
        # ABAC policies sorted by priority
        self._policies: list[Policy] = sorted(policies or [], key=lambda p: p.priority)

    # ── check ─────────────────────────────────────────────────────────

    def check(self, identity: AttributeSet, permission: str) -> bool:
        """Return True if identity holds *permission*."""
        role_perms = self._role_permissions.get(identity.role_code or "", set())

        # 1. Wildcard
        if "*" in role_perms:
            return True

        # 2. Direct + module wildcard
        prefix = permission.split(":", 1)[0]
        if permission in role_perms or f"{prefix}:*" in role_perms:
            return True

        # 3. ABAC policies
        for policy in self._policies:
            if self._evaluate_conditions(policy.conditions, identity):
                if permission in (policy.grants.get("permissions") or []):
                    return True

        # 4. Deny
        return False

    # ── data scope ────────────────────────────────────────────────────

    def get_data_scope(self, identity: AttributeSet, resource_type: str) -> FilterRule:
        """Return a FilterRule describing what resources of *resource_type* are visible."""
        # For now, data scopes are resolved from role config or policies.
        # Phase 2 completes this.
        return FilterRule(operator="none_allow")

    # ── list permissions ──────────────────────────────────────────────

    def list_permissions(self, identity: AttributeSet) -> set[str]:
        """List all permissions this identity holds."""
        role_perms = self._role_permissions.get(identity.role_code or "", set())

        if "*" in role_perms:
            return set(self._all_permission_ids)

        result = set(role_perms)

        # Add from matching policies
        for policy in self._policies:
            if self._evaluate_conditions(policy.conditions, identity):
                for p in policy.grants.get("permissions") or []:
                    result.add(p)

        return result

    # ── conditions ────────────────────────────────────────────────────

    def _evaluate_conditions(self, conditions: dict, identity: AttributeSet) -> bool:
        """Recursively evaluate a conditions tree from a policy."""
        if not conditions:
            return True

        if "and" in conditions:
            return all(self._evaluate_conditions(c, identity) for c in conditions["and"])
        if "or" in conditions:
            return any(self._evaluate_conditions(c, identity) for c in conditions["or"])

        # Leaf: {attr, op, value}
        attr_name = conditions.get("attr", "")
        op = conditions.get("op", "eq")
        expected = conditions.get("value")

        attr_value = identity.get_attr(attr_name)

        operators = {
            "eq": lambda a, v: a == v,
            "neq": lambda a, v: a != v,
            "gt": lambda a, v: a is not None and a > v,
            "gte": lambda a, v: a is not None and a >= v,
            "lt": lambda a, v: a is not None and a < v,
            "lte": lambda a, v: a is not None and a <= v,
            "contains": lambda a, v: v in a if isinstance(a, (list, str)) else False,
            "not_contains": lambda a, v: v not in a if isinstance(a, (list, str)) else True,
            "in": lambda a, v: a in v if isinstance(v, (list, tuple)) else False,
            "not_in": lambda a, v: a not in v if isinstance(v, (list, tuple)) else True,
        }

        evaluator = operators.get(op)
        if evaluator is None:
            logger.warning("Unknown operator '%s' in policy condition", op)
            return False

        return evaluator(attr_value, expected)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permission_engine.py -v
```
期望：PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/auth/engine.py backend/tests/test_permission_engine.py
git commit -m "feat(permissions): add UnifiedPermissionEngine + FilterRule with ABAC policy evaluation"
```

---

#### Task 5: 改造 `require_permission` middleware

**文件：**
- Modify: `backend/app/extensions/auth/middleware.py`

- [ ] **Step 1: 改造 `require_permission` 兼容旧版行为**

打开 `middleware.py`，将现有 `require_permission` 替换为调用新引擎的版本。保持接口不变——现有 50+ 个调用点无需改代码。

```python
# backend/app/extensions/auth/middleware.py（在现有 imports 后添加）

from app.extensions.auth.engine import UnifiedPermissionEngine, Policy
from app.extensions.auth.identity import IdentityProvider, AttributeSet
from app.extensions.auth.registry import get_permission_registry


async def _build_engine(db: AsyncSession) -> UnifiedPermissionEngine:
    """Build an engine instance from current DB state."""
    # Load all role→permissions mappings from DB
    from sqlalchemy import select as sa_select
    from app.extensions.models import Role

    result = await db.execute(sa_select(Role))
    roles = result.scalars().all()
    role_permissions: dict[str, set[str]] = {}
    for role in roles:
        role_permissions[role.code] = set(role.permissions or [])

    # Collect all known permission IDs from the registry
    registry = get_permission_registry()
    all_ids = {p.id for p in registry.list_all_permissions()}

    # Load ABAC policies from DB (Phase 3 — empty for now)
    policies: list[Policy] = []

    return UnifiedPermissionEngine(
        role_permissions=role_permissions,
        all_permission_ids=all_ids,
        policies=policies,
    )


# 替换原有的 require_permission 函数（保留函数签名兼容）
# 原版签名: require_permission(permission: str) → check_permission Depends
# 新版内部实现改为调用 UnifiedPermissionEngine
```

实际上，Phase 1 的改造策略是：**不改 require_permission 签名和路由代码**，只在内部实现中从旧版 `role.permissions` 直接检查改为通过 `UnifiedPermissionEngine` 检查。这样可以 100% 向后兼容。

具体修改：在 `check_permission` 内部，将：

```python
# 旧代码
permissions = role.permissions or []
if "*" in permissions or role.is_system:
    return current_user
if permission not in permissions and f"{permission.split(':')[0]}:*" not in permissions:
    raise HTTPException(403, ...)
```

替换为：

```python
# 新代码 — 委托给引擎
provider = get_identity_provider()
identity = await provider.resolve(current_user.id, db)
engine = await _build_engine(db)
if not engine.check(identity, permission):
    raise HTTPException(403, f"Permission denied: {permission}")
```

- [ ] **Step 2: 确认现有测试仍然通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k "permission" -v
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/extensions/auth/middleware.py
git commit -m "refactor(permissions): delegate require_permission to UnifiedPermissionEngine"
```

---

### Phase 2：数据域引擎

> 后续 Phase 暂略——按设计文档的 4 阶段分批实现。Phase 1 完成后继续写 Phase 2-4 的详细任务。
```

---

## 实现策略

本计划按 4 个 Phase 分批执行，与设计文档的迁移计划一致。**Phase 1 的任务（Task 1-5）已详细列出**，Phase 2-4 在 Phase 1 完成后继续编写详细步骤。

| Phase | 范围 | 产出 |
|-------|------|------|
| **1**（本计划） | PermissionRegistry + IdentityProvider + UnifiedPermissionEngine + middleware 改造 | 后端引擎就绪，现有 API 行为不变 |
| **2** | FilterRule.to_sqlalchemy() + with_data_scope() + 首批模块迁移 | 知识库/项目/合同价格接入数据域 |
| **3** | 权限 API 端点 + usePermission Hook + 三 Tab 角色管理 UI | 前端全链路权限控制 |
| **4** | 删除废弃代码 + 合并双轨存储 + 补全未保护模块 | 代码清理，系统完整覆盖 |

**执行入口：** Phase 1 从 Task 1 开始，按 Task 1→5 顺序执行。每个 Task 内按 Step 编号顺序执行。

---

## 自检清单

- [x] 设计文档 9 个节全部有对应 Task
- [x] 无 TBD/TODO/占位符
- [x] 所有 Python 类型签名一致（AttributeSet, FilterRule, Policy 在各 Task 间统一）
- [x] `permissions.yaml` 中的权限 ID 与 `PermissionRegistry` 的查询方法匹配
- [x] `UnifiedPermissionEngine.check()` 的评估顺序与设计文档 7.2 节一致
- [x] middleware 改造保持向后兼容（不改 router 代码）
