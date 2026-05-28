# Report Platform Workflow Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the project management module from a static 5-tab layout to a workflow-driven, AI-first staged UI that integrates with DeerFlow's agent system for automated report writing.

**Architecture:** Six-stage workflow (Project Setup → Outline Confirmation → AI Writing → Collaborative Editing → Approval → Final Output). Each stage has clear completion criteria and a progress indicator. The project module acts as a coordination layer; actual AI writing happens through DeerFlow's existing agent conversation system via split-screen layout.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Shadcn UI, Tiptap editor, DeerFlow agent SDK (useStream hook), Knowledge Factory template API.

---

## Context

The current project management module has 5 tabs (Overview, Kanban, Outline, Members, Approval) designed for human-driven report writing with AI assistance. The new design reflects a fundamentally different paradigm: **AI writes reports, humans direct and collaborate**. Users primarily give instructions to DeerFlow agents to execute writing tasks. After AI produces initial drafts, multiple humans collaborate to edit, supplement, confirm, and refine.

The project module integrates with two existing systems:
1. **DeerFlow Agent System** — for AI writing via conversation threads (reuse `useStream` hook and workspace chat components)
2. **Knowledge Factory (KF) Templates** — for report outline structures with content contracts, compliance rules, and RAG sources

## Design Principles

1. **AI-first writing**: DeerFlow agents write reports; humans direct, not write from scratch
2. **Coordination layer**: Project module manages structure, assignment, progress, and approval; actual content creation happens through DeerFlow conversations
3. **Workflow-driven**: Users progress through clear stages with visible completion criteria
4. **Split-screen collaboration**: Chapter management panel + content editing/AI conversation panel side by side
5. **Template-optional**: KF templates are recommended but not required; AI can generate outlines from report type + skills

## Stage 1: Project Setup

**Purpose:** Define the report's identity and optionally reference a template.

**Fields:**
- Project name (required)
- Report type (required, dropdown sourced from KF domain/report_type taxonomy)
- Report template (optional, select from KF published templates)

**Behavior:**
- Creating a project saves the record and immediately enters Stage 2
- No "client", "target standard", or "AI requirements" fields — those are handled through DeerFlow conversations in Stage 3

**UI:** Simple form, similar to current create dialog but with template selector connected to KF API (`GET /api/kf/templates`).

## Stage 2: Outline Confirmation

**Purpose:** Define the report's chapter structure before AI writing begins.

**Flow:**
1. If a KF template was selected in Stage 1 → import chapter structure from template's `root_sections_json`
2. If no template → invoke DeerFlow agent to generate outline using report-type-specific skills
3. User edits the outline:
   - Drag-and-drop reorder chapters
   - Add / delete / rename chapters
   - Adjust hierarchy (indent / unindent)
4. User clicks "Confirm Outline" → saves outline, creates empty chapter records (status: `pending`)

**UI:** Left panel: editable outline tree with drag handles. Right panel: read-only preview of final report structure.

**Data:** Each chapter becomes a `ChapterRecord` with fields: `id`, `projectId`, `title`, `level`, `parentId`, `order`, `status` (pending), `assignedTo` (null), `content` (null).

**Integration:** Outline generation without template uses DeerFlow's existing agent system. The project module sends a structured prompt to a new thread requesting outline generation for the given report type.

## Stage 3: AI Writing

**Purpose:** DeerFlow agent generates initial drafts for all chapters in one pass.

**Flow:**
1. User clicks "Start AI Writing"
2. System creates a DeerFlow conversation thread linked to this project
3. System sends a structured instruction to the thread: project name, report type, outline structure, template reference (if any)
4. User interacts with the agent through the DeerFlow chat interface:
   - Upload reference materials and data files
   - Enter writing requirements and context
   - Multi-round interaction for content refinement
5. Agent writes chapters and updates their status in real-time (pending → writing → draft)
6. All chapters reach `draft` status → Stage 3 complete

**UI — Split Screen:**
- Left panel: chapter list with status indicators (pending / writing / draft), collapsible per section
- Right panel: DeerFlow conversation interface (reuse `workspace/chat` components and `useStream` hook)

**Data:** Thread ID stored on project record. Chapter content updated by agent via API calls as it writes.

**Key integration:** Reuse existing DeerFlow streaming infrastructure. The project module adds a thin coordination layer on top.

## Stage 4: Collaborative Editing

**Purpose:** Multiple people edit AI-generated drafts chapter by chapter.

**Flow:**
1. Project manager assigns chapters to members (one person can handle multiple chapters)
2. Each member opens their assigned chapter in the split-screen editor:
   - Left panel: outline with assignment status (who's editing, chapter status)
   - Right panel: rich text editor (Tiptap) for the chapter content
3. Members can request AI assistance inline: "Help me improve the data analysis in section 3.2"
4. Chapter status transitions: draft → editing → completed
5. All chapters marked `completed` → ready for Stage 5

**Member assignment:**
- Select from existing user management system (users, departments, roles)
- Support filtering by department and role
- One chapter can have one primary editor (simple model for v1)

**UI — Split Screen:**
- Left panel: outline tree with colored status indicators, member avatars on assigned chapters
- Right panel: Tiptap rich text editor with the chapter content, plus an embedded DeerFlow chat panel for AI assistance

## Stage 5: Approval

**Purpose:** Unified approval for the entire report through a multi-step workflow.

**Flow:**
1. Project manager clicks "Submit for Approval" when all chapters are `completed`
2. System sends approval requests through a predefined workflow (e.g., initial review → secondary review → final review)
3. Each approver reviews in split-screen:
   - Left panel: chapter directory, click to jump
   - Right panel: report content (read-only mode) with highlight/annotation capability
4. Each approver can:
   - **Approve** (with optional comment)
   - **Reject** (specify which chapters need revision → returns to Stage 4 for those chapters)
   - **Comment** (no status change)
5. All approval steps passed → Stage 6

**Approval workflow source:** Default workflow from KF template or report type. Project manager can customize before submitting.

**UI — Split Screen:**
- Left panel: approval step indicator (current step, completed steps), chapter list with approval status
- Right panel: report preview (read-only) with annotation tools

## Stage 6: Final Output

**Purpose:** Generate and distribute the finalized report.

**Features:**
- **Report preview**: Full read-only preview with auto-generated table of contents
- **Export**: Word (.docx) and PDF formats
- **Publish**: Publish to document space (reuse existing `docmgr` module)
- **Version snapshot**: Save current version; support future version comparison

**UI:** Full-width report preview with floating action bar (export, publish, save version).

**On completion:** Project status changes to `published`.

## Shared UI Components

### Stage Progress Bar
- Horizontal stepper at the top of project detail page showing all 6 stages
- Current stage highlighted; completed stages clickable (can revisit)
- Future stages grayed out until reached
- Each stage pill shows: icon + label + completion checkmark

### Split Screen Layout
- Persistent across Stages 3-5
- Left panel (300px fixed): context-dependent (chapter list, approval status, outline)
- Right panel (flex-1): main content area (chat, editor, preview)
- Resizable divider between panels

### Chapter Status System
- `pending` — created but no content
- `writing` — AI is currently generating content
- `draft` — AI has produced initial content
- `editing` — human editor is working on it
- `completed` — editor has finished
- `rejected` — sent back for revision during approval
- `approved` — passed approval

## Backend Changes

### Data Model (replaces in-memory dicts)

**`projects` table:**
- id, name, report_type, template_id (nullable FK to KF templates)
- status: setup | outline | writing | editing | approval | published
- thread_id (nullable, links to DeerFlow conversation thread)
- current_stage: 1-6
- created_by, created_at, updated_at

**`chapters` table:**
- id, project_id, parent_id (nullable, self-referential for hierarchy)
- title, level, sort_order
- status: pending | writing | draft | editing | completed | rejected | approved
- content (TEXT, nullable)
- assigned_to (nullable FK to users)
- word_count_target, word_count_current
- created_at, updated_at

**`project_members` table:**
- id, project_id, user_id, role: manager | editor | reviewer | approver
- created_at

**`approval_workflows` table:**
- id, project_id, step_order, step_name, role_required
- status: pending | in_progress | approved | rejected

**`approval_records` table:**
- id, workflow_id, chapter_id (nullable), action: approve | reject | comment
- reviewer_id, comment, created_at

### API Endpoints

**Project lifecycle:**
- `POST /api/extensions/project/projects` — create project
- `GET /api/extensions/project/projects/{id}` — get project with outline
- `PATCH /api/extensions/project/projects/{id}` — update project
- `PATCH /api/extensions/project/projects/{id}/stage` — advance to next stage

**Outline & Chapters:**
- `GET /api/extensions/project/projects/{id}/outline` — get full outline tree
- `PATCH /api/extensions/project/projects/{id}/outline` — update outline structure
- `PATCH /api/extensions/project/chapters/{id}` — update chapter (content, status, assignment)
- `POST /api/extensions/project/chapters/{id}/status` — transition chapter status

**Members:**
- `POST /api/extensions/project/projects/{id}/members` — add member (user_id + role from user system)
- `DELETE /api/extensions/project/projects/{id}/members/{user_id}` — remove member
- `PATCH /api/extensions/project/projects/{id}/members/{user_id}` — change role

**AI Writing:**
- `POST /api/extensions/project/projects/{id}/start-writing` — create DeerFlow thread, send initial prompt
- Chapter status updates happen via DeerFlow agent tool calls back to project API

**Approval:**
- `POST /api/extensions/project/projects/{id}/submit-approval` — submit for approval
- `POST /api/extensions/project/approval/actions` — approve/reject/comment
- `GET /api/extensions/project/projects/{id}/approval-status` — get approval workflow status

**Export:**
- `POST /api/extensions/project/projects/{id}/export` — generate docx/pdf
- `POST /api/extensions/project/projects/{id}/publish` — publish to docmgr

## Frontend File Structure

```
src/extensions/project/
  ProjectListPage.tsx          — Project listing page
  ProjectWorkspace.tsx         — Main workspace with stage progress bar
  StageProgressBar.tsx         — Horizontal 6-stage stepper
  SplitScreenLayout.tsx        — Reusable split-screen with resizable divider
  ProjectSetup.tsx             — Stage 1: project creation form
  OutlineEditor.tsx            — Stage 2: draggable outline tree editor
  OutlinePreview.tsx           — Stage 2: read-only outline preview
  AiWritingPanel.tsx           — Stage 3: left panel (chapter status list)
  CollaborativeEditor.tsx      — Stage 4: left panel (assignment status) + right (Tiptap)
  ApprovalPanel.tsx            — Stage 5: approval workflow + report preview
  FinalOutputPanel.tsx         — Stage 6: preview + export actions
  ChapterStatusBadge.tsx       — Reusable chapter status indicator
  MemberAssignmentDialog.tsx   — Member picker with user/department/role filters
  api.ts                       — API client
  types.ts                     — TypeScript types
```

## Migration Path

1. **Phase 1**: Database tables + project CRUD + outline editor (Stages 1-2)
2. **Phase 2**: DeerFlow thread integration + AI writing (Stage 3)
3. **Phase 3**: Collaborative editing with Tiptap (Stage 4)
4. **Phase 4**: Approval workflow (Stage 5)
5. **Phase 5**: Export and publish (Stage 6)

Each phase produces a working, testable increment.
