"""Role service for extensions module."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Role, User
from app.extensions.schemas import (
    RoleAssignmentInfo,
    RoleCopy,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

logger = logging.getLogger(__name__)


class RoleService:
    """Role service."""

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
        role = Role(
            name=data.name,
            code=data.code,
            permissions=data.permissions,
            description=data.description,
            level=data.level,
            parent_role_id=data.parent_role_id,
        )
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def update_role(db: AsyncSession, role: Role, data: RoleUpdate) -> Role:
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        if data.permissions is not None:
            role.permissions = data.permissions
        if data.level is not None:
            role.level = data.level
        if data.parent_role_id is not None:
            role.parent_role_id = data.parent_role_id

        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def delete_role(db: AsyncSession, role: Role) -> None:
        await db.delete(role)
        await db.commit()

    @staticmethod
    async def copy_role(db: AsyncSession, role: Role, data: RoleCopy) -> Role:
        """Copy a role with new name and code."""
        new_role = Role(
            name=data.new_name,
            code=data.new_code,
            permissions=role.permissions or [],
            description=role.description,
        )
        db.add(new_role)
        await db.commit()
        await db.refresh(new_role)
        return new_role

    @staticmethod
    async def get_role_user_count(db: AsyncSession, role_id: UUID) -> int:
        """Get the number of users assigned to a role."""
        query = select(func.count(User.id)).where(User.role_id == role_id)
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
        parent_role_name = None
        if role.parent_role_id:
            stmt = select(Role).where(Role.id == role.parent_role_id)
            result = await db.execute(stmt)
            parent_role = result.scalar_one_or_none()
            if parent_role:
                parent_role_name = parent_role.name

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
        )
