"""Durable command inbox, idempotency and outbox projection."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from app.temporal.dispatcher import dispatch_outbox_once

from .conftest import TEST_DB_PATH, headers

PREFIX = "/api/workflow"


def _rows(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(TEST_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return list(connection.execute(sql, params).fetchall())


def _one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def _start(client: TestClient, *, key: str, user: dict | None = None, **variables) -> dict:
    response = client.post(
        f"{PREFIX}/instances",
        headers={**(user or headers("u1004", "Zhao Liu", "employee", "d01")), "Idempotency-Key": key},
        json={
            "flow_code": "leave",
            "business_id": f"cmd-{uuid4().hex[:8]}",
            "variables": variables,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_start_writes_command_runtime_and_outbox(client: TestClient) -> None:
    key = f"start-{uuid4().hex}"
    instance = _start(client, key=key, days=1)

    command = _one("select * from flow_command where idempotency_key = ?", (key,))
    assert command is not None
    assert command["command_type"] == "START"
    assert command["status"] == "APPLIED"
    assert json.loads(command["result"])["instance_id"] == instance["id"]

    runtime = _one("select * from flow_instance_runtime where instance_id = ?", (instance["id"],))
    assert runtime is not None
    assert runtime["engine"] == "local"
    assert runtime["status"] == "DISABLED"

    event = _one("select * from flow_outbox where instance_id = ? order by id desc", (instance["id"],))
    assert event is not None
    assert event["event_type"] == "workflow.instance.started"
    payload = json.loads(event["payload"])
    assert payload["instance"]["id"] == instance["id"]
    assert payload["tasks"]

    # Deliver with an injected sender so the test stays offline. The event is
    # committed as SENT only after the sender succeeds.
    delivered: list[int] = []

    async def sender(event_row, payload, headers, body) -> None:
        delivered.append(event_row.id)
        if event_row.id == event["id"]:
            assert headers["X-Workflow-Event"] == "workflow.instance.started"
            assert json.loads(body)["instance"]["id"] == instance["id"]

    asyncio.run(dispatch_outbox_once(limit=200, sender=sender))
    assert event["id"] in delivered
    sent = _one("select * from flow_outbox where id = ?", (event["id"],))
    assert sent is not None and sent["status"] == "SENT"


def test_start_idempotency_and_conflict(client: TestClient) -> None:
    key = f"start-{uuid4().hex}"
    first = _start(client, key=key, days=2)
    second = _start(client, key=key, days=2)
    assert first["id"] == second["id"]
    assert len(_rows("select * from flow_command where idempotency_key = ?", (key,))) == 1

    response = client.post(
        f"{PREFIX}/instances",
        headers={**headers("u1004", "Zhao Liu", "employee", "d01"), "Idempotency-Key": key},
        json={
            "flow_code": "expense",
            "business_id": "different",
            "variables": {"amount": 10},
        },
    )
    assert response.status_code == 409


def test_approve_command_is_idempotent(client: TestClient) -> None:
    instance = _start(client, key=f"start-{uuid4().hex}", days=1)
    task = client.get(
        f"{PREFIX}/tasks?instanceId={instance['id']}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    ).json()["items"][0]
    key = f"approve-{uuid4().hex}"
    request_headers = {
        **headers("u1001", "Zhang San", "manager", "d01"),
        "Idempotency-Key": key,
    }
    first = client.post(f"{PREFIX}/tasks/{task['id']}/approve", json={"message": "同意"}, headers=request_headers)
    assert first.status_code == 200, first.text
    assert first.json()["flow_status"] == "1"

    command = _one("select * from flow_command where idempotency_key = ?", (key,))
    assert command is not None
    assert command["command_type"] == "APPROVE"
    assert command["status"] == "APPLIED"

    second = client.post(f"{PREFIX}/tasks/{task['id']}/approve", json={"message": "同意"}, headers=request_headers)
    assert second.status_code == 200, second.text
    assert second.json()["flow_status"] == "1"
    histories = _rows(
        "select * from flow_his_task where instance_id = ? and node_code = 'dept' and approver = 'u1001'",
        (instance["id"],),
    )
    assert len(histories) == 1
    assert len(_rows("select * from flow_command where idempotency_key = ?", (key,))) == 1


def test_failed_command_records_domain_error_without_outbox(client: TestClient) -> None:
    instance = _start(client, key=f"start-{uuid4().hex}", days=1)
    task = client.get(
        f"{PREFIX}/tasks?instanceId={instance['id']}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    ).json()["items"][0]
    key = f"bad-{uuid4().hex}"
    response = client.post(
        f"{PREFIX}/tasks/{task['id']}/approve",
        json={"message": "越权"},
        headers={**headers("u1003", "Wang Wu", "finance", "d03"), "Idempotency-Key": key},
    )
    assert response.status_code == 403, response.text
    command = _one("select * from flow_command where idempotency_key = ?", (key,))
    assert command is not None
    assert command["status"] == "FAILED"
    assert command["error_code"] == 403
    assert _one("select * from flow_outbox where command_id = ?", (command["id"],)) is None
