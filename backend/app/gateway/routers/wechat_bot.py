"""WeChat iLink system bot: admin bind surface + user binding-code (E-续 ③).

Dedicated router for the system WeChat bot's production onboarding:
- admin binds/rebinds the bot from the browser (QR shown in the UI, not logs);
- a logged-in user generates a one-time binding code; sending `/connect <code>`
  to the bot links their WeChat identity to their DeerFlow account (handled in
  ChannelManager._handle_command), after which their messages run as that account.

Reuses the channel_connections persistence primitives (provider="wechat") but is
independent of the channel_connections feature flag — that feature's 渠道 UI stays off.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/channels/wechat-bot", tags=["channels"])
logger = logging.getLogger(__name__)

_BIND_CODE_TTL_SECONDS = 600


class WechatBotBindStatus(BaseModel):
    status: str | None = None
    qrcode_url: str | None = None
    bound: bool = False
    ilink_bot_id: str | None = None


class WechatBindCodeResponse(BaseModel):
    code: str
    instruction: str
    expires_in: int


class WechatShareQrcodeResponse(BaseModel):
    qrcode: str
    qrcode_img_content: str | None = None


async def _require_admin(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        from app.gateway.deps import get_current_user_from_request

        user = await get_current_user_from_request(request)
    if getattr(user, "system_role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required to manage the WeChat bot.")


def _get_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(user.id)


def _get_wechat_channel():
    """Return the running WechatChannel (duck-typed by get_bind_state), or None."""
    from app.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        return None
    channel = service.get_channel("wechat")
    if channel is None or not hasattr(channel, "get_bind_state"):
        return None
    return channel


def _get_connection_repo():
    from deerflow.persistence.channel_connections import ChannelConnectionRepository
    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return ChannelConnectionRepository(session_factory)


@router.post("/bind", status_code=202)
async def bind_wechat_bot(request: Request) -> dict[str, str]:
    """Admin: clear any token and start a fresh QR bind (non-blocking)."""
    await _require_admin(request)
    channel = _get_wechat_channel()
    if channel is None:
        raise HTTPException(status_code=409, detail="WeChat bot is not running.")
    await channel.start_bind()
    return {"status": "pending"}


@router.get("/bind/status", response_model=WechatBotBindStatus)
async def get_wechat_bot_bind_status(request: Request) -> WechatBotBindStatus:
    """Admin: poll the bind state (QR url + status)."""
    await _require_admin(request)
    channel = _get_wechat_channel()
    if channel is None:
        raise HTTPException(status_code=409, detail="WeChat bot is not running.")
    return WechatBotBindStatus(**channel.get_bind_state())


@router.post("/bind-code", response_model=WechatBindCodeResponse)
async def create_wechat_bind_code(request: Request) -> WechatBindCodeResponse:
    """User: generate a one-time code to link their WeChat to this account.

    Send `/connect <code>` to the WeChat bot; the bot consumes the code
    (ChannelManager._handle_command) and records the wechat_user → account link.
    """
    user_id = _get_user_id(request)
    repo = _get_connection_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="WeChat binding persistence is not available.")
    code = secrets.token_urlsafe(16)
    await repo.create_oauth_state(
        owner_user_id=user_id,
        provider="wechat",
        state=code,
        expires_at=datetime.now(UTC) + timedelta(seconds=_BIND_CODE_TTL_SECONDS),
    )
    return WechatBindCodeResponse(
        code=code,
        instruction=f"Send this to the WeChat bot: /connect {code}",
        expires_in=_BIND_CODE_TTL_SECONDS,
    )


@router.post("/share-qrcode/refresh", response_model=WechatShareQrcodeResponse)
async def refresh_wechat_share_qrcode(request: Request) -> WechatShareQrcodeResponse:
    """Admin: fetch a fresh share QR for end users to scan (adds ClawBot to their WeChat).

    Does NOT poll get_qrcode_status, so it does not rotate the bot_token or clobber
    the in-flight admin bind state. The QR is time-limited by iLink; re-fetch if expired.
    """
    await _require_admin(request)
    channel = _get_wechat_channel()
    if channel is None:
        raise HTTPException(status_code=409, detail="WeChat bot is not running.")
    data = await channel.fetch_share_qrcode()
    qrcode = str(data.get("qrcode") or "").strip()
    if not qrcode:
        raise HTTPException(status_code=502, detail="iLink did not return a share qrcode.")
    return WechatShareQrcodeResponse(
        qrcode=qrcode,
        qrcode_img_content=str(data.get("qrcode_img_content") or "").strip() or None,
    )
