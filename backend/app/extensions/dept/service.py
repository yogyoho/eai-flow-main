"""Department service for extensions module."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.extensions.models import Department, User
from app.extensions.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentTreeResponse,
    DepartmentUpdate,
)

logger = logging.getLogger(__name__)


class DepartmentService:
    """Department service."""

    @staticmethod
    async def list_departments(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Department], int]:
        """List all departments."""
        query = select(Department).offset(skip).limit(limit).order_by(Department.sort_order, Department.name)
        result = await db.execute(query)
        departments = result.scalars().all()

        count_query = select(func.count(Department.id))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(departments), total

    @staticmethod
    async def get_department_by_id(db: AsyncSession, dept_id: UUID) -> Department | None:
        """Get department by ID."""
        stmt = select(Department).where(Department.id == dept_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_department_by_name(db: AsyncSession, name: str) -> Department | None:
        """Get department by name."""
        stmt = select(Department).where(Department.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_department(db: AsyncSession, data: DepartmentCreate) -> Department:
        """Create a new department."""
        department = Department(
            name=data.name,
            code=data.code,
            description=data.description,
            parent_id=data.parent_id,
            leader_id=data.leader_id,
            sort_order=data.sort_order,
            status=data.status,
        )
        db.add(department)
        await db.commit()
        await db.refresh(department)
        return department

    @staticmethod
    async def update_department(db: AsyncSession, department: Department, data: DepartmentUpdate) -> Department:
        """Update an existing department."""
        if data.name is not None:
            department.name = data.name
        if data.code is not None:
            department.code = data.code
        if data.description is not None:
            department.description = data.description
        if data.parent_id is not None:
            department.parent_id = data.parent_id
        if data.leader_id is not None:
            department.leader_id = data.leader_id
        if data.sort_order is not None:
            department.sort_order = data.sort_order
        if data.status is not None:
            department.status = data.status

        await db.commit()
        await db.refresh(department)
        return department

    @staticmethod
    async def delete_department(db: AsyncSession, department: Department) -> None:
        """Delete a department."""
        await db.delete(department)
        await db.commit()

    @staticmethod
    async def get_children(db: AsyncSession, parent_id: UUID) -> list[Department]:
        """Get child departments of a parent."""
        stmt = select(Department).where(Department.parent_id == parent_id).order_by(Department.sort_order, Department.name)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_department_tree(db: AsyncSession) -> list[DepartmentTreeResponse]:
        """Get hierarchical department tree."""
        stmt = select(Department).options(selectinload(Department.children)).where(Department.parent_id == None).order_by(Department.sort_order, Department.name)
        result = await db.execute(stmt)
        root_departments = result.scalars().all()

        tree = []
        for dept in root_departments:
            tree.append(await DepartmentService._build_tree_node(db, dept))
        return tree

    @staticmethod
    async def _build_tree_node(db: AsyncSession, department: Department) -> DepartmentTreeResponse:
        """Build a tree node recursively."""
        children = await DepartmentService.get_children(db, department.id)
        child_nodes = []
        for child in children:
            child_nodes.append(await DepartmentService._build_tree_node(db, child))

        leader_name = None
        if department.leader_id:
            stmt = select(User).where(User.id == department.leader_id)
            result = await db.execute(stmt)
            leader = result.scalar_one_or_none()
            if leader:
                leader_name = leader.full_name or leader.username

        return DepartmentTreeResponse(
            id=department.id,
            name=department.name,
            code=department.code,
            description=department.description,
            parent_id=department.parent_id,
            leader_id=department.leader_id,
            leader_name=leader_name,
            sort_order=department.sort_order,
            status=department.status,
            children=child_nodes,
            created_at=department.created_at,
        )

    @staticmethod
    async def to_response(db: AsyncSession, department: Department) -> DepartmentResponse:
        """Convert department model to response."""
        leader_name = None
        if department.leader_id:
            stmt = select(User).where(User.id == department.leader_id)
            result = await db.execute(stmt)
            leader = result.scalar_one_or_none()
            if leader:
                leader_name = leader.full_name or leader.username

        return DepartmentResponse(
            id=department.id,
            name=department.name,
            code=department.code,
            description=department.description,
            parent_id=department.parent_id,
            leader_id=department.leader_id,
            leader_name=leader_name,
            sort_order=department.sort_order,
            status=department.status,
            created_at=department.created_at,
        )
