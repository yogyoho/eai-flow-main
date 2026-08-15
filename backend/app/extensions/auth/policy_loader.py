"""Shared loader for active ABAC policies — single source for require_permission + /me + with_data_scope."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.engine import Policy as EnginePolicy
from app.extensions.auth.models import Policy as PolicyModel


async def load_active_policies(db: AsyncSession) -> list[EnginePolicy]:
    """Return enabled policies ordered by priority, as engine Policy dataclasses."""
    rows = (
        (
            await db.execute(
                select(PolicyModel).where(PolicyModel.enabled == True).order_by(PolicyModel.priority)  # noqa: E712
            )
        )
        .scalars()
        .all()
    )
    return [EnginePolicy(name=r.name, priority=r.priority, conditions=r.conditions, grants=r.grants) for r in rows]
