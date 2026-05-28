"""JWT authentication utilities shared across EAIFlow business microservices.

All business microservices use the same JWT secret as the EAIFlow Gateway
to verify tokens issued by the gateway.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel


class TokenPayload(BaseModel):
    """JWT Token payload schema."""

    sub: str
    username: str
    role: Optional[str] = None
    permissions: list[str] = []
    exp: Optional[datetime] = None


@lru_cache
def get_jwt_secret() -> str:
    """Get JWT secret from environment variable."""
    import os

    secret = os.environ.get("JWT_SECRET_KEY", "change-me-in-production")
    return secret


@lru_cache
def get_jwt_algorithm() -> str:
    """Get JWT algorithm from environment variable."""
    import os

    return os.environ.get("JWT_ALGORITHM", "HS256")


@lru_cache
def get_access_token_expire_minutes() -> int:
    """Get access token expiry in minutes from environment variable."""
    import os

    return int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def verify_token(token: str) -> Optional[TokenPayload]:
    """Verify a JWT token and return its payload.

    Uses the shared JWT secret so tokens issued by EAIFlow Gateway
    are accepted here too.
    """
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[get_jwt_algorithm()],
        )
        return TokenPayload(
            sub=payload.get("sub", ""),
            username=payload.get("username", ""),
            role=payload.get("role"),
            permissions=payload.get("permissions", []),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            if "exp" in payload
            else None,
        )
    except JWTError:
        return None
