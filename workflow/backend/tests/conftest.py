"""Pytest fixtures: isolated SQLite database + FastAPI test client."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="eai-workflow-tests-"))
TEST_DB_PATH = _TMP / "test.db"
os.environ["WORKFLOW_DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["WORKFLOW_SEED_DEMO"] = "1"
os.environ["WORKFLOW_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["TEMPORAL_ENABLED"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as instance:
        yield instance


@pytest.fixture()
def api(client: TestClient) -> TestClient:
    return client


def headers(user: str = "u1001", name: str = "Zhang San", roles: str = "manager", dept: str = "d01") -> dict[str, str]:
    return {
        "X-User-Id": user,
        "X-User-Name": name,
        "X-User-Roles": roles,
        "X-User-Dept": dept,
        "X-Tenant-Id": "000000",
    }
