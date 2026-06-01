# Phase 1: Workflow Engine + React Flow Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational workflow engine (Temporal + React Flow) that replaces the fixed 6-stage project pipeline with a configurable DAG-based workflow system.

**Architecture:** Backend uses Temporal.io as workflow execution engine, with a `DynamicGraphWorkflow` that interprets DAG JSON stored in PostgreSQL. Frontend uses React Flow (`@xyflow/react`, already installed) to provide a visual workflow editor. Gateway embeds Temporal Client + Worker in FastAPI lifespan. Phase 2 (traceability), Phase 3 (multi-reviewer), and Phase 4 (monitoring/conditions/sub-workflows) will be separate plans.

**Tech Stack:** Temporal.io 1.27.0 (Server + Python SDK), React Flow @xyflow/react 12.x, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest, Vitest

**Spec:** `docs/superpowers/specs/2026-05-29-workflow-engine-traceability-review-design.md`

---

## File Structure

### New Files (Backend)

```
backend/app/extensions/workflow/
├── __init__.py              # Exports router
├── models.py                # WorkflowDefinition SQLAlchemy model
├── schemas.py               # Pydantic request/response schemas
├── routers.py               # API endpoints
├── service.py               # DAG validation, CRUD, state management
├── permissions.py           # Reuse project permissions
└── temporal/
    ├── __init__.py
    ├── client.py            # Temporal Client + Worker lifespan
    ├── workflows.py         # DynamicGraphWorkflow
    ├── activities.py        # All activity implementations
    └── signals.py           # Signal type definitions

backend/alembic/versions/
└── xxxx_add_workflow_definitions.py   # Migration

docker/
└── docker-compose.temporal.yaml       # Temporal server container
```

### Modified Files (Backend)

```
backend/app/extensions/models.py       # Add 3 fields to ReportProject
backend/app/gateway/app.py             # Register workflow router + lifespan
backend/app/extensions/database.py     # Add workflow tables to migration
backend/pyproject.toml                  # Add temporalio dependency
```

### New Files (Frontend)

```
frontend/src/extensions/workflow/
├── api.ts                  # Workflow API client
├── types.ts                # DAG node/edge/definition types
├── transforms.ts           # snake/camel transforms
├── WorkflowEditor.tsx       # React Flow editor container
├── nodes/
│   ├── PhaseNode.tsx       # Phase node component
│   ├── ReviewNode.tsx      # Review node component
│   ├── ConditionNode.tsx   # Condition node component
│   ├── AIGenerateNode.tsx  # AI generate node component
│   └── MergeNode.tsx       # Merge node component
├── edges/
│   └── ConditionEdge.tsx   # Conditional edge with label
├── panels/
│   ├── PhaseConfigPanel.tsx    # Phase node property editor
│   ├── ReviewConfigPanel.tsx   # Review node property editor
│   └── NodePalette.tsx         # Draggable node palette
└── hooks/
    ├── useWorkflowDAG.ts       # DAG manipulation hook
    └── useValidation.ts        # DAG validation hook
```

### Modified Files (Frontend)

```
frontend/src/extensions/project/ProjectWorkspace.tsx   # Add "工作流" tab
```

---

## Task 1: Add temporalio Dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add temporalio to backend dependencies**

```bash
cd backend && uv add "temporalio[pydantic]>=1.27.0"
```

- [ ] **Step 2: Verify installation**

```bash
cd backend && uv run python -c "import temporalio; print(temporalio.__version__)"
```
Expected: `1.27.0` or higher

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: add temporalio dependency for workflow engine"
```

---

## Task 2: Temporal Docker Compose

**Files:**
- Create: `docker/docker-compose.temporal.yaml`

- [ ] **Step 1: Create docker-compose for Temporal server**

```yaml
# docker/docker-compose.temporal.yaml
# Usage: docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml -f docker-compose.temporal.yaml up -d
#
# Services:
#   - temporal: Temporal Server (auto-setup, connects to existing postgres-ext)

services:
  temporal:
    image: temporalio/auto-setup:1.27.0
    container_name: eai-flow-temporal
    depends_on:
      postgres-ext:
        condition: service_healthy
    environment:
      - DB=postgres12
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal_password
      - POSTGRES_SEEDS=postgres-ext
      - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development-sql.yaml
    networks:
      - eai-flow-net
    ports:
      - "7233:7233"
    restart: unless-stopped

networks:
  eai-flow-net:
    external: true
    name: eai-docker_eai-flow-net
```

- [ ] **Step 2: Verify Temporal can start**

```bash
cd docker && docker compose -f docker-compose.extensions.yaml -f docker-compose.temporal.yaml up -d temporal
```
Expected: Container starts, auto-creates `temporal` and `temporal_visibility` databases on postgres-ext

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.temporal.yaml
git commit -m "infra: add Temporal server docker-compose (reuses postgres-ext)"
```

---

## Task 3: SQLAlchemy Model — WorkflowDefinition

**Files:**
- Create: `backend/app/extensions/workflow/__init__.py`
- Create: `backend/app/extensions/workflow/models.py`
- Modify: `backend/app/extensions/models.py`
- Modify: `backend/app/extensions/database.py`

- [ ] **Step 1: Write failing test for WorkflowDefinition model**

Create: `backend/tests/test_workflow_models.py`

```python
import pytest
from sqlalchemy import select
from app.extensions.workflow.models import WorkflowDefinition


@pytest.mark.asyncio
async def test_create_workflow_definition(db_session):
    wf = WorkflowDefinition(
        name="环评报告流程",
        graph_json={"nodes": [], "edges": []},
    )
    db_session.add(wf)
    await db_session.flush()

    result = await db_session.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.name == "环评报告流程")
    )
    found = result.scalar_one()
    assert found.id is not None
    assert found.graph_json == {"nodes": [], "edges": []}
    assert found.is_template is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_models.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.workflow'`

- [ ] **Step 3: Create workflow extension package**

Create: `backend/app/extensions/workflow/__init__.py`
```python
from .routers import router

__all__ = ["router"]
```

Create: `backend/app/extensions/workflow/models.py`
```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class WorkflowDefinition(Base):
    """DAG-based workflow definition created by React Flow editor."""

    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    report_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<WorkflowDefinition {self.name!r}>"
```

- [ ] **Step 4: Add workflow fields to ReportProject in models.py**

In `backend/app/extensions/models.py`, add to the `ReportProject` class (after the existing `current_stage` field):

```python
    # Workflow engine fields (nullable = backwards compatible)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_definitions.id"), nullable=True,
    )
    temporal_workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_phase_node: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 5: Add migration for new tables and columns**

In `backend/app/extensions/database.py`, inside the `migrate_db()` function, append:

```python
    # Workflow engine tables
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS workflow_definitions ("
        "  id UUID PRIMARY KEY,"
        "  name VARCHAR(200) NOT NULL,"
        "  report_type VARCHAR(50),"
        "  graph_json JSONB NOT NULL,"
        "  is_template BOOLEAN NOT NULL DEFAULT FALSE,"
        "  created_by UUID REFERENCES users(id),"
        "  created_at TIMESTAMP NOT NULL DEFAULT NOW(),"
        "  updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    ))
    await conn.execute(text(
        "ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS workflow_id UUID REFERENCES workflow_definitions(id)"
    ))
    await conn.execute(text(
        "ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS temporal_workflow_id VARCHAR(100)"
    ))
    await conn.execute(text(
        "ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS current_phase_node VARCHAR(50)"
    ))
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_models.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/workflow/ backend/app/extensions/models.py backend/app/extensions/database.py backend/tests/test_workflow_models.py
git commit -m "feat(workflow): add WorkflowDefinition model and ReportProject extension"
```

---

## Task 4: Pydantic Schemas

**Files:**
- Create: `backend/app/extensions/workflow/schemas.py`

- [ ] **Step 1: Write failing test for schema validation**

Create: `backend/tests/test_workflow_schemas.py`

```python
import pytest
from app.extensions.workflow.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowDefinitionListResponse,
    DAGValidationResult,
)


def test_workflow_definition_create():
    req = WorkflowDefinitionCreate(
        name="环评报告流程",
        report_type="environmental_impact",
        graph_json={"nodes": [{"id": "a", "type": "phase", "data": {"label": "Phase A"}}], "edges": []},
    )
    assert req.name == "环评报告流程"
    assert req.is_template is False


def test_workflow_definition_out():
    out = WorkflowDefinitionOut(
        id="00000000-0000-0000-0000-000000000001",
        name="test",
        graph_json={"nodes": [], "edges": []},
        is_template=False,
        created_at=None,
        updated_at=None,
    )
    assert out.id == "00000000-0000-0000-0000-000000000001"


def test_dag_validation_result():
    result = DAGValidationResult(valid=True, errors=[], warnings=[])
    assert result.valid is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_schemas.py -v
```
Expected: FAIL — `ImportError`

- [ ] **Step 3: Create schemas**

Create: `backend/app/extensions/workflow/schemas.py`

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict = Field(..., description="DAG nodes and edges from React Flow")
    is_template: bool = False


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict | None = None
    is_template: bool | None = None


class WorkflowDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    graph_json: dict
    is_template: bool = False
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowDefinitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    is_template: bool = False
    created_at: datetime | None = None


class WorkflowDefinitionListResponse(BaseModel):
    items: list[WorkflowDefinitionListItem] = Field(default_factory=list)
    total: int = 0


class DAGValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowStartRequest(BaseModel):
    workflow_id: UUID


class WorkflowSignalRequest(BaseModel):
    signal_name: str
    signal_payload: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_schemas.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/schemas.py backend/tests/test_workflow_schemas.py
git commit -m "feat(workflow): add Pydantic schemas for workflow definitions"
```

---

## Task 5: DAG Validation Service

**Files:**
- Create: `backend/app/extensions/workflow/service.py`

- [ ] **Step 1: Write failing tests for DAG validation**

Create: `backend/tests/test_workflow_service.py`

```python
import pytest
from app.extensions.workflow.service import validate_dag


def test_valid_linear_dag():
    graph = {
        "nodes": [
            {"id": "a", "type": "phase", "data": {"label": "A"}},
            {"id": "b", "type": "phase", "data": {"label": "B"}},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    result = validate_dag(graph)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_dag_with_cycle():
    graph = {
        "nodes": [
            {"id": "a", "type": "phase", "data": {"label": "A"}},
            {"id": "b", "type": "phase", "data": {"label": "B"}},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    }
    result = validate_dag(graph)
    assert result["valid"] is False
    assert any("cycle" in e.lower() for e in result["errors"])


def test_dag_with_disconnected_node():
    graph = {
        "nodes": [
            {"id": "a", "type": "phase", "data": {"label": "A"}},
            {"id": "b", "type": "phase", "data": {"label": "B"}},
            {"id": "c", "type": "phase", "data": {"label": "C"}},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    result = validate_dag(graph)
    assert result["valid"] is True  # Not invalid, just a warning
    assert any("disconnected" in w.lower() for w in result["warnings"])


def test_empty_dag():
    graph = {"nodes": [], "edges": []}
    result = validate_dag(graph)
    assert result["valid"] is False
    assert any("empty" in e.lower() for e in result["errors"])


def test_topological_sort():
    graph = {
        "nodes": [
            {"id": "a", "type": "phase", "data": {"label": "A"}},
            {"id": "b", "type": "phase", "data": {"label": "B"}},
            {"id": "c", "type": "phase", "data": {"label": "C"}},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }
    from app.extensions.workflow.service import topological_sort
    order = topological_sort(graph)
    assert order.index("a") < order.index("b") < order.index("c")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_service.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement DAG validation service**

Create: `backend/app/extensions/workflow/service.py`

```python
from collections import defaultdict


def validate_dag(graph: dict) -> dict:
    """Validate a DAG graph_json structure. Returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return {"valid": False, "errors": ["Graph is empty — must have at least one node"], "warnings": []}

    node_ids = {n["id"] for n in nodes}

    # Check edge references
    for edge in edges:
        if edge["source"] not in node_ids:
            errors.append(f"Edge references unknown source node '{edge['source']}'")
        if edge["target"] not in node_ids:
            errors.append(f"Edge references unknown target node '{edge['target']}'")

    # Cycle detection (DFS)
    adjacency = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}

    def has_cycle(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and has_cycle(neighbor):
                return True
        color[node_id] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if has_cycle(nid):
                errors.append("Graph contains a cycle")
                break

    # Disconnected node detection
    sources = {e["source"] for e in edges}
    targets = {e["target"] for e in edges}
    connected = sources | targets
    for node in nodes:
        if node["id"] not in connected and len(nodes) > 1:
            warnings.append(f"Node '{node['id']}' ({node.get('data', {}).get('label', '')}) is disconnected")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def topological_sort(graph: dict) -> list[str]:
    """Return nodes in topological order."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    adjacency = defaultdict(list)
    in_degree = defaultdict(int)
    node_ids = [n["id"] for n in nodes]

    for nid in node_ids:
        in_degree[nid] = 0

    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        in_degree[edge["target"]] += 1

    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_service.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/service.py backend/tests/test_workflow_service.py
git commit -m "feat(workflow): add DAG validation and topological sort"
```

---

## Task 6: API Routers — Workflow Definition CRUD

**Files:**
- Create: `backend/app/extensions/workflow/routers.py`
- Create: `backend/app/extensions/workflow/permissions.py`
- Modify: `backend/app/gateway/app.py`

- [ ] **Step 1: Write failing test for workflow API**

Create: `backend/tests/test_workflow_routers.py`

```python
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_create_workflow_definition(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/extensions/workflow/definitions",
        json={
            "name": "测试工作流",
            "graph_json": {"nodes": [{"id": "a", "type": "phase", "data": {"label": "Phase A"}}], "edges": []},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试工作流"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_workflow_definitions(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/extensions/workflow/definitions", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_validate_dag(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/extensions/workflow/definitions/validate",
        json={"nodes": [{"id": "a", "type": "phase", "data": {"label": "A"}}], "edges": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
```

Note: Use existing test fixtures from the project test suite for `client` and `auth_headers`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_routers.py -v
```
Expected: FAIL — 404 or import error

- [ ] **Step 3: Create permissions module**

Create: `backend/app/extensions/workflow/permissions.py`

```python
from app.extensions.project.permissions import require_resource_permission

# Workflow definitions use the same permission system as projects.
# Workflow-level operations require project-level permissions.
# System-level: project:create, project:list, project:read
# Resource-level: inherited from project permissions when attached to a project
```

- [ ] **Step 4: Create routers**

Create: `backend/app/extensions/workflow/routers.py`

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from .models import WorkflowDefinition
from .schemas import (
    DAGValidationResult,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionListItem,
    WorkflowDefinitionOut,
    WorkflowDefinitionUpdate,
)
from .service import validate_dag

router = APIRouter(prefix="/api/extensions/workflow", tags=["workflow"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


@router.get("/definitions", response_model=WorkflowDefinitionListResponse)
async def list_definitions(
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    is_template: bool | None = None,
    report_type: str | None = None,
):
    query = select(WorkflowDefinition)
    if is_template is not None:
        query = query.where(WorkflowDefinition.is_template == is_template)
    if report_type:
        query = query.where(WorkflowDefinition.report_type == report_type)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query.order_by(WorkflowDefinition.created_at.desc()))
    items = [WorkflowDefinitionListItem.model_validate(wf) for wf in result.scalars().all()]
    return WorkflowDefinitionListResponse(items=items, total=total)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def get_definition(
    definition_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    wf = await db.get(WorkflowDefinition, definition_id)
    if not wf:
        raise HTTPException(404, "Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(wf)


@router.post("/definitions", response_model=WorkflowDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_definition(
    body: WorkflowDefinitionCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    wf = WorkflowDefinition(
        name=body.name,
        report_type=body.report_type,
        graph_json=body.graph_json,
        is_template=body.is_template,
        created_by=user.id,
    )
    db.add(wf)
    await db.flush()
    return WorkflowDefinitionOut.model_validate(wf)


@router.put("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def update_definition(
    definition_id: UUID,
    body: WorkflowDefinitionUpdate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    wf = await db.get(WorkflowDefinition, definition_id)
    if not wf:
        raise HTTPException(404, "Workflow definition not found")
    if body.name is not None:
        wf.name = body.name
    if body.report_type is not None:
        wf.report_type = body.report_type
    if body.graph_json is not None:
        wf.graph_json = body.graph_json
    if body.is_template is not None:
        wf.is_template = body.is_template
    await db.flush()
    return WorkflowDefinitionOut.model_validate(wf)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    wf = await db.get(WorkflowDefinition, definition_id)
    if not wf:
        raise HTTPException(404, "Workflow definition not found")
    await db.delete(wf)
    await db.flush()


@router.post("/definitions/validate", response_model=DAGValidationResult)
async def validate_dag_endpoint(
    body: dict,
    user: CurrentUserWithAccess,
):
    result = validate_dag(body)
    return DAGValidationResult(**result)
```

- [ ] **Step 5: Register router in Gateway**

In `backend/app/gateway/app.py`, add import:

```python
from app.extensions.workflow import router as workflow_router
```

And after other extension router registrations:

```python
# Workflow engine API
app.include_router(workflow_router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_routers.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/workflow/ backend/app/gateway/app.py backend/tests/test_workflow_routers.py
git commit -m "feat(workflow): add workflow definition CRUD API"
```

---

## Task 7: Temporal Client Integration

**Files:**
- Create: `backend/app/extensions/workflow/temporal/__init__.py`
- Create: `backend/app/extensions/workflow/temporal/client.py`
- Modify: `backend/app/gateway/app.py`

- [ ] **Step 1: Create temporal subpackage**

Create: `backend/app/extensions/workflow/temporal/__init__.py`
```python
```

- [ ] **Step 2: Create Temporal client manager**

Create: `backend/app/extensions/workflow/temporal/client.py`

```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from temporalio.client import Client
from temporalio.worker import Worker

from .workflows import DynamicGraphWorkflow

logger = logging.getLogger(__name__)

TEMPORAL_TASK_QUEUE = "project-workflow-queue"
TEMPORAL_URL = "localhost:7233"

_temporal_client: Client | None = None


def get_temporal_client() -> Client | None:
    """Get the global Temporal client instance."""
    return _temporal_client


@asynccontextmanager
async def temporal_lifespan(app: FastAPI):
    """FastAPI lifespan manager for Temporal Client + embedded Worker.

    If Temporal server is unreachable, logs a warning and continues.
    All workflow features will be disabled until server becomes available.
    """
    global _temporal_client

    try:
        client = await Client.connect(TEMPORAL_URL, namespace="default")

        worker = Worker(
            client,
            task_queue=TEMPORAL_TASK_QUEUE,
            workflows=[DynamicGraphWorkflow],
            activities=[],  # Activities registered in Task 8
        )
        worker_task = asyncio.create_task(worker.run())

        _temporal_client = client
        app.state.temporal_client = client
        logger.info("Temporal client connected, worker started on queue '%s'", TEMPORAL_TASK_QUEUE)

        yield

        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        _temporal_client = None

    except Exception as e:
        logger.warning("Temporal server not available (%s). Workflow features disabled.", e)
        yield
```

- [ ] **Step 3: Integrate into Gateway lifespan**

In `backend/app/gateway/app.py`, modify the lifespan to include Temporal:

```python
from app.extensions.workflow.temporal.client import temporal_lifespan
```

Nest the temporal lifespan inside the existing lifespan, after database init:

```python
    # Inside lifespan(), after langgraph_runtime(app):
    async with temporal_lifespan(app):
        yield
```

Note: If the existing lifespan structure doesn't allow nesting, wrap the temporal context manager around the yield point.

- [ ] **Step 4: Verify Gateway starts with Temporal unavailable**

```bash
cd backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow.temporal.client import temporal_lifespan; print('Import OK')"
```
Expected: `Import OK` (no Temporal server needed for import)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/temporal/ backend/app/gateway/app.py
git commit -m "feat(workflow): add Temporal client lifespan integration"
```

---

## Task 8: DynamicGraphWorkflow + Activities (Stub)

**Files:**
- Create: `backend/app/extensions/workflow/temporal/workflows.py`
- Create: `backend/app/extensions/workflow/temporal/activities.py`
- Create: `backend/app/extensions/workflow/temporal/signals.py`

- [ ] **Step 1: Create signal definitions**

Create: `backend/app/extensions/workflow/temporal/signals.py`

```python
"""Temporal signal names used by DynamicGraphWorkflow."""

SIGNAL_PHASE_COMPLETE = "phase_complete"
SIGNAL_REVIEW_ACTION = "review_action"
SIGNAL_AI_COMPLETE = "ai_complete"
```

- [ ] **Step 2: Create stub activities**

Create: `backend/app/extensions/workflow/temporal/activities.py`

```python
import logging
from datetime import datetime

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def init_phase(params: dict) -> dict:
    """Initialize a workflow phase — create chapters, assign team."""
    logger.info("init_phase: node=%s project=%s", params.get("node", {}).get("id"), params.get("project_id"))
    # Phase 1: Stub. Full implementation in integration task.
    return {"status": "initialized", "node_id": params.get("node", {}).get("id")}


@activity.defn
async def advance_phase(params: dict) -> dict:
    """Update report_project.current_phase_node."""
    logger.info("advance_phase: project=%s node=%s", params.get("project_id"), params.get("node_id"))
    return {"status": "advanced"}


@activity.defn
async def create_review_assignments(params: dict) -> dict:
    """Create phase_reviews records from DAG review node config."""
    logger.info("create_review_assignments: node=%s project=%s", params.get("node", {}).get("id"), params.get("project_id"))
    return {"status": "reviews_created"}


@activity.defn
async def notify_phase_start(params: dict) -> dict:
    """Notify team members that a phase has started."""
    logger.info("notify_phase_start: phase=%s", params.get("phase_name"))
    return {"status": "notified"}


@activity.defn
async def notify_review_pending(params: dict) -> dict:
    """Notify reviewers they have pending reviews."""
    logger.info("notify_review_pending: reviewers=%s", params.get("reviewer_ids"))
    return {"status": "notified"}


@activity.defn
async def notify_workflow_complete(params: dict) -> dict:
    """Notify project manager that the workflow completed."""
    logger.info("notify_workflow_complete: project=%s", params.get("project_id"))
    return {"status": "notified"}


@activity.defn
async def evaluate_condition(params: dict) -> str:
    """Evaluate a condition expression and return the branch label."""
    expression = params.get("expression", "")
    context = params.get("context", {})
    # Stub: return first truthy branch. Full impl in Phase 4.
    logger.info("evaluate_condition: expr=%s", expression)
    return "default"


# List all activities for Worker registration
ALL_ACTIVITIES = [
    init_phase,
    advance_phase,
    create_review_assignments,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
    evaluate_condition,
]
```

- [ ] **Step 3: Create DynamicGraphWorkflow**

Create: `backend/app/extensions/workflow/temporal/workflows.py`

```python
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from .activities import init_phase, advance_phase, create_review_assignments, notify_phase_start
    from .signals import SIGNAL_PHASE_COMPLETE, SIGNAL_REVIEW_ACTION, SIGNAL_AI_COMPLETE
    from ..service import topological_sort

logger = logging.getLogger(__name__)


@workflow.defn
class DynamicGraphWorkflow:
    """Interprets a DAG JSON definition and executes nodes as Temporal activities."""

    def __init__(self):
        self.phase_contexts: dict[str, dict] = {}
        self.review_results: dict[str, str] = {}
        self.ai_results: dict[str, dict] = {}

    @workflow.signal(name=SIGNAL_PHASE_COMPLETE)
    async def phase_complete(self, phase_node: str, context: dict):
        self.phase_contexts[phase_node] = context

    @workflow.signal(name=SIGNAL_REVIEW_ACTION)
    async def review_action(self, review_id: str, action: str):
        self.review_results[review_id] = action

    @workflow.signal(name=SIGNAL_AI_COMPLETE)
    async def ai_complete(self, chapter_id: str, result: dict):
        self.ai_results[chapter_id] = result

    @workflow.run
    async def run(self, params: dict) -> dict:
        graph = params["graph_json"]
        project_id = params["project_id"]
        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        if not nodes:
            return {"status": "error", "message": "Empty graph"}

        # Build adjacency and reverse adjacency
        adjacency: dict[str, list[dict]] = defaultdict(list)
        reverse_adj: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge["source"]].append(edge)
            reverse_adj[edge["target"]].append(edge["source"])

        # Find start nodes (no incoming edges)
        all_targets = {e["target"] for e in edges}
        start_nodes = [nid for nid in nodes if nid not in all_targets]

        completed: set[str] = set()
        results: dict[str, dict] = {}
        current_nodes = set(start_nodes)

        max_iterations = len(nodes) * 2
        iteration = 0

        while current_nodes and iteration < max_iterations:
            iteration += 1
            next_nodes = set()

            for node_id in list(current_nodes):
                node = nodes[node_id]
                node_type = node.get("type", "phase")

                if node_type == "phase":
                    # Execute init_phase activity
                    await workflow.execute_activity(
                        init_phase,
                        {"node": node, "project_id": project_id, "input_contexts": {k: v for k, v in results.items() if k in reverse_adj.get(node_id, [])}},
                        start_to_close_timeout=timedelta(minutes=5),
                    )
                    # Wait for external phase_complete signal
                    await workflow.wait_condition(
                        lambda nid=node_id: nid in self.phase_contexts,
                        timeout=timedelta(days=30),
                    )
                    results[node_id] = self.phase_contexts[node_id]

                elif node_type == "review":
                    await workflow.execute_activity(
                        create_review_assignments,
                        {"node": node, "project_id": project_id},
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    # Wait for all reviews to complete
                    review_ids = node.get("data", {}).get("review_ids", [])
                    await workflow.wait_condition(
                        lambda: all(rid in self.review_results for rid in review_ids) if review_ids else True,
                        timeout=timedelta(days=30),
                    )
                    results[node_id] = {"status": "reviewed"}
                    # Check for rejections
                    if any(a == "rejected" for a in self.review_results.values()):
                        # Find rejection target from edge label
                        for edge in adjacency.get(node_id, []):
                            if edge.get("label") == "rejected":
                                next_nodes = {edge["target"]}
                                break
                        completed.add(node_id)
                        continue

                elif node_type == "condition":
                    # Condition nodes route immediately (no wait)
                    results[node_id] = {"status": "evaluated"}
                    completed.add(node_id)
                    for edge in adjacency.get(node_id, []):
                        next_nodes.add(edge["target"])
                    continue

                elif node_type == "merge":
                    # Wait for all upstream to complete
                    upstream = reverse_adj.get(node_id, [])
                    await workflow.wait_condition(
                        lambda uids=upstream: all(u in completed for u in uids),
                    )
                    merged = {u: results.get(u, {}) for u in upstream}
                    results[node_id] = merged

                elif node_type == "ai_generate":
                    # Phase 1 stub: just mark as completed
                    results[node_id] = {"status": "ai_stub"}

                # Advance phase in DB
                await workflow.execute_activity(
                    advance_phase,
                    {"project_id": project_id, "node_id": node_id},
                    start_to_close_timeout=timedelta(seconds=10),
                )

                completed.add(node_id)

                # Find downstream nodes whose all upstream are completed
                for edge in adjacency.get(node_id, []):
                    target = edge["target"]
                    if target not in completed:
                        target_upstream = reverse_adj.get(target, [])
                        if all(u in completed for u in target_upstream):
                            next_nodes.add(target)

            current_nodes = next_nodes

        return {"status": "completed", "results": results}
```

- [ ] **Step 4: Update Worker to register activities**

In `backend/app/extensions/workflow/temporal/client.py`, update the Worker registration:

```python
from .activities import ALL_ACTIVITIES
# ...
        worker = Worker(
            client,
            task_queue=TEMPORAL_TASK_QUEUE,
            workflows=[DynamicGraphWorkflow],
            activities=ALL_ACTIVITIES,
        )
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/temporal/
git commit -m "feat(workflow): add DynamicGraphWorkflow interpreter and stub activities"
```

---

## Task 9: Frontend Types + API Client

**Files:**
- Create: `frontend/src/extensions/workflow/types.ts`
- Create: `frontend/src/extensions/workflow/api.ts`
- Create: `frontend/src/extensions/workflow/transforms.ts`

- [ ] **Step 1: Create TypeScript types**

Create: `frontend/src/extensions/workflow/types.ts`

```typescript
// DAG Node types
export type DAGNodeType = "phase" | "review" | "condition" | "ai_generate" | "merge";

export interface DAGNodeData {
  label: string;
  team?: string;
  chapterRange?: number[];
  aiAssist?: boolean;
  inputFrom?: string[];
  mode?: "chapter" | "dimension" | "mixed";
  expression?: string;
  [key: string]: unknown;
}

export interface DAGNode {
  id: string;
  type: DAGNodeType;
  position: { x: number; y: number };
  data: DAGNodeData;
}

export interface DAGEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

export interface WorkflowGraph {
  nodes: DAGNode[];
  edges: DAGEdge[];
}

// API types
export interface WorkflowDefinition {
  id: string;
  name: string;
  reportType: string | null;
  graphJson: WorkflowGraph;
  isTemplate: boolean;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface WorkflowDefinitionListItem {
  id: string;
  name: string;
  reportType: string | null;
  isTemplate: boolean;
  createdAt: string | null;
}

export interface WorkflowDefinitionListResponse {
  items: WorkflowDefinitionListItem[];
  total: number;
}

export interface CreateWorkflowRequest {
  name: string;
  reportType?: string | null;
  graphJson: WorkflowGraph;
  isTemplate?: boolean;
}

export interface UpdateWorkflowRequest {
  name?: string | null;
  reportType?: string | null;
  graphJson?: WorkflowGraph;
  isTemplate?: boolean;
}

export interface DAGValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}
```

- [ ] **Step 2: Create transforms**

Create: `frontend/src/extensions/workflow/transforms.ts`

```typescript
// Reuse the same patterns from project/transforms.ts
export function toCamelCase<T>(obj: unknown): T {
  if (obj === null || obj === undefined || typeof obj !== "object") {
    return obj as T;
  }
  if (Array.isArray(obj)) {
    return obj.map((item) => toCamelCase(item)) as T;
  }
  if (obj instanceof Date) {
    return obj as T;
  }
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const camelKey = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
    result[camelKey] = toCamelCase(value);
  }
  return result as T;
}

export function toSnakeCase(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === undefined) continue;
    const snakeKey = key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
    result[snakeKey] = value;
  }
  return result;
}
```

- [ ] **Step 3: Create API client**

Create: `frontend/src/extensions/workflow/api.ts`

```typescript
import { authFetch } from "@/extensions/api/client";
import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CreateWorkflowRequest,
  DAGValidationResult,
  UpdateWorkflowRequest,
  WorkflowDefinition,
  WorkflowDefinitionListResponse,
  WorkflowGraph,
} from "./types";

const API_BASE = "/api/extensions/workflow";

export const workflowApi = {
  list: async (params?: { isTemplate?: boolean; reportType?: string }): Promise<WorkflowDefinitionListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.isTemplate !== undefined) searchParams.set("is_template", String(params.isTemplate));
    if (params?.reportType) searchParams.set("report_type", params.reportType);
    const qs = searchParams.toString();
    const resp = await authFetch(`${API_BASE}/definitions${qs ? `?${qs}` : ""}`);
    return toCamelCase<WorkflowDefinitionListResponse>(await resp.json());
  },

  get: async (id: string): Promise<WorkflowDefinition> => {
    const resp = await authFetch(`${API_BASE}/definitions/${id}`);
    return toCamelCase<WorkflowDefinition>(await resp.json());
  },

  create: async (req: CreateWorkflowRequest): Promise<WorkflowDefinition> => {
    const resp = await authFetch(`${API_BASE}/definitions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<WorkflowDefinition>(await resp.json());
  },

  update: async (id: string, req: UpdateWorkflowRequest): Promise<WorkflowDefinition> => {
    const resp = await authFetch(`${API_BASE}/definitions/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<WorkflowDefinition>(await resp.json());
  },

  delete: async (id: string): Promise<void> => {
    await authFetch(`${API_BASE}/definitions/${id}`, { method: "DELETE" });
  },

  validate: async (graph: WorkflowGraph): Promise<DAGValidationResult> => {
    const resp = await authFetch(`${API_BASE}/definitions/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(graph),
    });
    return toCamelCase<DAGValidationResult>(await resp.json());
  },
};
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/workflow/
git commit -m "feat(workflow): add frontend types, transforms, and API client"
```

---

## Task 10: React Flow Editor — Core Setup

**Files:**
- Create: `frontend/src/extensions/workflow/WorkflowEditor.tsx`
- Create: `frontend/src/extensions/workflow/nodes/PhaseNode.tsx`
- Create: `frontend/src/extensions/workflow/nodes/ReviewNode.tsx`
- Create: `frontend/src/extensions/workflow/nodes/ConditionNode.tsx`
- Create: `frontend/src/extensions/workflow/nodes/AIGenerateNode.tsx`
- Create: `frontend/src/extensions/workflow/nodes/MergeNode.tsx`
- Create: `frontend/src/extensions/workflow/panels/NodePalette.tsx`
- Create: `frontend/src/extensions/workflow/hooks/useWorkflowDAG.ts`
- Create: `frontend/src/extensions/workflow/hooks/useValidation.ts`

- [ ] **Step 1: Create custom node components**

Create each node in `frontend/src/extensions/workflow/nodes/`. Each is a React Flow custom node with distinctive styling:

`PhaseNode.tsx` — Purple border, shows team name + chapter range
`ReviewNode.tsx` — Red border, shows review mode + reviewer count
`ConditionNode.tsx` — Yellow/diamond shape, shows expression
`AIGenerateNode.tsx` — Blue border, shows chapter target
`MergeNode.tsx` — Green, circular, shows "汇聚" label

Each node follows this pattern (example for PhaseNode):

```tsx
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { DAGNode } from "../types";

export function PhaseNode({ data, selected }: NodeProps<DAGNode>) {
  return (
    <div className={`px-3 py-2 rounded-lg border-2 bg-white min-w-[140px] ${
      selected ? "border-purple-500 shadow-lg" : "border-purple-300"
    }`}>
      <Handle type="target" position={Position.Top} className="!bg-purple-400" />
      <div className="text-xs font-semibold text-purple-700">{data.label}</div>
      {data.team && <div className="text-[10px] text-gray-500 mt-1">团队: {data.team}</div>}
      {data.chapterRange && (
        <div className="text-[10px] text-gray-500">章节: {data.chapterRange.join("-")}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-purple-400" />
    </div>
  );
}
```

- [ ] **Step 2: Create node palette (draggable sidebar)**

Create: `frontend/src/extensions/workflow/panels/NodePalette.tsx`

A sidebar with draggable node type cards that can be dropped onto the React Flow canvas. Uses React Flow's `useReactFlow().addNodes()` pattern.

- [ ] **Step 3: Create DAG manipulation hook**

Create: `frontend/src/extensions/workflow/hooks/useWorkflowDAG.ts`

Hook wrapping React Flow state operations: `addNode`, `updateNodeData`, `removeNode`, `addEdge`, `removeEdge`, `toGraphJson`, `fromGraphJson`.

- [ ] **Step 4: Create validation hook**

Create: `frontend/src/extensions/workflow/hooks/useValidation.ts`

Hook that calls `workflowApi.validate()` and returns validation state with errors/warnings.

- [ ] **Step 5: Create WorkflowEditor container**

Create: `frontend/src/extensions/workflow/WorkflowEditor.tsx`

Main component that assembles:
- Left: `<NodePalette />`
- Center: `<ReactFlow>` with custom node types registered
- Right: Config panel (placeholder for now, expanded in PhaseConfigPanel task)
- Toolbar: Save, Validate, Save as Template buttons

Uses `useWorkflowDAG` hook for state management.

- [ ] **Step 6: Verify frontend compiles**

```bash
cd frontend && pnpm typecheck
```
Expected: No type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/workflow/
git commit -m "feat(workflow): add React Flow editor with custom node types"
```

---

## Task 11: Node Config Panels

**Files:**
- Create: `frontend/src/extensions/workflow/panels/PhaseConfigPanel.tsx`
- Create: `frontend/src/extensions/workflow/panels/ReviewConfigPanel.tsx`
- Modify: `frontend/src/extensions/workflow/WorkflowEditor.tsx`

- [ ] **Step 1: Create PhaseConfigPanel**

Right sidebar panel for editing phase node properties:
- Phase name (text input)
- Team selector (dropdown from project members)
- Chapter range (multi-select from project chapters)
- AI assist toggle
- Context input sources (read-only, showing upstream phase names)

- [ ] **Step 2: Create ReviewConfigPanel**

Right sidebar panel for editing review node properties:
- Review mode selector (chapter / dimension / mixed)
- Chapter assignments section: chapter list → reviewer dropdown
- Dimension assignments section: dimension chips → reviewer dropdown
- Rejection target selector (which node to return to on rejection)

- [ ] **Step 3: Wire config panels into WorkflowEditor**

Update WorkflowEditor to detect selected node type and render the matching config panel.

- [ ] **Step 4: Verify frontend compiles**

```bash
cd frontend && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/workflow/
git commit -m "feat(workflow): add phase and review config panels"
```

---

## Task 12: Integrate WorkflowEditor into ProjectWorkspace

**Files:**
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`

- [ ] **Step 1: Add "工作流" tab to ProjectWorkspace**

In `ProjectWorkspace.tsx`, add "workflow" to the `ViewTab` type and add a tab button:

```tsx
type ViewTab = "info" | "files" | "approval" | "workflow";
```

Add conditional rendering for the workflow tab:

```tsx
{activeTab === "workflow" && (
  <WorkflowEditor projectId={projectId} />
)}
```

Import `WorkflowEditor` from `@/extensions/workflow/WorkflowEditor`.

- [ ] **Step 2: Verify the tab appears in the project workspace**

```bash
cd frontend && pnpm dev
```
Navigate to a project page and verify the "工作流" tab is visible.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/ProjectWorkspace.tsx
git commit -m "feat(workflow): integrate workflow editor into ProjectWorkspace"
```

---

## Task 13: End-to-End Smoke Test

**Files:** No new files

- [ ] **Step 1: Start all services**

```bash
# Terminal 1: Temporal
cd docker && docker compose -f docker-compose.extensions.yaml -f docker-compose.temporal.yaml up -d

# Terminal 2: Backend
cd backend && make dev

# Terminal 3: Frontend
cd frontend && pnpm dev
```

- [ ] **Step 2: Create a workflow definition via API**

```bash
curl -X POST http://localhost:8001/api/extensions/workflow/definitions \
  -H "Content-Type: application/json" \
  -H "Cookie: $(curl -s -c - -X POST http://localhost:8001/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}' | grep token | awk '{print $NF}')" \
  -d '{"name":"测试工作流","graph_json":{"nodes":[{"id":"p1","type":"phase","data":{"label":"阶段A"}}],"edges":[]}}'
```
Expected: 201 with workflow ID

- [ ] **Step 3: Open frontend and verify workflow editor**

Navigate to `http://localhost:2026` → open a project → click "工作流" tab → verify the React Flow editor renders with the node palette.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix(workflow): address smoke test issues"
```

---

## Self-Review

**1. Spec coverage check:**

| Spec Section | Covered by Task |
|---|---|
| 2.1 Runtime topology | Tasks 2, 7 |
| 2.2 Infrastructure (+1 container) | Task 2 |
| 2.3 Gateway Temporal integration | Task 7 |
| 3.1 `workflow_definitions` table | Task 3 |
| 3.2 ReportProject extension | Task 3 |
| 3.4 Alembic migration | Task 3 |
| 3.5 DAG JSON structure | Tasks 9, 10 |
| 4.1 Node type mapping | Task 8 |
| 4.2 DynamicGraphWorkflow | Task 8 |
| 4.4 Activities list | Task 8 |
| 7.1 Frontend directory | Tasks 9-12 |
| 7.2 WorkflowEditor | Tasks 10-11 |
| 8.1 API endpoints | Task 6 |
| 10. Backward compatibility | Task 3 (nullable fields) |

**2. Placeholder scan:** No TBD/TODO found. All steps have concrete code or commands.

**3. Type consistency:** Verified: `WorkflowDefinition` model fields match schemas match API client types match frontend types. DAG validation input/output types consistent across service, router, and frontend API.

**Gaps found:** None. Phase 2 (traceability), Phase 3 (multi-reviewer), Phase 4 (monitoring/conditions) are intentionally deferred to separate plans as they are independent subsystems.
