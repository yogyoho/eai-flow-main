"""Command dispatcher and reconciliation retry behaviour."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import settings
from app.database import session_scope
from app.engine import commands
from app.models import FlowCommand, FlowInstanceRuntime
from app.temporal import dispatcher, reconciler
from app.utils import utcnow

from .conftest import TEST_DB_PATH, headers

PREFIX = "/api/workflow"


def _one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with sqlite3.connect(TEST_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(sql, params).fetchone()


def _start_and_task(client: TestClient) -> tuple[dict, dict]:
    response = client.post(
        f"{PREFIX}/instances",
        headers=headers("u1004", "Zhao Liu", "employee", "d01"),
        json={"flow_code": "leave", "business_id": f"disp-{uuid4().hex[:8]}", "variables": {"days": 1}},
    )
    assert response.status_code == 201, response.text
    instance = response.json()
    task = client.get(
        f"{PREFIX}/tasks?instanceId={instance['id']}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    ).json()["items"][0]
    return instance, task


def _create_pending(instance_id: int, task_id: int, key: str) -> int:
    async def run() -> int:
        async with session_scope() as session:
            command = await commands.create_command(
                session,
                command_type=commands.COMMAND_APPROVE,
                instance_id=instance_id,
                task_id=task_id,
                actor="u1001",
                payload={
                    "task_id": task_id,
                    "handler": "u1001",
                    "message": "同意",
                    "skip_type": "PASS",
                    "variables": {},
                },
                claims=["manager"],
                idempotency_key=key,
            )
            return command.id

    return asyncio.run(run())


class FakeHandle:
    def __init__(self, *, fail_signal: bool = False) -> None:
        self.fail_signal = fail_signal
        self.signals: list[tuple[str, dict]] = []
        self.result_run_id = "run-1"

    async def signal(self, name: str, payload: dict) -> None:
        if self.fail_signal:
            raise RuntimeError("signal unavailable")
        self.signals.append((name, payload))


class FakeClient:
    def __init__(self, *, fail_signal: bool = False) -> None:
        self.fail_signal = fail_signal
        self.handles: dict[str, FakeHandle] = {}
        self.started: list[tuple[str, int]] = []

    async def start_workflow(self, workflow, instance_id: int, **kwargs):
        self.started.append((kwargs["id"], instance_id))
        handle = FakeHandle(fail_signal=self.fail_signal)
        self.handles[kwargs["id"]] = handle
        return handle

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        return self.handles.setdefault(workflow_id, FakeHandle(fail_signal=self.fail_signal))


def test_dispatcher_signals_durable_command(client: TestClient, monkeypatch) -> None:
    instance, task = _start_and_task(client)
    key = f"disp-{uuid4().hex}"
    command_id = _create_pending(instance["id"], task["id"], key)
    monkeypatch.setattr(settings, "temporal_enabled", True)
    fake = FakeClient()

    result = asyncio.run(dispatcher.dispatch_command(command_id, client=fake))
    assert result is not None
    assert result.status == commands.COMMAND_DISPATCHED
    assert fake.started
    workflow_id, instance_id = fake.started[0]
    assert instance_id == instance["id"]
    assert fake.handles[workflow_id].signals == [("command", {"id": command_id})]

    runtime = _one("select * from flow_instance_runtime where instance_id = ?", (instance["id"],))
    assert runtime is not None and runtime["status"] == "RUNNING"
    row = _one("select * from flow_command where id = ?", (command_id,))
    assert row is not None and row["status"] == "DISPATCHED" and row["attempts"] == 1


def test_dispatcher_retries_then_fails_signal(client: TestClient, monkeypatch) -> None:
    instance, task = _start_and_task(client)
    command_id = _create_pending(instance["id"], task["id"], f"disp-{uuid4().hex}")
    monkeypatch.setattr(settings, "temporal_enabled", True)
    monkeypatch.setattr(settings, "command_max_attempts", 1)
    fake = FakeClient(fail_signal=True)

    result = asyncio.run(dispatcher.dispatch_command(command_id, client=fake))
    assert result is not None
    assert result.status == commands.COMMAND_FAILED
    assert result.error_code == 503
    row = _one("select * from flow_command where id = ?", (command_id,))
    assert row is not None and row["status"] == "FAILED"


def test_reconciler_requeues_stale_dispatched_command(client: TestClient, monkeypatch) -> None:
    instance, task = _start_and_task(client)
    command_id = _create_pending(instance["id"], task["id"], f"stale-{uuid4().hex}")

    async def mark_stale() -> None:
        async with session_scope() as session:
            await session.execute(
                update(FlowCommand)
                .where(FlowCommand.id == command_id)
                .values(
                    status=commands.COMMAND_DISPATCHED,
                    update_time=utcnow() - timedelta(seconds=max(300, settings.command_stale_seconds + 10)),
                    attempts=1,
                )
            )

    asyncio.run(mark_stale())
    monkeypatch.setattr(settings, "temporal_enabled", True)

    async def no_runtimes(*args, **kwargs) -> int:
        return 0

    monkeypatch.setattr(reconciler, "_reconcile_runtimes", no_runtimes)
    result = asyncio.run(reconciler.reconcile_once(client=FakeClient()))
    assert result["commands"] >= 1
    row = _one("select * from flow_command where id = ?", (command_id,))
    assert row is not None and row["status"] == "PENDING"
    assert row["available_at"] is not None


def test_reconciler_cancels_commands_for_terminal_instance(client: TestClient, monkeypatch) -> None:
    instance, task = _start_and_task(client)
    command_id = _create_pending(instance["id"], task["id"], f"term-{uuid4().hex}")

    async def terminate_instance() -> None:
        async with session_scope() as session:
            runtime = await session.get(FlowInstanceRuntime, instance["id"])
            if runtime is not None:
                runtime.status = "COMPLETED"
            await session.execute(
                update(FlowCommand).where(FlowCommand.id == command_id).values(status=commands.COMMAND_PENDING)
            )
            from app.models import FlowInstance

            row = await session.get(FlowInstance, instance["id"])
            assert row is not None
            row.flow_status = "8"

    asyncio.run(terminate_instance())
    monkeypatch.setattr(settings, "temporal_enabled", True)

    async def no_runtimes(*args, **kwargs) -> int:
        return 0

    monkeypatch.setattr(reconciler, "_reconcile_runtimes", no_runtimes)
    asyncio.run(reconciler.reconcile_once(client=FakeClient()))
    row = _one("select * from flow_command where id = ?", (command_id,))
    assert row is not None and row["status"] == "CANCELLED"
