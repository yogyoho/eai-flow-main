"""JWT 认证工具（支持共享密钥跨服务验证 EAIFlow Gateway 签发的 Token）

支持两种认证方式：
1. Cookie-based: 从 access_token HttpOnly cookie 读取 (主平台登录后自动携带)
2. Header-based: 从 Authorization: Bearer <token> 读取 (兼容旧 API 调用)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
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


def create_access_token(
    user_id: str,
    username: str,
    role: Optional[str] = None,
    permissions: list[str] | None = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    """Create a new JWT access token.

    Returns (token, expires_in_seconds) tuple.
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "permissions": permissions or [],
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    expires_in = int(expires_delta.total_seconds())
    return token, expires_in


def verify_token(token: str) -> Optional[TokenPayload]:
    """Verify a JWT token and return its payload.

    Uses the shared JWT secret so tokens issued by EAIFlow Gateway
    are accepted here too.
    """
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
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
        )
    except JWTError:
        return None


def _extract_token_from_cookie(request: Request) -> Optional[str]:
    """Extract JWT from the access_token cookie (set by Gateway login)."""
    return request.cookies.get("access_token")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """FastAPI dependency: extract and validate current user.

    Priority:
    1. access_token HttpOnly cookie (set by Gateway login) — primary method
    2. Authorization: Bearer <token> header — fallback for programmatic access
    """
    token: Optional[str] = None

    # 1. Try cookie-based auth first (main platform login flow)
    cookie_token = _extract_token_from_cookie(request)
    if cookie_token:
        token = cookie_token

    # 2. Fall back to Bearer header
    if not token and credentials is not None:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_permission(permission: str):
    """Factory for permission-checking FastAPI dependencies."""

    async def checker(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if permission not in current_user.permissions and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return current_user

    return checker
