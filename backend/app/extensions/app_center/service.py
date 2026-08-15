"""App-center service — static CRUD for domains & apps."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.app_center.models import AppDefinition, AppDomain
from app.extensions.app_center.schemas import (
    AppDefinitionCreate,
    AppDefinitionUpdate,
    AppDomainCreate,
    AppDomainUpdate,
)


class AppCenterService:
    # ── Domains ──

    @staticmethod
    async def list_domains(db: AsyncSession) -> list[AppDomain]:
        result = await db.execute(select(AppDomain).order_by(AppDomain.sort_order.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def create_domain(db: AsyncSession, req: AppDomainCreate) -> AppDomain:
        domain = AppDomain(**req.model_dump())
        db.add(domain)
        await db.flush()
        return domain

    @staticmethod
    async def update_domain(db: AsyncSession, key: str, req: AppDomainUpdate) -> AppDomain | None:
        domain = await db.get(AppDomain, key)
        if domain is None:
            return None
        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(domain, field, value)
        await db.flush()
        return domain

    @staticmethod
    async def delete_domain(db: AsyncSession, key: str) -> bool:
        domain = await db.get(AppDomain, key)
        if domain is None:
            return False
        await db.delete(domain)
        await db.flush()
        return True

    # ── Apps ──

    @staticmethod
    async def list_apps(db: AsyncSession) -> list[AppDefinition]:
        result = await db.execute(
            select(AppDefinition)
            .where(AppDefinition.is_enabled == True)  # noqa: E712
            .order_by(AppDefinition.sort_order.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all_apps(db: AsyncSession) -> list[AppDefinition]:
        """Admin: returns all apps including disabled ones."""
        result = await db.execute(select(AppDefinition).order_by(AppDefinition.sort_order.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def create_app(db: AsyncSession, req: AppDefinitionCreate) -> AppDefinition:
        app = AppDefinition(**req.model_dump())
        db.add(app)
        await db.flush()
        return app

    @staticmethod
    async def update_app(db: AsyncSession, app_id: str, req: AppDefinitionUpdate) -> AppDefinition | None:
        result = await db.execute(select(AppDefinition).where(AppDefinition.app_id == app_id))
        app = result.scalars().first()
        if app is None:
            return None
        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(app, field, value)
        await db.flush()
        return app

    @staticmethod
    async def delete_app(db: AsyncSession, app_id: str) -> bool:
        result = await db.execute(select(AppDefinition).where(AppDefinition.app_id == app_id))
        app = result.scalars().first()
        if app is None:
            return False
        await db.delete(app)
        await db.flush()
        return True
