"""User service for extensions module."""

import logging
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import hash_password, verify_password
from app.extensions.models import Department, Role, User
from app.extensions.schemas import (
    UserCreate,
    UserResponse,
    UserStatistics,
    UserUpdate,
)

logger = logging.getLogger(__name__)


class UserService:
    """User service."""

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
        """Get user by username."""
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_users(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        dept_id: UUID | None = None,
        role_id: UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[User], int]:
        """List users with filters."""
        query = select(User).where(User.is_deleted == False if not include_deleted else True)
        count_query = select(func.count(User.id)).where(User.is_deleted == False if not include_deleted else True)

        if dept_id:
            query = query.where(User.dept_id == dept_id)
            count_query = count_query.where(User.dept_id == dept_id)

        if role_id:
            query = query.where(User.role_id == role_id)
            count_query = count_query.where(User.role_id == role_id)

        if status:
            query = query.where(User.status == status)
            count_query = count_query.where(User.status == status)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())

        result = await db.execute(query)
        users = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(users), total

    @staticmethod
    async def search_users(
        db: AsyncSession,
        keyword: str | None = None,
        skip: int = 0,
        limit: int = 100,
        dept_id: UUID | None = None,
        role_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[User], int]:
        """Search users by keyword (username, email, full_name)."""
        query = select(User).where(User.is_deleted == False)
        count_query = select(func.count(User.id)).where(User.is_deleted == False)

        if keyword:
            keyword_filter = or_(
                User.username.ilike(f"%{keyword}%"),
                User.email.ilike(f"%{keyword}%"),
                User.full_name.ilike(f"%{keyword}%"),
            )
            query = query.where(keyword_filter)
            count_query = count_query.where(keyword_filter)

        if dept_id:
            query = query.where(User.dept_id == dept_id)
            count_query = count_query.where(User.dept_id == dept_id)

        if role_id:
            query = query.where(User.role_id == role_id)
            count_query = count_query.where(User.role_id == role_id)

        if status:
            query = query.where(User.status == status)
            count_query = count_query.where(User.status == status)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())

        result = await db.execute(query)
        users = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(users), total

    @staticmethod
    async def create_user(db: AsyncSession, data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            dept_id=data.dept_id,
            role_id=data.role_id,
            phone=data.phone,
            emp_no=data.emp_no,
            hire_date=data.hire_date,
        )
        db.add(user)
        await db.flush()

        from app.extensions.user_department.service import UserDepartmentService

        if data.dept_ids:
            primary = data.dept_id or (data.dept_ids[0] if data.dept_ids else None)
            await UserDepartmentService.update_user_departments(db, user.id, data.dept_ids, primary)
        elif data.dept_id:
            await UserDepartmentService.add_user_to_dept(db, user.id, data.dept_id, is_primary=True)

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
        """Update an existing user."""
        if data.email is not None:
            user.email = data.email
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.dept_id is not None:
            user.dept_id = data.dept_id
        if data.role_id is not None:
            user.role_id = data.role_id
        if data.status is not None:
            user.status = data.status
        if data.phone is not None:
            user.phone = data.phone
        if data.emp_no is not None:
            user.emp_no = data.emp_no
        if data.hire_date is not None:
            user.hire_date = data.hire_date
        if data.is_deleted is not None:
            user.is_deleted = data.is_deleted

        from app.extensions.user_department.service import UserDepartmentService

        if data.dept_ids is not None:
            primary = data.dept_id or (data.dept_ids[0] if data.dept_ids else None)
            await UserDepartmentService.update_user_departments(db, user.id, data.dept_ids, primary)

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def delete_user(db: AsyncSession, user: User) -> None:
        """Soft delete a user."""
        user.is_deleted = True
        await db.commit()

    @staticmethod
    async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str) -> bool:
        """Change user password. Returns True if successful, False if old password is wrong."""
        if not verify_password(old_password, user.password_hash):
            return False
        user.password_hash = hash_password(new_password)
        await db.commit()
        return True

    @staticmethod
    async def reset_password(db: AsyncSession, user: User, new_password: str) -> None:
        """Reset user password (admin operation)."""
        user.password_hash = hash_password(new_password)
        await db.commit()

    @staticmethod
    async def batch_operation(
        db: AsyncSession,
        user_ids: list[UUID],
        operation: str,
    ) -> tuple[list[UUID], list[dict]]:
        """Batch operation on users. Returns (success_ids, failed_list)."""
        success = []
        failed = []

        for user_id in user_ids:
            try:
                user = await UserService.get_user_by_id(db, user_id)
                if not user:
                    failed.append({"id": str(user_id), "error": "User not found"})
                    continue

                if operation == "enable":
                    user.status = "active"
                elif operation == "disable":
                    user.status = "inactive"
                elif operation == "delete":
                    await db.delete(user)

                success.append(user_id)
            except Exception as e:
                failed.append({"id": str(user_id), "error": str(e)})

        if success:
            await db.commit()

        return success, failed

    @staticmethod
    async def get_statistics(db: AsyncSession) -> UserStatistics:
        """Get user statistics."""
        total_query = select(func.count(User.id))
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        active_query = select(func.count(User.id)).where(User.status == "active")
        active_result = await db.execute(active_query)
        active = active_result.scalar() or 0

        inactive_query = select(func.count(User.id)).where(User.status == "inactive")
        inactive_result = await db.execute(inactive_query)
        inactive = inactive_result.scalar() or 0

        dept_query = select(User.dept_id, func.count(User.id)).group_by(User.dept_id)
        dept_result = await db.execute(dept_query)
        by_department: dict = {}
        for row in dept_result.all():
            if row[0]:
                dept_name = await UserService._get_dept_name(db, row[0])
                by_department[dept_name or str(row[0])] = row[1]
            else:
                by_department["未分配"] = row[1]

        role_query = select(User.role_id, func.count(User.id)).group_by(User.role_id)
        role_result = await db.execute(role_query)
        by_role: dict = {}
        for row in role_result.all():
            if row[0]:
                role_name = await UserService._get_role_name(db, row[0])
                by_role[role_name or str(row[0])] = row[1]
            else:
                by_role["未分配"] = row[1]

        return UserStatistics(
            total=total,
            active=active,
            inactive=inactive,
            by_department=by_department,
            by_role=by_role,
        )

    @staticmethod
    async def _get_dept_name(db: AsyncSession, dept_id: UUID) -> str | None:
        """Get department name by ID."""
        stmt = select(Department).where(Department.id == dept_id)
        result = await db.execute(stmt)
        dept = result.scalar_one_or_none()
        return dept.name if dept else None

    @staticmethod
    async def _get_role_name(db: AsyncSession, role_id: UUID) -> str | None:
        """Get role name by ID."""
        stmt = select(Role).where(Role.id == role_id)
        result = await db.execute(stmt)
        role = result.scalar_one_or_none()
        return role.name if role else None

    @staticmethod
    async def to_response(db: AsyncSession, user: User) -> UserResponse:
        """Convert user model to response."""
        role_name = None
        dept_name = None
        dept_ids = []
        primary_dept_id = None

        if user.role_id:
            stmt = select(Role).where(Role.id == user.role_id)
            result = await db.execute(stmt)
            role = result.scalar_one_or_none()
            if role:
                role_name = role.name

        if user.dept_id:
            stmt = select(Department).where(Department.id == user.dept_id)
            result = await db.execute(stmt)
            dept = result.scalar_one_or_none()
            if dept:
                dept_name = dept.name

        from app.extensions.user_department.service import UserDepartmentService

        dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user.id)

        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            emp_no=user.emp_no,
            hire_date=user.hire_date,
            dept_id=user.dept_id,
            dept_name=dept_name,
            dept_ids=dept_ids,
            primary_dept_id=primary_dept_id,
            role_id=user.role_id,
            role_name=role_name,
            status=user.status,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
