# page login info
email: admin@eai-flow.com
password: Admin@2026

# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DeerFlow** (Deep Exploration and Efficient Research Flow) is an AI super agent harness that orchestrates sub-agents, memory, and sandboxes for complex tasks via extensible skills. It is a full-stack application with:

- **Backend**: Python 3.12+ — LangGraph + FastAPI gateway, sandbox execution, memory, MCP integration
- **Frontend**: TypeScript — Next.js 16, React 19, Tailwind CSS 4
- **Infrastructure**: Docker, nginx reverse proxy (unified entry point on port 2026)

## Commands

### Quick Start (from project root)

```bash
make check        # Verify prerequisites (Node.js 22+, pnpm, uv, nginx)
make install      # Install all deps (backend + frontend + pre-commit hooks)
make dev          # Start all services with hot-reload (localhost:2026)
make stop         # Stop all services
make config       # First-time config setup (aborts if config.yaml exists)
```

### Backend (from `backend/`)

```bash
make install      # uv sync
make dev          # Gateway API with reload (port 8001)
make test         # PYTHONPATH=. uv run pytest tests/ -v
make lint         # ruff check . + ruff format --check .
make format       # ruff check --fix + ruff format

# Run a single test file
PYTHONPATH=. uv run pytest tests/test_<feature>.py -v
```

### Frontend (from `frontend/`)

```bash
pnpm install      # Install deps
pnpm dev          # Dev server with Turbopack (port 4000)
pnpm build        # Production build (requires BETTER_AUTH_SECRET)
pnpm test         # Vitest unit tests
pnpm test:e2e     # Playwright E2E tests
pnpm lint         # ESLint
pnpm typecheck    # tsc --noEmit
pnpm format:write # Prettier auto-fix

# Frontend build requires env var for production validation:
BETTER_AUTH_SECRET=local-dev-secret pnpm build
```

### Docker

```bash
make docker-init    # Build images + install deps (first time)
make docker-start   # Start dev services with hot-reload (localhost:2026)
make docker-stop    # Stop Docker services
make docker-logs    # View logs
```

## Architecture

### Runtime Topology

```
Browser -> Nginx (port 2026)
  |-> /api/langgraph/* -> Gateway embedded LangGraph runtime (port 8001), rewritten to /api/*
  |-> /api/*           -> Gateway FastAPI (port 8001)
  |-> /*               -> Next.js frontend (port 4000)
```

The agent runtime runs embedded in Gateway via `RunManager` + `run_agent()` + `StreamBridge`. Nginx exposes it at `/api/langgraph/*` and rewrites to Gateway's native `/api/*` routers.

### Backend: Harness / App Split

The backend has two layers with a **strict dependency direction**:

- **Harness** (`backend/packages/harness/deerflow/`): Publishable agent framework package (`deerflow-harness`). Import prefix: `deerflow.*`. Contains agent orchestration, tools, sandbox, models, MCP, skills, config.
- **App** (`backend/app/`): Application layer. Import prefix: `app.*`. Contains FastAPI Gateway and IM channel integrations.

**Dependency rule**: `app` imports `deerflow`, but `deerflow` **never** imports `app`. Enforced by `tests/test_harness_boundary.py` in CI.

### Agent System

- **Lead Agent** (`deerflow/agents/lead_agent/agent.py`): Entry point registered in `langgraph.json`. Dynamic model selection, tool loading, system prompt generation.
- **ThreadState**: Extends `AgentState` with sandbox, thread_data, title, artifacts, todos, uploaded_files, viewed_images.
- **Middleware Chain**: 17+ middlewares in strict order — ThreadData, Uploads, Sandbox, ErrorHandling, Guardrails, ToolError, Summarization, TodoList, TokenUsage, Title, Memory, ViewImage, SubagentLimit, LoopDetection, Clarification.
- **Subagents**: Dual thread pool (3 scheduler + 3 execution workers). Built-in: `general-purpose`, `bash`. Flow: `task()` tool -> `SubagentExecutor` -> background thread -> SSE events.

### Gateway API (`backend/app/gateway/`)

FastAPI app on port 8001. Key routers: `models`, `mcp`, `memory`, `skills`, `uploads`, `threads`, `runs`, `thread_runs`, `agents`, `suggestions`, `feedback`, `channels`, `auth`.

**Auth**: Cookie-based JWT (not Bearer tokens) with CSRF Double Submit Cookie. Fail-closed middleware — every non-public request requires a valid JWT. Contextvar-based user propagation for repository-layer owner filtering.

**Run lifecycle**: `start_run()` -> `RunRecord` via `RunManager` -> `run_agent()` as `asyncio.Task` -> `StreamBridge` -> `sse_consumer()` yields SSE frames matching LangGraph Platform protocol (compatible with `useStream` React hook).

### Frontend Architecture

- **Server state**: TanStack Query for all backend data (threads, models, agents, skills, memory, MCP)
- **Streaming**: `@langchain/langgraph-sdk/react` `useStream()` hook for real-time chat
- **Settings**: localStorage + `useSyncExternalStore` for user preferences
- **Components**: `ui/` (Shadcn, auto-generated), `ai-elements/` (Vercel AI SDK, auto-generated), `workspace/` (hand-written domain components)
- **Dual auth**: Core cookie-based auth for workspace, extensions JWT auth for admin/knowledge features

### Configuration

- **`config.yaml`** (project root): Models, tools, sandbox, memory, title generation, summarization, subagents. Config values starting with `$` resolve as env vars. Auto-reloads on file change.
- **`extensions_config.json`** (project root): MCP servers and skills. Hot-reloadable via Gateway API.
- **`backend/ruff.toml`**: Line length 240, Python 3.12, rules E/F/I/UP.

## Key Design Decisions

1. **Harness/App boundary** — publishable framework vs application code, enforced by tests
2. **Cookie-based auth with CSRF** — designed for browser clients, not Bearer tokens
3. **LangGraph Platform compatibility** — SSE wire format and REST API match LangGraph Platform so `useStream` React hook works without modification
4. **Per-user data isolation** — memory, threads, agents scoped to `user_id` via filesystem paths and metadata
5. **Config-driven** — `config.yaml` for core config, `extensions_config.json` for extensions, both hot-reloadable
6. **Sandbox virtual paths** — Agent sees `/mnt/user-data/`, physical paths are per-user per-thread directories

## CI/CD

PRs trigger four GitHub Actions workflows:
- **Backend unit tests**: Python 3.12, `uv sync --group dev`, `make test`
- **Frontend unit tests**: Node 22, pnpm 10.26.2, `make test`
- **E2E tests**: Playwright Chromium (only when `frontend/` files change)
- **Lint check**: Backend `make lint` + Frontend `pnpm format` + `pnpm lint` + `pnpm typecheck` + `pnpm build`

## Pre-commit Validation

Before submitting changes:

```bash
# Backend changes
cd backend && make lint && make test

# Frontend changes
cd frontend && pnpm lint && pnpm typecheck

# If touching env/auth/routing/build-sensitive files
cd frontend && BETTER_AUTH_SECRET=... pnpm build
```

## Detailed Documentation

- **Backend architecture/commands**: `backend/CLAUDE.md`
- **Frontend architecture/commands**: `frontend/CLAUDE.md`
- **Configuration**: `backend/docs/CONFIGURATION.md`
- **API reference**: `backend/docs/API.md`
- **Architecture deep-dive**: `backend/docs/ARCHITECTURE.md`
- **MCP setup**: `backend/docs/MCP_SERVER.md`
- **Streaming design**: `backend/docs/STREAMING.md`

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
