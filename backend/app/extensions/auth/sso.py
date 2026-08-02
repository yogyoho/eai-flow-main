"""EAI SSO — 通用 OIDC 第三登录门面（发起 + 回调）。

EAI-CUSTOM：上游 OIDC 发起路由把 state cookie 的 Path 绑在 /api/v1/auth/callback/*
（oidc_state.set_state_cookie），EAI 回调路径收不到该 cookie，故本模块用**相同签名格式**
（OIDCStatePayload + HS256 + auth jwt_secret）自写 Path=/ 的 state cookie，使
上游 get_state_cookie 可直接校验。复用上游 OIDCService（discover/auth_url/authenticate_callback），
仅 import 不修改。仅预建号可登（按工号 join extensions User.username）。
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.extensions.database import get_db
from app.extensions.models import User

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
    """读取 config.yaml auth.oidc 中的 provider 配置；未启用/未知 → 404。"""
    from deerflow.config.app_config import get_app_config

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
