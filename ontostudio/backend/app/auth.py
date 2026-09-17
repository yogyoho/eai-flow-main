"""OntoStudio 鉴权 — HS256 共享密钥 JWT 验签（S1 Task 2 实装）.

EAI-CUSTOM: ontology 包自 backend/app/extensions/ 迁出独立
（设计: docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md，D1 决策）。

查证结论（Task 2 落地前核对 backend 侧源码）：
- 验签库与 gateway 同款 = **PyJWT**（``import jwt``；backend/app/gateway/auth/jwt.py:37 HS256）。
- gateway upstream 签发（create_access_token, backend/app/gateway/auth/jwt.py:21）：
  claims = {sub=user_id UUID, exp, iat, ver}；secret = env **AUTH_JWT_SECRET**
  （backend/app/gateway/auth/config.py:68 —— 任务书猜测的 ``SECRET_KEY`` 不存在）。
- extensions JWT（backend/app/extensions/auth/jwt.py:25）：claims = {sub, username, role,
  permissions, exp, type}；secret = env JWT_SECRET/JWT_SECRET_KEY（另一套，不接入本服务，
  避免双 secret 源）。本服务只认 gateway upstream 同源 secret（设计 D1「复用网关签发的 JWT」）。
- cookie 名 = ``access_token``（backend/app/gateway/deps.py:590 同名读取）。

语义：
- secret 链: env ``ONTOSTUDIO_JWT_SECRET`` → 回退 gateway 同名 env ``AUTH_JWT_SECRET``；
  均未设置时 fail-closed（503，运营配置错误而非客户端错误）。
- 通道: ``Authorization: Bearer <jwt>`` 优先，回退 HttpOnly cookie ``access_token``（nginx
  同源路由下浏览器 cookie 自然携带，D1）。
- claims → CurrentUser: 尽量取 claims，缺省回填（gateway upstream token 只有 sub——
  username/email 等 v1 回填占位值；S2 前端直连如需真实资料再扩 token claims 或 DB bridge）。
- require_permission(perm) 签名保留（路由依赖声明零改动）；**v1 superadmin-only 口径**：
  token claims 的 roles(list)/role(str)/permissions(list) 含 ``superadmin`` 或 ``admin``
  即放行（gateway upstream token 无角色 claims → 一律 403，属预期收紧，S2 接 RBAC 时再放宽）。
- ``status`` 字段已补（T1 评审指出的 CurrentUser 缺失项），默认 "active"。
- MCP 传输层鉴权见 :func:`mcp_request_authorized`（X-Internal-Auth 共享头 或 合法 Bearer JWT）。
"""

from __future__ import annotations

import hmac
import os
import uuid

import jwt
from fastapi import HTTPException, Request, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ConfigDict

# gateway upstream 的 access_token cookie 名（backend/app/gateway/deps.py:590 同源）
ACCESS_TOKEN_COOKIE = "access_token"

# v1 superadmin-only 口径：角色/权限 claim 命中其一即视为 system:access 通过
_ADMIN_ROLE_CODES = {"superadmin", "admin"}


class CurrentUser(BaseModel):
    """Current user schema（字段形状与 gateway app.extensions.schemas.CurrentUser 一致）."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str | None = None
    role_id: uuid.UUID | None = None
    role_name: str | None = None
    dept_id: uuid.UUID | None = None
    dept_name: str | None = None
    status: str = "active"


def _jwt_secret() -> str:
    """Resolve the shared JWT secret（ONTOSTUDIO_JWT_SECRET → gateway 同名 AUTH_JWT_SECRET）.

    fail-closed: 均未配置时抛 503——服务端配置缺失，不猜 secret。
    """
    secret = os.getenv("ONTOSTUDIO_JWT_SECRET", "") or os.getenv("AUTH_JWT_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT auth not configured: set ONTOSTUDIO_JWT_SECRET (or gateway-same AUTH_JWT_SECRET)",
        )
    return secret


def decode_access_token(token: str) -> dict:
    """HS256 验签并返回 claims；任何失败抛 401（带 WWW-Authenticate: Bearer）。"""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except HTTPException:
        raise
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _extract_token(request: Request) -> str | None:
    """Bearer header 优先，回退 HttpOnly cookie（nginx 同源 D1 通道）。"""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


def _parse_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _claims_roles(claims: dict) -> list[str]:
    """Normalize role-ish claims（roles list / role str / role_name / permissions）→ 小写列表."""
    raw: list[str] = []
    roles_claim = claims.get("roles")
    if isinstance(roles_claim, (list, tuple)):
        raw.extend(str(r) for r in roles_claim)
    for key in ("role", "role_name"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            raw.append(value)
    permissions_claim = claims.get("permissions")
    if isinstance(permissions_claim, (list, tuple)):
        raw.extend(str(p) for p in permissions_claim)
    return [r.strip().casefold() for r in raw if r.strip()]


def claims_to_user(claims: dict) -> CurrentUser:
    """Map verified JWT claims → CurrentUser（gateway upstream 最小 claims 也接受）."""
    user_id = _parse_uuid(claims.get("sub"))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = claims.get("username") or claims.get("preferred_username") or "unknown"
    return CurrentUser(
        id=user_id,
        username=str(username),
        email=str(claims.get("email") or f"{username}@local"),
        full_name=claims.get("full_name"),
        role_id=_parse_uuid(claims.get("role_id")),
        role_name=claims.get("role_name") or claims.get("role"),
        dept_id=_parse_uuid(claims.get("dept_id")),
        dept_name=claims.get("dept_name"),
        status=claims.get("status") or "active",
    )


def _authenticate(request: Request) -> tuple[CurrentUser, list[str]]:
    """Authenticate a request → (user, normalized roles). 401 on missing/invalid token."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token(token)
    return claims_to_user(claims), _claims_roles(claims)


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI 依赖：验 JWT 并返回 CurrentUser（无权限判定）。"""
    user, _ = _authenticate(request)
    return user


def require_permission(permission: str):
    """依赖工厂（签名与 gateway app.extensions.auth.middleware.require_permission 一致）.

    v1 superadmin-only 口径：claims 角色命中 superadmin/admin 即放行（所有 permission 点
    同口径——路由现仅用 system:access）；其余 403。S2 再接 UnifiedPermissionEngine 细粒度 RBAC。
    """

    async def _check(request: Request) -> CurrentUser:
        user, roles = _authenticate(request)
        if not (_ADMIN_ROLE_CODES & set(roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _check


def mcp_request_authorized(headers: dict[bytes, bytes]) -> bool:
    """MCP streamable-http 传输层鉴权（ASGI guard 用，scope headers 键为小写 bytes）.

    - env ``ONTOSTUDIO_INTERNAL_AUTH_TOKEN`` 未设置 → 放行（内网开发态；Task 3 容器化时
      compose 两侧注入同一共享 token 后自动收紧）。
    - 设置后：``X-Internal-Auth`` 精确匹配（常量时间比较）**或** 合法 Bearer JWT（验签通过）
      二者其一即放行；否则 401 由 guard 回给 harness。
    """
    expected = os.getenv("ONTOSTUDIO_INTERNAL_AUTH_TOKEN", "")
    if not expected:
        return True

    internal = headers.get(b"x-internal-auth", b"").decode("latin-1")
    if internal and hmac.compare_digest(internal, expected):
        return True

    authorization = headers.get(b"authorization", b"").decode("latin-1")
    if authorization.lower().startswith("bearer "):
        try:
            decode_access_token(authorization[7:].strip())
            return True
        except HTTPException:
            return False
    return False
