"""EAI 回归测试：regenerate / edit-rerun prepare 路径（原始 checkpointer 适配版）。

上游 test_thread_regenerate_prepare.py 绑定 materialized state-accessor
（build_thread_checkpoint_state_accessor + FakeAccessor），EAI 的 regenerate/edit-rerun
走原始 checkpointer 路径，故这里改为直接 patch get_checkpointer/get_run_event_store/
get_run_manager/get_current_user，绕开 EAI 定制 auth。checkpoint_lineage 的 lineage-walk
主路径由 test_checkpoint_lineage.py 覆盖；此处 FakeCheckpointer 的 checkpoint 不带
parent_config，故 lineage 行走会抛 CheckpointParentMissingError 并回落到 chronological 扫描。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from deerflow.runtime import RunStatus
from deerflow.utils.messages import ORIGINAL_USER_CONTENT_KEY


def _checkpoint(
    checkpoint_id: str,
    messages: list[object],
    *,
    metadata: dict | None = None,
    goal: dict | None = None,
    next_tasks: tuple[str, ...] = (),
):
    channel_values = {"messages": messages}
    if goal is not None:
        channel_values["goal"] = goal
    return SimpleNamespace(
        config={
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
                "checkpoint_map": None,
            }
        },
        checkpoint={"channel_values": channel_values},
        metadata=metadata or {},
        next=next_tasks,
    )


class FakeCheckpointer:
    def __init__(self, history, *, latest=None):
        self.history = history
        self.latest = latest

    async def aget_tuple(self, config):
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if checkpoint_id:
            return next((item for item in self.history if item.config["configurable"]["checkpoint_id"] == checkpoint_id), None)
        return self.latest or (self.history[0] if self.history else None)

    async def alist(self, config, limit=200):
        for item in self.history[:limit]:
            yield item

    async def aget(self, config):
        # 原始 checkpointer 接口补齐；本测试的 checkpoint 无 parent_config，lineage 行走
        # 在首次迭代即抛 CheckpointParentMissingError，aget 不会被调用。
        return await self.aget_tuple(config)


class FakeEventStore:
    def __init__(self, rows):
        self.rows = rows

    async def list_messages(self, thread_id, *, limit=50, before_seq=None, after_seq=None):
        return self.rows[-limit:]


class FakeRunManager:
    def __init__(self, records):
        self.records = records

    async def list_by_thread(self, thread_id, *, user_id=None, limit=100):
        return self.records[:limit]

    async def get(self, run_id, *, user_id=None):
        return next((record for record in self.records if record.run_id == run_id), None)


def _patch_runs_deps(monkeypatch, *, checkpointer, event_store, run_manager=None, user_id="user-1"):
    """直接 patch thread_runs 的 4 个 deps，绕开 EAI 定制 auth（request 入参不再被使用）。"""
    from app.gateway.routers import thread_runs

    monkeypatch.setattr(thread_runs, "get_checkpointer", lambda request: checkpointer)
    monkeypatch.setattr(thread_runs, "get_run_event_store", lambda request: event_store)
    monkeypatch.setattr(thread_runs, "get_run_manager", lambda request: run_manager or FakeRunManager([]))

    async def _current_user(request):
        return user_id

    monkeypatch.setattr(thread_runs, "get_current_user", _current_user)
    return None  # request 不再被使用


def _ai_response_row(run_id: str, ai_id: str, text: str) -> dict:
    return {
        "run_id": run_id,
        "event_type": "llm.ai.response",
        "category": "message",
        "content": {"id": ai_id, "type": "ai", "content": text},
        "metadata": {"caller": "lead_agent"},
    }


def _success_run(run_id: str, *, last_ai_message: str) -> SimpleNamespace:
    return SimpleNamespace(run_id=run_id, status=RunStatus.success, metadata={}, last_ai_message=last_ai_message)


def test_prepare_regenerate_payload_returns_clean_input_and_base_checkpoint(monkeypatch):
    from app.gateway.routers import thread_runs

    human = HumanMessage(
        id="human-1",
        content="<uploaded_files>injected</uploaded_files>\n\n/data-analysis analyze data.csv",
        additional_kwargs={
            ORIGINAL_USER_CONTENT_KEY: "/data-analysis analyze data.csv",
            "files": [{"filename": "data.csv", "path": "/mnt/user-data/uploads/data.csv"}],
        },
    )
    ai = AIMessage(id="ai-1", content="answer v1")
    base = _checkpoint("ckpt-base", [])
    after_human = _checkpoint("ckpt-human", [human])
    latest = _checkpoint("ckpt-ai", [human, ai])
    checkpointer = FakeCheckpointer([latest, after_human, base])
    event_store = FakeEventStore([_ai_response_row("run-old", "ai-1", "answer v1")])

    _patch_runs_deps(monkeypatch, checkpointer=checkpointer, event_store=event_store)
    response = asyncio.run(thread_runs._prepare_regenerate_payload("thread-1", "ai-1", request=None))

    assert response.checkpoint == {
        "checkpoint_ns": "",
        "checkpoint_id": "ckpt-base",
        "checkpoint_map": None,
    }
    assert response.target_run_id == "run-old"
    assert response.metadata == {
        "regenerate_from_message_id": "ai-1",
        "regenerate_from_run_id": "run-old",
        "regenerate_checkpoint_id": "ckpt-base",
    }
    assert "title" not in response.input
    regenerated_human = response.input["messages"][0]
    assert regenerated_human["id"] == "human-1"
    assert regenerated_human["content"] == [{"type": "text", "text": "/data-analysis analyze data.csv"}]
    assert regenerated_human["additional_kwargs"] == {"files": [{"filename": "data.csv", "path": "/mnt/user-data/uploads/data.csv"}]}


def test_prepare_regenerate_payload_preserves_latest_thread_title(monkeypatch):
    from app.gateway.routers import thread_runs

    human = HumanMessage(id="human-1", content="question")
    ai = AIMessage(id="ai-1", content="answer v1")
    base = _checkpoint("ckpt-base", [])
    latest = _checkpoint("ckpt-ai", [human, ai])
    latest.checkpoint["channel_values"]["title"] = "User renamed title"
    checkpointer = FakeCheckpointer([latest, base])
    event_store = FakeEventStore([_ai_response_row("run-old", "ai-1", "answer v1")])

    _patch_runs_deps(monkeypatch, checkpointer=checkpointer, event_store=event_store)
    response = asyncio.run(thread_runs._prepare_regenerate_payload("thread-1", "ai-1", request=None))

    assert response.checkpoint["checkpoint_id"] == "ckpt-base"
    assert response.input["title"] == "User renamed title"


def test_prepare_edit_regenerate_payload_returns_new_human_and_edit_metadata(monkeypatch):
    from app.gateway.routers import thread_runs

    human = HumanMessage(
        id="human-1",
        content="<uploaded_files>injected</uploaded_files>\n\noriginal question",
        name="researcher",
        additional_kwargs={
            ORIGINAL_USER_CONTENT_KEY: "original question",
            "files": [{"filename": "data.csv", "path": "/mnt/user-data/uploads/data.csv"}],
            "referenced_message_contexts": [{"message_id": "ai-prev", "quote": "quoted"}],
            "hide_from_ui": False,
            "run_id": "old-run",
            "middleware_private": "do-not-copy",
        },
    )
    ai = AIMessage(id="ai-1", content="answer v1")
    base = _checkpoint("ckpt-base", [])
    after_human = _checkpoint("ckpt-human", [human])
    latest = _checkpoint("ckpt-ai", [human, ai])
    checkpointer = FakeCheckpointer([latest, after_human, base])
    event_store = FakeEventStore([_ai_response_row("run-old", "ai-1", "answer v1")])
    run_manager = FakeRunManager([_success_run("run-old", last_ai_message="answer v1")])

    _patch_runs_deps(monkeypatch, checkpointer=checkpointer, event_store=event_store, run_manager=run_manager)
    response = asyncio.run(
        thread_runs._prepare_edit_regenerate_payload(
            "thread-1",
            "human-1",
            "  updated question\nwith details  ",
            request=None,
        )
    )

    assert response.checkpoint == {
        "checkpoint_ns": "",
        "checkpoint_id": "ckpt-base",
        "checkpoint_map": None,
    }
    assert response.target_run_id == "run-old"
    assert response.replacement_human_message_id != "human-1"
    assert response.source_message_ids == ["human-1", "ai-1"]
    assert response.metadata == {
        "replay_kind": "edit",
        "regenerate_from_message_id": "ai-1",
        "regenerate_from_run_id": "run-old",
        "regenerate_checkpoint_id": "ckpt-base",
        "edit_from_message_id": "human-1",
        "edit_message_id": response.replacement_human_message_id,
        "edit_version_group_id": "human-1",
    }
    replacement = response.input["messages"][0]
    assert replacement == {
        "type": "human",
        "id": response.replacement_human_message_id,
        "name": "researcher",
        "content": [{"type": "text", "text": "updated question\nwith details"}],
        "additional_kwargs": {
            "files": [{"filename": "data.csv", "path": "/mnt/user-data/uploads/data.csv"}],
            "referenced_message_contexts": [{"message_id": "ai-prev", "quote": "quoted"}],
        },
    }
