"""EAI-CUSTOM: RAGFlow SSO — JWT minting + exchange client + per-user credentials — 本地定制,非上游."""

import logging
import time

import httpx
import jwt
from sqlalchemy import select
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
    """HTTP seam for tests (mirrors RAGFlowClient._request_with_retry pattern)."""
    async with httpx.AsyncClient(timeout=get_extensions_config().ragflow.timeout) as client:
        return await client.request(method, url, **kwargs)


async def exchange_mode_web(db: AsyncSession, user) -> str:
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
    return data.get("access_token", "")


async def get_or_issue_api_token(db: AsyncSession, user) -> str:
    """Per-user API token: cached row first; else mint+exchange mode=api and
    persist. Concurrent first-issue races rely on the unique constraint on
    eai_user_id (loser's insert fails; next call reads the winner's row)."""
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

    db.add(RagflowCredential(eai_user_id=user.id, api_token=api_token))
    await db.commit()
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
    except Exception as exc:  # noqa: BLE001 — fallback is deliberate
        logger.warning("RAGFlow per-user token unavailable (%s); falling back to shared key", exc)
        return RAGFlowClient()
