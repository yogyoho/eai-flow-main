"""Sync Extensions user operations to Gateway authentication system.

When users are created or managed through the Extensions admin UI (PostgreSQL),
this module ensures corresponding Gateway users exist in SQLite so those users
can log in through the main Gateway authentication endpoint.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Role as ExtRole

logger = logging.getLogger(__name__)

# Extensions role code → Gateway system_role
_GATEWAY_ROLE_MAP: dict[str, str] = {
    "superadmin": "admin",
    "admin": "admin",
}


async def _get_gateway_provider():
    """Lazy-load the Gateway LocalAuthProvider singleton.

    Returns None when the Gateway engine hasn't been initialized yet
    (e.g. during seed_db which runs before Gateway startup), or when
    any other error occurs during provider resolution.
    """
    try:
        from app.gateway.deps import get_local_provider

        return get_local_provider()
    except Exception:
        logger.debug("Gateway auth provider not available, skipping sync", exc_info=True)
        return None


async def _resolve_role_code(db: AsyncSession, role_id: UUID | None) -> str | None:
    """Resolve an Extensions role_id to its code string."""
    if role_id is None:
        return None
    stmt = select(ExtRole.code).where(ExtRole.id == role_id)
    result = await db.execute(stmt)
    row = result.one_or_none()
    return row[0] if row else None


def _map_to_gateway_role(role_code: str | None) -> str:
    """Map Extensions role code to Gateway system_role."""
    if role_code is None:
        return "user"
    return _GATEWAY_ROLE_MAP.get(role_code, "user")


async def sync_user_created(
    db: AsyncSession,
    email: str,
    password: str,
    role_id: UUID | None = None,
) -> None:
    """Create or update a Gateway user matching a newly created Extensions user.

    Best-effort: logs a warning and returns silently on failure so the
    Extensions operation is never rolled back due to sync issues.
    """
    logger.info("Syncing Gateway user for extensions creation: %s", email)

    try:
        provider = await _get_gateway_provider()
        if provider is None:
            logger.info("Gateway provider unavailable, user %s must login via Gateway registration", email)
            return

        role_code = await _resolve_role_code(db, role_id)
        gateway_role = _map_to_gateway_role(role_code)

        existing = await provider.get_user_by_email(email)
        if existing is not None:
            from app.gateway.auth.password import hash_password_async

            existing.password_hash = await hash_password_async(password)
            existing.system_role = gateway_role
            existing.token_version += 1
            await provider.update_user(existing)
            logger.info("Updated existing Gateway user for %s (role=%s)", email, gateway_role)
        else:
            await provider.create_user(email=email, password=password, system_role=gateway_role)
            logger.info("Created Gateway user for %s (role=%s)", email, gateway_role)
    except Exception:
        logger.warning("Failed to sync Gateway user creation for %s", email, exc_info=True)


async def sync_password_changed(email: str, new_password: str) -> None:
    """Update the Gateway user's password and invalidate existing sessions.

    Best-effort: logs a warning and returns silently on failure.
    """
    try:
        provider = await _get_gateway_provider()
        if provider is None:
            return

        from app.gateway.auth.password import hash_password_async

        user = await provider.get_user_by_email(email)
        if user is None:
            logger.debug("No Gateway user found for %s, skipping password sync", email)
            return

        user.password_hash = await hash_password_async(new_password)
        user.token_version += 1
        await provider.update_user(user)
        logger.info("Updated Gateway password for %s", email)
    except Exception:
        logger.warning("Failed to sync Gateway password change for %s", email, exc_info=True)


async def sync_user_disabled(email: str) -> None:
    """Invalidate all existing Gateway sessions for a disabled user.

    Gateway has no status/enabled field, so we bump token_version to
    invalidate all issued JWTs.

    Best-effort: logs a warning and returns silently on failure.
    """
    try:
        provider = await _get_gateway_provider()
        if provider is None:
            return

        user = await provider.get_user_by_email(email)
        if user is None:
            return

        user.token_version += 1
        await provider.update_user(user)
        logger.info("Invalidated Gateway sessions for disabled user %s", email)
    except Exception:
        logger.warning("Failed to sync Gateway disable for %s", email, exc_info=True)


async def sync_user_deleted(email: str) -> None:
    """Invalidate all existing Gateway sessions for a deleted user.

    Gateway has no delete_user API, so we bump token_version to invalidate
    all issued JWTs.

    Best-effort: logs a warning and returns silently on failure.
    """
    await sync_user_disabled(email)


async def sync_email_changed(old_email: str, new_email: str) -> None:
    """Update the Gateway user's email and invalidate existing sessions.

    Best-effort: logs a warning and returns silently on failure.
    """
    try:
        provider = await _get_gateway_provider()
        if provider is None:
            return

        user = await provider.get_user_by_email(old_email)
        if user is None:
            logger.debug("No Gateway user found for %s, skipping email sync", old_email)
            return

        # Use Pydantic model's attribute setter to update email
        user.email = new_email  # type: ignore[assignment]
        user.token_version += 1
        await provider.update_user(user)
        logger.info("Updated Gateway email %s → %s", old_email, new_email)
    except Exception:
        logger.warning("Failed to sync Gateway email change for %s", old_email, exc_info=True)
