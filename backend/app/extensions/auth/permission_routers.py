"""Permission API endpoints — registry, current user permissions, role config."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.engine import UnifiedPermissionEngine
from app.extensions.auth.identity import get_identity_provider
from app.extensions.auth.middleware import require_permission
from app.extensions.auth.registry import get_permission_registry
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/registry")
async def get_registry(
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    """Return all permission points, grouped by module with 3-level tree (Module → Page → Operation)."""
    registry = get_permission_registry()
    modules = []
    for module_key, mp in registry.list_modules():
        modules.append({
            "key": module_key,
            "display_name": mp.display_name,
            "pages": [
                {
                    "id": page.id,
                    "display_name": page.display_name,
                    "operations": [
                        {
                            "id": op.id,
                            "display_name": op.display_name,
                            "admin_only": op.admin_only,
                        }
                        for op in page.operations
                    ],
                }
                for page in mp.pages
            ],
            "permissions": [
                {
                    "id": p.id,
                    "display_name": p.display_name,
                    "description": p.description,
                    "admin_only": p.admin_only,
                }
                for p in mp.permissions
            ],
            "data_scopes": [
                {
                    "id": ds.id,
                    "display_name": ds.display_name,
                }
                for ds in mp.data_scopes
            ],
        })
    return {"modules": modules}


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

    # EAI-CUSTOM: A3 前端 admin 布局以 is_admin 为准（按角色的 is_system 标志），
    # 不再依赖前端硬编码显示名判权。
    is_admin = bool((registry.get_role_defaults(identity.role_code) or {}).get("is_system"))
    return {
        "permissions": permissions,
        "nav": nav_ids,
        "pages": page_ids,
        "data_scopes": data_scopes,
        "is_admin": is_admin,
        "identity": identity.to_dict(),
    }
