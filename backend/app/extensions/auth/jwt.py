"""JWT authentication utilities."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.extensions.config import get_extensions_config
from app.extensions.schemas import TokenPayload


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_access_token(
    user_id: str, username: str, role: Optional[str] = None, permissions: list[str] = None
) -> tuple[str, int]:
    """Generate an access token."""
    config = get_extensions_config()
    permissions = permissions or []

    exp = datetime.now(timezone.utc) + timedelta(
        minutes=config.jwt.access_token_expire_minutes
    )

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "permissions": permissions,
        "exp": int(exp.timestamp()),
        "type": "access",
    }

    token = jwt.encode(payload, config.jwt.secret, algorithm=config.jwt.algorithm)
    expires_in = config.jwt.access_token_expire_minutes * 60

    return token, expires_in


def generate_refresh_token(user_id: str) -> tuple[str, int]:
    """Generate a refresh token."""
    config = get_extensions_config()

    exp = datetime.now(timezone.utc) + timedelta(days=config.jwt.refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "exp": int(exp.timestamp()),
        "type": "refresh",
        "random": secrets.token_urlsafe(32),
    }

    token = jwt.encode(payload, config.jwt.secret, algorithm=config.jwt.algorithm)
    expires_in = config.jwt.refresh_token_expire_days * 24 * 60 * 60

    return token, expires_in


def verify_token(token: str, token_type: str = "access") -> Optional[TokenPayload]:
    """Verify a token and return the payload."""
    config = get_extensions_config()

    try:
        payload = jwt.decode(
            token,
            config.jwt.secret,
            algorithms=[config.jwt.algorithm],
        )

        if payload.get("type") != token_type:
            return None

        return TokenPayload(
            sub=payload.get("sub", ""),
            username=payload.get("username", ""),
            role=payload.get("role"),
            permissions=payload.get("permissions", []),
            exp=payload.get("exp"),
        )
    except InvalidTokenError:
        return None


def decode_token(token: str) -> Optional[dict]:
    """Decode a token without verification (for debugging)."""
    config = get_extensions_config()

    try:
        return jwt.decode(
            token,
            config.jwt.secret,
            algorithms=[config.jwt.algorithm],
            options={"verify_signature": False},
        )
    except InvalidTokenError:
        return None
