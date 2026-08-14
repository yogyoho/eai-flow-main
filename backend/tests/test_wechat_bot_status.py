"""Tests for the EAI-CUSTOM WeChat ClawBot activation-status endpoint.

The endpoint (`GET /api/channels/wechat/bot-status`) is a read-only view over
the auth-state file that ``WechatChannel`` already persists
(``{state_dir}/wechat-auth.json``). It must surface enough state for a user to
activate the bot (status + QR image URL when pending) while **never** leaking
the ``bot_token`` / ``ilink_bot_id`` / raw ``qrcode`` token.
"""

from __future__ import annotations

import json
from pathlib import Path

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.routers import channel_connections as cc

# ---------------------------------------------------------------------------
# Pure helper: _sanitize_wechat_bot_status
# ---------------------------------------------------------------------------


def test_sanitize_pending_returns_qrcode_url():
    # A real pending state has no bot_token yet (the channel only enters QR
    # binding when tokenless), so bot_bound is False and the QR URL is surfaced.
    view = cc._sanitize_wechat_bot_status(
        {
            "status": "pending",
            "qrcode": "internal-token-do-not-leak",
            "qrcode_img_content": "https://liteapp.weixin.qq.com/q/abc",
            "updated_at": 1723478400,
        }
    )
    assert view == {
        "status": "pending",
        "bot_bound": False,
        "qrcode_url": "https://liteapp.weixin.qq.com/q/abc",
        "updated_at": 1723478400,
    }


def test_sanitize_stale_status_with_token_is_bound():
    # Regression (e2e-found): the QR-login flow writes status="expired"/"timeout"
    # *without* clearing a previously stored bot_token (wechat.py::_save_auth_state
    # keeps self._bot_token via the `elif self._bot_token` merge branch). A
    # lingering token is the durable proof of activation — the card must report
    # the bot as bound, not mislead the admin into regenerating.
    for stale in ("expired", "timeout", "canceled", "invalid", "failed"):
        view = cc._sanitize_wechat_bot_status({"status": stale, "bot_token": "tok", "ilink_bot_id": "id", "updated_at": 1})
        assert view["status"] == stale
        assert view["bot_bound"] is True
        assert view["qrcode_url"] is None


def test_sanitize_confirmed_bot_bound():
    view = cc._sanitize_wechat_bot_status({"status": "confirmed", "bot_token": "tok", "ilink_bot_id": "id", "updated_at": 1})
    assert view["status"] == "confirmed"
    assert view["bot_bound"] is True
    # QR is only surfaced while pending so a stale confirmed-era image is never shown.
    assert view["qrcode_url"] is None


def test_sanitize_confirmed_without_token_is_not_bound():
    # Defensive: a confirmed marker with no usable token is not actually bound.
    view = cc._sanitize_wechat_bot_status({"status": "confirmed", "updated_at": 1})
    assert view["bot_bound"] is False


def test_sanitize_expired_hides_qrcode():
    view = cc._sanitize_wechat_bot_status({"status": "expired", "qrcode_img_content": "https://x", "updated_at": 1})
    assert view["status"] == "expired"
    assert view["bot_bound"] is False
    assert view["qrcode_url"] is None


def test_sanitize_missing_data_returns_none_status():
    view = cc._sanitize_wechat_bot_status(None)
    assert view == {"status": "none", "bot_bound": False, "qrcode_url": None, "updated_at": None}


def test_sanitize_never_leaks_secrets():
    view = cc._sanitize_wechat_bot_status(
        {
            "status": "pending",
            "qrcode": "Q",
            "qrcode_img_content": "https://x",
            "bot_token": "T",
            "ilink_bot_id": "I",
            "updated_at": 1,
        }
    )
    flat = json.dumps(view)
    for secret in ("bot_token", "ilink_bot_id", '"qrcode"'):
        assert secret not in flat


# ---------------------------------------------------------------------------
# Provider-table invariant: wechat is QR-activated, needs no pasted creds (bug-1176)
#


def test_wechat_has_no_pasted_credential_fields():
    # WeChat/iLink is QR-based: bot_token is auto-fetched into wechat-auth.json by
    # channels.wechat (QR login), NOT admin-pasted. So wechat must expose NO
    # credential form — the 渠道 tab offers a direct binding-code flow. Regression
    # guard: if someone re-adds bot_token here, the 渠道 tab would wrongly demand a
    # paste and /wechat/connect would be blocked on a runtime bot_token it never has.
    assert cc._CREDENTIAL_FIELDS["wechat"] == ()
    assert cc._credential_fields("wechat") == []


def test_wechat_runtime_configured_without_bot_token():
    # The connect endpoint's `configured` gate (_runtime_channel_configured) must
    # pass from channels.wechat's enabled flag ALONE — no pasted bot_token in the
    # runtime store. This is what lets POST /wechat/connect generate a binding
    # code while the bot runs via QR. A separate _runtime_channel_running check
    # still rejects a non-running bot.
    assert cc._RUNTIME_REQUIREMENTS["wechat"] == ()
    assert cc._runtime_channel_configured("wechat", {"wechat": {"enabled": True}}) is True
    assert cc._runtime_channel_configured("wechat", {"wechat": {"enabled": False}}) is False
    assert cc._runtime_channel_configured("wechat", {}) is False


# ---------------------------------------------------------------------------
# Pure helper: _load_wechat_auth_state
# ---------------------------------------------------------------------------


def test_load_auth_state_reads_file(tmp_path: Path):
    auth = tmp_path / "wechat-auth.json"
    auth.write_text(json.dumps({"status": "pending", "qrcode_img_content": "https://x"}), encoding="utf-8")
    data = cc._load_wechat_auth_state(auth)
    assert data == {"status": "pending", "qrcode_img_content": "https://x"}


def test_load_auth_state_missing_returns_none(tmp_path: Path):
    assert cc._load_wechat_auth_state(tmp_path / "wechat-auth.json") is None


def test_load_auth_state_corrupt_returns_none(tmp_path: Path):
    auth = tmp_path / "wechat-auth.json"
    auth.write_text("{not json", encoding="utf-8")
    assert cc._load_wechat_auth_state(auth) is None


def test_load_auth_state_none_path_returns_none():
    assert cc._load_wechat_auth_state(None) is None


# ---------------------------------------------------------------------------
# Endpoint wiring: GET /api/channels/wechat/bot-status
# ---------------------------------------------------------------------------


def _app_with_wechat_state(state_dir: Path, *, qrcode_login_enabled: bool = True):
    """Build an authed test app whose channels_config points at ``state_dir``."""
    app = make_authed_test_app()
    # _get_channels_config returns app.state.channels_config verbatim when it is a dict.
    app.state.channels_config = {
        "wechat": {
            "state_dir": str(state_dir),
            "qrcode_login_enabled": qrcode_login_enabled,
        }
    }
    app.include_router(cc.router)
    return app


def test_endpoint_pending_shows_qrcode(tmp_path: Path):
    (tmp_path / "wechat-auth.json").write_text(
        json.dumps({"status": "pending", "qrcode_img_content": "https://liteapp.weixin.qq.com/q/z", "updated_at": 7}),
        encoding="utf-8",
    )
    with TestClient(_app_with_wechat_state(tmp_path)) as client:
        resp = client.get("/api/channels/wechat/bot-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["qrcode_login_enabled"] is True
    assert body["qrcode_url"] == "https://liteapp.weixin.qq.com/q/z"
    assert body["bot_bound"] is False
    assert body["updated_at"] == 7
    assert "bot_token" not in json.dumps(body)


def test_endpoint_confirmed_reports_bound(tmp_path: Path):
    (tmp_path / "wechat-auth.json").write_text(json.dumps({"status": "confirmed", "bot_token": "tok", "updated_at": 9}), encoding="utf-8")
    with TestClient(_app_with_wechat_state(tmp_path)) as client:
        resp = client.get("/api/channels/wechat/bot-status")
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["bot_bound"] is True
    assert body["qrcode_url"] is None


def test_endpoint_missing_auth_file_reports_none(tmp_path: Path):
    with TestClient(_app_with_wechat_state(tmp_path)) as client:
        resp = client.get("/api/channels/wechat/bot-status")
    assert resp.status_code == 200
    assert resp.json() == {
        "qrcode_login_enabled": True,
        "status": "none",
        "bot_bound": False,
        "qrcode_url": None,
        "updated_at": None,
    }


def test_endpoint_qrcode_login_disabled_flag(tmp_path: Path):
    with TestClient(_app_with_wechat_state(tmp_path, qrcode_login_enabled=False)) as client:
        resp = client.get("/api/channels/wechat/bot-status")
    assert resp.json()["qrcode_login_enabled"] is False


def test_endpoint_handles_missing_wechat_config(tmp_path: Path):
    # If wechat is absent from channels_config, the endpoint must still 200
    # with a safe "none" status rather than 500.
    app = make_authed_test_app()
    app.state.channels_config = {}
    app.include_router(cc.router)
    with TestClient(app) as client:
        resp = client.get("/api/channels/wechat/bot-status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"
