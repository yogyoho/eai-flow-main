"""User-Department association service for extensions module."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Department, User, UserDepartment

logger = logging.getLogger(__name__)


class UserDepartmentService:
    """User-Department association service."""

    @staticmethod
    async def add_user_to_dept(
        db: AsyncSession,
        user_id: UUID,
        dept_id: UUID,
        is_primary: bool = False,
    ) -> UserDepartment:
        """Add user to a department."""
        existing = await UserDepartmentService.get_association(db, user_id, dept_id)
        if existing:
            return existing

        ud = UserDepartment(user_id=user_id, dept_id=dept_id, is_primary=is_primary)
        db.add(ud)
        await db.commit()
        await db.refresh(ud)
        return ud

    @staticmethod
    async def remove_user_from_dept(db: AsyncSession, user_id: UUID, dept_id: UUID) -> bool:
        """Remove user from a department. Returns True if removed, False if not found."""
        stmt = select(UserDepartment).where(
            UserDepartment.user_id == user_id,
            UserDepartment.dept_id == dept_id,
        )
        result = await db.execute(stmt)
        ud = result.scalar_one_or_none()
        if not ud:
            return False
        await db.delete(ud)
        await db.commit()
        return True

    @staticmethod
    async def set_primary_dept(db: AsyncSession, user_id: UUID, dept_id: UUID) -> None:
        """Set a department as the primary department for a user."""
        stmt = select(UserDepartment).where(UserDepartment.user_id == user_id)
        result = await db.execute(stmt)
        all_ud = result.scalars().all()

        for ud in all_ud:
            ud.is_primary = ud.dept_id == dept_id
        await db.commit()

    @staticmethod
    async def get_association(db: AsyncSession, user_id: UUID, dept_id: UUID) -> UserDepartment | None:
        """Get a specific user-department association."""
        stmt = select(UserDepartment).where(
            UserDepartment.user_id == user_id,
            UserDepartment.dept_id == dept_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_departments(db: AsyncSession, user_id: UUID) -> list[UserDepartment]:
        """Get all department associations for a user."""
        stmt = select(UserDepartment).where(UserDepartment.user_id == user_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_all_dept_ids(db: AsyncSession, user_id: UUID) -> tuple[list[UUID], UUID | None]:
        """Get all department IDs and primary department ID for a user.

        Returns:
            tuple of (all_dept_ids, primary_dept_id)
        """
        associations = await UserDepartmentService.get_user_departments(db, user_id)
        all_ids = [ud.dept_id for ud in associations]
        primary = next((ud.dept_id for ud in associations if ud.is_primary), None)
        return all_ids, primary

    @staticmethod
    async def update_user_departments(
        db: AsyncSession,
        user_id: UUID,
        dept_ids: list[UUID],
        primary_dept_id: UUID | None = None,
    ) -> list[UserDepartment]:
        """Replace all department associations for a user."""
        stmt = select(UserDepartment).where(UserDepartment.user_id == user_id)
        result = await db.execute(stmt)
        existing = result.scalars().all()
        for ud in existing:
            await db.delete(ud)

        if not dept_ids:
            await db.commit()
            return []

        primary = primary_dept_id or dept_ids[0]
        new_associations = []
        for dept_id in dept_ids:
            is_primary = dept_id == primary
            ud = UserDepartment(user_id=user_id, dept_id=dept_id, is_primary=is_primary)
            db.add(ud)
            new_associations.append(ud)

        await db.commit()
        for ud in new_associations:
            await db.refresh(ud)
        return new_associations

    @staticmethod
    async def get_department_users(
        db: AsyncSession,
        dept_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[User], int]:
        """Get all users in a department (direct associations only)."""
        stmt = (
            select(UserDepartment)
            .where(UserDepartment.dept_id == dept_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        associations = result.scalars().all()

        if not associations:
            return [], 0

        user_ids = [ud.user_id for ud in associations]
        user_stmt = select(User).where(User.id.in_(user_ids), User.is_deleted == False)
        user_result = await db.execute(user_stmt)
        users = list(user_result.scalars().all())

        count_stmt = select(UserDepartment).where(UserDepartment.dept_id == dept_id)
        count_result = await db.execute(count_stmt)
        total = len(count_result.scalars().all())

        return users, total

    @staticmethod
    async def get_department_users_recursive(db: AsyncSession, dept_id: UUID) -> list[User]:
        """Get all users in a department and its sub-departments."""
        dept_ids = [dept_id]

        async def get_child_ids(parent_id: UUID) -> None:
            stmt = select(Department.id).where(Department.parent_id == parent_id)
            result = await db.execute(stmt)
            children = result.scalars().all()
            for child_id in children:
                dept_ids.append(child_id)
                await get_child_ids(child_id)

        await get_child_ids(dept_id)

        stmt = select(UserDepartment).where(UserDepartment.dept_id.in_(dept_ids))
        result = await db.execute(stmt)
        associations = result.scalars().all()

        if not associations:
            return []

        user_ids = list(set(ud.user_id for ud in associations))
        user_stmt = select(User).where(User.id.in_(user_ids), User.is_deleted == False)
        user_result = await db.execute(user_stmt)
        return list(user_result.scalars().all())
