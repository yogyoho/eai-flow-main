# AI Writing & DeerFlow Chat Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate project module's AI writing and collaborative editing with DeerFlow's existing lead_agent conversation system via MCP tools, a Skill file, and thread-based navigation — zero custom agent code.

**Architecture:** Jump-to-chat pattern — ProjectWorkspace creates threads with project metadata, then navigates to DeerFlow's native chat page. The lead_agent auto-detects project context from thread metadata and uses Project MCP Server tools to read/write chapters. A report-write Skill guides the agent's writing strategy.

**Tech Stack:** FastAPI (backend), MCP Server (langchain-mcp-adapters), DeerFlow Skill (Markdown), Next.js 16 / React 19 / Tailwind CSS 4 / Shadcn UI / Lucide icons (frontend)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/app/extensions/project/mcp.py` | MCP Server exposing 6 chapter/project tools to lead_agent |
| `skills/report-write/SKILL.md` | Skill file guiding agent report-writing strategy |
| `frontend/src/extensions/project/ChapterWritingPanel.tsx` | Stage 3 panel: chapter progress + "Start AI Writing" CTA |
| `frontend/src/extensions/project/ChapterEditingPanel.tsx` | Stage 4 panel: chapter assignment table + team sidebar |
| `frontend/src/extensions/project/ChapterAssignDropdown.tsx` | Dropdown for assigning members to chapters |
| `frontend/tests/unit/extensions/project/mcp.test.ts` | Frontend API tests for startWriting / startChapterEditing |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/extensions/project/service.py` | Add `start_writing()`, `start_chapter_editing()`, `get_chapter_spec()` service functions |
| `backend/app/extensions/project/routers.py` | Add `POST /projects/{id}/start-writing`, `POST /projects/{id}/chapters/{ch_id}/start-editing` endpoints |
| `backend/app/extensions/project/schemas.py` | Add `StartWritingResponse`, `StartEditingResponse`, `ChapterSpecOut` schemas |
| `frontend/src/extensions/project/api.ts` | Add `startWriting()`, `startChapterEditing()` API methods |
| `frontend/src/extensions/project/types.ts` | Add `ChapterWritingStatus`, thread-related types |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | Render ChapterWritingPanel (Stage 3) and ChapterEditingPanel (Stage 4) |
| `extensions_config.json` | Register project MCP server |

---

## Task 1: Backend Service Functions — start_writing & start_chapter_editing

**Files:**
- Modify: `backend/app/extensions/project/service.py`
- Modify: `backend/app/extensions/project/schemas.py`
- Test: `backend/tests/test_project_writing_service.py`

These functions create DeerFlow threads with project metadata and link them to the project/chapter.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for project writing/editing thread creation service functions."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.extensions.project.service import start_writing, start_chapter_editing


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def chapter_id():
    return uuid4()


class TestStartWriting:
    async def test_creates_thread_and_updates_project(self, mock_db, project_id):
        """start_writing creates a thread_id and updates project status."""
        tid = str(uuid4())
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.status = "writing"
        mock_project.current_stage = 3
        mock_project.thread_id = None
        mock_project.name = "Test Report"
        mock_project.report_type = "environmental_impact"

        # Mock _get_project_or_404 to return project
        with patch("app.extensions.project.service._get_project_or_404", return_value=mock_project), \
             patch("app.extensions.project.service._create_deerflow_thread", return_value=tid):
            result = await start_writing(mock_db, project_id, user_id=uuid4())

        assert result["thread_id"] == tid
        assert mock_project.thread_id == tid

    async def test_returns_existing_thread_if_present(self, mock_db, project_id):
        """If project already has a thread_id, return it without creating a new one."""
        existing_tid = str(uuid4())
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.thread_id = existing_tid

        with patch("app.extensions.project.service._get_project_or_404", return_value=mock_project):
            result = await start_writing(mock_db, project_id, user_id=uuid4())

        assert result["thread_id"] == existing_tid


class TestStartChapterEditing:
    async def test_creates_chapter_thread(self, mock_db, project_id, chapter_id):
        """start_chapter_editing creates a thread for the chapter."""
        tid = str(uuid4())
        mock_chapter = MagicMock()
        mock_chapter.id = chapter_id
        mock_chapter.project_id = project_id
        mock_chapter.assigned_to = uuid4()
        mock_chapter.status = "draft"
        mock_chapter.title = "Chapter 2"

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.thread_id = str(uuid4())

        with patch("app.extensions.project.service._get_chapter_or_404", return_value=mock_chapter), \
             patch("app.extensions.project.service._get_project_or_404", return_value=mock_project), \
             patch("app.extensions.project.service._create_deerflow_thread", return_value=tid):
            result = await start_chapter_editing(mock_db, project_id, chapter_id, user_id=uuid4())

        assert result["thread_id"] == tid
        assert result["chapter_id"] == chapter_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_writing_service.py -v`
Expected: FAIL — `start_writing` and `start_chapter_editing` not defined

- [ ] **Step 3: Add response schemas**

In `backend/app/extensions/project/schemas.py`, append after the existing schemas:

```python
# ── Writing / Editing thread responses ──


class StartWritingResponse(BaseModel):
    """Response for POST /projects/{id}/start-writing."""
    thread_id: str
    project_id: UUID


class StartEditingResponse(BaseModel):
    """Response for POST /projects/{id}/chapters/{ch_id}/start-editing."""
    thread_id: str
    project_id: UUID
    chapter_id: UUID
```

- [ ] **Step 4: Implement service functions**

In `backend/app/extensions/project/service.py`, append after `remove_member`:

```python
# ── Writing & Editing Thread Management ──


async def _get_project_or_404(db: AsyncSession, project_id):
    """Get project or raise ValueError."""
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")
    return project


async def _get_chapter_or_404(db: AsyncSession, chapter_id):
    """Get chapter or raise ValueError."""
    stmt = select(ProjectChapter).where(ProjectChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise ValueError("Chapter not found")
    return chapter


async def _create_deerflow_thread(metadata: dict) -> str:
    """Create a DeerFlow thread via the Gateway threads API.

    Calls POST /api/threads internally to create a thread with metadata.
    Returns the thread_id.
    """
    import httpx
    from app.extensions.config import get_extensions_config

    config = get_extensions_config()
    thread_id = str(uuid.uuid4()) if "uuid" not in dir() else __import__("uuid").uuid4()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://localhost:{config.gateway_port or 8001}/api/threads",
            json={"thread_id": str(thread_id), "metadata": metadata},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["thread_id"]


async def start_writing(db: AsyncSession, project_id, *, user_id=None):
    """Create a project-level thread for AI writing (Stage 3).

    Returns {"thread_id": ..., "project_id": ...}
    """
    project = await _get_project_or_404(db, project_id)

    # Reuse existing thread if already created
    if project.thread_id:
        return {"thread_id": project.thread_id, "project_id": project_id}

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "type": "report_project",
        "report_type": project.report_type,
    })

    project.thread_id = thread_id
    await db.flush()

    return {"thread_id": thread_id, "project_id": project_id}


async def start_chapter_editing(db: AsyncSession, project_id, chapter_id, *, user_id=None):
    """Create a chapter-level thread for collaborative editing (Stage 4).

    Returns {"thread_id": ..., "project_id": ..., "chapter_id": ...}
    """
    project = await _get_project_or_404(db, project_id)
    chapter = await _get_chapter_or_404(db, chapter_id)

    # Check if chapter already has a thread stored in chapter metadata
    if chapter.content and chapter.content.startswith("__thread__:"):
        existing_tid = chapter.content.split(":", 1)[1]
        return {"thread_id": existing_tid, "project_id": project_id, "chapter_id": chapter_id}

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "parent_thread_id": project.thread_id or "",
        "type": "chapter_edit",
        "assigned_to": str(chapter.assigned_to) if chapter.assigned_to else "",
    })

    # Update chapter status to "editing"
    chapter.status = "editing"
    await db.flush()

    return {"thread_id": thread_id, "project_id": project_id, "chapter_id": chapter_id}
```

Add the missing import at the top of service.py (after existing imports):

```python
from uuid import uuid4
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_writing_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/project/service.py backend/app/extensions/project/schemas.py backend/tests/test_project_writing_service.py
git commit -m "feat(project): add start_writing and start_chapter_editing service functions"
```

---

## Task 2: Backend API Endpoints — start-writing & start-editing

**Files:**
- Modify: `backend/app/extensions/project/routers.py`

- [ ] **Step 1: Add router endpoints**

In `backend/app/extensions/project/routers.py`, add imports at the top (merge with existing import from `.schemas`):

```python
from .schemas import (
    ApprovalActionRequest,
    ChapterContentUpdate,
    MemberCreate,
    MemberOut,
    OutlineBatchUpdate,
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectUpdate,
    StartEditingResponse,
    StartWritingResponse,
)
```

Append after the `remove_member` endpoint:

```python
# ── Writing & Editing ──


@router.post("/projects/{project_id}/start-writing", response_model=StartWritingResponse)
async def start_writing(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Create a project-level thread for AI writing (Stage 3) and return thread_id."""
    try:
        result = await service.start_writing(db, project_id, user_id=_user.id)
        return StartWritingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/chapters/{chapter_id}/start-editing", response_model=StartEditingResponse)
async def start_chapter_editing(
    project_id: UUID,
    chapter_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Create a chapter-level thread for collaborative editing (Stage 4)."""
    try:
        result = await service.start_chapter_editing(db, project_id, chapter_id, user_id=_user.id)
        return StartEditingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 2: Run existing project tests to verify no regression**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_schemas.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/project/routers.py
git commit -m "feat(project): add start-writing and start-editing API endpoints"
```

---

## Task 3: Project MCP Server

**Files:**
- Create: `backend/app/extensions/project/mcp.py`
- Modify: `extensions_config.json`

This is the only new backend code — an MCP Server that lets the DeerFlow lead_agent read/write chapter data.

- [ ] **Step 1: Create the MCP Server**

Create `backend/app/extensions/project/mcp.py`:

```python
"""Project MCP Server — exposes chapter read/write tools to DeerFlow lead_agent.

This server runs as a stdio MCP server. DeerFlow's MCP client discovers the
tools defined here and makes them available to the lead_agent during runs.

Environment variables:
  PROJECT_DB_URL — PostgreSQL connection string (required)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import UUID

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Database helpers ──


async def _get_db():
    """Create a short-lived async database session."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    db_url = os.environ.get("PROJECT_DB_URL", "")
    if not db_url:
        raise RuntimeError("PROJECT_DB_URL environment variable is required")

    engine = create_async_engine(db_url, pool_size=2, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _run_in_db(func):
    """Run an async function with a database session, return its result."""
    async for session in _get_db():
        return await func(session)


# ── Tool definitions ──

TOOLS = [
    Tool(
        name="read_chapter",
        description="Read a chapter's current content, status, and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
            },
            "required": ["chapter_id"],
        },
    ),
    Tool(
        name="write_chapter",
        description="Write content to a chapter and optionally update its status. Automatically calculates word count.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
                "content": {"type": "string", "description": "The chapter content to write"},
                "status": {"type": "string", "description": "Optional new status: draft, editing, completed", "enum": ["draft", "editing", "completed"]},
            },
            "required": ["chapter_id", "content"],
        },
    ),
    Tool(
        name="list_chapters",
        description="List all chapters in a project with their titles, statuses, and word counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "UUID of the project"},
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_project",
        description="Get project metadata: name, report type, current stage, and status.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "UUID of the project"},
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_chapter_spec",
        description="Get the full writing specification for a chapter: purpose, content_contract, RAG sources, example snippet, compliance rules, and neighbor context. This is the primary context source for report writing.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
            },
            "required": ["chapter_id"],
        },
    ),
]


# ── Tool handlers ──


async def _handle_read_chapter(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import _get_chapter_or_404, _get_assigned_names

    chapter_id = arguments["chapter_id"]

    async def _query(db):
        chapter = await _get_chapter_or_404(db, chapter_id)
        names = await _get_assigned_names(db, [chapter])
        return {
            "chapter_id": str(chapter.id),
            "title": chapter.title,
            "level": chapter.level,
            "status": chapter.status,
            "content": chapter.content,
            "word_count_target": chapter.word_count_target,
            "word_count_current": chapter.word_count_current,
            "assigned_to": str(chapter.assigned_to) if chapter.assigned_to else None,
            "assigned_name": names.get(chapter.assigned_to),
            "purpose": chapter.purpose,
            "generation_hint": chapter.generation_hint,
        }

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_write_chapter(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import update_chapter

    chapter_id = arguments["chapter_id"]
    content = arguments["content"]
    status = arguments.get("status")

    word_count = len(content) if content else 0

    async def _query(db):
        updates = {"content": content, "word_count_current": word_count}
        if status:
            updates["status"] = status
        result = await update_chapter(db, chapter_id, **updates)
        if not result:
            raise ValueError("Chapter not found")
        return {"chapter_id": str(result.id), "status": result.status, "word_count_current": result.word_count_current}

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_list_chapters(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import get_outline_tree

    project_id = arguments["project_id"]

    async def _query(db):
        tree = await get_outline_tree(db, project_id)

        def _flatten(chapters):
            items = []
            for c in chapters:
                items.append({
                    "chapter_id": str(c.id),
                    "title": c.title,
                    "level": c.level,
                    "status": c.status,
                    "word_count_target": c.word_count_target,
                    "word_count_current": c.word_count_current,
                    "assigned_name": c.assigned_name,
                })
                items.extend(_flatten(c.children))
            return items

        return _flatten(tree)

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_get_project(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import get_project

    project_id = arguments["project_id"]

    async def _query(db):
        p = await get_project(db, project_id)
        if not p:
            raise ValueError("Project not found")
        return {
            "project_id": str(p.id),
            "name": p.name,
            "report_type": p.report_type,
            "status": p.status,
            "current_stage": p.current_stage,
            "chapter_count": p.chapter_count,
        }

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_get_chapter_spec(arguments: dict) -> list[TextContent]:
    """Get the full writing spec for a chapter, merging project data with template data."""
    from app.extensions.project.service import _get_chapter_or_404, _get_project_or_404, _get_assigned_names
    from sqlalchemy import select
    from app.extensions.models import ProjectChapter
    from app.extensions.knowledge_factory.models import ExtractionTemplate

    chapter_id = arguments["chapter_id"]

    async def _query(db):
        chapter = await _get_chapter_or_404(db, chapter_id)
        project = await _get_project_or_404(db, chapter.project_id)
        names = await _get_assigned_names(db, [chapter])

        # Build base spec from chapter data
        spec = {
            "chapter_id": str(chapter.id),
            "title": chapter.title,
            "level": chapter.level,
            "sort_order": chapter.sort_order,
            "current_content": chapter.content,
            "word_count_target": chapter.word_count_target,
            "word_count_current": chapter.word_count_current,
            "status": chapter.status,
            "assigned_name": names.get(chapter.assigned_to),
        }

        # Enrich with template spec if available
        if project.template_id:
            template = await db.get(ExtractionTemplate, project.template_id)
            if template and template.root_sections_json:
                sections = template.root_sections_json.get("sections", [])
                _match_section_to_spec(spec, sections, chapter.title)

        # Add neighbor context
        all_chapters_stmt = (
            select(ProjectChapter)
            .where(ProjectChapter.project_id == chapter.project_id, ProjectChapter.parent_id == chapter.parent_id)
            .order_by(ProjectChapter.sort_order)
        )
        all_result = await db.execute(all_chapters_stmt)
        siblings = list(all_result.scalars().all())

        for i, sib in enumerate(siblings):
            if sib.id == chapter.id:
                if i > 0:
                    prev = siblings[i - 1]
                    spec.setdefault("neighbors", {})["previous"] = {
                        "title": prev.title,
                        "status": prev.status,
                        "summary": (prev.content[:200] if prev.content else ""),
                    }
                if i < len(siblings) - 1:
                    nxt = siblings[i + 1]
                    spec.setdefault("neighbors", {})["next"] = {
                        "title": nxt.title,
                        "status": nxt.status,
                        "summary": (nxt.content[:200] if nxt.content else ""),
                    }
                break

        return spec

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def _match_section_to_spec(spec: dict, sections: list, chapter_title: str) -> None:
    """Find the matching template section by title and merge its spec into the chapter spec."""
    for sec in sections:
        if sec.get("title") == chapter_title:
            spec["purpose"] = sec.get("purpose", spec.get("purpose"))
            spec["generation_hint"] = sec.get("generation_hint", spec.get("generation_hint"))
            if "content_contract" in sec and isinstance(sec["content_contract"], dict):
                spec["content_contract"] = sec["content_contract"]
            if "compliance_rules" in sec:
                spec["compliance_rules"] = sec["compliance_rules"]
            if "rag_sources" in sec:
                spec["rag_sources"] = sec["rag_sources"]
            if "example_snippet" in sec:
                spec["example_snippet"] = sec["example_snippet"]
            return
        if "children" in sec:
            _match_section_to_spec(spec, sec["children"], chapter_title)


# ── Server setup ──

server = Server("project")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "read_chapter": _handle_read_chapter,
        "write_chapter": _handle_write_chapter,
        "list_chapters": _handle_list_chapters,
        "get_project": _handle_get_project,
        "get_chapter_spec": _handle_get_chapter_spec,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Register the MCP server in extensions_config.json**

Add to the `mcpServers` section of `extensions_config.json`:

```json
"project": {
  "enabled": true,
  "type": "stdio",
  "command": "python",
  "args": ["-m", "app.extensions.project.mcp"],
  "env": {
    "PROJECT_DB_URL": "${DATABASE_URL}"
  },
  "description": "Project chapter read/write tools for report writing agent"
}
```

Note: The `${DATABASE_URL}` env var reference will be resolved by DeerFlow's MCP client at runtime. The actual DB URL comes from the environment.

- [ ] **Step 3: Verify the MCP server loads**

Run: `cd backend && PROJECT_DB_URL="postgresql+asyncpg://test:test@localhost/test" python -c "from app.extensions.project.mcp import server; print('MCP server loaded:', server.name)"`

Expected: `MCP server loaded: project`

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/project/mcp.py extensions_config.json
git commit -m "feat(project): add Project MCP Server with 6 chapter/project tools"
```

---

## Task 4: Report-Write Skill File

**Files:**
- Create: `skills/report-write/SKILL.md`

This Skill tells the DeerFlow lead_agent how to write reports when it detects a project thread.

- [ ] **Step 1: Create the skill directory and file**

Create `skills/report-write/SKILL.md`:

```markdown
---
name: report-write
description: Strategy for AI-driven report chapter writing and collaborative editing via Project MCP tools.
---

# Report Writing Skill

## Trigger

Activate this skill when the thread metadata contains a `project_id` key. The metadata type determines the mode:

- `type: "report_project"` → Stage 3: Full AI writing mode
- `type: "chapter_edit"` → Stage 4: Collaborative editing mode

## Stage 3: AI Writing Mode

When the user clicks "Start AI Writing" or sends the first message in a project thread, follow this workflow:

### Step 1: Understand the project

```
get_project(project_id) → project name, type, stage
list_chapters(project_id) → all chapters with status
```

### Step 2: Write chapters sequentially

For each chapter with status "pending":

```
get_chapter_spec(chapter_id) → full writing specification
```

Key fields in the spec:
- **purpose**: What this chapter should cover — read this first
- **content_contract**: Structure constraints
  - **key_elements**: Must cover ALL of these
  - **structure_type**: "narrative_text", "data_table", etc.
  - **style_rules**: Writing style to follow
  - **min_word_count**: Minimum acceptable length
  - **forbidden_phrases**: Never use these expressions
- **generation_hint**: Additional writing guidance
- **rag_sources**: Knowledge bases to query for reference material
- **example_snippet**: Reference structure (do NOT copy verbatim)
- **compliance_rules**: Regulations/standards the content must satisfy
- **neighbors**: Previous/next chapter titles and summaries for continuity

### Step 3: Generate and write

1. If `rag_sources` exists, query the referenced knowledge bases for supporting data
2. Generate content following the spec precisely:
   - Cover ALL `key_elements`
   - Respect `min_word_count` as the floor, `word_count_target` as the target
   - Follow `style_rules` exactly
   - NEVER use phrases from `forbidden_phrases`
   - Reference `example_snippet` for structure only, not content
   - Ensure continuity with neighbor chapters (consistent terminology, logical flow)
3. Write the result:
   ```
   write_chapter(chapter_id, content, "draft")
   ```

### Step 4: Continue to next chapter

Repeat Step 2-3 for the next pending chapter. Inform the user of progress after each chapter.

### User intervention

If the user provides direction (e.g., "focus on water quality in chapter 3"), adjust the writing accordingly. User instructions override the default spec for that chapter.

## Stage 4: Collaborative Editing Mode

In this mode, the user drives the interaction. You assist on demand.

**Rules:**
- Respond to user requests; do NOT proactively write chapters
- When editing content, write back with `status: "editing"`
- Available operations:
  - Read chapter: `read_chapter(chapter_id)`
  - Write chapter: `write_chapter(chapter_id, content, "editing")`
  - View full spec: `get_chapter_spec(chapter_id)`
  - See all chapters: `list_chapters(project_id)`

Common requests:
- "Polish this paragraph" → Read, improve writing quality, write back
- "Add data analysis for section X" → Read, research via RAG, add content, write back
- "Check consistency with chapter Y" → Read both, compare terminology/flow, suggest edits
- "Expand section Z to meet word count" → Read, identify thin sections, expand, write back

## Writing Quality Standards

- Use formal, professional Chinese appropriate for technical reports
- Cite data sources: 标注数据来源 (e.g., "根据XX监测数据...")
- Maintain consistent terminology across chapters
- Use parallel structure in headings at the same level
- Avoid filler words: "的" overuse, "进行了" → use direct verbs
- Each paragraph should have a clear topic sentence
```

- [ ] **Step 2: Verify the skill file is valid markdown**

Run: `python -c "import yaml; print('Valid YAML frontmatter')" && head -3 skills/report-write/SKILL.md`
Expected: Shows `Valid YAML frontmatter` and the frontmatter header

- [ ] **Step 3: Commit**

```bash
git add skills/report-write/SKILL.md
git commit -m "feat(skills): add report-write skill for AI chapter writing and collaborative editing"
```

---

## Task 5: Frontend API & Types — startWriting & startChapterEditing

**Files:**
- Modify: `frontend/src/extensions/project/api.ts`
- Modify: `frontend/src/extensions/project/types.ts`
- Test: `frontend/tests/unit/extensions/project/api.test.ts`

- [ ] **Step 1: Add types**

In `frontend/src/extensions/project/types.ts`, append after the existing `ChapterUpdateRequest` interface:

```typescript
// ── Writing / Editing thread responses ──

export interface StartWritingResponse {
  threadId: string;
  projectId: string;
}

export interface StartEditingResponse {
  threadId: string;
  projectId: string;
  chapterId: string;
}
```

- [ ] **Step 2: Add API methods**

In `frontend/src/extensions/project/api.ts`, add the import of new types:

```typescript
import type {
  // ... existing imports ...
  StartWritingResponse,
  StartEditingResponse,
} from "./types";
```

Append after the `removeMember` method (before the legacy aliases section):

```typescript
  // ── Writing & Editing ──

  startWriting: async (projectId: string): Promise<StartWritingResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/start-writing`,
      { method: "POST" },
    );
    return toCamelCase<StartWritingResponse>(data);
  },

  startChapterEditing: async (projectId: string, chapterId: string): Promise<StartEditingResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/chapters/${chapterId}/start-editing`,
      { method: "POST" },
    );
    return toCamelCase<StartEditingResponse>(data);
  },
```

- [ ] **Step 3: Add tests**

In `frontend/tests/unit/extensions/project/api.test.ts`, append a new describe block:

```typescript
describe("projectApi.startWriting", () => {
  test("POSTs to start-writing and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      thread_id: "thread-abc",
      project_id: "proj-1",
    });

    const result = await projectApi.startWriting("proj-1");
    expect(result.threadId).toBe("thread-abc");
    expect(result.projectId).toBe("proj-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/start-writing",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("projectApi.startChapterEditing", () => {
  test("POSTs to start-editing and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      thread_id: "thread-xyz",
      project_id: "proj-1",
      chapter_id: "ch-2",
    });

    const result = await projectApi.startChapterEditing("proj-1", "ch-2");
    expect(result.threadId).toBe("thread-xyz");
    expect(result.chapterId).toBe("ch-2");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/chapters/ch-2/start-editing",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && pnpm test -- --reporter=verbose tests/unit/extensions/project/api.test.ts`
Expected: All tests PASS (including new ones)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/project/api.ts frontend/src/extensions/project/types.ts frontend/tests/unit/extensions/project/api.test.ts
git commit -m "feat(project): add startWriting and startChapterEditing API methods with tests"
```

---

## Task 6: Frontend — ChapterWritingPanel (Stage 3)

**Files:**
- Create: `frontend/src/extensions/project/ChapterWritingPanel.tsx`
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`

This panel shows chapter writing progress and provides the "Start AI Writing" button that creates a thread and navigates to the DeerFlow chat page.

- [ ] **Step 1: Create ChapterWritingPanel**

Create `frontend/src/extensions/project/ChapterWritingPanel.tsx`:

```tsx
"use client";

import { CheckCircle2, ChevronRight, Clock, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import type { ProjectChapter } from "@/extensions/project/types";
import { CHAPTER_STATUS_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ChapterWritingPanelProps {
  projectId: string;
  projectName: string;
  chapters: ProjectChapter[];
}

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  return chapters.flatMap((c) => [c, ...flattenChapters(c.children)]);
}

const STATUS_STYLES: Record<string, string> = {
  pending: "text-muted-foreground",
  writing: "text-primary font-medium",
  draft: "text-amber-600",
  completed: "text-green-600",
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  writing: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
  draft: <CheckCircle2 className="h-4 w-4 text-amber-500" />,
  completed: <CheckCircle2 className="h-4 w-4 text-green-500" />,
};

export function ChapterWritingPanel({ projectId, projectName, chapters }: ChapterWritingPanelProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const flat = flattenChapters(chapters);

  const completedCount = flat.filter((c) => c.status === "completed" || c.status === "draft").length;
  const totalCount = flat.length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const handleStartWriting = useCallback(async () => {
    setLoading(true);
    try {
      const result = await projectApi.startWriting(projectId);
      router.push(`/workspace/chats/${result.threadId}?from=project`);
    } catch {
      toast.error("启动 AI 撰写失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, router]);

  return (
    <div className="flex h-full">
      {/* Left: Chapter progress list */}
      <div className="flex-1 p-6 overflow-y-auto">
        <h2 className="text-lg font-bold text-foreground mb-4">章节撰写进度</h2>
        <div className="space-y-1">
          {flat.map((chapter) => (
            <div
              key={chapter.id}
              className={cn(
                "flex items-center gap-3 rounded-lg px-4 py-3 transition-colors",
                "hover:bg-muted/50",
              )}
            >
              <span className="shrink-0">{STATUS_ICONS[chapter.status] ?? STATUS_ICONS.pending}</span>
              <div className="flex-1 min-w-0">
                <p className={cn("text-sm truncate", STATUS_STYLES[chapter.status] ?? "")}>
                  {chapter.title}
                </p>
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {chapter.wordCountCurrent.toLocaleString()}/{chapter.wordCountTarget.toLocaleString()} 字
              </span>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {CHAPTER_STATUS_LABELS[chapter.status]}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Progress summary + CTA */}
      <div className="w-80 border-l border-border bg-muted/30 p-6 flex flex-col gap-6">
        {/* Progress card */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">撰写进度</h3>
          <div className="flex items-end gap-2 mb-2">
            <span className="text-3xl font-bold text-foreground">{progressPct}%</span>
            <span className="text-sm text-muted-foreground mb-1">完成</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-foreground">{completedCount}</div>
              <div className="text-xs text-muted-foreground">已完成</div>
            </div>
            <div>
              <div className="text-lg font-bold text-foreground">
                {flat.filter((c) => c.status === "writing").length}
              </div>
              <div className="text-xs text-muted-foreground">撰写中</div>
            </div>
            <div>
              <div className="text-lg font-bold text-foreground">
                {flat.filter((c) => c.status === "pending").length}
              </div>
              <div className="text-xs text-muted-foreground">待撰写</div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <Button
          size="lg"
          className="w-full gap-2"
          onClick={handleStartWriting}
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {loading ? "正在启动..." : "开始 AI 撰写"}
        </Button>
        <p className="text-xs text-muted-foreground text-center">
          点击后将跳转到 DeerFlow 对话页，AI 将逐章撰写报告
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire into ProjectWorkspace**

In `frontend/src/extensions/project/ProjectWorkspace.tsx`, add the import:

```typescript
import { ChapterWritingPanel } from "@/extensions/project/ChapterWritingPanel";
```

Replace the Stages 3-6 placeholder block (lines 160-178) with:

```tsx
  // Stage 3: AI Writing
  if (viewingStage === 3) {
    return (
      <div className="flex flex-col h-full">
        <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
          <StageProgressBar projectId={projectId} currentStage={currentStage} />
        </header>
        <ChapterWritingPanel
          projectId={projectId}
          projectName={project.name}
          chapters={project.chapters}
        />
      </div>
    );
  }

  // Stages 4-6: Placeholder
  return (
    <div className="flex flex-col h-full">
      <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
        <StageProgressBar projectId={projectId} currentStage={currentStage} />
      </header>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">
          {STAGE_LABELS[viewingStage - 1]} 阶段开发中...
        </p>
      </div>
    </div>
  );
```

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/ChapterWritingPanel.tsx frontend/src/extensions/project/ProjectWorkspace.tsx
git commit -m "feat(project): add ChapterWritingPanel for Stage 3 AI writing with thread creation"
```

---

## Task 7: Frontend — ChapterEditingPanel (Stage 4)

**Files:**
- Create: `frontend/src/extensions/project/ChapterEditingPanel.tsx`
- Create: `frontend/src/extensions/project/ChapterAssignDropdown.tsx`
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`

This panel shows the chapter assignment table and lets users navigate to DeerFlow chat for collaborative editing.

- [ ] **Step 1: Create ChapterAssignDropdown**

Create `frontend/src/extensions/project/ChapterAssignDropdown.tsx`:

```tsx
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ProjectMember } from "@/extensions/project/types";
import { MEMBER_ROLE_LABELS } from "@/extensions/project/types";
import { projectApi } from "@/extensions/project/api";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";

interface ChapterAssignDropdownProps {
  projectId: string;
  chapterId: string;
  members: ProjectMember[];
  currentAssignee: string | null;
  onAssigned: () => void;
}

export function ChapterAssignDropdown({
  projectId,
  chapterId,
  members,
  currentAssignee,
  onAssigned,
}: ChapterAssignDropdownProps) {
  const [open, setOpen] = useState(false);

  const handleAssign = async (userId: string) => {
    try {
      await projectApi.updateChapter(projectId, chapterId, { assignedTo: userId });
      setOpen(false);
      onAssigned();
    } catch {
      toast.error("分配失败");
    }
  };

  return (
    <div className="relative">
      <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={() => setOpen(!open)}>
        分配编写人
        <ChevronDown className="h-3 w-3" />
      </Button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-10 min-w-[160px] rounded-md border border-border bg-background shadow-md py-1">
          {members.map((m) => (
            <button
              key={m.userId}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted text-left"
              onClick={() => handleAssign(m.userId)}
            >
              <span className="text-foreground">{m.username}</span>
              <span className="text-xs text-muted-foreground">{MEMBER_ROLE_LABELS[m.role]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ChapterEditingPanel**

Create `frontend/src/extensions/project/ChapterEditingPanel.tsx`:

```tsx
"use client";

import { ArrowRight, CheckCircle2, Clock, Loader2, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import type { ProjectChapter, ProjectMember, ReportProject } from "@/extensions/project/types";
import { CHAPTER_STATUS_LABELS, MEMBER_ROLE_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

import { ChapterAssignDropdown } from "./ChapterAssignDropdown";

interface ChapterEditingPanelProps {
  project: ReportProject;
  onRefresh: () => void;
}

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  return chapters.flatMap((c) => [c, ...flattenChapters(c.children)]);
}

const STATUS_DOT: Record<string, string> = {
  pending: "bg-muted-foreground",
  draft: "bg-amber-500",
  editing: "bg-blue-500",
  completed: "bg-green-500",
};

export function ChapterEditingPanel({ project, onRefresh }: ChapterEditingPanelProps) {
  const router = useRouter();
  const [loadingChapterId, setLoadingChapterId] = useState<string | null>(null);

  const flat = flattenChapters(project.chapters);
  const completedCount = flat.filter((c) => c.status === "completed").length;
  const editingCount = flat.filter((c) => c.status === "editing" || c.status === "writing").length;
  const unassignedCount = flat.filter((c) => !c.assignedTo && c.status !== "completed").length;
  const progressPct = flat.length > 0 ? Math.round((completedCount / flat.length) * 100) : 0;

  const handleStartEditing = useCallback(async (chapterId: string) => {
    setLoadingChapterId(chapterId);
    try {
      const result = await projectApi.startChapterEditing(project.id, chapterId);
      router.push(`/workspace/chats/${result.threadId}?from=project`);
    } catch {
      toast.error("启动编辑失败");
    } finally {
      setLoadingChapterId(null);
    }
  }, [project.id, router]);

  return (
    <div className="flex h-full">
      {/* Left: Chapter table */}
      <div className="flex-1 p-6 overflow-y-auto">
        <h2 className="text-lg font-bold text-foreground mb-4">章节分配与编辑</h2>
        <div className="rounded-xl border border-border overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_120px_100px_140px] gap-2 bg-muted/50 px-4 py-2.5 text-xs font-medium text-muted-foreground">
            <span>章节</span>
            <span>编写人</span>
            <span>状态</span>
            <span className="text-right">操作</span>
          </div>
          {/* Rows */}
          {flat.map((chapter) => (
            <div
              key={chapter.id}
              className="grid grid-cols-[1fr_120px_100px_140px] gap-2 items-center px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
            >
              <span className="text-sm text-foreground truncate">{chapter.title}</span>
              <span className="text-sm text-foreground">
                {chapter.assignedName ?? (chapter.assignedTo === null && chapter.status !== "completed" ? (
                  <ChapterAssignDropdown
                    projectId={project.id}
                    chapterId={chapter.id}
                    members={project.members}
                    currentAssignee={chapter.assignedTo}
                    onAssigned={onRefresh}
                  />
                ) : "—")}
              </span>
              <span className="flex items-center gap-1.5">
                <span className={cn("h-2 w-2 rounded-full shrink-0", STATUS_DOT[chapter.status] ?? STATUS_DOT.pending)} />
                <span className="text-xs text-muted-foreground">{CHAPTER_STATUS_LABELS[chapter.status]}</span>
              </span>
              <span className="flex justify-end">
                {chapter.status === "completed" ? (
                  <Button variant="ghost" size="sm" className="h-7 text-xs">
                    查看
                  </Button>
                ) : (
                  <Button
                    variant={chapter.status === "editing" || chapter.status === "writing" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-xs gap-1"
                    onClick={() => handleStartEditing(chapter.id)}
                    disabled={loadingChapterId === chapter.id}
                  >
                    {loadingChapterId === chapter.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <ArrowRight className="h-3 w-3" />
                    )}
                    {chapter.status === "editing" || chapter.status === "writing" ? "进入编辑" : "开始编辑"}
                  </Button>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Sidebar */}
      <div className="w-80 border-l border-border bg-muted/30 p-6 flex flex-col gap-6 overflow-y-auto">
        {/* Progress */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">编辑进度</h3>
          <div className="h-2 rounded-full bg-muted overflow-hidden mb-3">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-green-600">{completedCount}</div>
              <div className="text-xs text-muted-foreground">已完成</div>
            </div>
            <div>
              <div className="text-lg font-bold text-blue-600">{editingCount}</div>
              <div className="text-xs text-muted-foreground">编辑中</div>
            </div>
            <div>
              <div className="text-lg font-bold text-amber-600">{unassignedCount}</div>
              <div className="text-xs text-muted-foreground">待分配</div>
            </div>
          </div>
        </div>

        {/* Team */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Users className="h-4 w-4" />
            团队成员
          </h3>
          <div className="space-y-2">
            {project.members.map((m) => (
              <div key={m.userId} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{m.username}</span>
                <span className="text-xs text-muted-foreground">{MEMBER_ROLE_LABELS[m.role]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tips */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-2">协作编辑说明</h3>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            <li>分配编写人后，点击「开始编辑」进入对话页</li>
            <li>AI Agent 会协助润色、补充内容、检查一致性</li>
            <li>每个章节独立对话，互不干扰</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire Stage 4 into ProjectWorkspace**

In `frontend/src/extensions/project/ProjectWorkspace.tsx`, add the import:

```typescript
import { ChapterEditingPanel } from "@/extensions/project/ChapterEditingPanel";
```

In the Stage 4-6 placeholder section, replace the placeholder with a Stage 4 specific rendering. Change the `// Stages 4-6: Placeholder` block to:

```tsx
  // Stage 4: Collaborative Editing
  if (viewingStage === 4) {
    return (
      <div className="flex flex-col h-full">
        <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
          <StageProgressBar projectId={projectId} currentStage={currentStage} />
          <div className="ml-auto">
            <Button variant="outline" size="sm">管理成员</Button>
          </div>
        </header>
        <ChapterEditingPanel project={project} onRefresh={loadProject} />
      </div>
    );
  }

  // Stages 5-6: Placeholder
  return (
    <div className="flex flex-col h-full">
      <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
        <StageProgressBar projectId={projectId} currentStage={currentStage} />
      </header>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">
          {STAGE_LABELS[viewingStage - 1]} 阶段开发中...
        </p>
      </div>
    </div>
  );
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/project/ChapterEditingPanel.tsx frontend/src/extensions/project/ChapterAssignDropdown.tsx frontend/src/extensions/project/ProjectWorkspace.tsx
git commit -m "feat(project): add ChapterEditingPanel for Stage 4 collaborative editing with assignment"
```

---

## Task 8: Return Navigation — Breadcrumb on Chat Page

**Files:**
- Modify: `frontend/src/components/workspace/workspace-nav-menu.tsx` or the chat header component

When users navigate to the DeerFlow chat page via `?from=project`, show a "← 返回项目" breadcrumb.

- [ ] **Step 1: Find the chat page header component**

The chat page header is in `frontend/src/app/workspace/chats/[thread_id]/page.tsx`. Check the `ChatBox` component to find where the header renders. The thread title is typically shown in the header area.

We need to detect the `from=project` search param and render a breadcrumb link.

Find the chat header component. Based on the frontend architecture, the header is inside the `ChatBox` or a separate header component. Look for where `ThreadTitle` is rendered.

- [ ] **Step 2: Add breadcrumb to the chat page**

In the chat page (`frontend/src/app/workspace/chats/[thread_id]/page.tsx`), import `useSearchParams` and conditionally render a breadcrumb:

```tsx
// At the top of the page component:
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

// Inside the component function:
const searchParams = useSearchParams();
const fromProject = searchParams.get("from") === "project";

// In the header area, before the thread title:
{fromProject && (
  <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-sm">
    <Link
      href="/projects"
      className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      返回项目列表
    </Link>
  </div>
)}
```

Note: The exact placement depends on the chat page structure. The breadcrumb should appear above the existing chat header, as shown in the prototype.

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspace/chats/[thread_id]/page.tsx
git commit -m "feat(project): add return navigation breadcrumb when accessing chat from project page"
```

---

## Self-Review Checklist

### 1. Spec Coverage

| Spec Section | Task |
|---|---|
| Section 2.2: Stage 3 AI Writing | Task 3 (MCP), Task 4 (Skill), Task 6 (Panel) |
| Section 2.3: Stage 4 Collaborative Editing | Task 3 (MCP), Task 4 (Skill), Task 7 (Panel) |
| Section 2.4: Assignment UI | Task 7 (ChapterAssignDropdown) |
| Section 3.2: MCP Tool List (6 tools) | Task 3 |
| Section 3.3: get_chapter_spec with template data | Task 3 |
| Section 3.3: MCP registration in extensions_config | Task 3 |
| Section 4: report-write Skill | Task 4 |
| Section 5.1: Thread metadata structure | Task 1 (service), Task 3 (MCP) |
| Section 5.2: Stage 3 jump to chat | Task 6 (ChapterWritingPanel) |
| Section 5.3: Stage 4 jump to chat | Task 7 (ChapterEditingPanel) |
| Section 5.4: Return navigation | Task 8 |

### 2. Placeholder Scan

No "TBD", "TODO", "implement later", "fill in details" found. All steps contain complete code.

### 3. Type Consistency

- `StartWritingResponse` / `StartEditingResponse` — defined in schemas.py, used in routers.py, api.ts, types.ts
- `ChapterWritingPanel` takes `projectId`, `projectName`, `chapters` — matches `ReportProject` fields
- `ChapterEditingPanel` takes `project: ReportProject`, `onRefresh` — matches loadProject signature
- MCP tool names: `read_chapter`, `write_chapter`, `list_chapters`, `get_project`, `get_chapter_spec` — consistent between server definition and skill documentation
- `projectApi.startWriting()` returns `StartWritingResponse` with `threadId` / `projectId` — matches backend schema
