"""Authentication module for extensions."""

from app.extensions.auth.jwt import (
    decode_token,
    generate_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.extensions.auth.middleware import (
    ACCESS_TOKEN_COOKIE,
    get_current_user,
    get_current_user_optional,
    require_permission,
    require_role,
)

__all__ = [
    "ACCESS_TOKEN_COOKIE",
    "decode_token",
    "generate_access_token",
    "generate_refresh_token",
    "get_current_user",
    "get_current_user_optional",
    "hash_password",
    "require_permission",
    "require_role",
    "verify_password",
    "verify_token",
]
