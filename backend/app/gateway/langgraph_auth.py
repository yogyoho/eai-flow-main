"""LangGraph Server auth handler — shares JWT logic with Gateway.

Loaded by LangGraph Server via langgraph.json ``auth.path``.
Reuses the same ``decode_token`` / ``get_auth_config`` as Gateway,
so both modes validate tokens with the same secret and rules.

Two layers:
  1. @auth.authenticate — validates JWT cookie, extracts user_id,
     and enforces CSRF on state-changing methods (POST/PUT/DELETE/PATCH)
  2. @auth.on — returns metadata filter so each user only sees own threads

The authorization layer follows the LangGraph SDK's recommended pattern:
  - Default deny for unhandled operations
  - Resource/action-specific handlers for threads (create/read/search/update/delete/create_run)
  - Store operations scoped to user namespace
  - Assistants and crons accepted without filtering (for now)
"""

import secrets

from langgraph_sdk import Auth

from app.gateway.auth.errors import TokenError
from app.gateway.auth.jwt import decode_token
from app.gateway.deps import get_local_provider

auth = Auth()

# Methods that require CSRF validation (state-changing per RFC 7231).
_CSRF_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def _check_csrf(request) -> None:
    """Enforce Double Submit Cookie CSRF check for state-changing requests.

    Mirrors Gateway's CSRFMiddleware logic so that LangGraph routes
    proxied directly by nginx have the same CSRF protection.
    """
    method = getattr(request, "method", "") or ""
    if method.upper() not in _CSRF_METHODS:
        return

    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("x-csrf-token")

    if not cookie_token or not header_token:
        raise Auth.exceptions.HTTPException(
            status_code=403,
            detail="CSRF token missing. Include X-CSRF-Token header.",
        )

    if not secrets.compare_digest(cookie_token, header_token):
        raise Auth.exceptions.HTTPException(
            status_code=403,
            detail="CSRF token mismatch.",
        )


@auth.authenticate
async def authenticate(request):
    """Validate the session cookie, decode JWT, and check token_version.

    Same validation chain as Gateway's get_current_user_from_request:
      cookie → decode JWT → DB lookup → token_version match
    Also enforces CSRF on state-changing methods.
    """
    # CSRF check before authentication so forged cross-site requests
    # are rejected early, even if the cookie carries a valid JWT.
    _check_csrf(request)

    token = request.cookies.get("access_token")
    if not token:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    payload = decode_token(token)
    if isinstance(payload, TokenError):
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = await get_local_provider().get_user(payload.sub)
    if user is None:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="User not found",
        )
    if user.token_version != payload.ver:
        raise Auth.exceptions.HTTPException(
            status_code=401,
            detail="Token revoked (password changed)",
        )

    return payload.sub


# ---------------------------------------------------------------------------
# Authorization handlers — LangGraph SDK recommended pattern
# ---------------------------------------------------------------------------


@auth.on
async def deny_all(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """Default deny: reject any operation without a specific handler."""
    return False


# -- Threads ----------------------------------------------------------------


@auth.on.threads.create
async def on_threads_create(ctx: Auth.types.AuthContext, value: dict):
    """Stamp user_id on thread metadata; accept without filter.

    The stamped metadata is persisted by the LangGraph runtime, so
    subsequent read/search operations can filter by user_id.
    """
    metadata = value.setdefault("metadata", {})
    metadata["user_id"] = ctx.user.identity
    # Returns None → accept without applying a filter


@auth.on.threads.read
async def on_threads_read(ctx: Auth.types.AuthContext, value: dict):
    """Only return threads owned by the authenticated user."""
    return {"user_id": ctx.user.identity}


@auth.on.threads.search
async def on_threads_search(ctx: Auth.types.AuthContext, value: dict):
    """Only return threads owned by the authenticated user."""
    return {"user_id": ctx.user.identity}


@auth.on.threads.update
async def on_threads_update(ctx: Auth.types.AuthContext, value: dict):
    """Stamp user_id and filter by owner on update."""
    metadata = value.setdefault("metadata", {})
    metadata["user_id"] = ctx.user.identity
    return {"user_id": ctx.user.identity}


@auth.on.threads.delete
async def on_threads_delete(ctx: Auth.types.AuthContext, value: dict):
    """Only allow deletion of threads owned by the authenticated user."""
    return {"user_id": ctx.user.identity}


@auth.on.threads.create_run
async def on_threads_create_run(ctx: Auth.types.AuthContext, value: dict):
    """Stamp user_id on run metadata; filter by owner.

    Ensures users can only create runs on their own threads.
    """
    metadata = value.setdefault("metadata", {})
    metadata["user_id"] = ctx.user.identity
    return {"user_id": ctx.user.identity}


# -- Store ------------------------------------------------------------------


@auth.on.store
async def scope_store(ctx: Auth.types.AuthContext, value: dict):
    """Scope all store operations to the authenticated user's namespace."""
    namespace = tuple(value["namespace"]) if value.get("namespace") else ()
    if not namespace or namespace[0] != ctx.user.identity:
        namespace = (ctx.user.identity, *namespace)
    value["namespace"] = namespace


# -- Assistants -------------------------------------------------------------
# Accept all assistant operations without user-level filtering for now.
# If per-user assistant isolation is needed later, add owner-based filters.


@auth.on.assistants
async def allow_assistants(ctx: Auth.types.AuthContext, value: dict):
    """Accept all assistant operations (no user-level filtering yet)."""
    return None


# -- Crons -------------------------------------------------------------------
# Accept all cron operations without user-level filtering for now.
# Crons are tied to threads which already enforce user isolation.


@auth.on.crons
async def allow_crons(ctx: Auth.types.AuthContext, value: dict):
    """Accept all cron operations (filtered by thread ownership upstream)."""
    return None
