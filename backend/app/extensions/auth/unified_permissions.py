"""Unified permission checking — single entry point for all project RBAC.

Replaces the dual-system (permissions.py + project_permissions.py) with
one function that resolves the effective ProjectRole and maps it to
permissions from the registry (permissions.yaml `project_roles:` section).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.models import ProjectMember
from app.extensions.models.role_permission import ProjectRole
from app.extensions.schemas import CurrentUser

# Legacy slot_type / duty values stored in ProjectMember.phase_duties JSONB → ProjectRole value.
# phase_duties entries carry the machine value under "slot_type" and a display label under "role".
_PHASE_DUTY_ROLE_MAP: dict[str, str] = {
    "lead": ProjectRole.PHASE_LEAD.value,
    "leader": ProjectRole.PHASE_LEAD.value,
    "reviewer": ProjectRole.REVIEWER.value,
    "dept_reviewer": ProjectRole.REVIEWER.value,
    "data_reviewer": ProjectRole.REVIEWER.value,
    "approver": ProjectRole.APPROVER.value,
    "company_reviewer": ProjectRole.APPROVER.value,
    "write": ProjectRole.WRITER.value,
    "writer": ProjectRole.WRITER.value,
}

# Legacy ProjectMember.role values → ProjectRole value (new unified taxonomy).
# The system writes: "owner" (creator), "writer"/"leader" (auto-assign),
# and VALID_MEMBER_ROLES (owner/manager/editor/reviewer/approver/member).
_MEMBER_ROLE_MAP: dict[str, str] = {
    "lead": ProjectRole.PHASE_LEAD.value,
    "leader": ProjectRole.PHASE_LEAD.value,
    "manager": ProjectRole.PHASE_LEAD.value,
    "dept_reviewer": ProjectRole.REVIEWER.value,
    "company_reviewer": ProjectRole.APPROVER.value,
    "editor": ProjectRole.WRITER.value,
    "member": ProjectRole.WRITER.value,
    "write": ProjectRole.WRITER.value,
    "writer": ProjectRole.WRITER.value,
}


async def resolve_user_project_role(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> ProjectRole | None:
    """Resolve a user's effective ProjectRole within a project.

    Priority:
    1. phase_duties override for the given phase_node (slot_type first)
    2. ProjectMember.role (with legacy role mapping)
    3. None (not a member)
    """
    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        return None

    # Phase-scoped role override. phase_duties stores the machine value under
    # "slot_type" (e.g. "leader"/"writer") in current writes, or "duty" in
    # legacy rows; "role" only holds a display label (e.g. "组长"/"组员").
    # Read slot_type → duty → role in that order.
    if phase_node and member.phase_duties:
        phase_duty = member.phase_duties.get(phase_node, {})
        duty_role = phase_duty.get("slot_type") or phase_duty.get("duty") or phase_duty.get("role")
        if duty_role:
            normalised = _PHASE_DUTY_ROLE_MAP.get(duty_role, duty_role)
            try:
                return ProjectRole(normalised)
            except ValueError:
                pass

    # Project-level role (legacy values mapped into the unified taxonomy)
    try:
        return ProjectRole(_MEMBER_ROLE_MAP.get(member.role, member.role))
    except ValueError:
        return None


async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> set[str]:
    """Return the effective permission set for a user in a project."""
    # Admin bypass — system role or wildcard (registry-backed, yaml authority)
    from app.extensions.auth.admin import is_superadmin
    from app.extensions.auth.registry import get_permission_registry

    if await is_superadmin(db, user_id):
        # Admin sees every permission granted to any project role
        registry = get_permission_registry()
        all_perms: set[str] = set()
        for perms in registry.get_project_roles().values():
            all_perms.update(perms)
        return all_perms

    project_role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    if not project_role:
        return set()

    registry = get_permission_registry()
    return set(registry.get_project_roles().get(project_role.value) or [])


async def require_project_permission(
    action: str,
    project_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
    phase_node: str | None = None,
):
    """FastAPI dependency: raise 403 if user lacks action in project."""
    perms = await get_user_permissions(db, user.id, project_id, phase_node)
    if action not in perms:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{action}' required",
        )
    return user


def RequireProjectPerm(action: str):
    """Factory: create a FastAPI dependency for a specific project permission."""
    async def _dep(
        project_id: UUID,
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ):
        return await require_project_permission(action, project_id, user, db)
    return Depends(_dep)


async def _resolve_project_role_str(
    db: AsyncSession, user_id: UUID, project_id: UUID, phase_node: str | None = None,
) -> str | None:
    """Resolve the effective project role as a plain string (or None)."""
    role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    return role.value if role else None


def require_project_member():
    """Dependency: caller must be a member of the path's project (or superadmin).

    Read-level access gate for endpoints under ``/projects/{project_id}/...``.
    Verifies a ``ProjectMember`` row exists for the request's ``project_id``
    (EAI-CUSTOM Task 12: closes IDOR on read endpoints that previously only
    checked ``system:access``). Superadmin bypasses via :func:`is_superadmin`.
    """
    async def _check(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        from app.extensions.auth.admin import is_superadmin

        if await is_superadmin(db, current_user.id):
            return current_user
        project_id = request.path_params.get("project_id")
        if project_id is None:
            raise HTTPException(status_code=400, detail="project_id required in path")
        from uuid import UUID as _UUID

        try:
            pid = _UUID(str(project_id))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid project_id")
        stmt = select(ProjectMember).where(
            ProjectMember.project_id == pid,
            ProjectMember.user_id == current_user.id,
        )
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")
        return current_user

    return _check


def require_resource_permission(action: str):
    """Compat shim: unified_permissions check; returns project role string (old signature).

    Replaces the legacy app.extensions.project.permissions.require_resource_permission.
    """
    async def check(
        current_user: CurrentUser = Depends(get_current_user),
        request: Request = ...,
        db: AsyncSession = Depends(get_db),
    ) -> str | None:
        from app.extensions.auth.cache import (
            get_cached_engine,
            get_cached_identity,
            set_cached_engine,
            set_cached_identity,
        )
        from app.extensions.auth.engine import UnifiedPermissionEngine
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.policy_loader import load_active_policies
        from app.extensions.auth.registry import get_permission_registry

        registry = get_permission_registry()
        provider = get_identity_provider()

        # Identity: resolve once per request and share with require_permission
        # via the request-scoped ContextVar cache (mirrors require_permission).
        identity = get_cached_identity()
        if identity is None:
            identity = await provider.resolve(current_user.id, db)
            set_cached_identity(identity)

        # Registry-based admin bypass (mirrors require_super_admin). Kept explicit
        # so superadmin skips engine construction entirely.
        defaults = registry.get_role_defaults(identity.role_code)
        is_system = bool(defaults and defaults.get("is_system"))
        resolved = registry.resolve_role_permissions(identity.role_code or "")
        if is_system or "*" in resolved:
            return "owner"

        # Base gate: every caller needs global system:access. Routed through the
        # ABAC engine (EAI-CUSTOM L3) so a policy that denies system:access is
        # honored here too — same engine construction / cache as require_permission.
        # NOTE: the project-role ACTION check below stays registry-only by design
        # (spec §4.1/§2) and is NOT routed through the ABAC engine.
        engine = get_cached_engine()
        if engine is None:
            engine = UnifiedPermissionEngine(
                role_permissions={
                    code: registry.resolve_role_permissions(code)
                    for code in registry.list_role_codes()
                },
                all_permission_ids={p.id for p in registry.list_all_permissions()},
                policies=await load_active_policies(db),
            )
            set_cached_engine(engine)
        if not engine.check(identity, "system:access"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Permission denied: system:access required",
            )

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
