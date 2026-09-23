"""Permission API endpoints — registry, current user permissions, role config."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.engine import UnifiedPermissionEngine
from app.extensions.auth.identity import AttributeSet, get_identity_provider
from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.auth.registry import get_permission_registry
from app.extensions.database import get_db
from app.extensions.models import Role
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
        modules.append(
            {
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
            }
        )
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
    role_permissions = {code: registry.resolve_role_permissions(code) for code in registry.list_role_codes()}
    all_ids = {p.id for p in registry.list_all_permissions()}

    # EAI-CUSTOM: Load active ABAC policies via shared loader so /me matches
    # require_permission enforcement exactly (fixes /me drift bug — previously
    # /me omitted policy-granted and policy-denied permissions).
    from app.extensions.auth.policy_loader import load_active_policies

    engine = UnifiedPermissionEngine(
        role_permissions=role_permissions,
        all_permission_ids=all_ids,
        policies=await load_active_policies(db),
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

    # EAI-CUSTOM: A3 前端 admin 布局以 is_admin 为准；后端超管定义 = is_system 标志
    # 或通配权限 "*"（见 middleware.require_super_admin），二者其一即视为 admin。
    # resolve_role_permissions 已展开 #inherit，继承来的通配 "*" 同样被覆盖。
    resolved_perms = registry.resolve_role_permissions(identity.role_code or "")
    is_admin = bool((registry.get_role_defaults(identity.role_code) or {}).get("is_system")) or "*" in resolved_perms
    return {
        "permissions": permissions,
        "nav": nav_ids,
        "pages": page_ids,
        "data_scopes": data_scopes,
        "is_admin": is_admin,
        "identity": identity.to_dict(),
    }


@router.get("/scope")
async def get_data_scope(
    resource: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """返回当前用户对某资源的数据范围规则（序列化 FilterRule）。

    EAI-CUSTOM (2026-09-22): 供 OntoStudio 动作层做实例级权限判定
    （设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3）。
    只读、无副作用；``resource`` 为 permissions.yaml 的**模块 key**
    （``ontology`` / ``contract_price`` / …），非 scope id。
    未知资源或角色无 scope → ``none_allow``（fail-closed）。

    ``role_code`` 取 ``roles.code``，**不是** ``CurrentUser.role_name``——后者装的是
    ``roles.name`` 显示名（实测 ``superadmin`` → ``"超级管理员"``），与 registry 的角色
    code 不同名，直接拿来查 ``_role_data_scopes`` 会恒 ``none_allow``。依据见
    ``AttributeSet.from_current_user`` 的 docstring。

    ⚠️ 身份字段面注意：本端点用 ``AttributeSet.from_current_user`` 构造身份，其中
    ``dept_ids`` 取自 ``users.dept_id``（单值），``member_projects`` 恒为空。二者与平台
    ``with_data_scope`` 用的**正典身份**（``IdentityProvider.resolve``：``user_departments``
    关联表 / ``project_members`` 查库）并不等价——对 ``dept_id`` 有值但 ``user_departments``
    无行的用户，本端点算出的 ``$identity.dept_ids`` 会比正典**更宽**。
    因此：**模板里引用 ``$identity.dept_ids`` / ``$identity.member_projects`` 的资源，
    不得把本端点的结果当作权威过滤条件**（本体动作层的 ``ontology_all`` 是空模板＝全量，
    不受影响）。补齐二者需调用方查库后传入，见 ``from_current_user``。
    """
    role_code: str | None = None
    if current_user.role_id is not None:
        role = await db.get(Role, current_user.role_id)
        if role is not None:
            role_code = role.code

    engine = DataScopeEngine.from_registry()
    identity = AttributeSet.from_current_user(current_user, role_code=role_code)
    rule = engine.get_data_scope(identity, resource)
    return {"resource": resource, "rule": rule.to_wire()}
