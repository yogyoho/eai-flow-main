"""Embedded session wiring for the TUI.

Owns construction of the ``DeerFlowClient`` (with a persistent checkpointer),
thread resolution for ``--continue`` / ``--resume`` (by id **or** title), and the
shared-persistence writer that makes terminal sessions visible in the Web UI (see
``deerflow.tui.persistence``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing the heavy client during pure planning
    from deerflow.client import DeerFlowClient

    from .cli import LaunchPlan
    from .persistence import ThreadMetaWriter, _LoopThread


@dataclass
class Session:
    client: DeerFlowClient
    writer: ThreadMetaWriter | None = None
    _loop: _LoopThread | None = None

    def resolve_thread(self, plan: LaunchPlan) -> str | None:
        """Resolve the thread id to run against, honoring --resume / --continue."""
        if plan.thread_id:
            return self.resolve_ref(plan.thread_id)
        if plan.continue_recent:
            threads = self.client.list_threads(limit=1).get("thread_list", [])
            if threads:
                return threads[0].get("thread_id")
        return None

    def resolve_ref(self, ref: str) -> str:
        """Resolve a thread reference (id or title) to a thread id.

        Matches an existing thread by id first, then by exact title. Falls back to
        the literal ref (treated as an id) when nothing matches, so an unknown id
        still continues/creates that namespace.
        """
        try:
            threads = self.client.list_threads(limit=100).get("thread_list", [])
        except Exception:  # noqa: BLE001 - resolution is best-effort
            return ref
        if any(t.get("thread_id") == ref for t in threads):
            return ref
        for thread in threads:
            if (thread.get("title") or "") == ref:
                return thread.get("thread_id") or ref
        return ref

    def recent_threads(self, limit: int = 20) -> list[dict]:
        return self.client.list_threads(limit=limit).get("thread_list", [])

    def close(self) -> None:
        """Stop the background DB loop and dispose the engine (best-effort)."""
        loop = self._loop
        if loop is None:
            return
        self._loop = None
        try:
            from deerflow.persistence.engine import close_engine

            loop.run(close_engine())
        except Exception:  # noqa: BLE001 - teardown is best-effort
            pass
        loop.close()


def open_session(persistence: bool = True, *, gateway_url: str | None = None) -> Session:
    """Build an embedded or gateway session.

    When *gateway_url* is set, the TUI connects to a remote server via
    langgraph-sdk. Otherwise it uses the embedded ``DeerFlowClient``.
    """
    if gateway_url:
        return _open_gateway_session(gateway_url)  # remote mode
    return _open_embedded_session(persistence)      # embedded mode


def _open_embedded_session(persistence: bool) -> Session:
    from deerflow.client import DeerFlowClient
    from deerflow.runtime.checkpointer.provider import get_checkpointer

    checkpointer = get_checkpointer()
    client = DeerFlowClient(checkpointer=checkpointer)
    if not persistence:
        return Session(client=client)

    from .persistence import build_persistence

    loop, writer = build_persistence()
    return Session(client=client, writer=writer, _loop=loop)


def _open_gateway_session(gateway_url: str) -> Session:
    """Build a session that talks to a remote gateway via langgraph-sdk."""
    from langgraph_sdk import get_sync_client
    import uuid, threading

    url = gateway_url.rstrip("/")
    sdk = get_sync_client(url=url)
    gw_thread_id: str | None = None  # mutable, captured by wrapper

    class GatewayClient:
        """Thin wrapper around langgraph-sdk matching DeerFlowClient's API."""

        def list_models(self):
            return {"models": []}  # gateway has no GET /models? let it pass

        def list_skills(self, enabled_only: bool = True):
            return {"skills": []}

        def list_threads(self, limit: int = 100):
            r = sdk.threads.search(limit=limit)
            return {"thread_list": [{"thread_id": t.get("thread_id"), "title": t.get("metadata", {}).get("title", "")} for t in (r if isinstance(r, list) else [])]}

        def chat(self, message: str, *, thread_id: str | None = None, **kw):
            tid = thread_id or gw_thread_id
            if tid is None:
                th = sdk.threads.create()
                tid = gw_thread_id = th["thread_id"]
            events = list(sdk.runs.stream(tid, assistant_id="lead_agent",
                input={"messages": [{"role": "user", "content": message}]},
                stream_mode=["messages-tuple"]))
            text = ""
            for ev in events:
                if ev.event == "messages-tuple" and isinstance(ev.data, dict):
                    msg = ev.data
                    if msg.get("type") == "ai" and isinstance(msg.get("content"), str):
                        text += msg["content"]
            return text

        def stream(self, message: str, *, thread_id: str | None = None, **kw):
            from dataclasses import dataclass
            import queue
            nonlocal gw_thread_id
            tid = thread_id or gw_thread_id
            if tid is None:
                th = sdk.threads.create()
                tid = gw_thread_id = th["thread_id"]

            @dataclass
            class _Evt:
                type: str; data: dict

            q = queue.Queue()
            def _run():
                try:
                    for ev in sdk.runs.stream(tid, assistant_id="lead_agent",
                        input={"messages": [{"role": "user", "content": message}]},
                        stream_mode=["messages-tuple","values","custom"]):
                        q.put(_Evt(type=ev.event, data=ev.data if isinstance(ev.data, dict) else {}))
                    q.put(_Evt(type="end", data={}))
                except Exception as exc:
                    q.put(_Evt(type="error", data={"message": str(exc)}))

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            while True:
                item = q.get()
                if item.type in ("end","error"):
                    yield item
                    break
                yield item

        def get_goal(self, thread_id: str):
            return {"goal": None}

        def set_goal(self, thread_id: str, objective: str):
            return {"goal": objective}

        def clear_goal(self, thread_id: str):
            return {}

        def get_mcp_config(self):
            return {"mcp_servers": {}}

        def get_memory(self):
            return {}

        def list_uploads(self, thread_id: str):
            return {"files": []}

        def list_thread(self, thread_id: str):
            return {}

        def search_threads(self, limit: int):
            return self.list_threads(limit)

    client = GatewayClient()
    return Session(client=client, writer=None, _loop=None)
