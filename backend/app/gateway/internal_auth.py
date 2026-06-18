"""Authentication for trusted Gateway internal callers."""

from __future__ import annotations

import os
import secrets
from types import SimpleNamespace

from deerflow.runtime.user_context import DEFAULT_USER_ID

INTERNAL_AUTH_HEADER_NAME = "X-DeerFlow-Internal-Token"
INTERNAL_OWNER_HEADER_NAME = "X-DeerFlow-Owner-User-Id"
INTERNAL_AUTH_ENV_VAR = "DEER_FLOW_INTERNAL_AUTH_TOKEN"


def _load_internal_auth_token() -> str:
    token = os.environ.get(INTERNAL_AUTH_ENV_VAR)
    if token:
        return token
    return secrets.token_urlsafe(32)


_INTERNAL_AUTH_TOKEN = _load_internal_auth_token()


def create_internal_auth_headers(*, owner_user_id: str | None = None) -> dict[str, str]:
    """Return headers that authenticate trusted Gateway internal calls.

    When ``owner_user_id`` is set (a per-message channel owner, e.g. the WeChat
    user a message came from), it is forwarded so the gateway attributes the
    call — and thus the agent run's memory/sandbox scope — to that user instead
    of the synthetic default user. Only honored when the internal token validates.
    """
    headers = {INTERNAL_AUTH_HEADER_NAME: _INTERNAL_AUTH_TOKEN}
    if owner_user_id:
        headers[INTERNAL_OWNER_HEADER_NAME] = owner_user_id
    return headers


def is_valid_internal_auth_token(token: str | None) -> bool:
    """Return True when *token* matches this Gateway worker's internal token."""
    return bool(token) and secrets.compare_digest(token, _INTERNAL_AUTH_TOKEN)


def get_internal_user(*, owner_user_id: str | None = None):
    """Return the synthetic user used for trusted internal channel calls.

    With ``owner_user_id``, the synthetic internal user impersonates that owner
    so channel-originated runs are scoped to the owner's memory/sandbox.
    """
    return SimpleNamespace(id=owner_user_id or DEFAULT_USER_ID, system_role="internal")
