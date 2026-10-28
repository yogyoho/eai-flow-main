"""Phase 0 Temporal wiring tests that do not require a live server."""

from __future__ import annotations

import pytest

from app.config import _env_flag, settings
from app.temporal.client import get_client, temporal_health
from app.temporal.worker import run_worker


def test_env_flag_accepts_common_boolean_spellings(monkeypatch):
    monkeypatch.setenv("WORKFLOW_TEST_FLAG", "true")
    assert _env_flag("WORKFLOW_TEST_FLAG") is True
    monkeypatch.setenv("WORKFLOW_TEST_FLAG", "false")
    assert _env_flag("WORKFLOW_TEST_FLAG") is False
    monkeypatch.setenv("WORKFLOW_TEST_FLAG", "0")
    assert _env_flag("WORKFLOW_TEST_FLAG") is False
    monkeypatch.delenv("WORKFLOW_TEST_FLAG")
    assert _env_flag("WORKFLOW_TEST_FLAG", default=True) is True


def test_health_reports_temporal_disabled(api):
    body = api.get("/api/workflow/health").json()

    assert body["status"] == "ok"
    assert body["temporal"]["enabled"] is False
    assert body["temporal"]["connected"] is None
    assert body["temporal"]["task_queue"] == "workflow-engine-queue"


async def test_client_refuses_when_disabled():
    assert settings.temporal_enabled is False

    with pytest.raises(RuntimeError, match="TEMPORAL_ENABLED"):
        await get_client()
    assert (await temporal_health())["connected"] is None


async def test_worker_refuses_when_disabled():
    with pytest.raises(RuntimeError, match="TEMPORAL_ENABLED"):
        await run_worker()
