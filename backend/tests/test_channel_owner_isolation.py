"""Unit tests for per-user isolation via internal-auth owner_user_id (E-续 ③ C-2b).

Each IM channel user (e.g. each WeChat user messaging the bot) must get an
agent run scoped to their own memory/sandbox. The owner flows through the
internal-auth ``X-DeerFlow-Owner-User-Id`` header; the gateway attributes the
call to that owner. This covers make_safe_user_id, the internal-auth owner
header/user, ChannelManager._resolve_owner_user_id, and the per-owner SDK
client cache.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, MessageBus
from app.channels.store import ChannelStore
from app.gateway.internal_auth import (
    INTERNAL_AUTH_HEADER_NAME,
    INTERNAL_OWNER_HEADER_NAME,
    create_internal_auth_headers,
    get_internal_user,
)
from deerflow.config.paths import make_safe_user_id
from deerflow.runtime.user_context import DEFAULT_USER_ID

# -- make_safe_user_id --------------------------------------------------------


def test_make_safe_user_id_passthrough_already_safe() -> None:
    assert make_safe_user_id("alice-123") == "alice-123"
    assert make_safe_user_id("ABC_def-0") == "ABC_def-0"


def test_make_safe_user_id_sanitizes_unsafe_and_adds_digest() -> None:
    raw = "o9cq80zHIkaaav@im.wechat"
    safe = make_safe_user_id(raw)
    # Unsafe chars (@ .) replaced with -, and a digest suffix appended so the
    # result stays in the safe charset and distinct inputs never collide.
    assert safe.startswith("o9cq80zHIkaaav-im-wechat-")
    suffix = safe.removeprefix("o9cq80zHIkaaav-im-wechat-")
    assert len(suffix) == 16 and suffix.isalnum()
    # Idempotent on the sanitized form would NOT hold (raw != sanitized), but a
    # second call on the SAME raw input is stable.
    assert make_safe_user_id(raw) == safe


def test_make_safe_user_id_distinct_inputs_never_collide() -> None:
    # Two inputs that sanitize to the same string must differ by digest.
    a = make_safe_user_id("user@x")
    b = make_safe_user_id("user.x")  # both sanitize to "user-x"
    assert a.startswith("user-x-") and b.startswith("user-x-")
    assert a != b


def test_make_safe_user_id_rejects_empty() -> None:
    with pytest.raises(ValueError):
        make_safe_user_id("")


# -- internal_auth owner header ----------------------------------------------


def test_internal_auth_headers_include_owner_when_provided() -> None:
    headers = create_internal_auth_headers(owner_user_id="owner-42")
    assert headers[INTERNAL_AUTH_HEADER_NAME]
    assert headers[INTERNAL_OWNER_HEADER_NAME] == "owner-42"


def test_internal_auth_headers_omit_owner_by_default() -> None:
    headers = create_internal_auth_headers()
    assert INTERNAL_OWNER_HEADER_NAME not in headers
    assert headers[INTERNAL_AUTH_HEADER_NAME]


def test_get_internal_user_defaults_to_default_user() -> None:
    user = get_internal_user()
    assert user.id == DEFAULT_USER_ID
    assert user.system_role == "internal"


def test_get_internal_user_adopts_owner() -> None:
    user = get_internal_user(owner_user_id="owner-42")
    assert user.id == "owner-42"
    assert user.system_role == "internal"


# -- ChannelManager._resolve_owner_user_id -----------------------------------


def _msg(*, user_id: str | None = "u", owner_user_id: str | None = None) -> InboundMessage:
    return InboundMessage(channel_name="wechat", chat_id="c", user_id=user_id or "", text="hi", owner_user_id=owner_user_id)


def _make_manager() -> ChannelManager:
    return ChannelManager(bus=MessageBus(), store=ChannelStore())


def test_resolve_owner_prefers_binding() -> None:
    manager = _make_manager()
    # channel_connections binding wins over platform user_id.
    assert manager._resolve_owner_user_id(_msg(user_id="platform-u", owner_user_id="bound-owner")) == "bound-owner"


def test_resolve_owner_derives_from_platform_user() -> None:
    manager = _make_manager()
    # No binding → normalize the platform user (e.g. WeChat iLink id).
    owner = manager._resolve_owner_user_id(_msg(user_id="o9cq80z@im.wechat"))
    assert owner == make_safe_user_id("o9cq80z@im.wechat")
    assert owner != DEFAULT_USER_ID


def test_resolve_owner_none_when_no_user() -> None:
    manager = _make_manager()
    assert manager._resolve_owner_user_id(_msg(user_id=None)) is None


# -- per-owner SDK client cache ----------------------------------------------


def test_get_client_caches_per_owner_and_passes_owner_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    def fake_get_client(url: str, headers: dict[str, str] | None = None, **kwargs: Any):
        captured.append({"url": url, "headers": dict(headers or {})})
        return object()  # distinct sentinel per call

    monkeypatch.setattr("langgraph_sdk.get_client", fake_get_client)

    manager = _make_manager()
    client_a = manager._get_client("owner-a")
    client_b = manager._get_client("owner-b")
    client_a2 = manager._get_client("owner-a")  # cached

    # Two distinct owners → two distinct clients (cache miss each).
    assert client_a is not client_b
    # Same owner → cached (no new client).
    assert client_a2 is client_a
    # Only two get_client calls (owner-a once, owner-b once).
    assert len(captured) == 2
    owners = {c["headers"].get(INTERNAL_OWNER_HEADER_NAME) for c in captured}
    assert owners == {"owner-a", "owner-b"}
    # Every client carries the internal token + CSRF double-submit.
    for c in captured:
        assert c["headers"][INTERNAL_AUTH_HEADER_NAME]
        assert c["headers"]["X-CSRF-Token"] == c["headers"]["Cookie"].removeprefix("csrf_token=")


def test_get_client_default_owner_has_no_owner_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, str]] = []

    def fake_get_client(url: str, headers: dict[str, str] | None = None, **kwargs: Any):
        captured.append(dict(headers or {}))
        return object()

    monkeypatch.setattr("langgraph_sdk.get_client", fake_get_client)

    manager = _make_manager()
    manager._get_client(None)  # legacy default-user path

    assert len(captured) == 1
    assert INTERNAL_OWNER_HEADER_NAME not in captured[0]
