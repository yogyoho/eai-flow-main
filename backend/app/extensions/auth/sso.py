"""EAI SSO — 通用 OIDC 第三登录门面（发起 + 回调）。

EAI-CUSTOM：上游 OIDC 发起路由把 state cookie 的 Path 绑在 /api/v1/auth/callback/*
（oidc_state.set_state_cookie），EAI 回调路径收不到该 cookie，故本模块用**相同签名格式**
（OIDCStatePayload + HS256 + auth jwt_secret）自写 Path=/ 的 state cookie，使
上游 get_state_cookie 可直接校验。复用上游 OIDCService（discover/auth_url/authenticate_callback），
仅 import 不修改。仅预建号可登（按工号 join extensions User.username）。
"""

import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.extensions.database import get_db
from app.extensions.models import User
from deerflow.config.app_config import get_app_config

logger = logging.getLogger(__name__)

sso_router = APIRouter(prefix="/oidc", tags=["SSO"])

_oidc_service = None


def _get_oidc_service():
    """懒加载 OIDCService 单例（复用上游实现，不修改）。"""
    global _oidc_service
    if _oidc_service is None:
        from app.gateway.auth.oidc import OIDCService

        _oidc_service = OIDCService()
    return _oidc_service


def _resolve_provider(provider: str):
    """读取 config.yaml auth.oidc 中的 provider 配置；未启用/未知 → 404。

    使用模块级 get_app_config（便于测试 monkeypatch 覆盖）。
    """
    app_config = get_app_config()
    oidc = app_config.auth.oidc
    if not oidc.enabled:
        return None, None
    pc = oidc.providers.get(provider)
    if pc is None:
        return None, None
    return oidc, pc


def _resolve_redirect_uri(request: Request, provider: str, configured: str | None) -> str:
    """派生回调地址（未配置时按请求 origin 构造，同上游模式）。"""
    if configured:
        return configured
    origin = f"{request.url.scheme}://{request.headers.get('host', 'localhost:8001')}"
    return f"{origin}/api/extensions/auth/oidc/callback/{provider}"


def _set_eai_state_cookie(response: Response, request: Request, payload) -> None:
    """用上游签名格式写 Path=/ 的 state cookie（EAI 回调可收到）。"""
    from app.gateway.auth.oidc_state import _sign_state_payload
    from app.gateway.csrf_middleware import is_secure_request

    response.set_cookie(
        key=f"df_oidc_state_{payload.provider}",
        value=_sign_state_payload(payload),
        httponly=True,
        secure=is_secure_request(request),
        samesite="lax",
        max_age=300,  # 5 分钟，与上游一致
        path="/",
    )


def _delete_eai_state_cookie(response: Response, request: Request, provider: str) -> None:
    """按 Path=/ 删除 EAI 写的 state cookie（上游 delete_state_cookie 的 path 不符）。"""
    from app.gateway.csrf_middleware import is_secure_request

    response.delete_cookie(
        key=f"df_oidc_state_{provider}",
        secure=is_secure_request(request),
        samesite="lax",
        path="/",
    )


@sso_router.get("/start")
async def sso_start(request: Request, provider: str, response: Response):
    """发起 OIDC 登录：discover → 生成 state/nonce/PKCE → 写 Path=/ 的 state cookie → 302 IdP。

    EAI-CUSTOM：自建发起（上游发起路由的 state cookie Path 不符）。
    """
    from app.gateway.auth.oidc_state import (
        OIDCStatePayload,
        compute_code_challenge,
        generate_code_verifier,
        generate_nonce,
        generate_oidc_state,
    )

    _oidc, pc = _resolve_provider(provider)
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not configured")

    metadata = await _get_oidc_service().discover(pc.issuer)
    state = generate_oidc_state()
    nonce = generate_nonce() if pc.nonce_enabled else None
    verifier = generate_code_verifier() if pc.pkce_enabled else None
    challenge = compute_code_challenge(verifier) if verifier else None

    redirect_uri = _resolve_redirect_uri(request, provider, pc.redirect_uri)
    auth_url = _get_oidc_service().build_authorization_url(
        metadata=metadata,
        client_id=pc.client_id,
        redirect_uri=redirect_uri,
        scopes=pc.scopes,
        state=state,
        nonce=nonce,
        code_challenge=challenge,
    )

    payload = OIDCStatePayload(provider=provider, state=state, nonce=nonce, code_verifier=verifier)
    _set_eai_state_cookie(response, request, payload)

    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@sso_router.get("/callback/{provider}")
async def sso_callback(
    request: Request,
    provider: str,
    response: Response,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """OIDC 回调：验 state → 换码/验签 → 按工号 join extensions User → 复用 _issue_gateway_session。

    EAI-CUSTOM：仅预建号可登（工号未预建/非 active → 401，绝不自动建号）。
    """
    from app.extensions.auth.routers import _issue_gateway_session
    from app.gateway.auth.oidc_state import get_state_cookie

    _oidc, pc = _resolve_provider(provider)
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not configured")

    # 1) state 校验（constant-time）
    payload = get_state_cookie(request, provider)
    if payload is None or not secrets.compare_digest(payload.state, state):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid OIDC state")

    # 2) 换码 + id_token 验签（复用上游 OIDCService）
    metadata = await _get_oidc_service().discover(pc.issuer)
    redirect_uri = _resolve_redirect_uri(request, provider, pc.redirect_uri)
    identity = await _get_oidc_service().authenticate_callback(
        provider_id=provider,
        metadata=metadata,
        client_id=pc.client_id,
        client_secret=pc.client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=payload.code_verifier,
        nonce=payload.nonce,
        auth_method=pc.token_endpoint_auth_method,
    )

    # 3) 提取工号（employee_number 首选，preferred_username 回退）；email 作次级别名
    emp_no = identity.claims.get("employee_number") or identity.claims.get("preferred_username")
    email = identity.email or ""

    # 4) 按工号 join extensions User（仅预建号）
    stmt = select(User).where(User.is_deleted == False)  # noqa: E712
    if emp_no:
        stmt = stmt.where(User.username == emp_no)
    elif email:
        stmt = stmt.where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # 工号未命中时回退 email
    if user is None and emp_no and email:
        stmt = select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SSO account not provisioned or inactive")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    _delete_eai_state_cookie(response, request, provider)
    return await _issue_gateway_session(user.email, request, response)
