"""Tests for the WeChat system-bot binding flow (E-续 ③): /connect code consumer
+ require_bound_identity access control.

Covers ChannelManager._handle_command "connect" branch (consume code → upsert
connection) and ChannelManager._handle_message require_bound_identity enforcement
(unbound chat rejected; /connect + bound users pass through).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus
from app.channels.store import ChannelStore


class _FakeRepo:
    """Async stand-in for ChannelConnectionRepository (binding subset)."""

    def __init__(self, *, consume_result: dict[str, Any] | None = None, bound_owner: str | None = None) -> None:
        self._consume_result = consume_result
        self._bound_owner = bound_owner
        self.consume_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []

    async def consume_oauth_state(self, *, provider: str, state: str, now: Any | None = None):
        self.consume_calls.append({"provider": provider, "state": state})
        return self._consume_result

    async def upsert_connection(self, **kwargs: Any) -> dict[str, Any]:
        self.upsert_calls.append(kwargs)
        return {"id": "conn-1", **kwargs}

    async def find_connection_by_external_identity(self, *, provider: str, external_account_id: str, workspace_id: str | None = None):
        if self._bound_owner and external_account_id == "wx-user":
            return {"id": "conn-bound", "owner_user_id": self._bound_owner, "workspace_id": None}
        return None


def _make_manager(*, connection_repo: Any | None = None, require_bound_identity: bool = False):
    bus = MessageBus()
    manager = ChannelManager(bus=bus, store=ChannelStore(), connection_repo=connection_repo, require_bound_identity=require_bound_identity)
    manager._semaphore = asyncio.Semaphore(5)  # normally created in start()
    outboxes: list[Any] = []

    async def _capture(msg):
        outboxes.append(msg)

    bus.subscribe_outbound(_capture)
    return manager, outboxes


def _msg(text: str, *, msg_type: InboundMessageType = InboundMessageType.CHAT, owner_user_id: str | None = None) -> InboundMessage:
    return InboundMessage(channel_name="wechat", chat_id="wx-user", user_id="wx-user", text=text, msg_type=msg_type, owner_user_id=owner_user_id)


# -- /connect consumer -------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_valid_code_links_account() -> None:
    repo = _FakeRepo(consume_result={"owner_user_id": "deerflow-user-42"})
    manager, outboxes = _make_manager(connection_repo=repo)

    await manager._handle_command(_msg("/connect ABC123", msg_type=InboundMessageType.COMMAND))

    assert repo.consume_calls == [{"provider": "wechat", "state": "ABC123"}]
    assert len(repo.upsert_calls) == 1
    upsert = repo.upsert_calls[0]
    assert upsert["provider"] == "wechat"
    assert upsert["external_account_id"] == "wx-user"
    assert upsert["owner_user_id"] == "deerflow-user-42"
    assert upsert["status"] == "connected"
    assert outboxes and "linked" in outboxes[0].text.lower()


@pytest.mark.asyncio
async def test_connect_invalid_code_does_not_link() -> None:
    repo = _FakeRepo(consume_result=None)  # expired / unknown
    manager, outboxes = _make_manager(connection_repo=repo)

    await manager._handle_command(_msg("/connect NOPE", msg_type=InboundMessageType.COMMAND))

    assert repo.consume_calls == [{"provider": "wechat", "state": "NOPE"}]
    assert repo.upsert_calls == []
    assert outboxes and "invalid" in outboxes[0].text.lower()


@pytest.mark.asyncio
async def test_connect_without_code_is_guided() -> None:
    repo = _FakeRepo()
    manager, outboxes = _make_manager(connection_repo=repo)

    await manager._handle_command(_msg("/connect", msg_type=InboundMessageType.COMMAND))

    assert repo.consume_calls == []
    assert repo.upsert_calls == []
    assert outboxes and "binding code" in outboxes[0].text.lower()


@pytest.mark.asyncio
async def test_connect_without_repo_is_unavailable() -> None:
    manager, outboxes = _make_manager(connection_repo=None)

    await manager._handle_command(_msg("/connect ABC", msg_type=InboundMessageType.COMMAND))

    assert outboxes and "not available" in outboxes[0].text.lower()


# -- require_bound_identity enforcement -------------------------------------


@pytest.mark.asyncio
async def test_require_bound_identity_rejects_unbound_chat() -> None:
    repo = _FakeRepo()  # find returns None → unbound
    manager, outboxes = _make_manager(connection_repo=repo, require_bound_identity=True)
    chat_calls: list[Any] = []

    async def _fake_chat(msg, extra_context=None):
        chat_calls.append(msg)

    manager._handle_chat = _fake_chat

    await manager._handle_message(_msg("hello"))

    assert chat_calls == []  # agent run never happened
    assert outboxes and "link" in outboxes[0].text.lower()


@pytest.mark.asyncio
async def test_require_bound_identity_allows_connect_command() -> None:
    # /connect must pass the gate even for unbound users (it's how they bind).
    repo = _FakeRepo(consume_result={"owner_user_id": "u-9"})
    manager, outboxes = _make_manager(connection_repo=repo, require_bound_identity=True)

    await manager._handle_message(_msg("/connect ABC", msg_type=InboundMessageType.COMMAND))

    # No "link first" rejection; the connect branch ran and linked.
    assert repo.upsert_calls and repo.upsert_calls[0]["owner_user_id"] == "u-9"
    assert not any("link" in o.text.lower() and "first" in o.text.lower() for o in outboxes)


@pytest.mark.asyncio
async def test_require_bound_identity_allows_bound_user() -> None:
    repo = _FakeRepo(bound_owner="deerflow-user-7")  # attach finds a binding
    manager, outboxes = _make_manager(connection_repo=repo, require_bound_identity=True)
    chat_calls: list[Any] = []

    async def _fake_chat(msg, extra_context=None):
        chat_calls.append(msg)

    manager._handle_chat = _fake_chat

    await manager._handle_message(_msg("hello"))

    assert len(chat_calls) == 1  # passed through to the agent
    assert chat_calls[0].owner_user_id == "deerflow-user-7"  # owner attached
    assert not any("link" in o.text.lower() and "first" in o.text.lower() for o in outboxes)


@pytest.mark.asyncio
async def test_no_require_bound_identity_lets_unbound_through() -> None:
    # With the flag off, unbound users still reach the agent (C-2b auto-isolate).
    manager, outboxes = _make_manager(connection_repo=None, require_bound_identity=False)
    chat_calls: list[Any] = []

    async def _fake_chat(msg, extra_context=None):
        chat_calls.append(msg)

    manager._handle_chat = _fake_chat

    await manager._handle_message(_msg("hello"))

    assert len(chat_calls) == 1
