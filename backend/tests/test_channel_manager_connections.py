"""Unit tests for the connection-aware thread routing added in E-续 ③ C-2a.

Covers ChannelManager._lookup_thread_id / _store_thread_id: the connection
path (a bound user's messages route via the connection repository) and the
fallback path (system-bot traffic uses the shared channel store, unchanged).

These are the per-connection thread-routing hooks grafted into dev's dispatch.
They are dead code unless channel_connections is enabled (connection_repo is
None in dev's default config), so the fallback path is what system bots hit.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, MessageBus
from app.channels.store import ChannelStore


class _FakeRepo:
    """Async stand-in for ChannelConnectionRepository."""

    def __init__(self, *, thread_id: str | None = None) -> None:
        self._thread_id = thread_id
        self.set_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    async def get_thread_id(self, connection_id, external_conversation_id, external_topic_id=None):
        self.get_calls.append(
            {
                "connection_id": connection_id,
                "external_conversation_id": external_conversation_id,
                "external_topic_id": external_topic_id,
            }
        )
        return self._thread_id

    async def set_thread_id(self, *, connection_id, owner_user_id, provider, external_conversation_id, thread_id, external_topic_id=None):
        self.set_calls.append(
            {
                "connection_id": connection_id,
                "owner_user_id": owner_user_id,
                "provider": provider,
                "external_conversation_id": external_conversation_id,
                "external_topic_id": external_topic_id,
                "thread_id": thread_id,
            }
        )


def _msg(*, connection_id: str | None = None, owner_user_id: str | None = None, topic_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel_name="feishu",
        chat_id="chat-1",
        user_id="ext-user",
        text="hi",
        topic_id=topic_id,
        connection_id=connection_id,
        owner_user_id=owner_user_id,
    )


def _make_manager(*, connection_repo: Any | None = None) -> ChannelManager:
    return ChannelManager(bus=MessageBus(), store=ChannelStore(), connection_repo=connection_repo)


# -- _lookup_thread_id -------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_thread_id_falls_back_to_store_without_connection() -> None:
    """System-bot traffic (no binding) must use the shared store, unchanged."""
    manager = _make_manager(connection_repo=None)
    manager.store.set_thread_id("feishu", "chat-1", "thread-store-1", topic_id=None, user_id="ext-user")

    result = await manager._lookup_thread_id(_msg())

    assert result == "thread-store-1"


@pytest.mark.asyncio
async def test_lookup_thread_id_uses_repo_when_connection_bound() -> None:
    repo = _FakeRepo(thread_id="thread-conn-1")
    manager = _make_manager(connection_repo=repo)

    result = await manager._lookup_thread_id(_msg(connection_id="conn-1", topic_id="topic-9"))

    assert result == "thread-conn-1"
    assert repo.get_calls == [
        {
            "connection_id": "conn-1",
            "external_conversation_id": "chat-1",
            "external_topic_id": "topic-9",
        }
    ]


@pytest.mark.asyncio
async def test_lookup_thread_id_falls_back_when_repo_none_but_connection_set() -> None:
    """A connection_id with no repo (shouldn't happen in dev) still degrades to the store."""
    manager = _make_manager(connection_repo=None)
    manager.store.set_thread_id("feishu", "chat-1", "thread-store-2", topic_id=None, user_id="ext-user")

    result = await manager._lookup_thread_id(_msg(connection_id="conn-1"))

    assert result == "thread-store-2"


# -- _store_thread_id --------------------------------------------------------


@pytest.mark.asyncio
async def test_store_thread_id_falls_back_to_store_without_connection() -> None:
    manager = _make_manager(connection_repo=None)

    await manager._store_thread_id(_msg(), "new-thread-1")

    assert manager.store.get_thread_id("feishu", "chat-1", topic_id=None) == "new-thread-1"


@pytest.mark.asyncio
async def test_store_thread_id_uses_repo_when_connection_bound() -> None:
    repo = _FakeRepo()
    manager = _make_manager(connection_repo=repo)

    await manager._store_thread_id(
        _msg(connection_id="conn-1", owner_user_id="user-42", topic_id="topic-9"),
        "new-thread-2",
    )

    assert repo.set_calls == [
        {
            "connection_id": "conn-1",
            "owner_user_id": "user-42",
            "provider": "feishu",
            "external_conversation_id": "chat-1",
            "external_topic_id": "topic-9",
            "thread_id": "new-thread-2",
        }
    ]
    # The shared store must NOT have been written for a bound connection.
    assert manager.store.get_thread_id("feishu", "chat-1", topic_id="topic-9") is None


@pytest.mark.asyncio
async def test_store_thread_id_falls_back_when_owner_missing() -> None:
    """A connection_id without an owner_user_id degrades to the store (defensive)."""
    repo = _FakeRepo()
    manager = _make_manager(connection_repo=repo)

    await manager._store_thread_id(_msg(connection_id="conn-1", owner_user_id=None), "new-thread-3")

    assert repo.set_calls == []
    assert manager.store.get_thread_id("feishu", "chat-1", topic_id=None) == "new-thread-3"
