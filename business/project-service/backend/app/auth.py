"""JWT 认证工具"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings


class TokenPayload(BaseModel):
    """JWT Token payload schema."""

    sub: str
    username: str
    role: Optional[str] = None
    permissions: list[str] = []
    exp: Optional[datetime] = None


security = HTTPBearer(auto_error=False)


def verify_token(token: str) -> Optional[TokenPayload]:
    """Verify a JWT token and return its payload."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """FastAPI dependency: extract and validate current user from Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
