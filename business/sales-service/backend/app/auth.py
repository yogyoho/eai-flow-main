"""EAI identity, permission and data-scope integration.

The sales service never stores passwords or a second account directory. It
validates the shared EAI JWT, calls the existing permission APIs on the Gateway,
and keeps only sales-specific extension fields in ``user_profiles``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Depends, Request
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.enums import ROLE_LABELS, ROLE_PERMISSIONS, ROLE_SCOPE, SALES_PERMISSIONS, SALES_ROLES
from app.errors import SalesError, forbidden
from app.models import SalesRegion, UserProfile

logger = logging.getLogger(__name__)
settings = get_settings()

ACCESS_TOKEN_COOKIE = "access_token"
IDENTITY_CACHE: dict[str, tuple[float, Identity]] = {}
_CACHE_LOCK = asyncio.Lock()


@dataclass
class Identity:
    user_id: str
    username: str
    display_name: str
    email: str | None = None
    role_code: str = ""
    sales_role: str = "sales_rep"
    region_code: str = "DEFAULT"
    data_scope: str = "self"
    dept_id: str | None = None
    dept_ids: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    is_admin: bool = False
    auth_source: str = "eai"

    @property
    def sales_role_label(self) -> str:
        return ROLE_LABELS.get(self.sales_role, self.sales_role)

    def has(self, permission: str) -> bool:
        return self.is_admin or "*" in self.permissions or permission in self.permissions

    def to_public(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "role_code": self.role_code,
            "sales_role": self.sales_role,
            "sales_role_label": self.sales_role_label,
            "region_code": self.region_code,
            "data_scope": self.data_scope,
            "dept_id": self.dept_id,
            "dept_ids": self.dept_ids,
            "is_admin": self.is_admin,
            "permissions": sorted(self.permissions),
            "auth_source": self.auth_source,
        }


def _unauthorized(detail: str = "登录已失效，请重新登录") -> SalesError:
    return SalesError(detail, "AUTH-401-INVALID_TOKEN", 401)


def _extract_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token:
        return token
    token = request.headers.get("x-access-token")
    if token:
        return token
    raise _unauthorized("未提供登录凭证")


def _decode(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise _unauthorized() from exc
    if not payload.get("sub"):
        raise _unauthorized("登录凭证缺少用户标识")
    return payload


def _local_identity(payload: dict[str, Any]) -> Identity:
    sales_role = str(payload.get("sales_role") or "")
    role_code = str(payload.get("role_code") or "")
    if sales_role not in SALES_ROLES:
        sales_role = role_code if role_code in SALES_ROLES else "sales_rep"
    is_admin = bool(payload.get("is_admin")) or role_code in {"admin", "superadmin", "system_admin"}
    if is_admin:
        sales_role = "sales_admin"
    perms = set(payload.get("permissions") or [])
    if is_admin:
        perms = set(SALES_PERMISSIONS)
    elif not any(p.startswith("sales.") for p in perms):
        perms = set(ROLE_PERMISSIONS[sales_role])
    data_scope = "all" if is_admin else str(payload.get("data_scope") or ROLE_SCOPE[sales_role])
    return Identity(
        user_id=str(payload["sub"]),
        username=str(payload.get("username") or "local-user"),
        display_name=str(payload.get("full_name") or payload.get("username") or "本地用户"),
        email=payload.get("email"),
        role_code=role_code,
        sales_role=sales_role,
        region_code=str(payload.get("region_code") or settings.default_region_code),
        data_scope=data_scope,
        dept_id=payload.get("dept_id"),
        dept_ids=list(payload.get("dept_ids") or []),
        permissions=perms,
        is_admin=is_admin,
        auth_source="local",
    )


async def _fetch_eai_me(request: Request, token: str) -> dict[str, Any]:
    # Gateway session auth reads the access_token cookie. Build that cookie from
    # the already-validated token instead of forwarding the browser's cookies:
    # a stale cookie must never override the credential the caller presented.
    headers = {"Accept": "application/json", "Cookie": f"{ACCESS_TOKEN_COOKIE}={token}"}
    url = settings.eai_base_url.rstrip("/") + "/api/permissions/me"
    try:
        async with httpx.AsyncClient(timeout=settings.eai_timeout_seconds) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise SalesError("无法连接统一权限中心", "AUTH-503-EAI_UNAVAILABLE", 503) from exc
    if response.status_code in (401, 403):
        raise SalesError("统一权限中心拒绝访问", "AUTH-403-EAI_DENIED", response.status_code)
    if response.status_code >= 500:
        raise SalesError("统一权限中心暂不可用", "AUTH-503-EAI_UNAVAILABLE", 503)
    if response.status_code >= 400:
        raise SalesError("统一权限中心返回异常", "AUTH-502-EAI_BAD_RESPONSE", 502)
    try:
        return response.json()
    except ValueError as exc:
        raise SalesError("统一权限中心响应格式错误", "AUTH-502-EAI_BAD_RESPONSE", 502) from exc


def _find_region(profile: UserProfile | None, regions: list[SalesRegion], dept_ids: list[str]) -> str:
    if profile and profile.region_code:
        return profile.region_code
    wanted = set(dept_ids)
    for region in regions:
        if region.eai_dept_id and region.eai_dept_id in wanted:
            return region.code
    return settings.default_region_code


async def _resolve_identity(request: Request, db: AsyncSession) -> Identity:
    token = _extract_token(request)
    payload = _decode(token)

    if settings.auth_mode.lower() == "local":
        identity = _local_identity(payload)
    else:
        cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        async with _CACHE_LOCK:
            cached = IDENTITY_CACHE.get(cache_key)
        if cached and cached[0] > now:
            identity = cached[1]
        else:
            data = await _fetch_eai_me(request, token)
            raw_identity = data.get("identity") or {}
            permissions = set(data.get("permissions") or [])
            is_admin = bool(data.get("is_admin")) or "*" in permissions
            role_code = str(raw_identity.get("role_code") or "")
            user_id = str(raw_identity.get("user_id") or payload["sub"])

            profile = await db.get(UserProfile, user_id)
            sales_role = profile.sales_role if profile and profile.sales_role else ""
            if sales_role not in SALES_ROLES:
                sales_role = role_code if role_code in SALES_ROLES else ("sales_admin" if is_admin else "sales_rep")

            dept_ids = [str(x) for x in (raw_identity.get("dept_ids") or [])]
            if raw_identity.get("dept_id") and str(raw_identity["dept_id"]) not in dept_ids:
                dept_ids.append(str(raw_identity["dept_id"]))

            has_sales_permission = any(p.startswith("sales.") for p in permissions)
            if not has_sales_permission and settings.sales_bootstrap_permissions and not is_admin:
                permissions |= set(ROLE_PERMISSIONS.get(sales_role, set()))
            if is_admin:
                permissions |= set(SALES_PERMISSIONS)

            identity = Identity(
                user_id=user_id,
                username=str(raw_identity.get("username") or payload["sub"]),
                display_name=str(data.get("full_name") or raw_identity.get("username") or "销售用户"),
                email=data.get("email"),
                role_code=role_code,
                sales_role=sales_role,
                region_code=settings.default_region_code,
                data_scope=(profile.data_scope if profile and profile.data_scope else ROLE_SCOPE.get(sales_role, "self")),
                dept_id=str(raw_identity["dept_id"]) if raw_identity.get("dept_id") else None,
                dept_ids=dept_ids,
                permissions=permissions,
                is_admin=is_admin,
                auth_source="eai",
            )
            async with _CACHE_LOCK:
                IDENTITY_CACHE[cache_key] = (now + settings.permission_cache_ttl_seconds, identity)

    # Resolve region and persist only sales-specific extensions. Existing EAI
    # users/roles/departments remain the single account source.
    profile = await db.get(UserProfile, identity.user_id)
    regions = list((await db.execute(select(SalesRegion).where(SalesRegion.is_active.is_(True)))).scalars())
    identity.region_code = _find_region(profile, regions, identity.dept_ids)
    if identity.sales_role in {"sales_admin", "sales_director", "compliance_officer"}:
        identity.data_scope = "all"
    elif profile and profile.data_scope:
        identity.data_scope = profile.data_scope

    if profile is None:
        profile = UserProfile(
            id=identity.user_id,
            username=identity.username,
            display_name=identity.display_name,
            email=identity.email,
            role_code=identity.role_code,
            sales_role=identity.sales_role,
            region_code=identity.region_code,
            data_scope=identity.data_scope,
            eai_dept_id=identity.dept_id,
            last_login_at=datetime.now(UTC),
        )
        db.add(profile)
        await db.flush()
    else:
        profile.username = identity.username
        profile.display_name = identity.display_name
        profile.email = identity.email
        profile.role_code = identity.role_code or profile.role_code
        if not profile.sales_role:
            profile.sales_role = identity.sales_role
        if not profile.region_code:
            profile.region_code = identity.region_code
        if not profile.data_scope:
            profile.data_scope = identity.data_scope
        profile.eai_dept_id = profile.eai_dept_id or identity.dept_id
        profile.last_login_at = datetime.now(UTC)
        profile.synced_at = datetime.now(UTC)
        if identity.sales_role not in {"sales_admin", "sales_director", "compliance_officer"} and profile.data_scope:
            identity.data_scope = profile.data_scope

    return identity


async def get_current_identity(request: Request, db: AsyncSession = Depends(get_db)) -> Identity:
    try:
        return await _resolve_identity(request, db)
    except SalesError:
        raise
    except Exception as exc:  # noqa: BLE001 - auth failures must not leak internals
        logger.exception("identity resolution failed")
        raise SalesError("无法解析登录身份", "AUTH-500-IDENTITY", 500) from exc


def require_sales_permission(permission: str):
    async def dependency(identity: Identity = Depends(get_current_identity)) -> Identity:
        if not identity.has(permission):
            raise forbidden(f"缺少权限：{permission}", "AUTH-403-PERMISSION_DENIED")
        return identity

    return dependency


def scope_condition(identity: Identity, model):
    if identity.is_admin or identity.data_scope == "all":
        return model.id.is_not(None)
    if identity.data_scope == "region":
        return model.region_code == identity.region_code
    return model.owner_id == identity.user_id


def can_access_opportunity(identity: Identity, opportunity) -> bool:
    if identity.is_admin or identity.data_scope == "all":
        return True
    if identity.data_scope == "region":
        return opportunity.region_code == identity.region_code
    return opportunity.owner_id == identity.user_id


def require_opportunity_access(identity: Identity, opportunity) -> None:
    if not can_access_opportunity(identity, opportunity):
        raise forbidden("无权访问该商机", "SALES-403-SCOPE_DENIED")
