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
- require_permission(perm) 签名保留（路由依赖声明零改动）；**v1 claims 口径 + v2 授权委托**：
  token claims 的 roles(list)/role(str)/permissions(list) 含 ``superadmin`` 或 ``admin``
  即放行；gateway upstream cookie 无角色 claims（v1 下浏览器全 403）→ v2（S2 Task 3）携带
  原样 Cookie 反查 gateway ``/api/permissions/me``（UnifiedPermissionEngine 单一真相源，
  is_admin / permissions 含目标点即放行，TTL 缓存，fail-closed），env ``ONTOSTUDIO_GATEWAY_URL``
  覆盖 gateway 基址（默认 http://gateway:8001 容器网络服务名）。
- ``status`` 字段已补（T1 评审指出的 CurrentUser 缺失项），默认 "active"。
- MCP 传输层鉴权见 :func:`mcp_request_authorized`（X-Internal-Auth 共享头 或 合法 Bearer JWT）。
"""

from __future__ import annotations

import hmac
import logging
import os
import time
import uuid

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# gateway upstream 的 access_token cookie 名（backend/app/gateway/deps.py:590 同源）
ACCESS_TOKEN_COOKIE = "access_token"

# v1 superadmin-only 口径：角色/权限 claim 命中其一即视为 system:access 通过
_ADMIN_ROLE_CODES = {"superadmin", "admin"}

# HS256 对称密钥最低字节数（RFC 7518 §3.2 建议 ≥32 字节；防弱 secret 被 PyJWT 静默接受）
_MIN_SECRET_LEN = 32


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

    fail-closed: 未配置或强度不足（<32 字节, 评审 Fix 3）均抛 503——服务端配置问题，不猜 secret。
    """
    secret = os.getenv("ONTOSTUDIO_JWT_SECRET", "") or os.getenv("AUTH_JWT_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT auth not configured: set ONTOSTUDIO_JWT_SECRET (or gateway-same AUTH_JWT_SECRET)",
        )
    if len(secret) < _MIN_SECRET_LEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'JWT secret too weak: {len(secret)} bytes < {_MIN_SECRET_LEN}; generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`',
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
        logger.warning("auth deny: %s %s — no token (评审 Fix 5 审计)", request.method, request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(token)
        user = claims_to_user(claims)
    except HTTPException as exc:
        logger.warning("auth deny: %s %s — %s", request.method, request.url.path, exc.detail)
        raise
    return user, _claims_roles(claims)


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI 依赖：验 JWT 并返回 CurrentUser（无权限判定）。"""
    user, _ = _authenticate(request)
    return user


def require_permission(permission: str):
    """依赖工厂（签名与 gateway app.extensions.auth.middleware.require_permission 一致）.

    v1 superadmin-only 口径：claims 角色命中 superadmin/admin 即放行（所有 permission 点
    同口径——路由现仅用 system:access）。

    v2（S2 Task 3, EAI-CUSTOM）：gateway upstream 签发的 cookie 无角色 claims（v1 下一律
    403，语义地图对浏览器全灭）。改为**授权委托**：携带原样 Cookie 调 gateway
    ``GET /api/permissions/me``（UnifiedPermissionEngine 单一真相源），``is_admin`` 或
    permissions 含目标点即放行；结果按用户 TTL 缓存。gateway 不可达一律 403 fail-closed。
    claims 自带角色的 token（extensions 式/未来 token 内嵌 RBAC）仍走 v1 快路径，零委托。
    """

    async def _check(request: Request) -> CurrentUser:
        user, roles = _authenticate(request)
        if _ADMIN_ROLE_CODES & set(roles):
            return user
        allowed = await _gateway_authorizes(request, user, permission)
        if not allowed:
            logger.warning(
                "authz deny: %s %s — user=%s roles=%s lacks '%s' (gateway delegation)",
                request.method,
                request.url.path,
                user.id,
                roles or "none",
                permission,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _check


# ── v2 授权委托：gateway UnifiedPermissionEngine（单一真相源）─────────────────
# EAI-CUSTOM (S2 Task 3): gateway cookie 通道无角色 claims → 携带原样 Cookie 反查
# gateway /api/permissions/me 判定。缓存 (user_id, permission) → (allowed, expires_monotonic)；
# TTL 内角色变更延迟生效（30s，可容忍——权限非高频变更面）。进程内缓存即可：单实例
# 部署，且授权判断失败方向恒为 fail-closed。
#
# EAI-CUSTOM (2026-09-22): 键必须含 permission。历史实现只按 user_id 做键，而值的语义
# 是"该用户对某一次查询的那个权限是否放行"——只查单一权限（system:access）时未暴露；
# 本体动作层引入第二个权限（ontology:action:review）后，同一用户在 TTL 内查两个权限会
# 命中错误缓存（把一个权限的放行结果当成另一个的）。见
# docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
_AUTHZ_DELEGATE_TTL_SECONDS = 30.0
_authz_cache: dict[tuple[uuid.UUID, str], tuple[bool, float]] = {}


def _gateway_base_url() -> str:
    """gateway 基址：容器网络默认服务名；宿主直跑 dev 时 env 覆盖（如 http://localhost:2026）."""
    return os.getenv("ONTOSTUDIO_GATEWAY_URL", "") or "http://gateway:8001"


async def _gateway_me(request: Request) -> dict | None:
    """反查 gateway ``/api/permissions/me`` → 解析后的 payload；任何失败一律 ``None``.

    EAI-CUSTOM (2026-09-22 Task 7): 从 ``_gateway_authorizes`` 抽出的**取数与解析**那一段
    ——动作层除了"这个权限放没放"，还要取同一个 payload 里的 ``identity.role_code``
    （见 :func:`resolve_actor_role`），两者共用同一条取数路径，免得两处各自漂移。

    fail-closed 面逐个说清（调用方据此决定返回 False 还是 None）：
    - 无 Cookie：**不打 warning**（浏览器会话过期是常态，打日志会淹没真故障），直接 None；
    - gateway 不可达 / 非 200 / JSON 畸形 / 顶层不是对象：打 warning + None。
    非对象那一档是实修：此前 ``_gateway_authorizes`` 直接 ``data.get(...)``，gateway 回一个
    JSON 数组或字符串时会以 ``AttributeError`` 逃成 500（fail-open 方向的反面——不是放行，
    是崩），现归一到 None → False。
    """
    cookie_header = request.headers.get("cookie", "")
    if not cookie_header:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_gateway_base_url()}/api/permissions/me",
                headers={"Cookie": cookie_header},
            )
    except httpx.HTTPError as exc:
        logger.warning("authz delegate: gateway /api/permissions/me unreachable — %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning(
            "authz delegate: gateway /api/permissions/me -> %d (fail-closed)", resp.status_code
        )
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def _gateway_authorizes(request: Request, user: CurrentUser, permission: str) -> bool:
    """问 gateway 权限引擎：is_admin 或 permissions 含 permission 即放行.

    fail-closed：无 Cookie / gateway 不可达 / 非 200（含 401/403）/ 响应异常 → False。
    200 且判定成功/失败均写缓存（TTL 内同用户同权限免重复反查）。
    """
    cached = _authz_cache.get((user.id, permission))
    if cached is not None:
        allowed, expires_at = cached
        if time.monotonic() < expires_at:
            return allowed
        _authz_cache.pop((user.id, permission), None)

    data = await _gateway_me(request)
    if data is None:
        return False
    allowed = bool(data.get("is_admin")) or permission in (data.get("permissions") or [])
    _authz_cache[(user.id, permission)] = (allowed, time.monotonic() + _AUTHZ_DELEGATE_TTL_SECONDS)
    return allowed


# ── 动作层公开入口（Task 7）──────────────────────────────────────────────
# 三个函数的失败方向**各自不同**，别合并成一句"都 fail-closed"：
#   authorize           → False（拒绝动作）
#   fetch_scope_rule    → none_allow（拒绝动作，且不泄漏"规则取不到"与"规则为空"的区别）
#   resolve_actor_role  → None（**不**拒绝动作——它只喂审计列，拒了一个合法动作是本末倒置）


async def authorize(request: Request, user: CurrentUser, permission: str) -> bool:
    """公开授权判定入口（动作层用）。

    与 ``require_permission`` 走的是**同一条**判定路径与**同一个** ``(user.id, permission)``
    复合键缓存——只是不抛异常、由调用方决定怎么把它变成 403。复合键的理由见 :data:`_authz_cache`。
    """
    return await _gateway_authorizes(request, user, permission)


async def resolve_actor_role(request: Request, user: CurrentUser) -> str | None:
    """动作发起者的角色 **code**（``permissions.yaml`` 的 roles 键），供审计行 ``actor_role``。

    **为什么不是 ``user.role_name``**（计划 Task 7 Step 3 给的是它，此处有意改）：

    1. ``CurrentUser.role_name`` 装的是 ``roles.name`` **显示名**（``superadmin`` →
       ``"超级管理员"``）——同一角色改名后，**历史审计行会跟着变意思**；而 code 是
       registry / ``identity.role_code`` / ``roles_custom.yaml`` overlay 的公共键，
       审计行只有拿它才对得上账。
    2. 更要紧的是：本服务的 ``role_name`` **只可能来自 JWT claims**（``claims_to_user``），
       而 gateway 签发的 access_token claims 是 ``{sub, exp, iat, ver}``（无角色，
       backend/app/gateway/auth/jwt.py:28）——浏览器经 nginx 带的是这个 Cookie。也就是说
       计划那一行会**给每一条真实审计行写 NULL**。同理 ``user.role_id`` 也是 claims-only。
       正典角色只能问 gateway 身份（``identity.role_code``，与 ``/scope`` 同一来源）。
    3. token 自带的 ``roles`` claim 也不能用：那是**调用方自己声明**的，不是授权真源
       （``require_permission`` 的 v1 快路径只把它当快路径，动作层的授权判定恒走委托）。

    失败方向：无 Cookie / gateway 不可达 / 身份里没有 role_code → ``None``（审计列可空）。
    **不缓存**：它只服务审计标注，而缓存会引入一份需要独立论证的 staleness；动作调用是
    人触发的低频写，多一次内网 GET 相对其后的全量重投影不是可感知的代价。
    """
    data = await _gateway_me(request)
    if data is None:
        return None
    identity = data.get("identity")
    if not isinstance(identity, dict):
        return None
    code = identity.get("role_code")
    return code if isinstance(code, str) and code else None


async def fetch_scope_rule(request: Request, resource: str):
    """取当前用户对 ``resource`` 的数据范围规则（gateway ``GET /api/permissions/scope``）。

    ``resource`` 是 ``permissions.yaml`` 的**模块 key**（``ontology`` / ``contract_price`` …
    —— 交付时按注册表写，别按模块名猜）。返回本地 ``FilterRule``（``app.ontology.scope``）。

    **任何失败一律 ``none_allow``**（拒绝一切），包括：无 Cookie、gateway 不可达、非 200、
    JSON 畸形、wire 规则编译不出来。方向为什么必须是拒而不是放行——这一层的意义就是
    「取不到范围 ⇒ 不让动作落在任何行上」，取不到当放行等于把数据范围层整个旁路掉。

    ``app.ontology.scope`` 用**惰性 import**：``app.auth`` 被 ``app.ontology.routers`` 顶层
    导入，而导入 ``app.ontology.*`` 会先执行 ``app/ontology/__init__.py``（它注册建表用的
    ``Base`` 子类）——顶层 import 会绕成环。返回类型因此不写注解（写了就得在顶层 import）。
    """
    from app.ontology.scope import FilterRule

    cookie_header = request.headers.get("cookie", "")
    if not cookie_header:
        return FilterRule(operator="none_allow")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_gateway_base_url()}/api/permissions/scope",
                params={"resource": resource},
                headers={"Cookie": cookie_header},
            )
        if resp.status_code != 200:
            logger.warning("scope delegate: gateway /api/permissions/scope -> %d (fail-closed)", resp.status_code)
            return FilterRule(operator="none_allow")
        payload = resp.json()
        wire = payload["rule"]
        return FilterRule.from_wire(wire)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # ValueError 盖 ``ScopeCompileError``（它继承 ValueError——wire 畸形就是从这个名字
        # 出来的，别在这里再列一条同族 except，那条永远到不了）与 json 解析失败；
        # KeyError/TypeError/AttributeError 盖"响应形状不是 {rule: {...}}"——这些**必须**
        # 在此归一，否则畸形响应会以裸异常逃成 500，而不是"按拒处理"。
        logger.warning("scope delegate: 取范围规则失败（按 none_allow 拒）— %s: %s", type(exc).__name__, exc)
        return FilterRule(operator="none_allow")


_MCP_OPEN_MODE_WARNED = False


def mcp_request_authorized(headers: dict[bytes, bytes]) -> bool:
    """MCP streamable-http 传输层鉴权（ASGI guard 用，scope headers 键为小写 bytes）.

    - env ``ONTOSTUDIO_INTERNAL_AUTH_TOKEN`` 未设置 → 放行（内网开发态；Task 3 容器化时
      compose 两侧注入同一共享 token 后自动收紧），首次放行打一次性 warning 防临时态永久化。
    - 设置后：``X-Internal-Auth`` 精确匹配（**按字节**常量时间比较——str 版 compare_digest
      遇非 ASCII 抛 TypeError 会变未认证 500，评审 Fix 1）**或** 合法 Bearer JWT（验签通过）
      二者其一即放行；否则 401 由 guard 回给 harness。
    """
    global _MCP_OPEN_MODE_WARNED
    expected = os.getenv("ONTOSTUDIO_INTERNAL_AUTH_TOKEN", "")
    if not expected:
        if not _MCP_OPEN_MODE_WARNED:
            _MCP_OPEN_MODE_WARNED = True
            logger.warning("MCP 传输层未配置 ONTOSTUDIO_INTERNAL_AUTH_TOKEN——当前对内网匿名开放；Task 3 compose 需 gateway(extensions_config headers) 与 ontostudio 两侧注入同一 token 后自动收紧")
        return True

    internal = headers.get(b"x-internal-auth")
    if internal and hmac.compare_digest(internal, expected.encode("utf-8")):
        return True

    authorization = headers.get(b"authorization", b"").decode("latin-1")
    if authorization.lower().startswith("bearer "):
        # 显式决策（评审 Fix 6）: MCP Bearer 通道只验签、**不做角色判定**——agent 通道是服务间
        # 信任（调用方 = gateway harness, 非终端用户身份），工具级权限由 server 内部契约约束。
        # 后续若引入终端用户直连 MCP，再在此叠加 require_permission 语义——勿当遗漏"修复"。
        try:
            decode_access_token(authorization[7:].strip())
            return True
        except HTTPException:
            return False
    return False
