"""OntoStudio 鉴权占位——S1 Task 2 替换为 JWT 共享密钥验签.

EAI-CUSTOM: ontology 包自 backend/app/extensions/ 迁出独立
（设计: docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）。
原 gateway 侧依赖 = app.extensions.auth.middleware.require_permission（HS256 JWT + RBAC
UnifiedPermissionEngine）+ app.extensions.schemas.CurrentUser；独立服务 Task 1 阶段无鉴权
（仅本地/内网开发态），此占位保住路由依赖声明的形状（require_permission(perm) → CurrentUser），
恒放行匿名用户。
Task 2 落地: env ONTOSTUDIO_JWT_SECRET（与 gateway 同源注入）HS256 验签 + Bearer/cookie
双通道 + system:access token-claims 判定；/health 豁免见 app/main.py。
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class CurrentUser(BaseModel):
    """Current user schema（字段形状与 gateway app.extensions.schemas.CurrentUser 一致）."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str | None = None
    role_id: uuid.UUID | None = None
    role_name: str | None = None
    dept_id: uuid.UUID | None = None
    dept_name: str | None = None


def require_permission(permission: str):
    """占位依赖工厂：无鉴权直通（Task 2 落地 JWT 验签后替换本实现）。"""

    async def _anonymous() -> CurrentUser:
        return CurrentUser(id=uuid.uuid4(), username="anonymous", email="anonymous@local")

    return _anonymous
