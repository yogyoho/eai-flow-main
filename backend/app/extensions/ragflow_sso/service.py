"""EAI-CUSTOM: RAGFlow SSO — JWT minting + exchange client + per-user credentials
+ shared-tenant 服务身份 — 本地定制,非上游."""

import logging
import time
import uuid

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


# ── EAI-CUSTOM (v1.1 共享租户修正案 Task 2): 服务身份 ──
# EAI 托管 KB 必须由同一个固定 RAGFlow 账号创建(全部落在同一租户、permission=team、
# 加入租户的 SSO 用户均可用)。服务身份 = 扩展库 User 行,首用自动建;其 RAGFlow
# 侧账号 sso-<service-user-uuid>@eai.internal 由 RAGFlow EnsureSSOUser 在交换时落库。
SERVICE_USERNAME = "ragflow-service"
SERVICE_EMAIL = "ragflow-service@eai.internal"


async def _get_or_create_service_user(db: AsyncSession):
    """服务身份首用自动建。并发首建竞态与 get_or_issue_api_token 同解:
    users.username/email 唯一约束兜底,败者撞 IntegrityError → 回滚 → 重查胜者行
    (自愈返回,不向上抛)。"""
    from app.extensions.auth.jwt import hash_password
    from app.extensions.models import User

    result = await db.execute(select(User).where(User.username == SERVICE_USERNAME))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        username=SERVICE_USERNAME,
        email=SERVICE_EMAIL,
        # 不可登录:哈希的是一次性随机串(镜像 sso_provision.go 的 unusable-password
        # 模式)——该账号仅用于铸造 mode=api 交换,永不走密码登录。
        password_hash=hash_password(uuid.uuid4().hex),
    )
    try:
        db.add(user)
        await db.commit()
    except IntegrityError:
        # 并发首建竞态:唯一约束兜底,回滚后重查胜者行(同 get_or_issue_api_token 先例)
        await db.rollback()
        result = await db.execute(select(User).where(User.username == SERVICE_USERNAME))
        user = result.scalar_one()
    await db.refresh(user)
    return user


async def get_service_client(db: AsyncSession):
    """共享租户 KB 生命周期专用客户端:绑定服务身份的 per-user token。

    不降级——SSO 未配置时 RuntimeError 直接上抛(与 get_client_for_user 的读取
    降级不同):生命周期必须响亮失败,绝不静默落回共享 key。"""
    cfg = get_extensions_config()
    if not cfg.ragflow.sso_secret:
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")
    service_user = await _get_or_create_service_user(db)
    api_key = await get_or_issue_api_token(db, service_user)
    from app.extensions.knowledge.client import RAGFlowClient

    return RAGFlowClient(api_key=api_key)
