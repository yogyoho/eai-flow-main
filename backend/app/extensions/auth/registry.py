"""Permission registry - loads permissions.yaml, serves permission metadata."""
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
class PageDef:
    id: str
    display_name: str
    operations: list[PermissionPoint] = field(default_factory=list)


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


@dataclass
class NavModule:
    key: str
    display_name: str
    nav_id: str
    admin_only: bool
    pages: list[PageDef] = field(default_factory=list)
    operations: list[PermissionPoint] = field(default_factory=list)
    data_scopes: list[DataScope] = field(default_factory=list)

    @property
    def permissions(self) -> list[PermissionPoint]:
        """Backward compatibility alias for operations."""
        return self.operations

    @permissions.setter
    def permissions(self, value: list[PermissionPoint]) -> None:
        self.operations = value


class PermissionRegistry:
    """Loads and serves the module-permission registry from a YAML file."""

    def __init__(self, yaml_path: str | None = None, overlay_path: str | None = None):
        """加载权限注册表。

        Args:
            yaml_path: 主权限配置文件路径（permissions.yaml）
            overlay_path: 角色自定义覆盖文件路径（roles_custom.yaml），
                          用于覆盖/扩展内置角色、添加自定义角色、禁用角色
        """
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

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("permissions.yaml not found at %s, registry is empty", self._path)
            return
        self._mtime = self._path.stat().st_mtime
        self._disabled_roles.clear()
        with open(self._path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        self._parse_modules(data.get("modules") or {})
        self._parse_roles(data.get("roles") or {})
        self._parse_project_roles(data.get("project_roles") or {})

        # 解析主文件中的 disabled_roles
        for code in (data.get("disabled_roles") or []):
            self._role_defaults.pop(code, None)
            self._disabled_roles.add(code)

        # 加载角色自定义覆盖文件（roles_custom.yaml）
        if self._overlay_path.exists():
            self._overlay_mtime = self._overlay_path.stat().st_mtime
            with open(self._overlay_path, encoding="utf-8") as fh:
                overlay = yaml.safe_load(fh) or {}
            self._apply_overlay(overlay)
        else:
            # 覆盖文件不存在时重置 mtime，以便文件后续出现时能被检测到
            self._overlay_mtime = 0.0

    def _parse_modules(self, modules_data: dict) -> None:
        self.modules.clear()
        self._all_permissions.clear()
        self._admin_only.clear()

        for module_key, module_data in modules_data.items():
            nav_id = module_data.get("nav_id", "")

            # Parse pages (v2/v3 format)
            # v3: operations are nested under pages
            # v2: pages and operations are separate lists
            all_ops: list[PermissionPoint] = []
            pages: list[PageDef] = []
            for p in module_data.get("pages") or []:
                page_ops: list[PermissionPoint] = []
                for op in (p.get("operations") or []):
                    perm = PermissionPoint(
                        id=op["id"],
                        display_name=op.get("display_name", op["id"]),
                        description=op.get("description"),
                        admin_only=op.get("admin_only", False),
                        module=module_key,
                    )
                    page_ops.append(perm)
                    all_ops.append(perm)
                    self._all_permissions[perm.id] = perm
                    if perm.admin_only:
                        self._admin_only.append(perm)

                pages.append(PageDef(
                    id=p["id"],
                    display_name=p.get("display_name", p["id"]),
                    operations=page_ops,
                ))

            # Parse module-level operations (v2) or permissions (v1) — backward compat
            ops_data = module_data.get("operations") or module_data.get("permissions") or []
            for p in ops_data:
                perm = PermissionPoint(
                    id=p["id"],
                    display_name=p.get("display_name", p["id"]),
                    description=p.get("description"),
                    admin_only=p.get("admin_only", False),
                    module=module_key,
                )
                all_ops.append(perm)
                self._all_permissions[perm.id] = perm
                if perm.admin_only:
                    self._admin_only.append(perm)

            # Parse data_scopes (same in v1 and v2)
            data_scopes: list[DataScope] = []
            for ds in module_data.get("data_scopes") or []:
                data_scopes.append(DataScope(
                    id=ds["id"],
                    display_name=ds.get("display_name", ds["id"]),
                    rule_template=ds.get("rule_template") or {},
                    module=module_key,
                ))

            nm = NavModule(
                key=module_key,
                display_name=module_data.get("display_name", module_key),
                nav_id=nav_id,
                admin_only=module_data.get("admin_only", False),
                pages=pages,
                operations=all_ops,
                data_scopes=data_scopes,
            )
            self.modules[module_key] = nm

    def _parse_roles(self, roles_data: dict) -> None:
        self._role_defaults.clear()
        for role_code, role_data in roles_data.items():
            self._role_defaults[role_code] = {
                "display_name": role_data.get("display_name", role_code),
                "is_system": role_data.get("is_system", False),
                "level": role_data.get("level", 10),
                "nav": list(role_data.get("nav") or []),
                "pages": list(role_data.get("pages") or []),
                "permissions": list(role_data.get("permissions") or []),
                "data_scopes": list(role_data.get("data_scopes") or []),
            }

    def get_permission(self, permission_id: str) -> PermissionPoint | None:
        return self._all_permissions.get(permission_id)

    def list_all_permissions(self) -> list[PermissionPoint]:
        return list(self._all_permissions.values())

    def list_admin_only_permissions(self) -> list[PermissionPoint]:
        return list(self._admin_only)

    def list_modules(self) -> list[tuple[str, NavModule]]:
        return list(self.modules.items())

    def get_data_scope(self, scope_id: str) -> DataScope | None:
        for mp in self.modules.values():
            for ds in mp.data_scopes:
                if ds.id == scope_id:
                    return ds
        return None

    def get_role_defaults(self, role_code: str) -> dict | None:
        return self._role_defaults.get(role_code)

    def list_nav_modules(self) -> list[NavModule]:
        """Return all modules that have nav_id (i.e. appear in navigation)."""
        return [m for m in self.modules.values() if m.nav_id]

    def get_nav_ids_for_role(self, role_code: str) -> list[str]:
        """Get allowed nav IDs for a role from role defaults."""
        defaults = self._role_defaults.get(role_code)
        if defaults is None:
            return []
        return list(defaults.get("nav") or [])

    def get_page_ids_for_role(self, role_code: str) -> list[str]:
        """Get allowed page IDs for a role from role defaults."""
        defaults = self._role_defaults.get(role_code)
        if defaults is None:
            return []
        return list(defaults.get("pages") or [])

    def resolve_role_permissions(self, role_code: str) -> set[str]:
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

    def _parse_project_roles(self, project_roles_data: dict) -> None:
        """解析项目级角色（project_roles）配置。"""
        self._project_roles = {
            code: list(perms or []) for code, perms in project_roles_data.items()
        }

    def _apply_overlay(self, overlay_data: dict) -> None:
        """应用角色自定义覆盖：合并/覆盖角色定义，处理禁用角色列表。"""
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
        """返回所有已注册的角色代码列表。"""
        return list(self._role_defaults.keys())

    def get_data_scopes_for_role(self, role_code: str) -> list[str]:
        """获取指定角色的数据范围列表。"""
        defaults = self._role_defaults.get(role_code)
        if defaults is None:
            return []
        return list(defaults.get("data_scopes") or [])

    def get_project_roles(self) -> dict[str, list[str]]:
        """返回项目级角色及其权限映射。"""
        return {code: list(perms) for code, perms in self._project_roles.items()}

    def is_role_disabled(self, role_code: str) -> bool:
        """检查指定角色是否已被禁用。"""
        return role_code in self._disabled_roles

    def reload(self) -> None:
        """强制重新加载注册表（包括主文件和覆盖文件）。"""
        self._load()

    def _check_reload(self) -> bool:
        reloaded = False
        if self._path.exists() and self._path.stat().st_mtime > self._mtime:
            reloaded = True
        # 检测覆盖文件变更：mtime 变化，或文件从存在变为不存在
        if self._overlay_path.exists():
            if self._overlay_path.stat().st_mtime > self._overlay_mtime:
                reloaded = True
        elif self._overlay_mtime > 0:
            # 覆盖文件之前存在，现已被删除
            reloaded = True
        if reloaded:
            logger.info("permissions.yaml / roles_custom.yaml changed, reloading registry")
            self._load()
        return reloaded


_registry: PermissionRegistry | None = None


def get_permission_registry() -> PermissionRegistry:
    global _registry
    if _registry is None:
        _registry = PermissionRegistry()
    _registry._check_reload()
    return _registry
