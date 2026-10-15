"""EAI-CUSTOM: RAGFlow SSO — JWT minting + exchange client + per-user credentials — 本地定制,非上游."""

import logging
import time

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.config import get_extensions_config
from app.extensions.ragflow_sso.models import RagflowCredential

logger = logging.getLogger(__name__)

AUDIENCE = "ragflow-sso"
TOKEN_TTL_SECONDS = 600


def mint_ragflow_jwt(user_id: str, username: str) -> str:
    """Sign a dedicated short-lived JWT with the shared secret (NOT the EAI
    session jwt.secret — isolation). RAGFlow validates: HS256 + exp required +
    type=access + aud=ragflow-sso."""
    cfg = get_extensions_config()
    if not cfg.ragflow.sso_secret:
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")
    now = int(time.time())
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "role": "user",
            "type": "access",
            "aud": AUDIENCE,
            "exp": now + TOKEN_TTL_SECONDS,
        },
        cfg.ragflow.sso_secret,
        algorithm="HS256",
    )


async def _exchange_request(method: str, url: str, **kwargs) -> httpx.Response:
    """Per-request httpx client; no retry by design (re-mint on flake is wasteful)."""
    async with httpx.AsyncClient(timeout=get_extensions_config().ragflow.timeout) as client:
        return await client.request(method, url, **kwargs)


async def exchange_mode_web(user) -> str:
    """Web SSO: mint + exchange for a RAGFlow session token (mode=web)."""
    token = mint_ragflow_jwt(str(user.id), user.username)
    cfg = get_extensions_config()
    resp = await _exchange_request(
        "POST",
        f"{cfg.ragflow.base_url}/api/v1/auth/sso/exchange",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "web"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"RAGFlow SSO exchange failed: HTTP {resp.status_code}")
    data = resp.json().get("data") or {}
    access_token = data.get("access_token", "")
    if not access_token:
        raise RuntimeError("RAGFlow SSO exchange returned no access_token")
    return access_token


async def get_or_issue_api_token(db: AsyncSession, user) -> str:
    """Per-user API token: cached row first; else mint+exchange mode=api and
    persist. Concurrent first-issue races are decided by the unique constraint
    on eai_user_id: the loser's insert raises IntegrityError and it serves the
    winner's row in-call (self-heal)."""
    stmt = select(RagflowCredential).where(RagflowCredential.eai_user_id == user.id)
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if cred is not None:
        return cred.api_token

    token = mint_ragflow_jwt(str(user.id), user.username)
    cfg = get_extensions_config()
    resp = await _exchange_request(
        "POST",
        f"{cfg.ragflow.base_url}/api/v1/auth/sso/exchange",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "api"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"RAGFlow SSO exchange failed: HTTP {resp.status_code}")
    api_token = (resp.json().get("data") or {}).get("api_token", "")
    if not api_token:
        raise RuntimeError("RAGFlow SSO exchange returned no api_token")

    try:
        db.add(RagflowCredential(eai_user_id=user.id, api_token=api_token))
        await db.commit()
    except IntegrityError:
        # unique-race: the concurrent first-issue won; serve its token
        await db.rollback()
        result = await db.execute(stmt)
        cred = result.scalar_one()
        return cred.api_token
    return api_token


async def get_client_for_user(db: AsyncSession, user):
    """RAGFlowClient bound to the caller's per-user token; shared key fallback
    when SSO is unconfigured or exchange fails (audit degrades, service stays
    up — spec §5 fallback contract)."""
    from app.extensions.knowledge.client import RAGFlowClient

    cfg = get_extensions_config()
    if not cfg.ragflow.sso_secret:
        return RAGFlowClient()
    try:
        api_key = await get_or_issue_api_token(db, user)
        return RAGFlowClient(api_key=api_key)
    except (RuntimeError, httpx.HTTPError, SQLAlchemyError) as exc:
        # EAI-CUSTOM: 回滚是安全 no-op(无 pending 时);DB 层失败会把 session 置为
        # invalidated(PendingRollbackError 会毒化请求余下所有查询)——先回滚再降级,
        # 审计降级但请求不 500。编程错误(TypeError 等)不在白名单,直接上抛。
        # 只记异常类型 + user id,不记 exc——SQLAlchemy 异常串会内嵌 api_token 值。
        await db.rollback()
        logger.warning(
            "RAGFlow per-user token unavailable (%s) for user %s; falling back to shared key",
            type(exc).__name__,
            user.id,
        )
        return RAGFlowClient()
