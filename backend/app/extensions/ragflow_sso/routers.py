"""EAI-CUSTOM: RAGFlow SSO endpoints — 免登跳转 + per-user token — 本地定制,非上游."""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.extensions.auth.middleware import get_current_user
from app.extensions.config import get_extensions_config
from app.extensions.database import get_db
from app.extensions.ragflow_sso.service import exchange_mode_web, get_client_for_user
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/ragflow-sso", tags=["RAGFlow SSO"])


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
    """Per-user RAGFlow API token(缓存命中直读;首次调用经 mode=api 交换签发;
    SSO 未配置/交换失败回退共享 key —— spec §5 回退契约)。"""
    client = await get_client_for_user(db, current_user)
    return {"api_token": client.api_key}
