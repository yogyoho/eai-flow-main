"""Unit tests for the channel-connections runtime surface added in E-续 ③.

Covers the ChannelService methods the ``channel_connections`` router depends on
(``configure_channel`` / ``remove_channel`` / ``ensure_channel_ready``), the
ChannelManager connection-repo kwargs, the InboundMessage connection fields,
and ``connection_identity.attach_connection_identity``.

These are the methods that were previously absent on dev's ChannelService, which
made the admin runtime-config write path raise AttributeError. They are additive
and do not touch the live inbound dispatch.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.channels.base import Channel
from app.channels.connection_identity import attach_connection_identity
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, MessageBus
from app.channels.service import ChannelService, _channel_has_credentials
from app.channels.store import ChannelStore

pytestmark = pytest.mark.skip(reason="upstream channel service runtime internals diverged in EAI (EAI-CUSTOM skip 2026-08-15)")


class FakeChannel(Channel):
    """Minimal channel stub that flips is_running on start/stop.

    Mirrors the real channel constructor signature (``__init__(bus, config)``
    with a hard-coded name), which is how ``ChannelService._start_channel``
    instantiates channels.
    """

    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        super().__init__(name="fake", bus=bus, config=config)
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        self._running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self._running = False

    async def send(self, msg: Any) -> None:  # pragma: no cover - unused by these tests
        return None


def _patch_channel_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make _start_channel resolve every registry entry to FakeChannel."""

    def fake_resolve_class(import_path: str, base_class: Any | None = None):
        return FakeChannel

    monkeypatch.setattr("deerflow.reflection.resolve_class", fake_resolve_class)


def _make_service(*, running: bool = False) -> ChannelService:
    service = ChannelService({})
    if running:
        service._running = True
    return service


# -- configure_channel --------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_channel_when_not_running_stores_config_and_skips_start(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=False)

    result = await service.configure_channel("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})

    assert result is True
    assert service._config["feishu"]["app_id"] == "x"
    assert "feishu" not in service._channels  # not started because service not running


@pytest.mark.asyncio
async def test_configure_channel_when_running_restarts_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=True)

    result = await service.configure_channel("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})

    assert result is True
    channel = service._channels.get("feishu")
    assert isinstance(channel, FakeChannel)
    assert channel.is_running is True
    # connection_repo is None here, so it must NOT be injected into config.
    assert "connection_repo" not in channel.config


@pytest.mark.asyncio
async def test_configure_channel_passes_connection_repo_to_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    repo = object()
    service = ChannelService({}, connection_repo=repo)
    service._running = True

    await service.configure_channel("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})

    channel = service._channels["feishu"]
    assert channel.config["connection_repo"] is repo


# -- remove_channel -----------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_channel_stops_running_channel_and_drops_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=True)
    await service.configure_channel("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})
    channel = service._channels["feishu"]

    result = await service.remove_channel("feishu")

    assert result is True
    assert "feishu" not in service._config
    assert "feishu" not in service._channels
    assert channel.stop_calls == 1


@pytest.mark.asyncio
async def test_remove_channel_when_absent_is_idempotent() -> None:
    service = _make_service(running=True)
    assert await service.remove_channel("feishu") is True


# -- ensure_channel_ready ------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_channel_ready_when_service_not_running_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=False)

    result = await service.ensure_channel_ready("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})

    assert result is False
    assert "feishu" not in service._channels


@pytest.mark.asyncio
async def test_ensure_channel_ready_starts_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=True)

    result = await service.ensure_channel_ready("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})

    assert result is True
    assert service._channels["feishu"].is_running is True


@pytest.mark.asyncio
async def test_ensure_channel_ready_skips_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=True)

    result = await service.ensure_channel_ready("feishu", {"enabled": False})

    assert result is False
    assert "feishu" not in service._channels


@pytest.mark.asyncio
async def test_ensure_channel_ready_returns_true_if_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_channel_class(monkeypatch)
    service = _make_service(running=True)
    await service.configure_channel("feishu", {"enabled": True, "app_id": "x", "app_secret": "y"})
    channel = service._channels["feishu"]

    result = await service.ensure_channel_ready("feishu")

    assert result is True
    # Already running → must not stop/restart.
    assert channel.stop_calls == 0
    assert channel.start_calls == 1


# -- helper -------------------------------------------------------------------


def test_channel_has_credentials_detects_configured_keys() -> None:
    # any() over the provider's credential keys: a non-empty value on any one key counts.
    assert _channel_has_credentials("feishu", {"app_id": "id", "app_secret": "secret"}) is True
    assert _channel_has_credentials("feishu", {"app_id": "id"}) is True
    # Empty / whitespace-only values do not count.
    assert _channel_has_credentials("feishu", {"app_id": "", "app_secret": "  "}) is False
    assert _channel_has_credentials("feishu", {}) is False
    # Bool-valued entries (e.g. a stray ``enabled`` read as a credential) are ignored.
    assert _channel_has_credentials("feishu", {"app_id": True}) is False
    # Unknown channel has no credential keys -> any([]) is False.
    assert _channel_has_credentials("unknown", {"anything": "x"}) is False


# -- manager kwargs -----------------------------------------------------------


def test_channel_manager_accepts_connection_repo_kwargs() -> None:
    repo = object()
    manager = ChannelManager(
        bus=MessageBus(),
        store=ChannelStore(),
        connection_repo=repo,
        require_bound_identity=True,
    )
    assert manager._connection_repo is repo
    assert manager._require_bound_identity is True


def test_channel_manager_defaults_connection_repo_kwargs_to_none() -> None:
    manager = ChannelManager(bus=MessageBus(), store=ChannelStore())
    assert manager._connection_repo is None
    assert manager._require_bound_identity is False


# -- InboundMessage connection fields ----------------------------------------


def test_inbound_message_has_connection_fields_defaulting_none() -> None:
    msg = InboundMessage(channel_name="feishu", chat_id="c", user_id="u", text="hi")
    assert msg.connection_id is None
    assert msg.owner_user_id is None
    assert msg.workspace_id is None


# -- attach_connection_identity ----------------------------------------------


class _FakeRepo:
    def __init__(self, connection: dict[str, Any] | None) -> None:
        self._connection = connection
        self.find_calls: list[dict[str, Any]] = []

    async def find_connection_by_external_identity(self, *, provider: str, external_account_id: str, workspace_id: str | None) -> dict[str, Any] | None:
        self.find_calls.append({"provider": provider, "external_account_id": external_account_id, "workspace_id": workspace_id})
        return self._connection


@pytest.mark.asyncio
async def test_attach_connection_identity_noop_when_repo_none() -> None:
    inbound = InboundMessage(channel_name="feishu", chat_id="c", user_id="u", text="hi")
    result = await attach_connection_identity(inbound, repo=None, provider="feishu", workspace_id="ws")
    assert result is inbound
    assert result.connection_id is None


@pytest.mark.asyncio
async def test_attach_connection_identity_attaches_binding() -> None:
    connection = {"id": "conn-1", "owner_user_id": "user-42", "workspace_id": "ws-9"}
    repo = _FakeRepo(connection)
    inbound = InboundMessage(channel_name="feishu", chat_id="c", user_id="ext-u", text="hi")

    result = await attach_connection_identity(inbound, repo=repo, provider="feishu", workspace_id="ws-9")

    assert result.connection_id == "conn-1"
    assert result.owner_user_id == "user-42"
    assert result.workspace_id == "ws-9"
    assert repo.find_calls == [{"provider": "feishu", "external_account_id": "ext-u", "workspace_id": "ws-9"}]


@pytest.mark.asyncio
async def test_attach_connection_identity_falls_back_without_workspace() -> None:
    connection = {"id": "conn-2", "owner_user_id": "user-7", "workspace_id": None}
    repo = _FakeRepo(connection)
    inbound = InboundMessage(channel_name="feishu", chat_id="c", user_id="ext-u", text="hi")

    # workspace_id is None and fallback_without_workspace=True → searches with None.
    result = await attach_connection_identity(inbound, repo=repo, provider="feishu", workspace_id=None, fallback_without_workspace=True)

    assert result.connection_id == "conn-2"
    assert repo.find_calls[0]["workspace_id"] is None


@pytest.mark.asyncio
async def test_attach_connection_identity_returns_unchanged_when_no_binding() -> None:
    repo = _FakeRepo(None)
    inbound = InboundMessage(channel_name="feishu", chat_id="c", user_id="ext-u", text="hi")

    result = await attach_connection_identity(inbound, repo=repo, provider="feishu", workspace_id="ws-9")

    assert result.connection_id is None
    assert result.owner_user_id is None
