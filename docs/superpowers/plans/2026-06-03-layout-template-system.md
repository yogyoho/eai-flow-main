# Layout Template System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete Layout Template management system so the Report Output page has real data — built-in seed templates plus user-created custom templates, stored in PostgreSQL via a new backend CRUD API.

**Architecture:** New backend module `backend/app/extensions/output/` with SQLAlchemy model, Pydantic schemas, service layer, and FastAPI router. Frontend gets a template editor modal and card action buttons. Seed function inserts 4 built-in templates on first startup.

**Tech Stack:** SQLAlchemy 2.0 async, Pydantic v2, FastAPI, PostgreSQL, React 19, TypeScript, Tailwind CSS 4

---

## File Structure

### Backend (new module)

| File | Responsibility |
|------|---------------|
| `backend/app/extensions/output/__init__.py` | Module marker (empty) |
| `backend/app/extensions/output/models.py` | SQLAlchemy `LayoutTemplate` model |
| `backend/app/extensions/output/schemas.py` | Pydantic request/response schemas |
| `backend/app/extensions/output/service.py` | CRUD business logic |
| `backend/app/extensions/output/routers.py` | FastAPI router with 5 endpoints |
| `backend/app/extensions/output/seed.py` | Built-in template seed data + idempotent seed function |

### Backend (modify existing)

| File | Change |
|------|--------|
| `backend/app/extensions/database.py` | Add `layout_templates` CREATE TABLE in `migrate_db()` |
| `backend/app/gateway/app.py` | Import + register output router |

### Frontend (new)

| File | Responsibility |
|------|---------------|
| `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` | Collapsible-section form for creating/editing templates |

### Frontend (modify existing)

| File | Change |
|------|--------|
| `frontend/src/extensions/output/types.ts` | Add `isBuiltin` to `LayoutTemplate` |
| `frontend/src/extensions/output/transforms.ts` | Map `is_builtin` → `isBuiltin` |
| `frontend/src/extensions/output/api.ts` | Add `createTemplate`, `updateTemplate`, `deleteTemplate` |
| `frontend/src/extensions/output/components/LayoutTemplateCard.tsx` | Add hover actions (edit/duplicate/delete) |
| `frontend/src/extensions/output/OutputManager.tsx` | Add "新建模板" button, wire editor modal |

### Tests

| File | Purpose |
|------|---------|
| `backend/tests/test_layout_template.py` | CRUD endpoint tests |

---

## Task 1: Backend — Database Migration

**Files:**
- Modify: `backend/app/extensions/database.py` — inside `migrate_db()` function

- [ ] **Step 1: Add `layout_templates` CREATE TABLE to `migrate_db()`**

Find the end of the `migrate_db()` function (before the final closing of the async context manager) and add the table creation. The table follows the existing pattern of `CREATE TABLE IF NOT EXISTS` with all columns inline.

```python
        # --- Layout Templates ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS layout_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(200) NOT NULL,
                report_type VARCHAR(100) NOT NULL,
                is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
                page_settings JSONB NOT NULL,
                cover_template JSONB,
                toc_settings JSONB,
                body_styles JSONB NOT NULL,
                heading_styles JSONB NOT NULL DEFAULT '[]',
                table_styles JSONB,
                figure_styles JSONB,
                header_footer JSONB,
                reference_style VARCHAR(50) NOT NULL DEFAULT 'gb7714',
                appendix_rules JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
```

- [ ] **Step 2: Restart gateway and verify table creation**

Run: `docker compose -p eai-docker restart gateway`
Then verify: `docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "\d layout_templates"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/database.py
git commit -m "feat(output): add layout_templates table migration"
```

---

## Task 2: Backend — SQLAlchemy Model + Pydantic Schemas

**Files:**
- Create: `backend/app/extensions/output/__init__.py`
- Create: `backend/app/extensions/output/models.py`
- Create: `backend/app/extensions/output/schemas.py`

- [ ] **Step 1: Create module `__init__.py`**

Create an empty file at `backend/app/extensions/output/__init__.py`.

- [ ] **Step 2: Create SQLAlchemy model**

Create `backend/app/extensions/output/models.py`:

```python
"""SQLAlchemy model for layout_templates table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class LayoutTemplate(Base):
    __tablename__ = "layout_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cover_template: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    toc_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    body_styles: Mapped[dict] = mapped_column(JSONB, nullable=False)
    heading_styles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    table_styles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    figure_styles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    header_footer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reference_style: Mapped[str] = mapped_column(String(50), nullable=False, default="gb7714")
    appendix_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: Create Pydantic schemas**

Create `backend/app/extensions/output/schemas.py`:

```python
"""Pydantic schemas for layout template CRUD."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Nested schemas (mirror frontend types.ts exactly) ---

class PageSettingsSchema(BaseModel):
    paperSize: str = "A4"
    orientation: str = "portrait"
    marginTop: float = 2.54
    marginBottom: float = 2.54
    marginLeft: float = 3.17
    marginRight: float = 3.17


class CoverTemplateSchema(BaseModel):
    showLogo: bool = True
    logoPosition: str = "center"
    showTitle: bool = True
    showClient: bool = True
    showDate: bool = True
    showProjectNumber: bool = True


class TocSettingsSchema(BaseModel):
    maxDepth: int = 3
    showPageNumbers: bool = True
    leaderDots: bool = True


class BodyStylesSchema(BaseModel):
    fontFamily: str = "宋体"
    fontSize: int = 12
    lineHeight: float = 1.5
    paragraphSpacing: int = 6
    firstLineIndent: int = 2


class HeadingStyleSchema(BaseModel):
    level: int
    fontFamily: str = "黑体"
    fontSize: int = 14
    fontWeight: int = 700
    color: str = "#333333"
    numbering: str = "decimal"


class TableStylesSchema(BaseModel):
    headerBg: str = "#2B579A"
    headerColor: str = "#FFFFFF"
    borderColor: str = "#CCCCCC"
    stripeRows: bool = True


class FigureStylesSchema(BaseModel):
    captionPosition: str = "below"
    numbering: str = "chapter"
    showSource: bool = True


class HeaderFooterSchema(BaseModel):
    headerText: str = ""
    footerText: str = ""
    showPageNumber: bool = True
    showLogo: bool = False


class AppendixRulesSchema(BaseModel):
    numbering: str = "A-B-C"
    separateToc: bool = False


# --- Create / Update / Response ---

class LayoutTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str = Field(..., min_length=1, max_length=100)
    page_settings: PageSettingsSchema
    cover_template: CoverTemplateSchema | None = None
    toc_settings: TocSettingsSchema | None = None
    body_styles: BodyStylesSchema
    heading_styles: list[HeadingStyleSchema] = Field(default_factory=list)
    table_styles: TableStylesSchema | None = None
    figure_styles: FigureStylesSchema | None = None
    header_footer: HeaderFooterSchema | None = None
    reference_style: str = "gb7714"
    appendix_rules: AppendixRulesSchema | None = None


class LayoutTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    report_type: str | None = Field(None, min_length=1, max_length=100)
    page_settings: PageSettingsSchema | None = None
    cover_template: CoverTemplateSchema | None = None
    toc_settings: TocSettingsSchema | None = None
    body_styles: BodyStylesSchema | None = None
    heading_styles: list[HeadingStyleSchema] | None = None
    table_styles: TableStylesSchema | None = None
    figure_styles: FigureStylesSchema | None = None
    header_footer: HeaderFooterSchema | None = None
    reference_style: str | None = None
    appendix_rules: AppendixRulesSchema | None = None


class LayoutTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    is_builtin: bool
    page_settings: dict
    cover_template: dict | None = None
    toc_settings: dict | None = None
    body_styles: dict
    heading_styles: list
    table_styles: dict | None = None
    figure_styles: dict | None = None
    header_footer: dict | None = None
    reference_style: str
    appendix_rules: dict | None = None
    created_at: datetime
    updated_at: datetime


class LayoutTemplateListResponse(BaseModel):
    items: list[LayoutTemplateResponse]
    total: int
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/output/__init__.py backend/app/extensions/output/models.py backend/app/extensions/output/schemas.py
git commit -m "feat(output): add LayoutTemplate model and Pydantic schemas"
```

---

## Task 3: Backend — Service Layer + Router

**Files:**
- Create: `backend/app/extensions/output/service.py`
- Create: `backend/app/extensions/output/routers.py`

- [ ] **Step 1: Create service layer**

Create `backend/app/extensions/output/service.py`:

```python
"""Business logic for layout template CRUD."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.output.models import LayoutTemplate
from app.extensions.output.schemas import LayoutTemplateCreate, LayoutTemplateUpdate

logger = logging.getLogger(__name__)


class LayoutTemplateService:
    @staticmethod
    async def list_templates(db: AsyncSession) -> list[LayoutTemplate]:
        stmt = select(LayoutTemplate).order_by(LayoutTemplate.is_builtin.desc(), LayoutTemplate.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_template(db: AsyncSession, template_id: uuid.UUID) -> LayoutTemplate | None:
        return await db.get(LayoutTemplate, template_id)

    @staticmethod
    async def create_template(db: AsyncSession, data: LayoutTemplateCreate) -> LayoutTemplate:
        template = LayoutTemplate(
            name=data.name,
            report_type=data.report_type,
            page_settings=data.page_settings.model_dump(),
            cover_template=data.cover_template.model_dump() if data.cover_template else None,
            toc_settings=data.toc_settings.model_dump() if data.toc_settings else None,
            body_styles=data.body_styles.model_dump(),
            heading_styles=[h.model_dump() for h in data.heading_styles],
            table_styles=data.table_styles.model_dump() if data.table_styles else None,
            figure_styles=data.figure_styles.model_dump() if data.figure_styles else None,
            header_footer=data.header_footer.model_dump() if data.header_footer else None,
            reference_style=data.reference_style,
            appendix_rules=data.appendix_rules.model_dump() if data.appendix_rules else None,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def update_template(
        db: AsyncSession, template: LayoutTemplate, data: LayoutTemplateUpdate
    ) -> LayoutTemplate:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return template

        for field, value in update_data.items():
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
                value = [v.model_dump() for v in value]
            setattr(template, field, value)

        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def delete_template(db: AsyncSession, template: LayoutTemplate) -> None:
        await db.delete(template)
        await db.commit()

    @staticmethod
    async def duplicate_template(db: AsyncSession, template: LayoutTemplate) -> LayoutTemplate:
        new_template = LayoutTemplate(
            name=f"{template.name} (副本)",
            report_type=template.report_type,
            page_settings=dict(template.page_settings),
            cover_template=dict(template.cover_template) if template.cover_template else None,
            toc_settings=dict(template.toc_settings) if template.toc_settings else None,
            body_styles=dict(template.body_styles),
            heading_styles=list(template.heading_styles),
            table_styles=dict(template.table_styles) if template.table_styles else None,
            figure_styles=dict(template.figure_styles) if template.figure_styles else None,
            header_footer=dict(template.header_footer) if template.header_footer else None,
            reference_style=template.reference_style,
            appendix_rules=dict(template.appendix_rules) if template.appendix_rules else None,
        )
        db.add(new_template)
        await db.commit()
        await db.refresh(new_template)
        return new_template
```

- [ ] **Step 2: Create FastAPI router**

Create `backend/app/extensions/output/routers.py`:

```python
"""FastAPI router for layout template CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.output.schemas import (
    LayoutTemplateCreate,
    LayoutTemplateListResponse,
    LayoutTemplateResponse,
    LayoutTemplateUpdate,
)
from app.extensions.output.service import LayoutTemplateService

router = APIRouter(prefix="/api/extensions/output", tags=["output"])


@router.get("/templates", response_model=LayoutTemplateListResponse)
async def list_templates(db: AsyncSession = Depends(get_db)):
    templates = await LayoutTemplateService.list_templates(db)
    return LayoutTemplateListResponse(
        items=[LayoutTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


@router.get("/templates/{template_id}", response_model=LayoutTemplateResponse)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return LayoutTemplateResponse.model_validate(template)


@router.post("/templates", response_model=LayoutTemplateResponse, status_code=201)
async def create_template(data: LayoutTemplateCreate, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.create_template(db, data)
    return LayoutTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=LayoutTemplateResponse)
async def update_template(
    template_id: UUID,
    data: LayoutTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    updated = await LayoutTemplateService.update_template(db, template, data)
    return LayoutTemplateResponse.model_validate(updated)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in templates cannot be deleted")
    await LayoutTemplateService.delete_template(db, template)


@router.post("/templates/{template_id}/duplicate", response_model=LayoutTemplateResponse, status_code=201)
async def duplicate_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    duplicated = await LayoutTemplateService.duplicate_template(db, template)
    return LayoutTemplateResponse.model_validate(duplicated)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/output/service.py backend/app/extensions/output/routers.py
git commit -m "feat(output): add layout template CRUD service and router"
```

---

## Task 4: Backend — Register Router + Seed Data

**Files:**
- Create: `backend/app/extensions/output/seed.py`
- Modify: `backend/app/gateway/app.py`

- [ ] **Step 1: Create seed module**

Create `backend/app/extensions/output/seed.py`:

```python
"""Built-in layout templates — seeded idempotently on first startup."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.output.models import LayoutTemplate

logger = logging.getLogger(__name__)

# Deterministic UUIDs for built-in templates (so re-seeding is safe)
BUILTIN_TEMPLATES = [
    {
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "环评报告（国标）",
        "report_type": "environmental_assessment",
        "page_settings": {
            "paperSize": "A4", "orientation": "portrait",
            "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17,
        },
        "body_styles": {
            "fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5,
            "paragraphSpacing": 6, "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "黑体", "fontSize": 12, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True, "logoPosition": "center",
            "showTitle": True, "showClient": True, "showDate": True, "showProjectNumber": True,
        },
        "toc_settings": {"maxDepth": 3, "showPageNumbers": True, "leaderDots": True},
        "table_styles": {"headerBg": "#2B579A", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": True},
        "figure_styles": {"captionPosition": "below", "numbering": "chapter", "showSource": True},
        "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": False},
        "reference_style": "gb7714",
        "appendix_rules": {"numbering": "A-B-C", "separateToc": False},
    },
    {
        "id": "00000000-0000-4000-8000-000000000002",
        "name": "可行性研究报告",
        "report_type": "feasibility_study",
        "page_settings": {
            "paperSize": "A4", "orientation": "portrait",
            "marginTop": 2.5, "marginBottom": 2.5, "marginLeft": 2.8, "marginRight": 2.8,
        },
        "body_styles": {
            "fontFamily": "仿宋", "fontSize": 12, "lineHeight": 1.5,
            "paragraphSpacing": 6, "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "黑体", "fontSize": 13, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 4, "fontFamily": "楷体", "fontSize": 12, "fontWeight": 700, "color": "#444444", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True, "logoPosition": "center",
            "showTitle": True, "showClient": True, "showDate": True, "showProjectNumber": True,
        },
        "toc_settings": {"maxDepth": 4, "showPageNumbers": True, "leaderDots": True},
        "table_styles": {"headerBg": "#1F4E79", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": True},
        "figure_styles": {"captionPosition": "below", "numbering": "chapter", "showSource": True},
        "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": False},
        "reference_style": "gb7714",
        "appendix_rules": {"numbering": "A-B-C", "separateToc": False},
    },
    {
        "id": "00000000-0000-4000-8000-000000000003",
        "name": "技术咨询报告",
        "report_type": "technical_consulting",
        "page_settings": {
            "paperSize": "A4", "orientation": "portrait",
            "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17,
        },
        "body_styles": {
            "fontFamily": "微软雅黑", "fontSize": 11, "lineHeight": 1.75,
            "paragraphSpacing": 8, "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "微软雅黑", "fontSize": 15, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 2, "fontFamily": "微软雅黑", "fontSize": 13, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "微软雅黑", "fontSize": 12, "fontWeight": 600, "color": "#444444", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True, "logoPosition": "left",
            "showTitle": True, "showClient": True, "showDate": True, "showProjectNumber": False,
        },
        "toc_settings": {"maxDepth": 3, "showPageNumbers": True, "leaderDots": True},
        "table_styles": {"headerBg": "#3B5998", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": True},
        "figure_styles": {"captionPosition": "below", "numbering": "chapter", "showSource": True},
        "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": True},
        "reference_style": "gb7714",
        "appendix_rules": {"numbering": "A-B-C", "separateToc": False},
    },
    {
        "id": "00000000-0000-4000-8000-000000000004",
        "name": "通用A4报告",
        "report_type": "general",
        "page_settings": {
            "paperSize": "A4", "orientation": "portrait",
            "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17,
        },
        "body_styles": {
            "fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5,
            "paragraphSpacing": 6, "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "none"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "none"},
        ],
        "cover_template": {
            "showLogo": False, "logoPosition": "center",
            "showTitle": True, "showClient": False, "showDate": True, "showProjectNumber": False,
        },
        "toc_settings": {"maxDepth": 2, "showPageNumbers": True, "leaderDots": True},
        "table_styles": {"headerBg": "#F0F0F0", "headerColor": "#333333", "borderColor": "#CCCCCC", "stripeRows": False},
        "figure_styles": {"captionPosition": "below", "numbering": "continuous", "showSource": False},
        "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": False},
        "reference_style": "gb7714",
        "appendix_rules": {"numbering": "A-B-C", "separateToc": False},
    },
]


async def seed_builtin_templates(db: AsyncSession) -> None:
    """Insert built-in templates if none exist. Idempotent."""
    import uuid

    stmt = select(LayoutTemplate).where(LayoutTemplate.is_builtin.is_(True)).limit(1)
    result = await db.execute(stmt)
    if result.scalars().first():
        return

    for tpl_data in BUILTIN_TEMPLATES:
        template = LayoutTemplate(
            id=uuid.UUID(tpl_data["id"]),
            name=tpl_data["name"],
            report_type=tpl_data["report_type"],
            is_builtin=True,
            page_settings=tpl_data["page_settings"],
            body_styles=tpl_data["body_styles"],
            heading_styles=tpl_data["heading_styles"],
            cover_template=tpl_data.get("cover_template"),
            toc_settings=tpl_data.get("toc_settings"),
            table_styles=tpl_data.get("table_styles"),
            figure_styles=tpl_data.get("figure_styles"),
            header_footer=tpl_data.get("header_footer"),
            reference_style=tpl_data.get("reference_style", "gb7714"),
            appendix_rules=tpl_data.get("appendix_rules"),
        )
        db.add(template)

    await db.commit()
    logger.info("Seeded %d built-in layout templates", len(BUILTIN_TEMPLATES))
```

- [ ] **Step 2: Register router in gateway app.py**

In `backend/app/gateway/app.py`, add the import near the other extension imports (around line 30-49):

```python
from app.extensions.output.routers import router as output_router
```

And add the router registration near the other `app.include_router(...)` calls (around line 470):

```python
# Layout template management API
app.include_router(output_router)
```

- [ ] **Step 3: Call seed function during startup**

In `backend/app/gateway/app.py`, find the lifespan function where `await migrate_db()` is called. After that line, add:

```python
    from app.extensions.database import get_db_context
    from app.extensions.output.seed import seed_builtin_templates

    async with get_db_context() as db:
        await seed_builtin_templates(db)
```

- [ ] **Step 4: Restart gateway and verify**

Run: `docker compose -p eai-docker restart gateway`

Then verify seed data:
```
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT id, name, report_type, is_builtin FROM layout_templates"
```

Expected: 4 rows with `is_builtin = true`.

Then verify API:
```
curl -s http://localhost:8001/api/extensions/output/templates | python -m json.tool
```

Expected: JSON with `items` array of 4 templates.

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/seed.py backend/app/gateway/app.py
git commit -m "feat(output): add built-in template seed data and register router"
```

---

## Task 5: Backend — Tests

**Files:**
- Create: `backend/tests/test_layout_template.py`

- [ ] **Step 1: Write CRUD tests**

Create `backend/tests/test_layout_template.py`:

```python
"""Tests for layout template CRUD endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_templates_empty_seeded(client: AsyncClient) -> None:
    """List returns built-in templates after seed."""
    resp = await client.get("/api/extensions/output/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_create_and_get_template(client: AsyncClient) -> None:
    """Create a template and retrieve it by ID."""
    create_payload = {
        "name": "Test Template",
        "report_type": "general",
        "page_settings": {
            "paperSize": "A4",
            "orientation": "portrait",
            "marginTop": 2.54,
            "marginBottom": 2.54,
            "marginLeft": 3.17,
            "marginRight": 3.17,
        },
        "body_styles": {
            "fontFamily": "宋体",
            "fontSize": 12,
            "lineHeight": 1.5,
            "paragraphSpacing": 6,
            "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
        ],
        "reference_style": "gb7714",
    }
    resp = await client.post("/api/extensions/output/templates", json=create_payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Test Template"
    assert created["is_builtin"] is False
    template_id = created["id"]

    # Get by ID
    resp = await client.get(f"/api/extensions/output/templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Template"


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient) -> None:
    """Update a custom template's name."""
    create_payload = {
        "name": "Before Update",
        "report_type": "general",
        "page_settings": {"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        "body_styles": {"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 6, "firstLineIndent": 2},
        "heading_styles": [],
        "reference_style": "gb7714",
    }
    resp = await client.post("/api/extensions/output/templates", json=create_payload)
    template_id = resp.json()["id"]

    resp = await client.put(
        f"/api/extensions/output/templates/{template_id}",
        json={"name": "After Update"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "After Update"


@pytest.mark.asyncio
async def test_delete_custom_template(client: AsyncClient) -> None:
    """Delete a custom template returns 204."""
    create_payload = {
        "name": "To Delete",
        "report_type": "general",
        "page_settings": {"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        "body_styles": {"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 6, "firstLineIndent": 2},
        "heading_styles": [],
        "reference_style": "gb7714",
    }
    resp = await client.post("/api/extensions/output/templates", json=create_payload)
    template_id = resp.json()["id"]

    resp = await client.delete(f"/api/extensions/output/templates/{template_id}")
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(f"/api/extensions/output/templates/{template_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_builtin_template_forbidden(client: AsyncClient) -> None:
    """Deleting a built-in template returns 403."""
    # Use one of the deterministic built-in IDs
    builtin_id = "00000000-0000-4000-8000-000000000001"
    resp = await client.delete(f"/api/extensions/output/templates/{builtin_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_template(client: AsyncClient) -> None:
    """Duplicate creates a copy with '(副本)' suffix."""
    create_payload = {
        "name": "Original",
        "report_type": "general",
        "page_settings": {"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        "body_styles": {"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 6, "firstLineIndent": 2},
        "heading_styles": [],
        "reference_style": "gb7714",
    }
    resp = await client.post("/api/extensions/output/templates", json=create_payload)
    template_id = resp.json()["id"]

    resp = await client.post(f"/api/extensions/output/templates/{template_id}/duplicate")
    assert resp.status_code == 201
    assert resp.json()["name"] == "Original (副本)"
    assert resp.json()["is_builtin"] is False


@pytest.mark.asyncio
async def test_get_nonexistent_template(client: AsyncClient) -> None:
    """GET a non-existent template returns 404."""
    resp = await client.get("/api/extensions/output/templates/00000000-1111-2222-3333-444444444444")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_layout_template.py -v`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_layout_template.py
git commit -m "test(output): add CRUD endpoint tests for layout templates"
```

---

## Task 6: Frontend — Update Types + API + Transforms

**Files:**
- Modify: `frontend/src/extensions/output/types.ts`
- Modify: `frontend/src/extensions/output/transforms.ts`
- Modify: `frontend/src/extensions/output/api.ts`

- [ ] **Step 1: Add `isBuiltin` to `LayoutTemplate` type**

In `frontend/src/extensions/output/types.ts`, add `isBuiltin: boolean` field to the `LayoutTemplate` interface after the `reportType` field:

```typescript
export interface LayoutTemplate {
  id: string;
  name: string;
  reportType: string;
  isBuiltin: boolean;  // <-- add this line
  pageSettings: PageSettings;
  // ... rest unchanged
```

- [ ] **Step 2: Update `transformTemplate` to map `is_builtin`**

In `frontend/src/extensions/output/transforms.ts`, add the mapping in `transformTemplate`:

```typescript
export function transformTemplate(data: Record<string, unknown>): LayoutTemplate {
  return {
    id: data.id as string,
    name: data.name as string,
    reportType: data.report_type as string,
    isBuiltin: (data.is_builtin as boolean) ?? false,  // <-- add this line
    pageSettings: data.page_settings as LayoutTemplate["pageSettings"],
    // ... rest unchanged
```

- [ ] **Step 3: Add CRUD methods to `outputApi`**

In `frontend/src/extensions/output/api.ts`, add three new methods to the `outputApi` object:

```typescript
  createTemplate: async (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">): Promise<LayoutTemplate> => {
    const payload: Record<string, unknown> = {
      name: data.name,
      report_type: data.reportType,
      page_settings: data.pageSettings,
      body_styles: data.bodyStyles,
      heading_styles: data.headingStyles ?? [],
      reference_style: data.referenceStyle ?? "gb7714",
    };
    if (data.coverTemplate) payload.cover_template = data.coverTemplate;
    if (data.tocSettings) payload.toc_settings = data.tocSettings;
    if (data.tableStyles) payload.table_styles = data.tableStyles;
    if (data.figureStyles) payload.figure_styles = data.figureStyles;
    if (data.headerFooter) payload.header_footer = data.headerFooter;
    if (data.appendixRules) payload.appendix_rules = data.appendixRules;

    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return transformTemplate(resp);
  },

  updateTemplate: async (id: string, data: Partial<Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">>): Promise<LayoutTemplate> => {
    const payload: Record<string, unknown> = {};
    if (data.name !== undefined) payload.name = data.name;
    if (data.reportType !== undefined) payload.report_type = data.reportType;
    if (data.pageSettings !== undefined) payload.page_settings = data.pageSettings;
    if (data.bodyStyles !== undefined) payload.body_styles = data.bodyStyles;
    if (data.headingStyles !== undefined) payload.heading_styles = data.headingStyles;
    if (data.coverTemplate !== undefined) payload.cover_template = data.coverTemplate;
    if (data.tocSettings !== undefined) payload.toc_settings = data.tocSettings;
    if (data.tableStyles !== undefined) payload.table_styles = data.tableStyles;
    if (data.figureStyles !== undefined) payload.figure_styles = data.figureStyles;
    if (data.headerFooter !== undefined) payload.header_footer = data.headerFooter;
    if (data.referenceStyle !== undefined) payload.reference_style = data.referenceStyle;
    if (data.appendixRules !== undefined) payload.appendix_rules = data.appendixRules;

    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    return transformTemplate(resp);
  },

  deleteTemplate: async (id: string): Promise<void> => {
    await authFetch<void>(`${API_BASE}/templates/${id}`, {
      method: "DELETE",
    });
  },

  duplicateTemplate: async (id: string): Promise<LayoutTemplate> => {
    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}/duplicate`, {
      method: "POST",
    });
    return transformTemplate(resp);
  },
```

Also add the missing imports at the top of `api.ts` if `LayoutTemplate` is not already imported:

```typescript
import type { GenerateOutputRequest, GenerateOutputResult, HistoryEntry, LayoutTemplate } from "./types";
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/output/types.ts frontend/src/extensions/output/transforms.ts frontend/src/extensions/output/api.ts
git commit -m "feat(output): add isBuiltin type, CRUD API methods for layout templates"
```

---

## Task 7: Frontend — LayoutTemplateEditor Component

**Files:**
- Create: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`

- [ ] **Step 1: Create the template editor component**

Create `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` — a modal dialog with collapsible sections for all layout template fields. The component receives an optional `template` prop for editing mode (null = create mode).

```typescript
"use client";

import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import React, { useState, useCallback } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import type {
  AppendixRules,
  BodyStyles,
  CoverTemplate,
  FigureStyles,
  HeaderFooter,
  HeadingStyle,
  LayoutTemplate,
  PageSettings,
  TableStyles,
  TocSettings,
} from "@/extensions/output/types";
import { cn } from "@/lib/utils";

// --- Section toggle ---
function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors"
      >
        {title}
        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && <div className="border-t border-border px-4 py-4 space-y-4">{children}</div>}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-sm font-medium text-foreground">{children}</label>;
}

const PAPER_OPTIONS = [
  { value: "A4", label: "A4" },
  { value: "A3", label: "A3" },
  { value: "B5", label: "B5" },
  { value: "letter", label: "Letter" },
];

const ORIENTATION_OPTIONS = [
  { value: "portrait", label: "纵向" },
  { value: "landscape", label: "横向" },
];

const REFERENCE_OPTIONS = [
  { value: "gb7714", label: "GB/T 7714" },
  { value: "apa", label: "APA" },
  { value: "mla", label: "MLA" },
  { value: "chicago", label: "Chicago" },
];

const APPENDIX_NUMBERING_OPTIONS = [
  { value: "A-B-C", label: "A-B-C" },
  { value: "I-II-III", label: "I-II-III" },
  { value: "1-2-3", label: "1-2-3" },
];

const HEADING_NUMBERING_OPTIONS = [
  { value: "decimal", label: "1, 2, 3" },
  { value: "chinese", label: "一, 二, 三" },
  { value: "none", label: "无编号" },
];

const CAPTION_POSITION_OPTIONS = [
  { value: "above", label: "图上方" },
  { value: "below", label: "图下方" },
];

const FIGURE_NUMBERING_OPTIONS = [
  { value: "chapter", label: "按章节" },
  { value: "continuous", label: "连续编号" },
];

const REPORT_TYPE_OPTIONS = [
  { value: "environmental_assessment", label: "环评报告" },
  { value: "feasibility_study", label: "可行性研究报告" },
  { value: "technical_consulting", label: "技术咨询报告" },
  { value: "general", label: "通用报告" },
];

interface LayoutTemplateEditorProps {
  template: LayoutTemplate | null;
  onSave: (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">) => Promise<void>;
  onCancel: () => void;
}

const DEFAULT_PAGE_SETTINGS: PageSettings = {
  paperSize: "A4", orientation: "portrait",
  marginTop: 2.54, marginBottom: 2.54, marginLeft: 3.17, marginRight: 3.17,
};

const DEFAULT_BODY_STYLES: BodyStyles = {
  fontFamily: "宋体", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 6, firstLineIndent: 2,
};

const DEFAULT_HEADING_STYLES: HeadingStyle[] = [
  { level: 1, fontFamily: "黑体", fontSize: 16, fontWeight: 700, color: "#333333", numbering: "decimal" },
  { level: 2, fontFamily: "黑体", fontSize: 14, fontWeight: 700, color: "#333333", numbering: "decimal" },
];

export function LayoutTemplateEditor({ template, onSave, onCancel }: LayoutTemplateEditorProps) {
  const isEdit = template !== null;

  const [name, setName] = useState(template?.name ?? "");
  const [reportType, setReportType] = useState(template?.reportType ?? "general");
  const [pageSettings, setPageSettings] = useState<PageSettings>(template?.pageSettings ?? DEFAULT_PAGE_SETTINGS);
  const [coverTemplate, setCoverTemplate] = useState<CoverTemplate | null>(template?.coverTemplate ?? null);
  const [tocSettings, setTocSettings] = useState<TocSettings | null>(template?.tocSettings ?? null);
  const [bodyStyles, setBodyStyles] = useState<BodyStyles>(template?.bodyStyles ?? DEFAULT_BODY_STYLES);
  const [headingStyles, setHeadingStyles] = useState<HeadingStyle[]>(template?.headingStyles ?? DEFAULT_HEADING_STYLES);
  const [tableStyles, setTableStyles] = useState<TableStyles | null>(template?.tableStyles ?? null);
  const [figureStyles, setFigureStyles] = useState<FigureStyles | null>(template?.figureStyles ?? null);
  const [headerFooter, setHeaderFooter] = useState<HeaderFooter | null>(template?.headerFooter ?? null);
  const [referenceStyle, setReferenceStyle] = useState(template?.referenceStyle ?? "gb7714");
  const [appendixRules, setAppendixRules] = useState<AppendixRules | null>(template?.appendixRules ?? null);

  const [saving, setSaving] = useState(false);

  const handleSave = useCallback(async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        reportType,
        pageSettings,
        coverTemplate,
        tocSettings,
        bodyStyles,
        headingStyles,
        tableStyles,
        figureStyles,
        headerFooter,
        referenceStyle,
        appendixRules,
      });
    } finally {
      setSaving(false);
    }
  }, [name, reportType, pageSettings, coverTemplate, tocSettings, bodyStyles, headingStyles, tableStyles, figureStyles, headerFooter, referenceStyle, appendixRules, onSave]);

  const updateHeading = (index: number, field: keyof HeadingStyle, value: string | number) => {
    setHeadingStyles((prev) => prev.map((h, i) => (i === index ? { ...h, [field]: value } : h)));
  };

  const addHeadingLevel = () => {
    const lastLevel = headingStyles[headingStyles.length - 1]?.level ?? 0;
    setHeadingStyles((prev) => [...prev, { level: lastLevel + 1, fontFamily: "黑体", fontSize: 12, fontWeight: 700, color: "#333333", numbering: "decimal" }]);
  };

  const removeHeadingLevel = (index: number) => {
    setHeadingStyles((prev) => prev.filter((_, i) => i !== index));
  };

  const inputCls = "w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20";
  const inlineInputCls = "w-20 rounded-md border border-border bg-muted px-2 py-1.5 text-sm text-center outline-none focus:border-primary focus:ring-1 focus:ring-primary/20";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
          <h2 className="text-lg font-semibold text-foreground">{isEdit ? "编辑排版模板" : "新建排版模板"}</h2>
          <button type="button" onClick={onCancel} className="text-muted-foreground hover:text-foreground text-sm">✕</button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {/* 基本信息 */}
          <Section title="基本信息" defaultOpen>
            <div className="space-y-3">
              <div>
                <FieldLabel>模板名称</FieldLabel>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：环评报告（国标）" className={inputCls} />
              </div>
              <div>
                <FieldLabel>报告类型</FieldLabel>
                <AdminSelect value={reportType} onChange={setReportType} options={REPORT_TYPE_OPTIONS} className="w-full" />
              </div>
            </div>
          </Section>

          {/* 页面设置 */}
          <Section title="页面设置" defaultOpen>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <FieldLabel>纸张尺寸</FieldLabel>
                <AdminSelect value={pageSettings.paperSize} onChange={(v) => setPageSettings({ ...pageSettings, paperSize: v as PageSettings["paperSize"] })} options={PAPER_OPTIONS} className="w-full" />
              </div>
              <div>
                <FieldLabel>方向</FieldLabel>
                <AdminSelect value={pageSettings.orientation} onChange={(v) => setPageSettings({ ...pageSettings, orientation: v as PageSettings["orientation"] })} options={ORIENTATION_OPTIONS} className="w-full" />
              </div>
            </div>
            <div>
              <FieldLabel>页边距 (cm)</FieldLabel>
              <div className="grid grid-cols-4 gap-3 mt-1">
                <div className="text-center"><span className="text-xs text-muted-foreground">上</span><input type="number" step="0.01" value={pageSettings.marginTop} onChange={(e) => setPageSettings({ ...pageSettings, marginTop: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">下</span><input type="number" step="0.01" value={pageSettings.marginBottom} onChange={(e) => setPageSettings({ ...pageSettings, marginBottom: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">左</span><input type="number" step="0.01" value={pageSettings.marginLeft} onChange={(e) => setPageSettings({ ...pageSettings, marginLeft: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">右</span><input type="number" step="0.01" value={pageSettings.marginRight} onChange={(e) => setPageSettings({ ...pageSettings, marginRight: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
              </div>
            </div>
          </Section>

          {/* 封面配置 */}
          <Section title="封面配置">
            <div className="grid grid-cols-2 gap-4">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showLogo ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showLogo: e.target.checked })} className="rounded" /> 显示Logo</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showTitle ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showTitle: e.target.checked })} className="rounded" /> 显示标题</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showClient ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showClient: e.target.checked })} className="rounded" /> 显示客户</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showDate ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showDate: e.target.checked })} className="rounded" /> 显示日期</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showProjectNumber ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showProjectNumber: e.target.checked })} className="rounded" /> 显示项目编号</label>
            </div>
          </Section>

          {/* 正文样式 */}
          <Section title="正文样式" defaultOpen>
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>字体</FieldLabel><input type="text" value={bodyStyles.fontFamily} onChange={(e) => setBodyStyles({ ...bodyStyles, fontFamily: e.target.value })} className={inputCls} /></div>
              <div><FieldLabel>字号 (pt)</FieldLabel><input type="number" value={bodyStyles.fontSize} onChange={(e) => setBodyStyles({ ...bodyStyles, fontSize: parseInt(e.target.value) || 12 })} className={inputCls} /></div>
              <div><FieldLabel>行高</FieldLabel><input type="number" step="0.1" value={bodyStyles.lineHeight} onChange={(e) => setBodyStyles({ ...bodyStyles, lineHeight: parseFloat(e.target.value) || 1.5 })} className={inputCls} /></div>
              <div><FieldLabel>段落间距 (pt)</FieldLabel><input type="number" value={bodyStyles.paragraphSpacing} onChange={(e) => setBodyStyles({ ...bodyStyles, paragraphSpacing: parseInt(e.target.value) || 0 })} className={inputCls} /></div>
              <div><FieldLabel>首行缩进 (字符)</FieldLabel><input type="number" value={bodyStyles.firstLineIndent} onChange={(e) => setBodyStyles({ ...bodyStyles, firstLineIndent: parseInt(e.target.value) || 0 })} className={inputCls} /></div>
            </div>
          </Section>

          {/* 标题样式 */}
          <Section title="标题样式">
            <div className="space-y-3">
              {headingStyles.map((h, i) => (
                <div key={i} className="flex items-end gap-3 rounded-lg border border-border/50 p-3">
                  <div className="shrink-0"><span className="text-xs font-medium text-muted-foreground">级别 {h.level}</span></div>
                  <div className="flex-1 grid grid-cols-5 gap-2">
                    <input type="text" value={h.fontFamily} onChange={(e) => updateHeading(i, "fontFamily", e.target.value)} placeholder="字体" className={inlineInputCls + " !w-full"} />
                    <input type="number" value={h.fontSize} onChange={(e) => updateHeading(i, "fontSize", parseInt(e.target.value) || 12)} placeholder="字号" className={inlineInputCls + " !w-full"} />
                    <input type="number" value={h.fontWeight} onChange={(e) => updateHeading(i, "fontWeight", parseInt(e.target.value) || 400)} placeholder="粗细" className={inlineInputCls + " !w-full"} />
                    <input type="color" value={h.color} onChange={(e) => updateHeading(i, "color", e.target.value)} className="h-9 w-full rounded border border-border cursor-pointer" />
                    <AdminSelect value={h.numbering} onChange={(v) => updateHeading(i, "numbering", v)} options={HEADING_NUMBERING_OPTIONS} className="w-full" />
                  </div>
                  <button type="button" onClick={() => removeHeadingLevel(i)} className="shrink-0 text-destructive text-xs hover:underline">删除</button>
                </div>
              ))}
              <button type="button" onClick={addHeadingLevel} className="text-sm text-primary hover:underline">+ 添加级别</button>
            </div>
          </Section>

          {/* 表格样式 */}
          <Section title="表格样式">
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>表头背景色</FieldLabel><input type="color" value={tableStyles?.headerBg ?? "#2B579A"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), headerBg: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div><FieldLabel>表头字色</FieldLabel><input type="color" value={tableStyles?.headerColor ?? "#FFFFFF"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), headerColor: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div><FieldLabel>边框色</FieldLabel><input type="color" value={tableStyles?.borderColor ?? "#CCCCCC"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), borderColor: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div className="flex items-end"><label className="flex items-center gap-2 text-sm pb-2"><input type="checkbox" checked={tableStyles?.stripeRows ?? true} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), stripeRows: e.target.checked })} className="rounded" /> 斑马纹</label></div>
            </div>
          </Section>

          {/* 图表样式 */}
          <Section title="图表样式">
            <div className="grid grid-cols-3 gap-4">
              <div><FieldLabel>标题位置</FieldLabel><AdminSelect value={figureStyles?.captionPosition ?? "below"} onChange={(v) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), captionPosition: v as "above" | "below" })} options={CAPTION_POSITION_OPTIONS} className="w-full" /></div>
              <div><FieldLabel>编号方式</FieldLabel><AdminSelect value={figureStyles?.numbering ?? "chapter"} onChange={(v) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), numbering: v as "chapter" | "continuous" })} options={FIGURE_NUMBERING_OPTIONS} className="w-full" /></div>
              <div className="flex items-end"><label className="flex items-center gap-2 text-sm pb-2"><input type="checkbox" checked={figureStyles?.showSource ?? true} onChange={(e) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), showSource: e.target.checked })} className="rounded" /> 显示来源</label></div>
            </div>
          </Section>

          {/* 页眉页脚 */}
          <Section title="页眉页脚">
            <div className="space-y-3">
              <div><FieldLabel>页眉文本</FieldLabel><input type="text" value={headerFooter?.headerText ?? ""} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), headerText: e.target.value })} className={inputCls} /></div>
              <div><FieldLabel>页脚文本</FieldLabel><input type="text" value={headerFooter?.footerText ?? ""} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), footerText: e.target.value })} className={inputCls} /></div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={headerFooter?.showPageNumber ?? true} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), showPageNumber: e.target.checked })} className="rounded" /> 显示页码</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={headerFooter?.showLogo ?? false} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), showLogo: e.target.checked })} className="rounded" /> 显示Logo</label>
              </div>
            </div>
          </Section>

          {/* 参考文献与附录 */}
          <Section title="参考文献与附录">
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>参考文献格式</FieldLabel><AdminSelect value={referenceStyle} onChange={setReferenceStyle} options={REFERENCE_OPTIONS} className="w-full" /></div>
              <div><FieldLabel>附录编号</FieldLabel><AdminSelect value={appendixRules?.numbering ?? "A-B-C"} onChange={(v) => setAppendixRules({ ...(appendixRules ?? { numbering: "A-B-C" as const, separateToc: false }), numbering: v as "A-B-C" | "I-II-III" | "1-2-3" })} options={APPENDIX_NUMBERING_OPTIONS} className="w-full" /></div>
            </div>
            <label className="flex items-center gap-2 text-sm mt-3"><input type="checkbox" checked={appendixRules?.separateToc ?? false} onChange={(e) => setAppendixRules({ ...(appendixRules ?? { numbering: "A-B-C" as const, separateToc: false }), separateToc: e.target.checked })} className="rounded" /> 附录独立目录</label>
          </Section>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4 shrink-0">
          <button type="button" onClick={onCancel} className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors">取消</button>
          <button type="button" onClick={handleSave} disabled={!name.trim() || saving} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> 保存中...</> : "保存模板"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output): add LayoutTemplateEditor component with collapsible sections"
```

---

## Task 8: Frontend — Update LayoutTemplateCard + OutputManager

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateCard.tsx`
- Modify: `frontend/src/extensions/output/OutputManager.tsx`

- [ ] **Step 1: Update LayoutTemplateCard with hover actions**

Replace the entire content of `frontend/src/extensions/output/components/LayoutTemplateCard.tsx`:

```typescript
"use client";

import { Copy, FileText, Pencil, Trash2 } from "lucide-react";
import React, { useState } from "react";
import { toast } from "sonner";

import { outputApi } from "@/extensions/output/api";
import type { LayoutTemplate } from "@/extensions/output/types";
import { cn } from "@/lib/utils";

interface LayoutTemplateCardProps {
  template: LayoutTemplate;
  onEdit?: (template: LayoutTemplate) => void;
  onRefresh?: () => void;
}

export function LayoutTemplateCard({ template, onEdit, onRefresh }: LayoutTemplateCardProps) {
  const [showActions, setShowActions] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDuplicate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await outputApi.duplicateTemplate(template.id);
      toast.success(`已复制「${template.name}」`);
      onRefresh?.();
    } catch {
      toast.error("复制失败");
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除「${template.name}」吗？此操作不可撤销。`)) return;
    setDeleting(true);
    try {
      await outputApi.deleteTemplate(template.id);
      toast.success(`已删除「${template.name}」`);
      onRefresh?.();
    } catch {
      toast.error("删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit?.(template);
  };

  return (
    <div
      className={cn(
        "relative rounded-xl border border-border bg-background p-5 shadow-sm",
        "transition-all hover:border-primary/30 hover:shadow-md",
        "text-left w-full",
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Action buttons — top right */}
      {showActions && !deleting && (
        <div className="absolute right-3 top-3 flex items-center gap-1 rounded-lg bg-background/90 p-1 shadow-sm border border-border/50 backdrop-blur-sm z-10">
          {!template.isBuiltin && (
            <button type="button" onClick={handleEdit} title="编辑" className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-primary transition-colors">
              <Pencil className="h-3.5 w-3.5" />
            </button>
          )}
          <button type="button" onClick={handleDuplicate} title="复制" className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-primary transition-colors">
            <Copy className="h-3.5 w-3.5" />
          </button>
          {!template.isBuiltin && (
            <button type="button" onClick={handleDelete} title="删除" className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="truncate text-sm font-medium text-foreground">
            {template.name}
          </h3>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              {template.reportType}
            </span>
            {template.isBuiltin && (
              <span className="inline-flex items-center rounded-full border border-muted-foreground/20 bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                内置
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-1.5 border-t border-border/50 pt-3 text-xs text-muted-foreground">
        {template.pageSettings && (
          <div className="flex justify-between">
            <span>页面尺寸</span>
            <span className="text-foreground">
              {template.pageSettings.paperSize}
              {template.pageSettings.orientation === "landscape" ? " 横向" : " 纵向"}
            </span>
          </div>
        )}
        {template.bodyStyles && (
          <div className="flex justify-between">
            <span>正文字体</span>
            <span className="text-foreground">
              {template.bodyStyles.fontFamily} {template.bodyStyles.fontSize}pt
            </span>
          </div>
        )}
        {template.referenceStyle && (
          <div className="flex justify-between">
            <span>参考文献</span>
            <span className="text-foreground">{template.referenceStyle}</span>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update OutputManager — add create button + editor modal wiring**

In `frontend/src/extensions/output/OutputManager.tsx`, make these changes:

1. Add imports at the top:

```typescript
import { Plus } from "lucide-react";  // add to existing lucide import
import { toast } from "sonner";        // new import

import { LayoutTemplateEditor } from "./components/LayoutTemplateEditor";  // new import
import type { LayoutTemplate } from "./types";  // new import
```

2. Update the `TemplatesTab` component to include a "新建模板" button and the editor modal. Replace the entire `TemplatesTab` function:

```typescript
function TemplatesTab() {
  const [templates, setTemplates] = useState<LayoutTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<LayoutTemplate | null>(null);

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await outputApi.listTemplates();
      setTemplates(data);
    } catch (err) {
      if ((err as Error & { status?: number })?.status === 404) {
        setTemplates([]);
      } else {
        setError(err instanceof Error ? err.message : "加载模板失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const handleCreateSave = useCallback(
    async (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">) => {
      await outputApi.createTemplate(data);
      toast.success("模板已创建");
      setShowEditor(false);
      loadTemplates();
    },
    [loadTemplates],
  );

  const handleEditSave = useCallback(
    async (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">) => {
      if (!editingTemplate) return;
      await outputApi.updateTemplate(editingTemplate.id, data);
      toast.success("模板已更新");
      setEditingTemplate(null);
      loadTemplates();
    },
    [editingTemplate, loadTemplates],
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mb-4 h-8 w-8 animate-spin" />
        <span>加载模板中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-destructive">
        <span className="mb-2 text-lg">加载失败</span>
        <span className="mb-4 text-sm text-muted-foreground">{error}</span>
        <button
          type="button"
          className="rounded-lg bg-destructive px-4 py-2 text-sm text-white hover:bg-destructive/90"
          onClick={() => void loadTemplates()}
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">共 {templates.length} 个模板</span>
        <button
          type="button"
          onClick={() => setShowEditor(true)}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          新建模板
        </button>
      </div>

      {templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <FileText className="mb-4 h-12 w-12" />
          <span className="mb-2 text-lg">暂无排版模板</span>
          <span className="text-sm">点击上方「新建模板」创建第一个排版模板</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => (
            <LayoutTemplateCard
              key={template.id}
              template={template}
              onEdit={(t) => setEditingTemplate(t)}
              onRefresh={loadTemplates}
            />
          ))}
        </div>
      )}

      {showEditor && (
        <LayoutTemplateEditor
          template={null}
          onSave={handleCreateSave}
          onCancel={() => setShowEditor(false)}
        />
      )}
      {editingTemplate && (
        <LayoutTemplateEditor
          template={editingTemplate}
          onSave={handleEditSave}
          onCancel={() => setEditingTemplate(null)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd frontend && pnpm typecheck`

Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateCard.tsx frontend/src/extensions/output/OutputManager.tsx
git commit -m "feat(output): template card actions + create/edit modal in OutputManager"
```

---

## Task 9: Integration Verification

- [ ] **Step 1: Restart all containers**

```bash
docker compose -p eai-docker restart gateway frontend
```

- [ ] **Step 2: Verify the full flow in browser**

1. Open `http://localhost:2026/output?tab=templates`
2. Verify 4 built-in template cards are displayed
3. Hover over a built-in card — only "复制" button appears
4. Click "新建模板" — editor modal opens
5. Fill in a name and save — new template appears in the grid
6. Hover over the custom template — "编辑", "复制", "删除" all appear
7. Click "复制" on any template — duplicate with "(副本)" appears
8. Click "删除" on a custom template — confirm dialog, then removed

- [ ] **Step 3: Run backend tests**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_layout_template.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(output): complete layout template system — seed, CRUD, editor"
```
