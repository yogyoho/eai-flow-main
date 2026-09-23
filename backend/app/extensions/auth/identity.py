"""Identity provider - resolves a user to an AttributeSet for ABAC evaluation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Department, ProjectMember, Role, User, UserDepartment

logger = logging.getLogger(__name__)


@dataclass
class AttributeSet:
    """User identity expressed as an extensible attribute set for ABAC evaluation."""

    user_id: str
    username: str

    role_code: str | None = None
    role_level: int = 0
    dept_id: str | None = None
    dept_ids: list[str] = field(default_factory=list)

    member_projects: list[str] = field(default_factory=list)
    project_roles: dict[str, str] = field(default_factory=dict)

    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize all relevant fields to a dict for policy evaluation."""
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
        """Resolve a dotted attribute path, e.g. 'labels.region'."""
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

    @classmethod
    def from_current_user(cls, user, *, role_code: str | None, member_projects: list[str] | None = None) -> AttributeSet:
        """由 gateway CurrentUser 构造身份——**不是**授权判定的正典路径，别拿它做鉴权。

        EAI-CUSTOM (2026-09-23, I-3)：它此前是 ``GET /api/permissions/scope`` 的身份来源，
        现已改用 ``IdentityProvider.resolve``。原因（也是"别再用它做鉴权"的理由）：本方法的
        ``dept_ids`` 取自 ``users.dept_id``（单值）、``member_projects`` 缺省为空，而正典
        ``resolve`` 取 ``user_departments`` 关联表 / ``project_members`` 查库——两者不等价：
        ``dept_ids`` 方向**更宽**（关联表无行时本方法仍给出单值），``member_projects`` 方向
        **更窄**（恒空会让 ``id IN $identity.member_projects`` 退化成 ``= ANY(ARRAY[])`` = FALSE，
        丢分支）。鉴权路径用它会得到与平台不一致的判定。

        **现状：本仓零调用点、零测试**（I-3 之后成为孤儿）。保留是待裁事项，不是遗漏——
        若最终确认不再需要，应连同删除；若保留，请只用于非鉴权用途（展示/调试）。

        ``role_code`` 的告警仍然有效：**必须**由调用方从 ``roles.code`` 解析后传入，
        **不得传 ``user.role_name``**——实测 ``roles.name`` 是显示名（DB: ``superadmin`` →
        ``"超级管理员"``），而 ``DataScopeEngine._role_data_scopes`` 由
        ``registry.list_role_codes()``（角色 **code**）建键；传 name 会恒落空 → 恒
        ``none_allow``，且原因极难定位。该参数**刻意不给默认值**：宁可调用点 TypeError，
        也不要静默 404。
        """
        return cls(
            user_id=str(user.id),
            username=str(user.username),
            role_code=role_code,
            dept_ids=[str(user.dept_id)] if getattr(user, "dept_id", None) else [],
            member_projects=member_projects or [],
        )


class TagResolver(Protocol):
    """Protocol for pluggable identity tag resolvers."""

    name: str

    async def resolve(self, user_id: str, db: AsyncSession) -> dict:
        """Return {tags: [...], labels: {...}, extra: {...}}."""
        ...


class DefaultTagResolver:
    """从用户角色/部门派生默认标签（role:<code> / dept:<name>）——不改 schema，给 identity.tags 真实值。

    EAI-CUSTOM (标签池): 若无其它显式标签源，用户至少拥有角色与部门的自动标签，
    供策略 conditions 的 tags 属性使用（如 tags contains role:dept_head）。
    """

    name = "default-tags"

    async def resolve(self, user_id: str, db: AsyncSession) -> dict:
        tags: list[str] = []
        stmt = select(User).where(User.id == user_id)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if user is None:
            return {"tags": [], "labels": {}, "extra": {}}
        # EAI-CUSTOM (标签池 A): 显式用户标签（admin 在用户管理设置）优先并入
        if user.tags:
            tags.extend(t for t in user.tags if t)
        if user.role_id:
            role = await db.get(Role, user.role_id)
            if role and role.code:
                tags.append(f"role:{role.code}")
        stmt = select(UserDepartment).where(UserDepartment.user_id == user.id)
        uds = (await db.execute(stmt)).scalars().all()
        for ud in uds:
            dept = await db.get(Department, ud.dept_id)
            if dept and dept.name:
                tags.append(f"dept:{dept.name}")
        return {"tags": tags, "labels": {}, "extra": {}}


class IdentityProvider:
    """Resolves a user to an AttributeSet for permission evaluation."""

    def __init__(self) -> None:
        self._tag_resolvers: list[TagResolver] = []

    def register_tag_resolver(self, resolver: TagResolver) -> None:
        """Register a pluggable tag resolver to enrich the AttributeSet."""
        self._tag_resolvers.append(resolver)

    async def resolve(self, user_id: str, db: AsyncSession) -> AttributeSet:
        """Load user identity from DB and return a populated AttributeSet."""
        # Load User
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")

        attrs = AttributeSet(
            user_id=str(user.id),
            username=str(user.username),
            dept_id=str(user.dept_id) if user.dept_id else None,
        )

        # Load Role
        if user.role_id:
            role = await db.get(Role, user.role_id)
            if role:
                attrs.role_code = role.code
                attrs.role_level = role.level or 0
            else:
                # EAI-CUSTOM (2026-09-23, M-2): role_id 有值却查不到 Role → role_code 静默为
                # None → 所有按角色解析的数据范围恒 none_allow → 调用方拿到 404「不在可见
                # 范围内」，而真因是角色行缺失（roles 表由注册表启动时校准，不同步即发生）。
                # 本文件第 77-79 行的家规是「宁可调用点 TypeError，也不要静默 404」，
                # 此处至少按 middleware.py 对同类情形的先例留痕，别让原因只能靠猜。
                logger.warning(
                    "Identity resolve: user=%s 的 role_id=%s 在 roles 表中查不到 → role_code 置空，按角色解析的数据范围将恒为 none_allow",
                    user.id,
                    user.role_id,
                )

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


_identity_provider: IdentityProvider | None = None


def get_identity_provider() -> IdentityProvider:
    """Return the singleton IdentityProvider instance."""
    global _identity_provider
    if _identity_provider is None:
        _identity_provider = IdentityProvider()
        # EAI-CUSTOM (标签池): 注册默认派生标签 resolver（role:* / dept:*），生产默认启用
        _identity_provider.register_tag_resolver(DefaultTagResolver())
    return _identity_provider
