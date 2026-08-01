"""Role service for extensions module."""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from uuid import UUID

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.registry import get_permission_registry
from app.extensions.models import Role, User
from app.extensions.schemas import (
    RoleAssignmentInfo,
    RoleCopy,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

logger = logging.getLogger(__name__)


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


class RoleService:
    """Role service."""

    _store: RoleOverlayStore | None = None

    @classmethod
    def _overlay(cls) -> RoleOverlayStore:
        if cls._store is None:
            cls._store = RoleOverlayStore()
        return cls._store

    @staticmethod
    async def get_role_by_id(db: AsyncSession, role_id: UUID) -> Role | None:
        stmt = select(Role).where(Role.id == role_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_role_by_code(db: AsyncSession, code: str) -> Role | None:
        stmt = select(Role).where(Role.code == code)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_roles(db: AsyncSession, skip: int = 0, limit: int = 100) -> tuple[list[Role], int]:
        query = select(Role).offset(skip).limit(limit).order_by(Role.created_at.desc())
        result = await db.execute(query)
        roles = result.scalars().all()

        count_query = select(func.count(Role.id))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(roles), total

    @staticmethod
    async def create_role(db: AsyncSession, data: RoleCreate) -> Role:
        store = RoleService._overlay()
        mtime_before = store.mtime()  # EAI-CUSTOM (I1): 读前捕获 mtime，乐观锁才能覆盖读-写窗口
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
        store.write(overlay, expect_mtime=mtime_before)
        store.notify_registry_reload()
        registry = get_permission_registry()
        await _calibrate_single_role(db, registry, data.code)
        return await RoleService.get_role_by_code(db, data.code)

    @staticmethod
    async def update_role(db: AsyncSession, role: Role, data: RoleUpdate) -> Role:
        store = RoleService._overlay()
        mtime_before = store.mtime()  # EAI-CUSTOM (I1): 读前捕获 mtime，乐观锁才能覆盖读-写窗口
        overlay = store.read()
        code = role.code
        entry = overlay["roles"].get(code)
        if entry is None:
            # 内置角色首次编辑 → 从 registry 默认值构建 overlay 条目，
            # 保留 data_scopes/is_system，并保留 #inherit 标记（不展平继承）
            defaults = get_permission_registry().get_role_defaults(code) or {}
            entry = {
                "display_name": defaults.get("display_name", role.name),
                "permissions": list(defaults.get("permissions") or role.permissions or []),
                "nav": defaults.get("nav") or role.nav or [],
                "data_scopes": defaults.get("data_scopes") or [],
                "is_system": defaults.get("is_system", bool(role.is_system)),
                "level": defaults.get("level", role.level or 10),
                "description": defaults.get("description", role.description),
            }
            overlay["roles"][code] = entry
        if data.name is not None:
            entry["display_name"] = data.name
        if data.permissions is not None:
            # EAI-CUSTOM (I3): 若前端回传的权限集与当前已解析结果一致（仅改名称等），保留 overlay 中
            # 的 #inherit 标记，避免展平继承链导致后续父角色权限变更不再传播
            resolved_current = get_permission_registry().resolve_role_permissions(code)
            if set(data.permissions) != resolved_current:
                entry["permissions"] = list(data.permissions)
        if data.nav is not None:
            entry["nav"] = list(data.nav)
        if data.level is not None:
            entry["level"] = data.level
        if data.description is not None:
            entry["description"] = data.description
        # EAI-CUSTOM (U4): data scopes 写透到 overlay（先校验 scope id 必须存在于 registry，deny-by-default 之外的未知 id 一律拒绝）
        if data.data_scopes is not None:
            registry = get_permission_registry()
            invalid = [sid for sid in data.data_scopes if registry.get_data_scope(sid) is None]
            if invalid:
                raise ValueError(f"Unknown data scope ids: {invalid}")
            entry["data_scopes"] = list(data.data_scopes)
        store.write(overlay, expect_mtime=mtime_before)
        store.notify_registry_reload()
        registry = get_permission_registry()
        await _calibrate_single_role(db, registry, code)
        return await RoleService.get_role_by_code(db, code)

    @staticmethod
    async def delete_role(db: AsyncSession, role: Role) -> None:
        store = RoleService._overlay()
        mtime_before = store.mtime()  # EAI-CUSTOM (I1): 读前捕获 mtime，乐观锁才能覆盖读-写窗口
        overlay = store.read()
        code = role.code
        if code in overlay["roles"]:
            overlay["roles"].pop(code, None)
        else:
            # 内置角色 → tombstone（disabled_roles）
            disabled = overlay.get("disabled_roles") or []
            if code not in disabled:
                overlay["disabled_roles"] = disabled + [code]
        store.write(overlay, expect_mtime=mtime_before)
        store.notify_registry_reload()
        await db.delete(role)
        await db.commit()

    @staticmethod
    async def copy_role(db: AsyncSession, role: Role, data: RoleCopy) -> Role:
        store = RoleService._overlay()
        mtime_before = store.mtime()  # EAI-CUSTOM (I1): 读前捕获 mtime，乐观锁才能覆盖读-写窗口
        overlay = store.read()
        if data.new_code in overlay["roles"]:
            raise ValueError(f"Role code already exists: {data.new_code}")
        from app.extensions.auth.registry import get_permission_registry

        registry = get_permission_registry()
        src_perms = sorted(registry.resolve_role_permissions(role.code))
        src_defaults = registry.get_role_defaults(role.code) or {}
        overlay["roles"][data.new_code] = {
            "display_name": data.new_name,
            "permissions": src_perms,
            "nav": src_defaults.get("nav") or [],
            "data_scopes": src_defaults.get("data_scopes") or [],
            "level": src_defaults.get("level", 10),
            "description": role.description,
        }
        store.write(overlay, expect_mtime=mtime_before)
        store.notify_registry_reload()
        await _calibrate_single_role(db, registry, data.new_code)
        return await RoleService.get_role_by_code(db, data.new_code)

    @staticmethod
    async def get_role_user_count(db: AsyncSession, role_id: UUID) -> int:
        """Get the number of active (non-soft-deleted) users assigned to a role."""
        query = select(func.count(User.id)).where(
            User.role_id == role_id,
            User.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def get_all_role_assignments(db: AsyncSession) -> list[RoleAssignmentInfo]:
        """Get all roles with their user counts."""
        roles_query = select(Role)
        roles_result = await db.execute(roles_query)
        roles = roles_result.scalars().all()

        assignments = []
        for role in roles:
            user_count = await RoleService.get_role_user_count(db, role.id)
            assignments.append(
                RoleAssignmentInfo(
                    role_id=role.id,
                    role_name=role.name,
                    user_count=user_count,
                    permissions=role.permissions or [],
                )
            )
        return assignments

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


async def _calibrate_single_role(db: AsyncSession, registry, code: str) -> None:
    """Recalibrate a single DB role row as a mirror of the registry (yaml+overlay)."""
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
            description=defaults.get("description"),
        ))
    else:
        r = await RoleService.get_role_by_code(db, code)
        if r:
            r.name = defaults.get("display_name", code)
            r.permissions = resolved
            r.is_system = defaults.get("is_system", False)
            r.level = defaults.get("level", 10)
            r.nav = defaults.get("nav") or []
            r.description = defaults.get("description")
    await db.commit()
