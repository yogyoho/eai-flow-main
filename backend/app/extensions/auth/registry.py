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
    """Loads and serves the module-permission registry from a YAML file."""

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

    def _check_reload(self) -> bool:
        if not self._path.exists():
            return False
        current_mtime = self._path.stat().st_mtime
        if current_mtime > self._mtime:
            logger.info("permissions.yaml changed, reloading registry")
            self._load()
            return True
        return False


_registry: PermissionRegistry | None = None


def get_permission_registry() -> PermissionRegistry:
    global _registry
    if _registry is None:
        _registry = PermissionRegistry()
    _registry._check_reload()
    return _registry
