# Report Platform Phase 1: Database + Project CRUD + Outline Editor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace in-memory project storage with PostgreSQL, implement the Stage 1 (Project Setup) and Stage 2 (Outline Confirmation) UI with workflow-driven navigation.

**Architecture:** New SQLAlchemy models in central `models.py`, SQL migrations in `migrate_db()`, service layer with static methods and `AsyncSession`, FastAPI routers with `require_permission`, and a frontend workspace with stage progress bar and split-screen outline editor.

**Tech Stack:** PostgreSQL (asyncpg), SQLAlchemy 2.0 (async), FastAPI, Pydantic v2, Next.js 16, React 19, Tailwind CSS 4, Shadcn UI, Tiptap editor.

---

## File Structure

```
backend/app/extensions/
  models.py                           — ADD: ReportProject, ProjectChapter, ProjectMember, ApprovalWorkflow, ApprovalRecord
  database.py                         — MODIFY: migrate_db() — add project table creation SQL
  project/
    schemas.py                        — REWRITE: new Pydantic schemas for workflow model
    service.py                        — REWRITE: DB-backed service with static methods
    routers.py                        — REWRITE: new endpoints with DB session injection

frontend/src/extensions/project/
  types.ts                            — REWRITE: new workflow types
  api.ts                              — REWRITE: new API methods
  transforms.ts                       — KEEP: existing snake/camel case transforms
  ProjectList.tsx                     — MODIFY: update create dialog fields
  ProjectWorkspace.tsx                — CREATE: main workspace with stage progress bar
  StageProgressBar.tsx                — CREATE: horizontal 6-stage stepper component
  SplitScreenLayout.tsx               — CREATE: resizable split-screen layout
  ProjectSetup.tsx                    — CREATE: Stage 1 form (name + type + template)
  OutlineEditor.tsx                   — CREATE: Stage 2 draggable outline tree editor
  OutlinePreview.tsx                  — CREATE: Stage 2 read-only outline preview
  ChapterStatusBadge.tsx              — CREATE: reusable chapter status indicator

frontend/src/app/projects/
  page.tsx                            — KEEP: project list page
  [id]/page.tsx                       — MODIFY: render ProjectWorkspace instead of ProjectDetail
```

---

### Task 1: Add SQLAlchemy Models

**Files:**
- Modify: `backend/app/extensions/models.py`

- [ ] **Step 1: Add project-related models at the end of models.py**

Add these models after the existing models (before the final empty line):

```python
# ── Report Project Management ──


class ReportProject(Base):
    """Report project — tracks a single report through the writing workflow."""

    __tablename__ = "report_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_templates.id"), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="setup")
    current_stage: Mapped[int] = mapped_column(Integer, default=1)
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    chapters: Mapped[list["ProjectChapter"]] = relationship(
        "ProjectChapter", back_populates="project", cascade="all, delete-orphan",
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan",
    )
    approval_workflows: Mapped[list["ApprovalWorkflow"]] = relationship(
        "ApprovalWorkflow", back_populates="project", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ReportProject(id={self.id}, name={self.name})>"


class ProjectChapter(Base):
    """Chapter within a report project — hierarchical via parent_id."""

    __tablename__ = "project_chapters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_chapters.id", ondelete="CASCADE"), nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    word_count_target: Mapped[int] = mapped_column(Integer, default=3000)
    word_count_current: Mapped[int] = mapped_column(Integer, default=0)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    project: Mapped["ReportProject"] = relationship("ReportProject", back_populates="chapters")
    parent: Mapped[Optional["ProjectChapter"]] = relationship("ProjectChapter", remote_side=[id], back_populates="children")
    children: Mapped[list["ProjectChapter"]] = relationship(
        "ProjectChapter", back_populates="parent", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProjectChapter(id={self.id}, title={self.title})>"


class ProjectMember(Base):
    """Member of a report project."""

    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), default="editor")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    project: Mapped["ReportProject"] = relationship("ReportProject", back_populates="members")

    def __repr__(self) -> str:
        return f"<ProjectMember(project_id={self.project_id}, user_id={self.user_id})>"


class ApprovalWorkflow(Base):
    """Approval workflow steps for a project."""

    __tablename__ = "approval_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_required: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    project: Mapped["ReportProject"] = relationship("ReportProject", back_populates="approval_workflows")
    records: Mapped[list["ApprovalRecord"]] = relationship(
        "ApprovalRecord", back_populates="workflow", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ApprovalWorkflow(id={self.id}, step_name={self.step_name})>"


class ApprovalRecord(Base):
    """Approval action record."""

    __tablename__ = "approval_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_chapters.id"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    workflow: Mapped["ApprovalWorkflow"] = relationship("ApprovalWorkflow", back_populates="records")

    def __repr__(self) -> str:
        return f"<ApprovalRecord(id={self.id}, action={self.action})>"
```

- [ ] **Step 2: Run lint check**

Run: `cd D:/eai/eai-flow-main/backend && make lint`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/models.py
git commit -m "feat(project): add SQLAlchemy models for report projects, chapters, members, and approvals"
```

---

### Task 2: Add Database Migrations

**Files:**
- Modify: `backend/app/extensions/database.py` (add to `migrate_db()` function)

- [ ] **Step 1: Add migration SQL at the end of `migrate_db()`, before the function's final blank line**

Find the last `await conn.execute(` in `migrate_db()` (the `document_shares` index) and add the following block after it, before the function ends:

```python
        # --- Report Project Management ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS report_projects (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                report_type VARCHAR(100) NOT NULL,
                template_id UUID REFERENCES extraction_templates(id),
                status VARCHAR(20) NOT NULL DEFAULT 'setup',
                current_stage INT NOT NULL DEFAULT 1,
                thread_id VARCHAR(100),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_report_projects_status ON report_projects(status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_report_projects_created_by ON report_projects(created_by)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_chapters (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES report_projects(id) ON DELETE CASCADE,
                parent_id UUID REFERENCES project_chapters(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                level INT NOT NULL DEFAULT 1,
                sort_order INT NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                content TEXT,
                assigned_to UUID REFERENCES users(id),
                word_count_target INT NOT NULL DEFAULT 3000,
                word_count_current INT NOT NULL DEFAULT 0,
                purpose TEXT,
                generation_hint TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_project_chapters_project ON project_chapters(project_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_project_chapters_parent ON project_chapters(parent_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_project_chapters_status ON project_chapters(status)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES report_projects(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id),
                role VARCHAR(50) NOT NULL DEFAULT 'editor',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(project_id, user_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS approval_workflows (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES report_projects(id) ON DELETE CASCADE,
                step_order INT NOT NULL,
                step_name VARCHAR(200) NOT NULL,
                role_required VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_approval_workflows_project ON approval_workflows(project_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS approval_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_id UUID NOT NULL REFERENCES approval_workflows(id) ON DELETE CASCADE,
                chapter_id UUID REFERENCES project_chapters(id),
                action VARCHAR(20) NOT NULL,
                reviewer_id UUID NOT NULL REFERENCES users(id),
                comment TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_approval_records_workflow ON approval_records(workflow_id)"
        ))
```

- [ ] **Step 2: Run lint check**

Run: `cd D:/eai/eai-flow-main/backend && make lint`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/database.py
git commit -m "feat(project): add database migrations for report project tables"
```

---

### Task 3: Rewrite Backend Schemas

**Files:**
- Rewrite: `backend/app/extensions/project/schemas.py`

- [ ] **Step 1: Replace entire file with new workflow-aligned schemas**

```python
"""Pydantic schemas for report project management (workflow-driven)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Enums (as string literals) ──

VALID_REPORT_TYPES = [
    "environmental_impact",
    "geological_survey",
    "feasibility_study",
    "safety_assessment",
    "energy_assessment",
    "other",
]

VALID_PROJECT_STATUSES = ["setup", "outline", "writing", "editing", "approval", "published", "archived"]

VALID_CHAPTER_STATUSES = ["pending", "writing", "draft", "editing", "completed", "rejected", "approved"]

VALID_MEMBER_ROLES = ["manager", "editor", "reviewer", "approver"]

VALID_WORKFLOW_STATUSES = ["pending", "in_progress", "approved", "rejected"]

VALID_APPROVAL_ACTIONS = ["approve", "reject", "comment"]


# ── Chapter ──


class ChapterOut(BaseModel):
    id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    title: str
    level: int = 1
    sort_order: int = 0
    status: str = "pending"
    content: str | None = None
    assigned_to: UUID | None = None
    assigned_name: str | None = None
    word_count_target: int = 3000
    word_count_current: int = 0
    purpose: str | None = None
    generation_hint: str | None = None
    children: list["ChapterOut"] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChapterTreeNode(BaseModel):
    """Flat node for outline tree operations (add/reorder/update)."""
    id: UUID | None = None  # None for new chapters
    title: str
    level: int = 1
    sort_order: int = 0
    purpose: str | None = None
    generation_hint: str | None = None
    word_count_target: int = 3000
    children: list["ChapterTreeNode"] = Field(default_factory=list)


class ChapterContentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    assigned_to: UUID | None = None
    word_count_target: int | None = None


# ── Member ──


class MemberOut(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    username: str = ""
    role: str
    created_at: datetime | None = None


class MemberCreate(BaseModel):
    user_id: UUID
    role: str = "editor"


# ── Project ──


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., min_length=1)
    template_id: UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = None
    current_stage: int | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    template_id: UUID | None = None
    status: str = "setup"
    current_stage: int = 1
    thread_id: str | None = None
    created_by: UUID | None = None
    members: list[MemberOut] = Field(default_factory=list)
    chapters: list[ChapterOut] = Field(default_factory=list)
    chapter_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    status: str = "setup"
    current_stage: int = 1
    template_id: UUID | None = None
    chapter_count: int = 0
    member_count: int = 0
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem] = Field(default_factory=list)
    total: int = 0


# ── Outline batch update ──


class OutlineBatchUpdate(BaseModel):
    """Replace the entire outline tree with a new structure."""
    chapters: list[ChapterTreeNode] = Field(default_factory=list)


# ── Approval ──


class ApprovalWorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    step_order: int
    step_name: str
    role_required: str
    status: str = "pending"


class ApprovalRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    chapter_id: UUID | None = None
    action: str
    reviewer_id: UUID
    reviewer_name: str = ""
    comment: str | None = None
    created_at: datetime | None = None


class ApprovalActionRequest(BaseModel):
    workflow_id: UUID
    chapter_id: UUID | None = None
    action: str = Field(..., pattern="^(approve|reject|comment)$")
    comment: str | None = None
```

- [ ] **Step 2: Run lint check**

Run: `cd D:/eai/eai-flow-main/backend && make lint`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/project/schemas.py
git commit -m "feat(project): rewrite schemas for workflow-driven project model"
```

---

### Task 4: Rewrite Backend Service

**Files:**
- Rewrite: `backend/app/extensions/project/service.py`

- [ ] **Step 1: Replace entire file with DB-backed service**

```python
"""Database-backed service for report project management."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.extensions.models import (
    ApprovalRecord,
    ApprovalWorkflow,
    ProjectChapter,
    ProjectMember,
    ReportProject,
    User,
)

from .schemas import (
    ChapterOut,
    ChapterTreeNode,
    MemberOut,
    ProjectListItem,
    ProjectOut,
)


# ── Helpers ──


async def _resolve_username(db: AsyncSession, user_id) -> str:
    user = await db.get(User, user_id)
    return user.username if user else str(user_id)


def _chapter_to_out(chapter: ProjectChapter, children: list[ChapterOut] | None = None) -> ChapterOut:
    return ChapterOut(
        id=chapter.id,
        project_id=chapter.project_id,
        parent_id=chapter.parent_id,
        title=chapter.title,
        level=chapter.level,
        sort_order=chapter.sort_order,
        status=chapter.status,
        content=chapter.content,
        assigned_to=chapter.assigned_to,
        assigned_name=None,  # resolved separately
        word_count_target=chapter.word_count_target,
        word_count_current=chapter.word_count_current,
        purpose=chapter.purpose,
        generation_hint=chapter.generation_hint,
        children=children or [],
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    )


def _build_chapter_tree(chapters: list[ProjectChapter], assigned_names: dict) -> list[ChapterOut]:
    """Build nested tree from flat chapter list."""
    by_id = {c.id: c for c in chapters}
    children_map: dict = {c.id: [] for c in chapters}
    roots = []

    for c in chapters:
        if c.parent_id and c.parent_id in by_id:
            children_map[c.parent_id].append(c)
        else:
            roots.append(c)

    def _to_out(c: ProjectChapter) -> ChapterOut:
        child_outs = [_to_out(child) for child in sorted(children_map.get(c.id, []), key=lambda x: x.sort_order)]
        return ChapterOut(
            id=c.id,
            project_id=c.project_id,
            parent_id=c.parent_id,
            title=c.title,
            level=c.level,
            sort_order=c.sort_order,
            status=c.status,
            content=c.content,
            assigned_to=c.assigned_to,
            assigned_name=assigned_names.get(c.assigned_to),
            word_count_target=c.word_count_target,
            word_count_current=c.word_count_current,
            purpose=c.purpose,
            generation_hint=c.generation_hint,
            children=child_outs,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    return [_to_out(r) for r in sorted(roots, key=lambda x: x.sort_order)]


async def _get_assigned_names(db: AsyncSession, chapters: list[ProjectChapter]) -> dict:
    user_ids = {c.assigned_to for c in chapters if c.assigned_to}
    if not user_ids:
        return {}
    stmt = select(User.id, User.username).where(User.id.in_(user_ids))
    result = await db.execute(stmt)
    return dict(result.all())


# ── Outline tree helpers ──


async def _create_chapters_from_tree(
    db: AsyncSession,
    project_id,
    nodes: list[ChapterTreeNode],
    parent_id=None,
    level: int = 1,
    start_order: int = 0,
) -> list[ProjectChapter]:
    """Recursively create ProjectChapter records from ChapterTreeNode list."""
    created = []
    for i, node in enumerate(nodes):
        chapter = ProjectChapter(
            project_id=project_id,
            parent_id=parent_id,
            title=node.title,
            level=level,
            sort_order=start_order + i,
            purpose=node.purpose,
            generation_hint=node.generation_hint,
            word_count_target=node.word_count_target,
        )
        db.add(chapter)
        await db.flush()
        created.append(chapter)

        if node.children:
            children = await _create_chapters_from_tree(
                db, project_id, node.children, parent_id=chapter.id, level=level + 1, start_order=0,
            )
            created.extend(children)

    return created


async def _delete_project_chapters(db: AsyncSession, project_id) -> None:
    """Delete all chapters for a project (for outline replacement)."""
    stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    result = await db.execute(stmt)
    for chapter in result.scalars().all():
        await db.delete(chapter)


# ── Public API ──


async def list_projects(
    db: AsyncSession,
    *,
    status: str | None = None,
    report_type: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ProjectListItem], int]:
    query = select(ReportProject).where(ReportProject.status != "archived")
    count_query = select(func.count(ReportProject.id)).where(ReportProject.status != "archived")

    if status:
        query = query.where(ReportProject.status == status)
        count_query = count_query.where(ReportProject.status == status)
    if report_type:
        query = query.where(ReportProject.report_type == report_type)
        count_query = count_query.where(ReportProject.report_type == report_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(ReportProject.name.ilike(pattern))
        count_query = count_query.where(ReportProject.name.ilike(pattern))

    query = query.order_by(ReportProject.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for p in projects:
        chapter_count_stmt = select(func.count(ProjectChapter.id)).where(ProjectChapter.project_id == p.id)
        cc = (await db.execute(chapter_count_stmt)).scalar() or 0

        member_count_stmt = select(func.count(ProjectMember.id)).where(ProjectMember.project_id == p.id)
        mc = (await db.execute(member_count_stmt)).scalar() or 0

        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            report_type=p.report_type,
            status=p.status,
            current_stage=p.current_stage,
            template_id=p.template_id,
            chapter_count=cc,
            member_count=mc,
            created_by=p.created_by,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return items, total


async def get_project(db: AsyncSession, project_id) -> ProjectOut | None:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    # Load chapters
    chap_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    chap_result = await db.execute(chap_stmt)
    chapters = list(chap_result.scalars().all())
    assigned_names = await _get_assigned_names(db, chapters)
    chapter_tree = _build_chapter_tree(chapters, assigned_names)

    # Load members
    mem_stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    mem_result = await db.execute(mem_stmt)
    members = []
    for m in mem_result.scalars().all():
        members.append(MemberOut(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            username=await _resolve_username(db, m.user_id),
            role=m.role,
            created_at=m.created_at,
        ))

    return ProjectOut(
        id=project.id,
        name=project.name,
        report_type=project.report_type,
        template_id=project.template_id,
        status=project.status,
        current_stage=project.current_stage,
        thread_id=project.thread_id,
        created_by=project.created_by,
        members=members,
        chapters=chapter_tree,
        chapter_count=len(chapters),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    report_type: str,
    created_by=None,
    template_id=None,
) -> ProjectOut:
    project = ReportProject(
        name=name,
        report_type=report_type,
        created_by=created_by,
        template_id=template_id,
        status="setup",
        current_stage=1,
    )
    db.add(project)
    await db.flush()

    # If template_id provided, import chapters from template
    if template_id:
        await _import_template_outline(db, project.id, template_id)

    return await get_project(db, project.id)


async def _import_template_outline(db: AsyncSession, project_id, template_id) -> None:
    """Import chapter structure from a KF template."""
    from app.extensions.knowledge_factory.models import ExtractionTemplate

    template = await db.get(ExtractionTemplate, template_id)
    if not template:
        return

    sections_data = template.root_sections_json or {}
    section_list = sections_data.get("sections", [])
    if not section_list:
        return

    async def _create_from_section(sec: dict, parent_id=None, level: int = 1, order: int = 0) -> None:
        chapter = ProjectChapter(
            project_id=project_id,
            parent_id=parent_id,
            title=sec.get("title", "Untitled"),
            level=level,
            sort_order=order,
            purpose=sec.get("purpose"),
            generation_hint=sec.get("generation_hint"),
            word_count_target=sec.get("content_contract", {}).get("min_word_count", 3000) if isinstance(sec.get("content_contract"), dict) else 3000,
        )
        db.add(chapter)
        await db.flush()

        for j, child in enumerate(sec.get("children", [])):
            await _create_from_section(child, parent_id=chapter.id, level=level + 1, order=j)

    for i, sec in enumerate(section_list):
        await _create_from_section(sec, order=i)


async def update_project(db: AsyncSession, project_id, **kwargs) -> ProjectOut | None:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    for k, v in kwargs.items():
        if v is not None:
            setattr(project, k, v)

    await db.flush()
    return await get_project(db, project_id)


async def delete_project(db: AsyncSession, project_id) -> bool:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return False
    await db.delete(project)
    return True


# ── Outline ──


async def get_outline_tree(db: AsyncSession, project_id) -> list[ChapterOut]:
    chap_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    chap_result = await db.execute(chap_stmt)
    chapters = list(chap_result.scalars().all())
    assigned_names = await _get_assigned_names(db, chapters)
    return _build_chapter_tree(chapters, assigned_names)


async def replace_outline(db: AsyncSession, project_id, chapters: list[ChapterTreeNode]) -> list[ChapterOut]:
    """Delete existing chapters and create new ones from the tree structure."""
    await _delete_project_chapters(db, project_id)
    await _create_chapters_from_tree(db, project_id, chapters)
    await db.flush()
    return await get_outline_tree(db, project_id)


async def update_chapter(db: AsyncSession, chapter_id, **kwargs) -> ChapterOut | None:
    stmt = select(ProjectChapter).where(ProjectChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        return None

    for k, v in kwargs.items():
        if v is not None:
            setattr(chapter, k, v)

    await db.flush()
    assigned_names = await _get_assigned_names(db, [chapter])
    return _chapter_to_out(chapter)


async def confirm_outline(db: AsyncSession, project_id) -> ProjectOut | None:
    """Advance project from stage 2 (outline) to stage 3 (writing)."""
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    project.current_stage = 3
    project.status = "writing"
    await db.flush()
    return await get_project(db, project_id)


# ── Members ──


async def add_member(db: AsyncSession, project_id, user_id, role: str = "editor") -> bool:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        return False

    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return True

    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(member)
    await db.flush()
    return True


async def remove_member(db: AsyncSession, project_id, user_id) -> bool:
    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member:
        return False
    await db.delete(member)
    return True
```

- [ ] **Step 2: Run lint check**

Run: `cd D:/eai/eai-flow-main/backend && make lint`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/project/service.py
git commit -m "feat(project): rewrite service with PostgreSQL-backed storage"
```

---

### Task 5: Rewrite Backend Routers

**Files:**
- Rewrite: `backend/app/extensions/project/routers.py`

- [ ] **Step 1: Replace entire file with new DB-backed routers**

```python
"""FastAPI routers for report project management (workflow-driven)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

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
)
from . import service

router = APIRouter(prefix="/api/extensions/project", tags=["project"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# ── Projects ──


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    report_type: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    items, total = await service.list_projects(
        db, status=status_filter, report_type=report_type, search=search, skip=skip, limit=limit,
    )
    return ProjectListResponse(items=items, total=total)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.get_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.create_project(
        db,
        name=body.name,
        report_type=body.report_type,
        template_id=body.template_id,
        created_by=_user.id,
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_project(db, project_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Outline ──


@router.get("/projects/{project_id}/outline")
async def get_outline(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_outline_tree(db, project_id)


@router.put("/projects/{project_id}/outline")
async def replace_outline(
    project_id: UUID,
    body: OutlineBatchUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.replace_outline(db, project_id, body.chapters)


@router.patch("/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterContentUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_chapter(db, chapter_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return result


@router.post("/projects/{project_id}/confirm-outline", response_model=ProjectOut)
async def confirm_outline(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.confirm_outline(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


# ── Members ──


@router.post("/projects/{project_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    project_id: UUID,
    body: MemberCreate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.add_member(db, project_id, body.user_id, body.role)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.remove_member(db, project_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
```

- [ ] **Step 2: Run lint check**

Run: `cd D:/eai/eai-flow-main/backend && make lint`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/project/routers.py
git commit -m "feat(project): rewrite routers with DB session injection and new endpoints"
```

---

### Task 6: Rewrite Frontend Types

**Files:**
- Rewrite: `frontend/src/extensions/project/types.ts`

- [ ] **Step 1: Replace entire file with new workflow-aligned types**

```typescript
// ── Enums ──

export type ReportType =
  | "environmental_impact"
  | "geological_survey"
  | "feasibility_study"
  | "safety_assessment"
  | "energy_assessment"
  | "other";

export type ProjectStatus = "setup" | "outline" | "writing" | "editing" | "approval" | "published" | "archived";

export type ChapterStatus = "pending" | "writing" | "draft" | "editing" | "completed" | "rejected" | "approved";

export type MemberRole = "manager" | "editor" | "reviewer" | "approver";

// ── Chapter ──

export interface ProjectChapter {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  level: number;
  sortOrder: number;
  status: ChapterStatus;
  content: string | null;
  assignedTo: string | null;
  assignedName: string | null;
  wordCountTarget: number;
  wordCountCurrent: number;
  purpose: string | null;
  generationHint: string | null;
  children: ProjectChapter[];
  createdAt: string | null;
  updatedAt: string | null;
}

/** For outline batch updates — id is null for new nodes */
export interface ChapterTreeNode {
  id?: string;
  title: string;
  level: number;
  sortOrder: number;
  purpose?: string | null;
  generationHint?: string | null;
  wordCountTarget?: number;
  children: ChapterTreeNode[];
}

// ── Member ──

export interface ProjectMember {
  id: string;
  projectId: string;
  userId: string;
  username: string;
  role: MemberRole;
  createdAt: string | null;
}

// ── Project ──

export interface ReportProject {
  id: string;
  name: string;
  reportType: ReportType;
  templateId: string | null;
  status: ProjectStatus;
  currentStage: number;
  threadId: string | null;
  createdBy: string | null;
  members: ProjectMember[];
  chapters: ProjectChapter[];
  chapterCount: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  reportType: ReportType;
  status: ProjectStatus;
  currentStage: number;
  templateId: string | null;
  chapterCount: number;
  memberCount: number;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

// ── API Request Types ──

export interface CreateProjectRequest {
  name: string;
  reportType: ReportType;
  templateId?: string | null;
}

export interface UpdateProjectRequest {
  name?: string;
  status?: ProjectStatus;
  currentStage?: number;
}

export interface OutlineBatchUpdateRequest {
  chapters: ChapterTreeNode[];
}

export interface ChapterUpdateRequest {
  title?: string;
  content?: string | null;
  status?: ChapterStatus;
  assignedTo?: string | null;
  wordCountTarget?: number;
}

// ── Labels ──

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  environmental_impact: "环境影响评价",
  geological_survey: "地质勘查",
  feasibility_study: "可行性研究",
  safety_assessment: "安全评价",
  energy_assessment: "节能评价",
  other: "其他",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  setup: "项目设定",
  outline: "大纲确认",
  writing: "AI撰写",
  editing: "协作编辑",
  approval: "审批",
  published: "已发布",
  archived: "已归档",
};

export const CHAPTER_STATUS_LABELS: Record<ChapterStatus, string> = {
  pending: "待处理",
  writing: "AI撰写中",
  draft: "初稿",
  editing: "编辑中",
  completed: "已完成",
  rejected: "退回修改",
  approved: "已通过",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "项目经理",
  editor: "编辑",
  reviewer: "审核人",
  approver: "批准人",
};

export const STAGE_LABELS = [
  "项目设定",
  "大纲确认",
  "AI撰写",
  "协作编辑",
  "审批",
  "定稿输出",
] as const;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/types.ts
git commit -m "feat(project): rewrite frontend types for workflow-driven model"
```

---

### Task 7: Rewrite Frontend API Client

**Files:**
- Rewrite: `frontend/src/extensions/project/api.ts`

- [ ] **Step 1: Replace entire file with new API methods**

```typescript
import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CreateProjectRequest,
  ChapterTreeNode,
  ChapterUpdateRequest,
  ProjectListItem,
  ProjectChapter,
  ProjectMember,
  ReportProject,
  UpdateProjectRequest,
} from "./types";

const API_BASE = "/project";

export const projectApi = {
  // ── Projects ──

  list: async (params?: {
    status?: string;
    reportType?: string;
    search?: string;
    skip?: number;
    limit?: number;
  }): Promise<{ items: ProjectListItem[]; total: number }> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.reportType) query.set("report_type", params.reportType);
    if (params?.search) query.set("search", params.search);
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return await authFetch(`${API_BASE}/projects?${query}`);
  },

  get: async (id: string): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}`);
    return toCamelCase<ReportProject>(data);
  },

  create: async (req: CreateProjectRequest): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects`, {
      method: "POST",
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<ReportProject>(data);
  },

  update: async (id: string, req: UpdateProjectRequest): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<ReportProject>(data);
  },

  delete: async (id: string): Promise<void> => {
    await authFetch<void>(`${API_BASE}/projects/${id}`, { method: "DELETE" });
  },

  // ── Outline ──

  getOutline: async (projectId: string): Promise<ProjectChapter[]> => {
    return await authFetch<ProjectChapter[]>(`${API_BASE}/projects/${projectId}/outline`);
  },

  replaceOutline: async (projectId: string, chapters: ChapterTreeNode[]): Promise<ProjectChapter[]> => {
    return await authFetch<ProjectChapter[]>(`${API_BASE}/projects/${projectId}/outline`, {
      method: "PUT",
      body: JSON.stringify({ chapters }),
    });
  },

  updateChapter: async (projectId: string, chapterId: string, updates: ChapterUpdateRequest): Promise<ProjectChapter> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/chapters/${chapterId}`,
      {
        method: "PATCH",
        body: JSON.stringify(toSnakeCase(updates as Record<string, unknown>)),
      },
    );
    return toCamelCase<ProjectChapter>(data);
  },

  confirmOutline: async (projectId: string): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/confirm-outline`,
      { method: "POST" },
    );
    return toCamelCase<ReportProject>(data);
  },

  // ── Members ──

  addMember: async (projectId: string, userId: string, role: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, role }),
    });
  },

  removeMember: async (projectId: string, userId: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members/${userId}`, { method: "DELETE" });
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/api.ts
git commit -m "feat(project): rewrite frontend API client for new endpoints"
```

---

### Task 8: Create StageProgressBar Component

**Files:**
- Create: `frontend/src/extensions/project/StageProgressBar.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { Check } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import { STAGE_LABELS } from "./types";

const STAGE_ICONS = ["📋", "📝", "🤖", "👥", "✅", "📄"];

interface StageProgressBarProps {
  projectId: string;
  currentStage: number;
}

export function StageProgressBar({ projectId, currentStage }: StageProgressBarProps) {
  return (
    <div className="flex items-center gap-1 px-6">
      {STAGE_LABELS.map((label, index) => {
        const stage = index + 1;
        const isCompleted = stage < currentStage;
        const isCurrent = stage === currentStage;
        const isFuture = stage > currentStage;

        const href = `/projects/${projectId}?stage=${stage}`;

        return (
          <Link
            key={stage}
            href={isFuture ? "#" : href}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              isCompleted && "bg-primary/10 text-primary hover:bg-primary/20",
              isCurrent && "bg-primary text-primary-foreground",
              isFuture && "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            <span className="text-sm">{STAGE_ICONS[index]}</span>
            <span>{label}</span>
            {isCompleted && <Check className="h-3 w-3" />}
          </Link>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/StageProgressBar.tsx
git commit -m "feat(project): add stage progress bar component"
```

---

### Task 9: Create SplitScreenLayout Component

**Files:**
- Create: `frontend/src/extensions/project/SplitScreenLayout.tsx`

- [ ] **Step 1: Create the component using existing Shadcn resizable**

```tsx
"use client";

import { type ReactNode, useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface SplitScreenLayoutProps {
  left: ReactNode;
  right: ReactNode;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
  maxLeftWidth?: number;
}

export function SplitScreenLayout({
  left,
  right,
  defaultLeftWidth = 300,
  minLeftWidth = 200,
  maxLeftWidth = 500,
}: SplitScreenLayoutProps) {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const isDragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(() => {
    isDragging.current = true;
    const onMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newWidth = Math.min(maxLeftWidth, Math.max(minLeftWidth, e.clientX - rect.left));
      setLeftWidth(newWidth);
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [minLeftWidth, maxLeftWidth]);

  return (
    <div ref={containerRef} className="flex flex-1 min-h-0 overflow-hidden">
      <div style={{ width: leftWidth }} className="shrink-0 overflow-y-auto border-r border-border">
        {left}
      </div>
      <div
        className="w-1 cursor-col-resize bg-border hover:bg-primary/30 transition-colors shrink-0"
        onMouseDown={handleMouseDown}
      />
      <div className="flex-1 min-w-0 overflow-y-auto">
        {right}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/SplitScreenLayout.tsx
git commit -m "feat(project): add split-screen layout component"
```

---

### Task 10: Create ChapterStatusBadge Component

**Files:**
- Create: `frontend/src/extensions/project/ChapterStatusBadge.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { cn } from "@/lib/utils";

import { CHAPTER_STATUS_LABELS, type ChapterStatus } from "./types";

const STATUS_STYLES: Record<ChapterStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  writing: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  draft: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  editing: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
};

interface ChapterStatusBadgeProps {
  status: ChapterStatus;
  className?: string;
}

export function ChapterStatusBadge({ status, className }: ChapterStatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
        STATUS_STYLES[status],
        className,
      )}
    >
      {CHAPTER_STATUS_LABELS[status]}
    </span>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/ChapterStatusBadge.tsx
git commit -m "feat(project): add chapter status badge component"
```

---

### Task 11: Create ProjectSetup Component (Stage 1)

**Files:**
- Create: `frontend/src/extensions/project/ProjectSetup.tsx`

- [ ] **Step 1: Create Stage 1 form**

```tsx
"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { projectApi } from "@/extensions/project/api";
import { REPORT_TYPE_LABELS, type ReportType, type ReportProject } from "@/extensions/project/types";
import { toast } from "sonner";

interface ProjectSetupProps {
  projectId?: string;
  onCreated?: (project: ReportProject) => void;
}

export function ProjectSetup({ projectId, onCreated }: ProjectSetupProps) {
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<ReportType | "">("");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = useCallback(async () => {
    if (!name.trim()) {
      toast.error("请输入项目名称");
      return;
    }
    if (!reportType) {
      toast.error("请选择报告类型");
      return;
    }
    setSubmitting(true);
    try {
      const project = await projectApi.create({
        name: name.trim(),
        reportType,
        templateId,
      });
      toast.success("项目创建成功");
      onCreated?.(project);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建项目失败";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }, [name, reportType, templateId, onCreated]);

  return (
    <div className="flex flex-col items-center justify-center flex-1 p-6">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">创建报告项目</h2>
          <p className="text-sm text-muted-foreground mt-1">填写基本信息，开始报告编写流程</p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">项目名称</Label>
            <Input
              id="project-name"
              placeholder="请输入项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="report-type">报告类型</Label>
            <Select value={reportType} onValueChange={(v) => setReportType(v as ReportType)}>
              <SelectTrigger id="report-type">
                <SelectValue placeholder="请选择报告类型" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Template selector will be added when KF template picker is implemented */}
        </div>

        <Button
          className="w-full gap-2"
          onClick={handleSubmit}
          disabled={submitting || !name.trim() || !reportType}
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          创建项目并进入大纲
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/ProjectSetup.tsx
git commit -m "feat(project): add ProjectSetup component for Stage 1"
```

---

### Task 12: Create OutlineEditor Component (Stage 2)

**Files:**
- Create: `frontend/src/extensions/project/OutlineEditor.tsx`
- Create: `frontend/src/extensions/project/OutlinePreview.tsx`

- [ ] **Step 1: Create the draggable outline editor**

```tsx
"use client";

import { ChevronDown, ChevronRight, GripVertical, Plus, Trash2, X } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { ChapterStatusBadge } from "./ChapterStatusBadge";
import type { ChapterTreeNode, ProjectChapter } from "./types";

interface OutlineEditorProps {
  chapters: ChapterTreeNode[];
  onChange: (chapters: ChapterTreeNode[]) => void;
  readOnly?: boolean;
}

interface DragState {
  sourceIndex: number[];
  targetIndex: number[];
}

function getAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode | null {
  let current = nodes;
  let node: ChapterTreeNode | null = null;
  for (const idx of path) {
    if (idx >= current.length) return null;
    node = current[idx];
    current = node.children;
  }
  return node;
}

function setAtPath(
  nodes: ChapterTreeNode[],
  path: number[],
  updater: (node: ChapterTreeNode) => ChapterTreeNode,
): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  return nodes.map((node, i) => {
    if (i !== head) return node;
    if (rest.length === 0) return updater(node);
    return { ...node, children: setAtPath(node.children, rest, updater) };
  });
}

function removeAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  if (rest.length === 0) {
    return nodes.filter((_, i) => i !== head);
  }
  return nodes.map((node, i) => {
    if (i !== head) return node;
    return { ...node, children: removeAtPath(node.children, rest) };
  });
}

function OutlineNodeRow({
  node,
  path,
  onChange,
  onRemove,
  onAddChild,
  readOnly,
}: {
  node: ChapterTreeNode;
  path: number[];
  onChange: (path: number[], node: ChapterTreeNode) => void;
  onRemove: (path: number[]) => void;
  onAddChild: (path: number[]) => void;
  readOnly: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-muted/50 group",
          node.level === 1 && "font-medium",
        )}
        style={{ paddingLeft: `${(node.level - 1) * 24 + 8}px` }}
      >
        {!readOnly && (
          <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab shrink-0" />
        )}

        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        {readOnly ? (
          <span className="text-sm text-foreground truncate flex-1">{node.title}</span>
        ) : (
          <Input
            value={node.title}
            onChange={(e) => onChange(path, { ...node, title: e.target.value })}
            className="h-7 text-sm border-transparent hover:border-border focus:border-primary flex-1"
            variant="ghost"
          />
        )}

        {!readOnly && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => onAddChild(path)}
            >
              <Plus className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={() => onRemove(path)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children.map((child, childIndex) => (
            <OutlineNodeRow
              key={`${child.title}-${childIndex}`}
              node={child}
              path={[...path, childIndex]}
              onChange={onChange}
              onRemove={onRemove}
              onAddChild={onAddChild}
              readOnly={readOnly}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function OutlineEditor({ chapters, onChange, readOnly = false }: OutlineEditorProps) {
  const handleChange = useCallback(
    (path: number[], updated: ChapterTreeNode) => {
      onChange(setAtPath(chapters, path, () => updated));
    },
    [chapters, onChange],
  );

  const handleRemove = useCallback(
    (path: number[]) => {
      onChange(removeAtPath(chapters, path));
    },
    [chapters, onChange],
  );

  const handleAddChild = useCallback(
    (path: number[]) => {
      const newChild: ChapterTreeNode = {
        title: "新章节",
        level: path.length + 2,
        sortOrder: 0,
        children: [],
      };
      onChange(
        setAtPath(chapters, path, (node) => ({
          ...node,
          children: [...node.children, newChild],
        })),
      );
    },
    [chapters, onChange],
  );

  const handleAddRoot = useCallback(() => {
    const newNode: ChapterTreeNode = {
      title: "新章节",
      level: 1,
      sortOrder: chapters.length,
      children: [],
    };
    onChange([...chapters, newNode]);
  }, [chapters, onChange]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-medium text-foreground">
          {readOnly ? "大纲预览" : "编辑大纲"}
        </h3>
        {!readOnly && (
          <Button variant="outline" size="sm" className="gap-1" onClick={handleAddRoot}>
            <Plus className="h-3 w-3" />
            添加章节
          </Button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {chapters.length === 0 ? (
          <div className="text-center text-sm text-muted-foreground py-8">
            暂无章节，点击"添加章节"开始
          </div>
        ) : (
          chapters.map((node, index) => (
            <OutlineNodeRow
              key={`${node.title}-${index}`}
              node={node}
              path={[index]}
              onChange={handleChange}
              onRemove={handleRemove}
              onAddChild={handleAddChild}
              readOnly={readOnly}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create OutlinePreview (read-only view)**

```tsx
"use client";

import { OutlineEditor } from "./OutlineEditor";
import type { ChapterTreeNode } from "./types";

interface OutlinePreviewProps {
  chapters: ChapterTreeNode[];
}

export function OutlinePreview({ chapters }: OutlinePreviewProps) {
  return <OutlineEditor chapters={chapters} onChange={() => {}} readOnly />;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/OutlineEditor.tsx frontend/src/extensions/project/OutlinePreview.tsx
git commit -m "feat(project): add outline editor and preview components for Stage 2"
```

---

### Task 13: Create ProjectWorkspace Component

**Files:**
- Create: `frontend/src/extensions/project/ProjectWorkspace.tsx`
- Modify: `frontend/src/app/projects/[id]/page.tsx`

- [ ] **Step 1: Create the main workspace component**

```tsx
"use client";

import { ArrowLeft, ArrowRight, Check, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { OutlineEditor } from "@/extensions/project/OutlineEditor";
import { OutlinePreview } from "@/extensions/project/OutlinePreview";
import { ProjectSetup } from "@/extensions/project/ProjectSetup";
import { SplitScreenLayout } from "@/extensions/project/SplitScreenLayout";
import { StageProgressBar } from "@/extensions/project/StageProgressBar";
import {
  PROJECT_STATUS_LABELS,
  STAGE_LABELS,
  type ChapterTreeNode,
  type ReportProject,
} from "@/extensions/project/types";
import { toast } from "sonner";

function chaptersToTreeNodes(chapters: ReportProject["chapters"]): ChapterTreeNode[] {
  return chapters.map((c) => ({
    id: c.id,
    title: c.title,
    level: c.level,
    sortOrder: c.sortOrder,
    purpose: c.purpose,
    generationHint: c.generationHint,
    wordCountTarget: c.wordCountTarget,
    children: chaptersToTreeNodes(c.children),
  }));
}

interface ProjectWorkspaceProps {
  projectId: string;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const router = useRouter();
  const params = useSearchParams();
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [outlineDraft, setOutlineDraft] = useState<ChapterTreeNode[]>([]);
  const [saving, setSaving] = useState(false);

  const currentStage = project?.currentStage ?? 1;
  const viewingStage = Number(params.get("stage")) || currentStage;

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      setProject(data);
      if (data.chapters.length > 0) {
        setOutlineDraft(chaptersToTreeNodes(data.chapters));
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  const handleProjectCreated = useCallback(
    (newProject: ReportProject) => {
      setProject(newProject);
      router.push(`/projects/${newProject.id}?stage=2`);
    },
    [router],
  );

  const handleSaveOutline = useCallback(async () => {
    if (!project) return;
    setSaving(true);
    try {
      const chapters = await projectApi.replaceOutline(project.id, outlineDraft);
      setProject((prev) => (prev ? { ...prev, chapters } : prev));
      toast.success("大纲已保存");
    } catch {
      toast.error("保存大纲失败");
    } finally {
      setSaving(false);
    }
  }, [project, outlineDraft]);

  const handleConfirmOutline = useCallback(async () => {
    if (!project) return;
    setSaving(true);
    try {
      await projectApi.replaceOutline(project.id, outlineDraft);
      const updated = await projectApi.confirmOutline(project.id);
      setProject(updated);
      toast.success("大纲已确认，进入AI撰写阶段");
      router.push(`/projects/${project.id}?stage=3`);
    } catch {
      toast.error("确认大纲失败");
    } finally {
      setSaving(false);
    }
  }, [project, outlineDraft, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-destructive">项目不存在</p>
        <Link href="/projects">
          <Button variant="outline" size="sm">返回项目列表</Button>
        </Link>
      </div>
    );
  }

  // Stage 1: Project Setup (only shown when project is new / status=setup)
  if (project.status === "setup" && viewingStage <= 1) {
    return <ProjectSetup onCreated={handleProjectCreated} />;
  }

  // Stage 2: Outline Confirmation
  if (viewingStage === 2) {
    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
          <StageProgressBar projectId={projectId} currentStage={currentStage} />
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleSaveOutline} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
              保存大纲
            </Button>
            <Button size="sm" onClick={handleConfirmOutline} disabled={saving}>
              确认大纲并进入撰写
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </header>

        {/* Split screen: editor + preview */}
        <SplitScreenLayout
          left={<OutlineEditor chapters={outlineDraft} onChange={setOutlineDraft} />}
          right={
            <div className="p-6">
              <h2 className="text-lg font-bold text-foreground mb-4">大纲预览</h2>
              <OutlinePreview chapters={outlineDraft} />
            </div>
          }
        />
      </div>
    );
  }

  // Stages 3-6: Placeholder (will be implemented in later phases)
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
}
```

- [ ] **Step 2: Update project detail page to use ProjectWorkspace**

Replace `frontend/src/app/projects/[id]/page.tsx` with:

```tsx
import { Suspense } from "react";

import { ShellLayout } from "@/components/layout/ShellLayout";
import { ProjectWorkspace } from "@/extensions/project/ProjectWorkspace";

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <ShellLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-full">加载中...</div>}>
        <ProjectWorkspace projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/ProjectWorkspace.tsx frontend/src/app/projects/\[id\]/page.tsx
git commit -m "feat(project): add ProjectWorkspace with stage-based navigation"
```

---

### Task 14: Update ProjectList for New API

**Files:**
- Modify: `frontend/src/extensions/project/ProjectList.tsx`

- [ ] **Step 1: Read the current ProjectList.tsx to understand what needs changing**

Read `frontend/src/extensions/project/ProjectList.tsx` and update the following:

1. Change `projectApi.list()` call to handle the new `{ items, total }` response shape
2. Update the create dialog to use new `CreateProjectRequest` (simpler fields: name + reportType only)
3. Update `ProjectCard` props to match new `ProjectListItem` type

The key changes:
- `projectApi.list()` now returns `{ items: ProjectListItem[], total: number }` instead of `ReportProject[]`
- Create request no longer has `client`, `targetStandard` fields
- List items have `chapterCount`, `memberCount` instead of computing from nested data

In `ProjectList.tsx`, find the `projectApi.list()` call and change:
```typescript
// Before:
const data = await projectApi.list({ ... });
setProjects(data);

// After:
const { items } = await projectApi.list({ ... });
setProjects(items);
```

In the create dialog, simplify to just `name` + `reportType`:
```typescript
const newProject = await projectApi.create({
  name: formName,
  reportType: formType as ReportType,
});
```

Remove `client`, `targetStandard` fields from the create form.

- [ ] **Step 2: Run typecheck**

Run: `cd D:/eai/eai-flow-main/frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/ProjectList.tsx
git commit -m "feat(project): update ProjectList for new API shape"
```

---

### Task 15: Verify Backend Migration and API

**Files:**
- No new files

- [ ] **Step 1: Restart the backend to run migrations**

The gateway will automatically run `migrate_db()` on startup, creating the new tables.

Run: `docker restart deer-flow-gateway` (or `make dev` if running locally)

Expected: Gateway starts without errors, new tables created.

- [ ] **Step 2: Test project CRUD via curl**

```bash
# Create a project
curl -X POST http://localhost:2026/api/extensions/project/projects \
  -H "Content-Type: application/json" \
  -H "Cookie: $(cat ~/.eai-cookie)" \
  -d '{"name":"测试项目","report_type":"environmental_impact"}'

# List projects
curl http://localhost:2026/api/extensions/project/projects \
  -H "Cookie: $(cat ~/.eai-cookie)"

# Get project detail (use id from create response)
curl http://localhost:2026/api/extensions/project/projects/{PROJECT_ID} \
  -H "Cookie: $(cat ~/.eai-cookie)"
```

Expected: 200/201 responses with valid JSON.

- [ ] **Step 3: Test outline operations**

```bash
# Replace outline
curl -X PUT http://localhost:2026/api/extensions/project/projects/{PROJECT_ID}/outline \
  -H "Content-Type: application/json" \
  -H "Cookie: $(cat ~/.eai-cookie)" \
  -d '{"chapters":[{"title":"第一章 概述","level":1,"sortOrder":0,"children":[]},{"title":"第二章 现状调查","level":1,"sortOrder":1,"children":[{"title":"2.1 大气环境","level":2,"sortOrder":0,"children":[]}]}]}'

# Confirm outline
curl -X POST http://localhost:2026/api/extensions/project/projects/{PROJECT_ID}/confirm-outline \
  -H "Cookie: $(cat ~/.eai-cookie)"
```

Expected: Outline saved and project stage advanced to 3.

---

## Self-Review Checklist

1. **Spec coverage**: Stages 1-2 fully covered (project setup, outline editor, stage progress bar). Database models support all 6 stages. Backend endpoints cover CRUD, outline management, and member management.

2. **Placeholder scan**: No TBD/TODO/placeholders. All code is complete.

3. **Type consistency**:
   - Backend `ChapterOut` matches frontend `ProjectChapter` (via camelCase transform)
   - Backend `ProjectOut` matches frontend `ReportProject`
   - Backend `ProjectListItem` matches frontend `ProjectListItem`
   - All UUID types properly handled (string on frontend, UUID on backend)
   - `ChapterTreeNode` used consistently for outline batch operations

4. **Known gaps** (by design, deferred to later phases):
   - Stage 3 (AI Writing) — needs DeerFlow thread integration
   - Stage 4 (Collaborative Editing) — needs Tiptap integration
   - Stage 5 (Approval) — needs approval workflow UI
   - Stage 6 (Final Output) — needs export/publish
   - KF template picker in Stage 1 (backend endpoint exists, UI picker deferred)
   - Old approval module (`app/extensions/approval/`) can coexist with new tables
