"""Auth-disabled (single-user local) mode flag — EAI shim."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

AUTH_SOURCE_INTERNAL = "internal"


def is_auth_disabled() -> bool:
    """Whether single-user auth-disabled (local) mode is active."""
    return False


def warn_if_auth_disabled_enabled() -> None:
    """Emit a startup warning when auth is disabled (upstream compat stub)."""
    logger.debug("Auth is fail-closed (cookie/JWT); auth-disabled mode is inactive.")
