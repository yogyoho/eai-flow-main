"""Auth-disabled (single-user local) mode flag.

This deployment uses fail-closed cookie/JWT auth — every non-public request
requires a valid JWT — so local auth-disabled mode is never active. The
upstream channel-connections router imports ``is_auth_disabled`` to decide
whether a configured, running channel should be reported as "connected"
without a per-user binding (the single-user local mode that routes every
inbound message to the synthetic default user). Because that mode is off
here, this always reports auth as enabled, and every channel connection must
be an explicit persisted user-owned binding.

Kept as a thin shim so the upstream ``channel_connections`` router imports
unchanged.
"""

from __future__ import annotations


def is_auth_disabled() -> bool:
    """Whether single-user auth-disabled (local) mode is active.

    Always ``False`` here: auth is fail-closed and every channel message
    must belong to a persisted user-owned binding.
    """
    return False
