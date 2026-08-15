"""Request-scoped caching for permission engine and identity.

Uses ContextVar so cached values are isolated per request (each async
request gets its own context) and automatically cleaned up when the
request ends.
"""

from __future__ import annotations

from contextvars import ContextVar

from app.extensions.auth.engine import UnifiedPermissionEngine
from app.extensions.auth.identity import AttributeSet

_request_engine: ContextVar[UnifiedPermissionEngine | None] = ContextVar("_perm_engine", default=None)
_request_identity: ContextVar[AttributeSet | None] = ContextVar("_perm_identity", default=None)


def get_cached_engine() -> UnifiedPermissionEngine | None:
    return _request_engine.get(None)


def set_cached_engine(engine: UnifiedPermissionEngine) -> None:
    _request_engine.set(engine)


def get_cached_identity() -> AttributeSet | None:
    return _request_identity.get(None)


def set_cached_identity(identity: AttributeSet) -> None:
    _request_identity.set(identity)


def clear_permission_cache() -> None:
    """Clear all cached permission state. Useful in tests or long-lived contexts."""
    _request_engine.set(None)
    _request_identity.set(None)
