"""Permission API endpoints — registry, current user permissions, role config."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.engine import UnifiedPermissionEngine
from app.extensions.auth.identity import get_identity_provider
from app.extensions.auth.middleware import require_permission, resolve_data_scope
from app.extensions.auth.registry import get_permission_registry
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

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
    current_user: CurrentUser = Depends(require_permission("system:access")),
):
    """返回当前用户对某资源的数据范围规则（序列化 FilterRule）。

    EAI-CUSTOM (2026-09-22): 供 OntoStudio 动作层做实例级权限判定
    （设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3）。
    只读、无副作用；``resource`` 为 permissions.yaml 的**模块 key**
    （``ontology`` / ``contract_price`` / …），非 scope id。
    未知资源或角色无 scope → ``none_allow``（fail-closed）。

    判定体走 :func:`app.extensions.auth.middleware.resolve_data_scope`——**与
    ``with_data_scope`` 同一条路径**（超管旁路 + ABAC ``deny_data_scopes`` 扣减）。
    EAI-CUSTOM (2026-09-23, 计划 Task 7 硬性验收项)：此前本端点自建判定，缺那两步，
    其中 deny 扣减那半是 **fail-open**——平台侧读全域封锁而 OntoStudio 的动作无视它。
    一致性由 ``tests/test_permissions_scope_endpoint.py`` 逐态断言（见该文件
    ``test_scope_endpoint_matches_with_data_scope_*``）。

    身份走**正典** ``IdentityProvider.resolve``——与 ``with_data_scope``
    （middleware.py）和同文件的 ``/me`` 同一条路径：``role_code`` 取 ``roles.code``、
    ``dept_ids`` 取 ``user_departments`` 关联表、``member_projects`` 取 ``project_members``。

    I-3 (2026-09-23 质量审查)：此前是本端点**自建身份**（``users.dept_id`` 单值 + 手工
    ``db.get(Role, …)`` 查 role_code），只复刻了半个 ``resolve``——那个自建入口已随本修复
    删除（它零调用方、零测试，留着只会让人照着把这个问题写回来）——于是 ``users.dept_id``
    有值而 ``user_departments`` 无行的用户，当时这里算出的 ``$identity.dept_ids`` 与平台不同
    （**方向按字段分别读，别再当成一句话**）：

    | 字段 | 化简来源 | 偏离方向 |
    |---|---|---|
    | ``dept_ids`` | ``users.dept_id``（单值） vs ``user_departments``（关联表） | **更宽** |
    | ``member_projects`` | 恒 ``[]`` vs ``project_members`` 查库 | **更窄**（丢分支：``= ANY(ARRAY[])`` = FALSE ⇒ fail-closed 拒绝） |

    "更窄"无安全问题（拒绝方向），但两个方向不同，写文档时别合并成"端点结果比平台宽"。
    现在两端同源，这表格只剩历史意义；保留是为了说明为什么不再是这个形态。

    ``require_permission("system:access")`` 与同 router 的 ``/registry``（``role:read``）、
    ``/me``（``system:access``）对齐——此前只挂 ``get_current_user``，比同级松一档。
    """
    # M-3: 未知 resource 与"角色没有配 scope"今天都产出 none_allow，调用方拿到 404 却分不清
    # 是 typo 还是真没授权。注册表能区分"模块不存在"，那就留痕。
    if resource not in {key for key, _ in get_permission_registry().list_modules()}:
        logger.warning("数据范围请求了未注册的资源 key %r（疑似 typo）→ 按 none_allow 拒绝", resource)

    try:
        rule = await resolve_data_scope(current_user, db, resource)
    except ValueError as exc:
        # resolve 对"用户不在库中"（会话有效但用户行已删）抛 ValueError。
        # 取 403 而非 404/401：调用者**已通过认证**（JWT 有效），失败的是它的主体在组织
        # 目录里解析不出来——这是授权上下文问题，不是"资源不存在"，也不是"要重新登录"
        # （401 会让前端进刷新循环，而刷新拿不到任何不同的结果）。
        # 注意：M-1 给本端点挂了 require_permission，它内部**也**会 resolve 一次（同请求缓存），
        # 故用户行缺失的常见情形在依赖层就已失败；这里兜的是两次 resolve 之间的窗口。
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"无法解析调用者身份: {exc}") from exc

    return {"resource": resource, "rule": rule.to_wire()}
