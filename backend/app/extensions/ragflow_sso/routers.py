"""EAI-CUSTOM: RAGFlow SSO endpoints — 免登跳转 + per-user token — 本地定制,非上游."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.extensions.auth.middleware import get_current_user
from app.extensions.config import get_extensions_config
from app.extensions.database import get_db
from app.extensions.ragflow_sso.service import exchange_mode_web, get_or_issue_api_token
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/ragflow-sso", tags=["RAGFlow SSO"])

logger = logging.getLogger(__name__)


@router.get("/login")
async def ragflow_sso_login(current_user: CurrentUser = Depends(get_current_user)):
    """302 到 RAGFlow ?auth=<会话 token>:上游 root loader 落地 localStorage 并
    去参,前端零改动(RAGFlow spec §4)。显式 302（登录跳转契约;GET 导航下与
    Starlette 默认 307 等价）。"""
    cfg = get_extensions_config()
    access_token = await exchange_mode_web(current_user)
    return RedirectResponse(url=f"{cfg.ragflow.base_url}/?auth={access_token}", status_code=302)


@router.post("/token")
async def ragflow_sso_token(
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Per-user RAGFlow API token(缓存;首次调用经交换签发)。

    只返回 per-user token——共享 key 永不经由此端点外发(否则任何登录用户
    可取回共享 key,绕过 per-user 审计与数据集可见性,spec §5/§6)。
    """
    try:
        api_token = await get_or_issue_api_token(db, current_user)
    except (RuntimeError, httpx.HTTPError):
        # EAI-CUSTOM (SSO Plan 2): 交换失败曾只回 503 无服务端日志,排障无迹——补 warning
        logger.warning("ragflow sso exchange failed for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAGFlow SSO unavailable",
        ) from None
    return {"api_token": api_token}
