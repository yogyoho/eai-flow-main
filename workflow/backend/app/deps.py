"""Request context dependencies.

``local`` mode trusts the reverse-proxy ``X-User-*`` headers and is intended for
the standalone demo and the test suite. ``eai`` mode validates the shared EAI
JWT and resolves the authoritative identity + permission set through the
Gateway's ``/api/permissions/me`` endpoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from dataclasses import dataclass, field

import httpx
from fastapi import Header, HTTPException, Request
from jose import JWTError, jwt

from .config import settings

_CACHE: dict[str, tuple[float, RequestContext]] = {}
_CACHE_LOCK = asyncio.Lock()


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


@dataclass(slots=True)
class RequestContext:
    handler: str = "system"
    name: str = "系统"
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dept: str | None = None
    tenant_id: str = settings.default_tenant
    is_admin: bool = False
    auth_mode: str = field(default_factory=lambda: settings.auth_mode)

    @property
    def claims(self) -> list[str]:
        values = [f"role:{role}" for role in self.roles] + list(self.roles)
        values.extend(self.permissions)
        if self.is_admin:
            values.append("*")
        if self.dept:
            values.extend([f"dept:{self.dept}", self.dept])
        return values

    def has_permission(self, permission: str) -> bool:
        return self.is_admin or "*" in self.permissions or permission in self.permissions


def _unauthorized(detail: str = "登录已失效，请重新登录") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    token = request.cookies.get(settings.access_token_cookie)
    if token:
        return token
    token = request.headers.get("x-access-token")
    return token.strip() if token and token.strip() else None


def _decode(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise _unauthorized() from exc
    if not payload.get("sub"):
        raise _unauthorized("登录凭证缺少用户标识")
    return payload


async def _fetch_eai_me(token: str) -> dict:
    # Gateway session auth reads the access_token cookie. Build that cookie from
    # the already-validated token instead of forwarding the browser's cookies: a
    # stale cookie must never override the credential the caller presented.
    headers = {
        "Accept": "application/json",
        "Cookie": f"{settings.access_token_cookie}={token}",
    }
    url = settings.eai_base_url.rstrip("/") + "/api/permissions/me"
    try:
        async with httpx.AsyncClient(timeout=settings.eai_timeout_seconds) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="无法连接统一权限中心") from exc
    if response.status_code in (401, 403):
        raise _unauthorized("统一权限中心拒绝访问")
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="统一权限中心暂不可用")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="统一权限中心返回异常")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="统一权限中心响应格式错误") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="统一权限中心响应格式错误")
    return data


def _context_from_eai(payload: dict, data: dict, tenant_id: str) -> RequestContext:
    identity = data.get("identity")
    if not isinstance(identity, dict):
        identity = {}
    raw_permissions = data.get("permissions")
    permissions = (
        [str(item) for item in raw_permissions if item] if isinstance(raw_permissions, (list, tuple, set)) else []
    )
    is_admin = bool(data.get("is_admin")) or "*" in permissions
    role_code = str(identity.get("role_code") or payload.get("role_code") or "")
    roles: list[str] = [role_code] if role_code else []
    raw_roles = identity.get("roles")
    for role in raw_roles if isinstance(raw_roles, (list, tuple, set)) else []:
        value = str(role)
        if value and value not in roles:
            roles.append(value)
    raw_dept_ids = identity.get("dept_ids")
    dept_ids = [str(item) for item in raw_dept_ids if item] if isinstance(raw_dept_ids, (list, tuple, set)) else []
    dept = str(identity.get("dept_id") or (dept_ids[0] if dept_ids else "") or "")
    handler = str(identity.get("user_id") or payload["sub"])
    name = str(
        data.get("full_name")
        or identity.get("username")
        or payload.get("full_name")
        or payload.get("username")
        or handler
    )
    return RequestContext(
        handler=handler,
        name=name,
        roles=roles,
        permissions=permissions,
        dept=dept or None,
        tenant_id=tenant_id,
        is_admin=is_admin,
        auth_mode="eai",
    )


async def _resolve_eai(token: str | None) -> RequestContext:
    if not token:
        raise _unauthorized("未提供登录凭证")
    cache_key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    async with _CACHE_LOCK:
        if len(_CACHE) > 1024:
            for key, (expires, _) in list(_CACHE.items()):
                if expires <= now:
                    del _CACHE[key]
        cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    payload = _decode(token)
    data = await _fetch_eai_me(token)
    # In EAI mode the tenant is part of the authoritative token, never a
    # caller-controlled header. Local/demo mode keeps the X-Tenant-Id override.
    tenant_id = str(payload.get("tenant_id") or settings.default_tenant)
    context = _context_from_eai(payload, data, tenant_id)
    async with _CACHE_LOCK:
        _CACHE[cache_key] = (now + settings.permission_cache_ttl_seconds, context)
    return context


def _context_from_headers(
    *,
    x_user_id: str | None,
    x_user_name: str | None,
    x_user_roles: str | None,
    x_user_dept: str | None,
    tenant_id: str,
) -> RequestContext:
    return RequestContext(
        handler=(x_user_id or "system").strip() or "system",
        name=(x_user_name or "系统").strip() or "系统",
        roles=_split(x_user_roles),
        dept=(x_user_dept or "").strip() or None,
        tenant_id=tenant_id,
        auth_mode="local",
    )


async def get_context(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
    x_user_roles: str | None = Header(default=None, alias="X-User-Roles"),
    x_user_dept: str | None = Header(default=None, alias="X-User-Dept"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_internal_token: str | None = Header(default=None, alias="X-Workflow-Internal-Token"),
) -> RequestContext:
    tenant_id = (x_tenant_id or settings.default_tenant).strip() or settings.default_tenant
    if settings.internal_token and x_internal_token and hmac.compare_digest(settings.internal_token, x_internal_token):
        # Trusted BFF path: the caller has already authenticated the end user.
        return _context_from_headers(
            x_user_id=x_user_id,
            x_user_name=x_user_name,
            x_user_roles=x_user_roles,
            x_user_dept=x_user_dept,
            tenant_id=tenant_id,
        )
    if settings.auth_mode == "local":
        return _context_from_headers(
            x_user_id=x_user_id,
            x_user_name=x_user_name,
            x_user_roles=x_user_roles,
            x_user_dept=x_user_dept,
            tenant_id=tenant_id,
        )
    return await _resolve_eai(_extract_token(request))
