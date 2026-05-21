# Document Space Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate sandbox files into the document space with folder management, editing, preview, and sharing capabilities.

**Architecture:** Extend the existing `ai_documents` model with a `doc_type` field to distinguish manual documents from sandbox file references. Add a `document_shares` table for sharing. Frontend adds a restructured sidebar, file preview, batch operations, and a share dialog.

**Tech Stack:** Python 3.12 / SQLAlchemy / FastAPI (backend), TypeScript / React 19 / TanStack Query / Tailwind CSS / shadcn/ui (frontend)

---

## File Structure

### Backend — Create
- `backend/app/extensions/docmgr/share_models.py` — DocumentShare SQLAlchemy model
- `backend/app/extensions/docmgr/share_schemas.py` — Share-related Pydantic schemas
- `backend/app/extensions/docmgr/share_service.py` — Share CRUD service

### Backend — Modify
- `backend/app/extensions/models.py` — Add `doc_type`, `file_ref_path`, `file_size`, `file_mime` to AIDocument
- `backend/app/extensions/schemas.py` — Add new fields to AIDocument schemas
- `backend/app/extensions/docmgr/service.py` — Add sync, move, rename, batch delete, preview methods
- `backend/app/extensions/docmgr/routers.py` — Add new endpoints
- `backend/app/extensions/database.py` — Add migration for new columns and table

### Frontend — Create
- `frontend/src/extensions/docmgr/ShareDialog.tsx` — Share dialog component
- `frontend/src/extensions/docmgr/FolderPickerDialog.tsx` — Folder picker for move operations
- `frontend/src/extensions/docmgr/BatchActionBar.tsx` — Batch operation toolbar
- `frontend/src/extensions/docmgr/FilePreviewModal.tsx` — Image/file preview modal

### Frontend — Modify
- `frontend/src/extensions/api/index.ts` — Add new API methods
- `frontend/src/extensions/docmgr/DocumentManagement.tsx` — Restructured sidebar, file cards, batch mode
- `frontend/src/extensions/docmgr/useDocuments.ts` — Add doc_type filter, sync, batch ops
- `frontend/src/core/i18n/locales/zh-CN.ts` — New i18n keys
- `frontend/src/core/i18n/locales/en-US.ts` — New i18n keys
- `frontend/src/core/i18n/locales/types.ts` — New type keys

---

## Task 1: Backend — Extend AIDocument Model and Schemas

**Files:**
- Modify: `backend/app/extensions/models.py`
- Modify: `backend/app/extensions/schemas.py`
- Modify: `backend/app/extensions/database.py`
- Test: `backend/tests/test_document_space.py` (create)

- [ ] **Step 1: Write the failing test for new fields**

```python
"""Tests for document space enhancement — model & schema fields."""

import pytest
from app.extensions.models import AIDocument
from app.extensions.schemas import AIDocumentCreate, AIDocumentResponse


def test_ai_document_model_has_new_fields():
    """AIDocument model should expose doc_type, file_ref_path, file_size, file_mime."""
    col_names = {c.name for c in AIDocument.__table__.columns}
    assert "doc_type" in col_names
    assert "file_ref_path" in col_names
    assert "file_size" in col_names
    assert "file_mime" in col_names


def test_ai_document_create_schema_accepts_file_ref_fields():
    """AIDocumentCreate should accept doc_type and file ref fields."""
    data = AIDocumentCreate(
        title="test.md",
        folder="测试",
        doc_type="file_ref",
        file_ref_path="/mnt/user-data/test.md",
        file_size=1024,
        file_mime="text/markdown",
    )
    assert data.doc_type == "file_ref"
    assert data.file_ref_path == "/mnt/user-data/test.md"


def test_ai_document_response_includes_new_fields():
    """AIDocumentResponse should serialize new fields."""
    schema_fields = set(AIDocumentResponse.model_fields.keys())
    assert "doc_type" in schema_fields
    assert "file_ref_path" in schema_fields
    assert "file_size" in schema_fields
    assert "file_mime" in schema_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py -v`
Expected: FAIL — new columns and schema fields don't exist yet

- [ ] **Step 3: Add columns to AIDocument model in `backend/app/extensions/models.py`**

Add after the `status` field in the `AIDocument` class:

```python
    doc_type: Mapped[str] = mapped_column(String(20), default="document", nullable=False)
    file_ref_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Import `BigInteger` from `sqlalchemy` (add to existing imports).

- [ ] **Step 4: Update Pydantic schemas in `backend/app/extensions/schemas.py`**

Add `doc_type`, `file_ref_path`, `file_size`, `file_mime` to these classes:

In `AIDocumentCreate`:
```python
    doc_type: str = Field(default="document", max_length=20)
    file_ref_path: str | None = Field(None, max_length=500)
    file_size: int | None = None
    file_mime: str | None = Field(None, max_length=100)
```

In `AIDocumentUpdate`:
```python
    doc_type: str | None = Field(None, max_length=20)
    file_ref_path: str | None = Field(None, max_length=500)
    file_size: int | None = None
    file_mime: str | None = Field(None, max_length=100)
```

In `AIDocumentResponse`:
```python
    doc_type: str = "document"
    file_ref_path: str | None = None
    file_size: int | None = None
    file_mime: str | None = None
```

- [ ] **Step 5: Add migration in `backend/app/extensions/database.py`**

Inside `migrate_db()`, add after the existing migrations:

```python
    # Document space enhancement: doc_type and file reference fields
    await conn.execute(
        text(
            "ALTER TABLE ai_documents ADD COLUMN IF NOT EXISTS "
            "doc_type VARCHAR(20) DEFAULT 'document' NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE ai_documents ADD COLUMN IF NOT EXISTS "
            "file_ref_path VARCHAR(500)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE ai_documents ADD COLUMN IF NOT EXISTS "
            "file_size BIGINT"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE ai_documents ADD COLUMN IF NOT EXISTS "
            "file_mime VARCHAR(100)"
        )
    )
```

- [ ] **Step 6: Update `to_response` in `backend/app/extensions/docmgr/service.py`**

In the `to_response` static method, add the new fields:

```python
    @staticmethod
    async def to_response(doc: AIDocument) -> AIDocumentResponse:
        return AIDocumentResponse(
            id=doc.id,
            user_id=doc.user_id,
            source_thread_id=doc.source_thread_id,
            title=doc.title,
            content=doc.content,
            folder=doc.folder,
            is_starred=doc.is_starred,
            is_shared=doc.is_starred,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            doc_type=doc.doc_type,
            file_ref_path=doc.file_ref_path,
            file_size=doc.file_size,
            file_mime=doc.file_mime,
        )
```

Also update `create` method to accept new fields:

```python
    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, data: AIDocumentCreate) -> AIDocument:
        document = AIDocument(
            user_id=user_id,
            title=data.title,
            content=data.content,
            folder=data.folder,
            source_thread_id=data.source_thread_id,
            doc_type=data.doc_type,
            file_ref_path=data.file_ref_path,
            file_size=data.file_size,
            file_mime=data.file_mime,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py -v`
Expected: PASS

- [ ] **Step 8: Run existing tests to verify no regression**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/extensions/models.py backend/app/extensions/schemas.py backend/app/extensions/database.py backend/app/extensions/docmgr/service.py backend/tests/test_document_space.py
git commit -m "feat(docmgr): add doc_type and file reference fields to AIDocument model"
```

---

## Task 2: Backend — Sync Thread Files Endpoint

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`
- Modify: `backend/app/extensions/docmgr/routers.py`
- Test: `backend/tests/test_document_space.py`

- [ ] **Step 1: Write the failing test for sync**

Append to `backend/tests/test_document_space.py`:

```python
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from app.extensions.docmgr.service import AIDocumentService


@pytest.mark.asyncio
async def test_sync_thread_files_creates_file_ref_docs():
    """sync_thread_files should create file_ref documents for each sandbox file."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # Mock: no existing docs for this thread+path combo
    db.execute.return_value = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    user_id = UUID("12345678-1234-1234-1234-123456789012")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake sandbox files
        os.makedirs(os.path.join(tmpdir, "sub"), exist_ok=True)
        with open(os.path.join(tmpdir, "report.md"), "w") as f:
            f.write("# Report\nContent here")
        with open(os.path.join(tmpdir, "data.csv"), "w") as f:
            f.write("a,b\n1,2")

        with patch("app.extensions.docmgr.service.Paths") as mock_paths:
            mock_paths.sandbox_user_data_dir.return_value = tmpdir
            with patch("app.extensions.docmgr.service.AIDocumentService._get_thread_title", new_callable=AsyncMock, return_value="测试线程"):
                result = await AIDocumentService.sync_thread_files(
                    db=db,
                    user_id=user_id,
                    thread_id="thread-001",
                    sandbox_dir=tmpdir,
                )

    assert result["synced"] >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py::test_sync_thread_files_creates_file_ref_docs -v`
Expected: FAIL — `sync_thread_files` doesn't exist

- [ ] **Step 3: Implement sync_thread_files in `backend/app/extensions/docmgr/service.py`**

Add necessary imports at top:

```python
import os
import mimetypes
from pathlib import Path
```

Add these methods to `AIDocumentService`:

```python
    @staticmethod
    async def _get_thread_title(db: AsyncSession, thread_id: str) -> str:
        """Get thread display name from threads_meta table."""
        try:
            stmt = select(ThreadMetaRow.display_name).where(ThreadMetaRow.thread_id == thread_id)
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            return row or thread_id[:8]
        except Exception:
            return thread_id[:8]

    @staticmethod
    async def sync_thread_files(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        sandbox_dir: str,
    ) -> dict:
        """Sync sandbox files for a thread into document space as file_ref records."""
        folder_name = await AIDocumentService._get_thread_title(db, thread_id)
        synced = 0
        skipped = 0
        max_per_sync = 100

        sandbox_path = Path(sandbox_dir)
        if not sandbox_path.exists():
            return {"synced": 0, "skipped": 0, "message": "Sandbox directory not found"}

        for filepath in sandbox_path.rglob("*"):
            if not filepath.is_file():
                continue
            if synced >= max_per_sync:
                break

            rel_path = str(filepath.relative_to(sandbox_path))
            abs_path = str(filepath)
            file_size = filepath.stat().st_size
            mime_type, _ = mimetypes.guess_type(filepath.name)
            if mime_type is None:
                mime_type = "application/octet-stream"

            # Check for existing file_ref with same path and thread
            existing = await db.execute(
                select(AIDocument).where(
                    AIDocument.user_id == user_id,
                    AIDocument.file_ref_path == abs_path,
                    AIDocument.source_thread_id == thread_id,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            doc = AIDocument(
                user_id=user_id,
                title=filepath.name,
                folder=folder_name,
                source_thread_id=thread_id,
                doc_type="file_ref",
                file_ref_path=abs_path,
                file_size=file_size,
                file_mime=mime_type,
                status="active",
            )
            db.add(doc)
            synced += 1

        await db.commit()
        return {"synced": synced, "skipped": skipped}
```

Add import for ThreadMetaRow at top of service.py:

```python
from deerflow.persistence.thread_meta.model import ThreadMetaRow
```

- [ ] **Step 4: Add the sync endpoint in `backend/app/extensions/docmgr/routers.py`**

Add a new request schema and endpoint:

```python
class SyncThreadFilesRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=100)


@router.post("/sync-thread-files")
async def sync_thread_files(
    request: SyncThreadFilesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Sync sandbox files from a thread into document space."""
    from deerflow.config.paths import Paths

    sandbox_dir = Paths.sandbox_user_data_dir(
        user_id=str(current_user.id),
        thread_id=request.thread_id,
    )
    result = await AIDocumentService.sync_thread_files(
        db=db,
        user_id=current_user.id,
        thread_id=request.thread_id,
        sandbox_dir=sandbox_dir,
    )
    return result
```

Note: Check `Paths.sandbox_user_data_dir` signature and adjust accordingly. The exact method may be `Paths.thread_dir()` with subpath `/user-data/`. Verify the actual API.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/routers.py backend/tests/test_document_space.py
git commit -m "feat(docmgr): add sync-thread-files endpoint for sandbox file integration"
```

---

## Task 3: Backend — Move, Rename, Batch Delete, Preview Endpoints

**Files:**
- Modify: `backend/app/extensions/docmgr/service.py`
- Modify: `backend/app/extensions/docmgr/routers.py`
- Test: `backend/tests/test_document_space.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_document_space.py`:

```python
@pytest.mark.asyncio
async def test_move_file_ref_to_document():
    """Moving a file_ref to '我的文档' should change doc_type to document."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    doc = MagicMock()
    doc.doc_type = "file_ref"
    doc.file_ref_path = "/tmp/test.md"
    doc.content = None

    with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="# Hello"))), __exit__=MagicMock(return_value=False)))):
        with patch("os.path.exists", return_value=True):
            result = await AIDocumentService.move_to_documents(db, doc)

    assert doc.doc_type == "document"
    assert doc.content == "# Hello"


@pytest.mark.asyncio
async def test_batch_delete_documents():
    """batch_delete should delete documents by IDs."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[MagicMock(), MagicMock()])))))
    db.commit = AsyncMock()

    result = await AIDocumentService.batch_delete(
        db=db,
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        doc_ids=[UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")],
    )
    assert result == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py::test_move_file_ref_to_document tests/test_document_space.py::test_batch_delete_documents -v`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Implement service methods in `service.py`**

Add to `AIDocumentService`:

```python
    @staticmethod
    async def move_to_documents(db: AsyncSession, doc: AIDocument) -> AIDocument:
        """Move a file_ref document to '我的文档' by reading file content into DB."""
        if doc.doc_type != "file_ref":
            return doc
        if doc.file_ref_path and os.path.exists(doc.file_ref_path):
            text_mimes = {"text/markdown", "text/plain", "text/html", "text/x-rst"}
            if doc.file_mime in text_mimes:
                with open(doc.file_ref_path, "r", encoding="utf-8", errors="replace") as f:
                    doc.content = f.read()
            else:
                doc.content = json.dumps({"type": "binary_ref", "file_ref_path": doc.file_ref_path, "file_mime": doc.file_mime})
        else:
            doc.content = json.dumps({"type": "file_missing", "file_ref_path": doc.file_ref_path})

        doc.doc_type = "document"
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def batch_delete(db: AsyncSession, user_id: UUID, doc_ids: list[UUID]) -> int:
        """Delete multiple documents. Returns count deleted."""
        if not doc_ids:
            return 0
        if len(doc_ids) > 50:
            raise ValueError("Batch delete limited to 50 documents")
        stmt = select(AIDocument).where(
            AIDocument.user_id == user_id,
            AIDocument.id.in_(doc_ids),
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()
        count = 0
        for doc in docs:
            await db.delete(doc)
            count += 1
        await db.commit()
        return count

    @staticmethod
    async def rename(db: AsyncSession, doc: AIDocument, new_title: str) -> AIDocument:
        """Rename a document. For file_ref, also rename physical file."""
        if doc.doc_type == "file_ref" and doc.file_ref_path:
            old_path = Path(doc.file_ref_path)
            if old_path.exists():
                new_path = old_path.parent / new_title
                old_path.rename(new_path)
                doc.file_ref_path = str(new_path)
        doc.title = new_title
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def read_file_content(doc: AIDocument) -> str | None:
        """Read file content for preview. Returns None for missing files."""
        if not doc.file_ref_path or not os.path.exists(doc.file_ref_path):
            return None
        file_size = os.path.getsize(doc.file_ref_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return None
        with open(doc.file_ref_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
```

Add `import json` at top of service.py.

- [ ] **Step 4: Add endpoints in `routers.py`**

```python
class MoveRequest(BaseModel):
    folder: str | None = Field(None, max_length=255)
    to_documents: bool = False


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class BatchDeleteRequest(BaseModel):
    ids: list[UUID] = Field(..., min_length=1, max_length=50)


@router.put("/documents/{doc_id}/move", response_model=AIDocumentResponse)
async def move_document(
    doc_id: UUID,
    request: MoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Move document to a folder or to My Documents."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if request.to_documents:
        doc = await AIDocumentService.move_to_documents(db, doc)
    if request.folder:
        doc = await AIDocumentService.update(db, doc, AIDocumentUpdate(folder=request.folder))
    return await AIDocumentService.to_response(doc)


@router.put("/documents/{doc_id}/rename", response_model=AIDocumentResponse)
async def rename_document(
    doc_id: UUID,
    request: RenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename a document."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = await AIDocumentService.rename(db, doc, request.title)
    return await AIDocumentService.to_response(doc)


@router.delete("/documents/batch", response_model=MessageResponse)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Batch delete documents."""
    count = await AIDocumentService.batch_delete(db, current_user.id, request.ids)
    return MessageResponse(message=f"Deleted {count} documents")


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Read file content for preview."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.doc_type != "file_ref":
        return {"content": doc.content, "doc_type": doc.doc_type}
    content = await AIDocumentService.read_file_content(doc)
    return {"content": content, "doc_type": doc.doc_type, "file_mime": doc.file_mime, "file_size": doc.file_size}
```

- [ ] **Step 5: Update list_docs to support doc_type filter**

In `service.py`, update `list_docs` signature and body:

Add parameter `doc_type: str | None = None` and filter logic:

```python
        if doc_type is not None:
            query = query.where(AIDocument.doc_type == doc_type)
            count_query = count_query.where(AIDocument.doc_type == doc_type)
```

Update the router `list_documents` to accept and pass `doc_type`:

```python
@router.get("/documents", response_model=AIDocumentListResponse)
async def list_documents(
    folder: str | None = Query(None),
    starred: bool | None = Query(None),
    shared: bool | None = Query(None),
    doc_type: str | None = Query(None, description="Filter by doc_type: document or file_ref"),
    q: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    documents, total = await AIDocumentService.list_docs(
        db, user_id=current_user.id, folder=folder, starred=starred, shared=shared, doc_type=doc_type, q=q, skip=skip, limit=limit,
    )
    ...
```

- [ ] **Step 6: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/routers.py backend/tests/test_document_space.py
git commit -m "feat(docmgr): add move, rename, batch delete, and preview endpoints"
```

---

## Task 4: Backend — Document Shares Model and Endpoints

**Files:**
- Create: `backend/app/extensions/docmgr/share_models.py`
- Create: `backend/app/extensions/docmgr/share_schemas.py`
- Create: `backend/app/extensions/docmgr/share_service.py`
- Modify: `backend/app/extensions/database.py`
- Modify: `backend/app/extensions/docmgr/routers.py`
- Test: `backend/tests/test_document_space.py`

- [ ] **Step 1: Create `backend/app/extensions/docmgr/share_models.py`**

```python
"""Document share model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions.database import Base


class DocumentShare(Base):
    """Document share record — tracks who a document is shared with."""

    __tablename__ = "document_shares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    share_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "department" | "link"
    share_target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    permission: Mapped[str] = mapped_column(String(10), default="read", nullable=False)  # "read" | "edit"
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
```

- [ ] **Step 2: Create `backend/app/extensions/docmgr/share_schemas.py`**

```python
"""Document share schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    document_id: UUID
    share_type: str = Field(..., pattern="^(user|department|link)$")
    share_target_id: str | None = None
    permission: str = Field(default="read", pattern="^(read|edit)$")


class ShareResponse(BaseModel):
    id: UUID
    document_id: UUID
    share_type: str
    share_target_id: str | None = None
    share_token: str | None = None
    permission: str
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class SharedDocumentResponse(BaseModel):
    document: dict
    permission: str
    shared_by: UUID
```

- [ ] **Step 3: Create `backend/app/extensions/docmgr/share_service.py`**

```python
"""Document share service."""

import secrets
import logging
from uuid import UUID

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.docmgr.share_models import DocumentShare
from app.extensions.docmgr.share_schemas import ShareCreateRequest, ShareResponse
from app.extensions.models import AIDocument

logger = logging.getLogger(__name__)


class ShareService:
    @staticmethod
    async def create_share(db: AsyncSession, user_id: UUID, data: ShareCreateRequest) -> ShareResponse:
        """Create a new share record."""
        # Verify ownership
        doc = await db.execute(
            select(AIDocument).where(AIDocument.id == data.document_id, AIDocument.user_id == user_id)
        )
        if not doc.scalar_one_or_none():
            raise ValueError("Document not found or not owned by user")

        token = None
        if data.share_type == "link":
            token = secrets.token_urlsafe(32)

        share = DocumentShare(
            document_id=data.document_id,
            share_type=data.share_type,
            share_target_id=data.share_target_id,
            share_token=token,
            permission=data.permission,
            created_by=user_id,
        )
        db.add(share)

        # Mark document as shared
        await db.execute(
            select(AIDocument).where(AIDocument.id == data.document_id)
        )
        doc_result = await db.execute(select(AIDocument).where(AIDocument.id == data.document_id))
        doc_obj = doc_result.scalar_one_or_none()
        if doc_obj:
            doc_obj.is_shared = True

        await db.commit()
        await db.refresh(share)
        return ShareResponse(
            id=share.id,
            document_id=share.document_id,
            share_type=share.share_type,
            share_target_id=share.share_target_id,
            share_token=share.share_token,
            permission=share.permission,
            created_by=share.created_by,
            created_at=share.created_at,
        )

    @staticmethod
    async def list_shares(db: AsyncSession, document_id: UUID, user_id: UUID) -> list[ShareResponse]:
        """List all shares for a document."""
        stmt = select(DocumentShare).where(DocumentShare.document_id == document_id, DocumentShare.created_by == user_id)
        result = await db.execute(stmt)
        shares = result.scalars().all()
        return [
            ShareResponse(
                id=s.id,
                document_id=s.document_id,
                share_type=s.share_type,
                share_target_id=s.share_target_id,
                share_token=s.share_token,
                permission=s.permission,
                created_by=s.created_by,
                created_at=s.created_at,
            )
            for s in shares
        ]

    @staticmethod
    async def revoke_share(db: AsyncSession, share_id: UUID, user_id: UUID) -> bool:
        """Revoke a share."""
        stmt = select(DocumentShare).where(DocumentShare.id == share_id, DocumentShare.created_by == user_id)
        result = await db.execute(stmt)
        share = result.scalar_one_or_none()
        if not share:
            return False
        await db.delete(share)
        await db.commit()
        return True

    @staticmethod
    async def get_shared_document(db: AsyncSession, token: str, user_id: UUID | None = None) -> dict | None:
        """Get a shared document by link token."""
        stmt = select(DocumentShare).where(DocumentShare.share_token == token, DocumentShare.share_type == "link")
        result = await db.execute(stmt)
        share = result.scalar_one_or_none()
        if not share:
            return None

        doc_stmt = select(AIDocument).where(AIDocument.id == share.document_id)
        doc_result = await db.execute(doc_stmt)
        doc = doc_result.scalar_one_or_none()
        if not doc:
            return None

        return {
            "document": {
                "id": str(doc.id),
                "title": doc.title,
                "content": doc.content,
                "doc_type": doc.doc_type,
                "file_ref_path": doc.file_ref_path,
                "file_mime": doc.file_mime,
            },
            "permission": share.permission,
            "shared_by": str(share.created_by),
        }

    @staticmethod
    async def list_shared_with_me(db: AsyncSession, user_id: UUID) -> list[dict]:
        """List documents shared with the current user (direct user share only)."""
        stmt = (
            select(DocumentShare, AIDocument)
            .join(AIDocument, DocumentShare.document_id == AIDocument.id)
            .where(DocumentShare.share_target_id == str(user_id))
            .order_by(DocumentShare.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "document": {
                    "id": str(doc.id),
                    "title": doc.title,
                    "content": doc.content,
                    "doc_type": doc.doc_type,
                    "folder": doc.folder,
                    "updated_at": doc.updated_at.isoformat(),
                },
                "permission": share.permission,
                "share_type": share.share_type,
                "shared_by": str(share.created_by),
            }
            for share, doc in rows
        ]
```

- [ ] **Step 4: Add migration for document_shares table in `database.py`**

Inside `migrate_db()`, after the existing migrations:

```python
    # Document shares table
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS document_shares ("
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "document_id UUID NOT NULL REFERENCES ai_documents(id) ON DELETE CASCADE,"
            "share_type VARCHAR(20) NOT NULL,"
            "share_target_id VARCHAR(100),"
            "share_token VARCHAR(64) UNIQUE,"
            "permission VARCHAR(10) NOT NULL DEFAULT 'read',"
            "created_by UUID NOT NULL REFERENCES users(id),"
            "created_at TIMESTAMP NOT NULL DEFAULT NOW()"
            ")"
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_document_shares_document_id ON document_shares(document_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_document_shares_share_token ON document_shares(share_token)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_document_shares_created_by ON document_shares(created_by)")
    )
```

- [ ] **Step 5: Add share endpoints in `routers.py`**

Add import:

```python
from app.extensions.docmgr.share_schemas import ShareCreateRequest, ShareResponse, SharedDocumentResponse
from app.extensions.docmgr.share_service import ShareService
```

Add endpoints:

```python
@router.post("/documents/{doc_id}/share", response_model=ShareResponse)
async def share_document(
    doc_id: UUID,
    data: ShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Share a document."""
    data.document_id = doc_id
    try:
        return await ShareService.create_share(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/{doc_id}/shares", response_model=list[ShareResponse])
async def list_document_shares(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all shares for a document."""
    return await ShareService.list_shares(db, doc_id, current_user.id)


@router.delete("/shares/{share_id}", response_model=MessageResponse)
async def revoke_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke a share."""
    revoked = await ShareService.revoke_share(db, share_id, current_user.id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Share not found")
    return MessageResponse(message="Share revoked successfully")


@router.get("/shared-with-me")
async def shared_with_me(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List documents shared with the current user."""
    return await ShareService.list_shared_with_me(db, current_user.id)


@router.get("/shared/{token}")
async def access_shared_document(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Access a shared document via link token."""
    result = await ShareService.get_shared_document(db, token, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Shared document not found or link invalid")
    return result
```

- [ ] **Step 6: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_document_space.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/docmgr/share_models.py backend/app/extensions/docmgr/share_schemas.py backend/app/extensions/docmgr/share_service.py backend/app/extensions/database.py backend/app/extensions/docmgr/routers.py backend/tests/test_document_space.py
git commit -m "feat(docmgr): add document sharing model, service, and API endpoints"
```

---

## Task 5: Frontend — API Client and i18n

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`
- Modify: `frontend/src/core/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/core/i18n/locales/en-US.ts`
- Modify: `frontend/src/core/i18n/locales/types.ts`

- [ ] **Step 1: Update API client in `frontend/src/extensions/api/index.ts`**

Add to the `AIDocument` interface:

```typescript
  doc_type?: "document" | "file_ref";
  file_ref_path?: string | null;
  file_size?: number | null;
  file_mime?: string | null;
```

Add to `docmgrApi`:

```typescript
  syncThreadFiles: async (threadId: string): Promise<{ synced: number; skipped: number }> => {
    return request("/api/extensions/docmgr/sync-thread-files", {
      method: "POST",
      body: JSON.stringify({ thread_id: threadId }),
    });
  },

  moveDocument: async (id: string, data: { folder?: string; toDocuments?: boolean }): Promise<AIDocument> => {
    return request(`/api/extensions/docmgr/documents/${id}/move`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  renameDocument: async (id: string, title: string): Promise<AIDocument> => {
    return request(`/api/extensions/docmgr/documents/${id}/rename`, {
      method: "PUT",
      body: JSON.stringify({ title }),
    });
  },

  batchDelete: async (ids: string[]): Promise<{ message: string }> => {
    return request("/api/extensions/docmgr/documents/batch", {
      method: "DELETE",
      body: JSON.stringify({ ids }),
    });
  },

  previewDocument: async (id: string): Promise<{ content: string | null; doc_type: string; file_mime?: string; file_size?: number }> => {
    return request(`/api/extensions/docmgr/documents/${id}/preview`);
  },

  shareDocument: async (docId: string, data: { share_type: string; share_target_id?: string; permission: string }): Promise<any> => {
    return request(`/api/extensions/docmgr/documents/${docId}/share`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  listShares: async (docId: string): Promise<any[]> => {
    return request(`/api/extensions/docmgr/documents/${docId}/shares`);
  },

  revokeShare: async (shareId: string): Promise<{ message: string }> => {
    return request(`/api/extensions/docmgr/shares/${shareId}`, { method: "DELETE" });
  },

  sharedWithMe: async (): Promise<any[]> => {
    return request("/api/extensions/docmgr/shared-with-me");
  },

  accessSharedDocument: async (token: string): Promise<any> => {
    return request(`/api/extensions/docmgr/shared/${token}`);
  },
```

- [ ] **Step 2: Add i18n keys to `frontend/src/core/i18n/locales/types.ts`**

Add to the `TranslationKeys` interface inside the appropriate sections:

```typescript
  docSpace: {
    myDocuments: string;
    myFavorites: string;
    myShares: string;
    aiTaskArchive: string;
    myFolders: string;
    syncToDocSpace: string;
    syncSuccess: string;
    viewInDocSpace: string;
    moveToDocuments: string;
    moveToFolder: string;
    rename: string;
    batchDelete: string;
    share: string;
    shareToUser: string;
    shareViaLink: string;
    sharePermission: string;
    readPermission: string;
    editPermission: string;
    copyLink: string;
    manageShares: string;
    revokeShare: string;
    linkCopied: string;
    selectTarget: string;
    newFolder: string;
    fileMissing: string;
    preview: string;
    noFiles: string;
    syncedCount: string;
  };
```

- [ ] **Step 3: Add Chinese translations to `frontend/src/core/i18n/locales/zh-CN.ts`**

```typescript
docSpace: {
  myDocuments: "我的文档",
  myFavorites: "我的收藏",
  myShares: "我的分享",
  aiTaskArchive: "AI任务存档",
  myFolders: "我的文件夹",
  syncToDocSpace: "同步到文档空间",
  syncSuccess: "同步成功",
  viewInDocSpace: "在文档空间中查看",
  moveToDocuments: "移到我的文档",
  moveToFolder: "移动到文件夹",
  rename: "重命名",
  batchDelete: "批量删除",
  share: "分享",
  shareToUser: "分享给用户/部门",
  shareViaLink: "通过链接分享",
  sharePermission: "权限",
  readPermission: "只读",
  editPermission: "可编辑",
  copyLink: "复制链接",
  manageShares: "管理分享",
  revokeShare: "撤销分享",
  linkCopied: "链接已复制",
  selectTarget: "选择分享对象",
  newFolder: "新建文件夹",
  fileMissing: "文件已丢失",
  preview: "预览",
  noFiles: "暂无文件",
  syncedCount: "已同步 {count} 个文件",
},
```

- [ ] **Step 4: Add English translations to `frontend/src/core/i18n/locales/en-US.ts`**

```typescript
docSpace: {
  myDocuments: "My Documents",
  myFavorites: "My Favorites",
  myShares: "My Shares",
  aiTaskArchive: "AI Task Archive",
  myFolders: "My Folders",
  syncToDocSpace: "Sync to Document Space",
  syncSuccess: "Sync Successful",
  viewInDocSpace: "View in Document Space",
  moveToDocuments: "Move to My Documents",
  moveToFolder: "Move to Folder",
  rename: "Rename",
  batchDelete: "Batch Delete",
  share: "Share",
  shareToUser: "Share to User/Department",
  shareViaLink: "Share via Link",
  sharePermission: "Permission",
  readPermission: "Read Only",
  editPermission: "Can Edit",
  copyLink: "Copy Link",
  manageShares: "Manage Shares",
  revokeShare: "Revoke Share",
  linkCopied: "Link Copied",
  selectTarget: "Select Target",
  newFolder: "New Folder",
  fileMissing: "File Missing",
  preview: "Preview",
  noFiles: "No Files",
  syncedCount: "Synced {count} file(s)",
},
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/api/index.ts frontend/src/core/i18n/locales/types.ts frontend/src/core/i18n/locales/zh-CN.ts frontend/src/core/i18n/locales/en-US.ts
git commit -m "feat(docmgr): add API client methods and i18n keys for document space enhancement"
```

---

## Task 6: Frontend — Restructured Sidebar and File Cards

**Files:**
- Modify: `frontend/src/extensions/docmgr/useDocuments.ts`
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: Update `useDocuments.ts` to support doc_type filter and new operations**

Add `doc_type` to the filter interface:

```typescript
interface DocumentFilter {
  folder?: string;
  starred?: boolean;
  shared?: boolean;
  doc_type?: "document" | "file_ref";
  q?: string;
}
```

Add new methods to the hook's return:

```typescript
  const syncThreadFiles = useCallback(async (threadId: string) => {
    return docmgrApi.syncThreadFiles(threadId);
  }, []);

  const moveToDocuments = useCallback(async (id: string) => {
    const doc = await docmgrApi.moveDocument(id, { toDocuments: true });
    await loadDocs();
    return doc;
  }, [loadDocs]);

  const moveToFolder = useCallback(async (id: string, folder: string) => {
    const doc = await docmgrApi.moveDocument(id, { folder });
    await loadDocs();
    return doc;
  }, [loadDocs]);

  const renameDoc = useCallback(async (id: string, title: string) => {
    const doc = await docmgrApi.renameDocument(id, title);
    await loadDocs();
    return doc;
  }, [loadDocs]);

  const batchDeleteDocs = useCallback(async (ids: string[]) => {
    await docmgrApi.batchDelete(ids);
    await loadDocs();
  }, [loadDocs]);

  const previewDoc = useCallback(async (id: string) => {
    return docmgrApi.previewDocument(id);
  }, []);
```

Return these alongside existing returns.

- [ ] **Step 2: Restructure sidebar in `DocumentManagement.tsx`**

Replace the existing sidebar navigation with the new structure. The key change is the sidebar section:

```tsx
{/* Sidebar */}
<div className="w-56 border-r bg-muted/30 flex flex-col">
  {/* My Folders section */}
  <div className="p-3">
    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
      {t.docSpace.myFolders}
    </h3>
    <nav className="space-y-0.5">
      <SidebarItem
        icon={<FileText className="h-4 w-4" />}
        label={t.docSpace.myDocuments}
        active={filter.doc_type === "document" && !filter.starred && !filter.shared}
        onClick={() => setFilter({ doc_type: "document" })}
      />
      <SidebarItem
        icon={<Star className="h-4 w-4" />}
        label={t.docSpace.myFavorites}
        active={filter.starred === true}
        onClick={() => setFilter({ starred: true })}
      />
      <SidebarItem
        icon={<Share2 className="h-4 w-4" />}
        label={t.docSpace.myShares}
        active={filter.shared === true}
        onClick={() => setFilter({ shared: true })}
      />
    </nav>
  </div>

  <Separator />

  {/* AI Task Archive section */}
  <div className="p-3">
    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
      {t.docSpace.aiTaskArchive}
    </h3>
    <nav className="space-y-0.5">
      <SidebarItem
        icon={<FolderOpen className="h-4 w-4" />}
        label={t.docSpace.aiTaskArchive}
        active={filter.doc_type === "file_ref"}
        onClick={() => setFilter({ doc_type: "file_ref" })}
      />
    </nav>

    {/* Thread folders under AI Task Archive */}
    {folders
      .filter((f) => f !== "默认文件夹")
      .map((folder) => (
        <SidebarItem
          key={folder}
          icon={<Folder className="h-4 w-4" />}
          label={folder}
          active={filter.folder === folder && filter.doc_type === "file_ref"}
          onClick={() => setFilter({ doc_type: "file_ref", folder })}
          className="pl-6"
        />
      ))}
  </div>
</div>
```

Add a simple `SidebarItem` helper component at the top of the file or inline:

```tsx
function SidebarItem({ icon, label, active, onClick, className }: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${className || ""} ${
        active ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      {icon}
      <span className="truncate">{label}</span>
    </button>
  );
}
```

- [ ] **Step 3: Update document card rendering to handle file_ref**

In the card rendering section, add conditional display:

```tsx
{doc.doc_type === "file_ref" ? (
  // File reference card
  <div
    onClick={() => handleFileRefClick(doc)}
    className="group relative border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer bg-card"
  >
    <div className="flex items-start gap-3">
      {isImageFile(doc.file_mime) ? (
        <Image className="h-8 w-8 text-muted-foreground shrink-0" />
      ) : isTextFile(doc.file_mime) ? (
        <FileText className="h-8 w-8 text-muted-foreground shrink-0" />
      ) : (
        <File className="h-8 w-8 text-muted-foreground shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="font-medium truncate">{doc.title}</p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(doc.file_size)} · {formatDate(doc.updated_at)}
        </p>
      </div>
    </div>
    {doc.status === "file_missing" && (
      <p className="text-xs text-destructive mt-2">{t.docSpace.fileMissing}</p>
    )}
    {/* Star toggle + context menu */}
    ...
  </div>
) : (
  // Existing document card (unchanged)
  ...
)}
```

Add helper functions:

```typescript
function isImageFile(mime?: string | null) {
  return mime?.startsWith("image/");
}

function isTextFile(mime?: string | null) {
  return mime?.startsWith("text/") || mime === "application/json";
}

function formatFileSize(bytes?: number | null) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

- [ ] **Step 4: Add handleFileRefClick handler**

```typescript
const handleFileRefClick = async (doc: AIDocument) => {
  if (isImageFile(doc.file_mime)) {
    // Open image preview modal
    setPreviewDoc(doc);
  } else if (isTextFile(doc.file_mime)) {
    // Load content and open editor
    const result = await docmgrApi.previewDocument(doc.id);
    if (result.content) {
      setCurrentDoc({ ...doc, content: result.content });
      setView("editor");
    }
  }
  // Other file types: offer download (handled via context menu)
};
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/useDocuments.ts frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): restructure sidebar with my folders and AI task archive sections"
```

---

## Task 7: Frontend — New Components (ShareDialog, FolderPicker, BatchActionBar, FilePreviewModal)

**Files:**
- Create: `frontend/src/extensions/docmgr/FilePreviewModal.tsx`
- Create: `frontend/src/extensions/docmgr/FolderPickerDialog.tsx`
- Create: `frontend/src/extensions/docmgr/BatchActionBar.tsx`
- Create: `frontend/src/extensions/docmgr/ShareDialog.tsx`

- [ ] **Step 1: Create `FilePreviewModal.tsx`**

```tsx
"use client";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { AIDocument } from "@/extensions/api";

interface FilePreviewModalProps {
  doc: AIDocument | null;
  onClose: () => void;
}

export function FilePreviewModal({ doc, onClose }: FilePreviewModalProps) {
  if (!doc) return null;

  const isImage = doc.file_mime?.startsWith("image/");

  return (
    <Dialog open={!!doc} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogTitle>{doc.title}</DialogTitle>
        <div className="mt-4 flex items-center justify-center min-h-[300px]">
          {isImage && doc.file_ref_path ? (
            <img
              src={`/api/extensions/docmgr/documents/${doc.id}/preview`}
              alt={doc.title}
              className="max-w-full max-h-[60vh] object-contain rounded"
            />
          ) : (
            <p className="text-muted-foreground">Preview not available</p>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-2">
          {doc.file_size ? `${(doc.file_size / 1024).toFixed(1)} KB` : ""} · {doc.file_mime}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Create `FolderPickerDialog.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface FolderPickerDialogProps {
  folders: string[];
  open: boolean;
  onClose: () => void;
  onSelect: (folder: string) => void;
}

export function FolderPickerDialog({ folders, open, onClose, onSelect }: FolderPickerDialogProps) {
  const [newFolder, setNewFolder] = useState("");

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-sm">
        <DialogTitle>移动到文件夹</DialogTitle>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {folders.map((folder) => (
            <button
              key={folder}
              onClick={() => { onSelect(folder); onClose(); }}
              className="w-full text-left px-3 py-2 rounded-md hover:bg-muted text-sm"
            >
              {folder}
            </button>
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          <Input
            placeholder="新建文件夹"
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!newFolder.trim()}
            onClick={() => { onSelect(newFolder.trim()); setNewFolder(""); onClose(); }}
          >
            创建
          </Button>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>取消</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Create `BatchActionBar.tsx`**

```tsx
"use client";

import { Button } from "@/components/ui/button";
import { Trash2, Star, FolderInput } from "lucide-react";

interface BatchActionBarProps {
  selectedCount: number;
  onMoveToFolder: () => void;
  onDelete: () => void;
  onStar: () => void;
  onClear: () => void;
}

export function BatchActionBar({ selectedCount, onMoveToFolder, onDelete, onStar, onClear }: BatchActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-card border shadow-lg rounded-full px-4 py-2">
      <span className="text-sm text-muted-foreground mr-2">已选 {selectedCount} 项</span>
      <Button size="sm" variant="ghost" onClick={onMoveToFolder}>
        <FolderInput className="h-4 w-4 mr-1" /> 移动
      </Button>
      <Button size="sm" variant="ghost" onClick={onStar}>
        <Star className="h-4 w-4 mr-1" /> 加星
      </Button>
      <Button size="sm" variant="ghost" className="text-destructive" onClick={onDelete}>
        <Trash2 className="h-4 w-4 mr-1" /> 删除
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear}>
        取消
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Create `ShareDialog.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { docmgrApi } from "@/extensions/api";
import { Check, Copy, Link2, Users } from "lucide-react";

interface ShareDialogProps {
  docId: string;
  open: boolean;
  onClose: () => void;
}

export function ShareDialog({ docId, open, onClose }: ShareDialogProps) {
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState<"read" | "edit">("read");
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleShareToUser = async () => {
    setLoading(true);
    try {
      await docmgrApi.shareDocument(docId, {
        share_type: "user",
        share_target_id: targetId,
        permission,
      });
      setTargetId("");
    } finally {
      setLoading(false);
    }
  };

  const handleShareViaLink = async () => {
    setLoading(true);
    try {
      const result = await docmgrApi.shareDocument(docId, {
        share_type: "link",
        permission,
      });
      setLinkToken(result.share_token);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = () => {
    if (linkToken) {
      navigator.clipboard.writeText(`${window.location.origin}/doc/shared/${linkToken}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle>分享文档</DialogTitle>
        <Tabs defaultValue="link">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="link"><Link2 className="h-4 w-4 mr-1" /> 链接分享</TabsTrigger>
            <TabsTrigger value="user"><Users className="h-4 w-4 mr-1" /> 指定用户</TabsTrigger>
          </TabsList>
          <TabsContent value="link" className="space-y-3 mt-3">
            <div className="flex gap-2">
              <Button size="sm" variant={permission === "read" ? "default" : "ghost"} onClick={() => setPermission("read")}>只读</Button>
              <Button size="sm" variant={permission === "edit" ? "default" : "ghost"} onClick={() => setPermission("edit")}>可编辑</Button>
            </div>
            {!linkToken ? (
              <Button onClick={handleShareViaLink} disabled={loading} className="w-full">生成分享链接</Button>
            ) : (
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs bg-muted px-2 py-1 rounded truncate">
                  {`${window.location.origin}/doc/shared/${linkToken}`}
                </code>
                <Button size="icon" variant="ghost" onClick={handleCopyLink}>
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            )}
          </TabsContent>
          <TabsContent value="user" className="space-y-3 mt-3">
            <Input placeholder="输入用户ID或部门" value={targetId} onChange={(e) => setTargetId(e.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" variant={permission === "read" ? "default" : "ghost"} onClick={() => setPermission("read")}>只读</Button>
              <Button size="sm" variant={permission === "edit" ? "default" : "ghost"} onClick={() => setPermission("edit")}>可编辑</Button>
            </div>
            <Button onClick={handleShareToUser} disabled={loading || !targetId.trim()} className="w-full">分享</Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/FilePreviewModal.tsx frontend/src/extensions/docmgr/FolderPickerDialog.tsx frontend/src/extensions/docmgr/BatchActionBar.tsx frontend/src/extensions/docmgr/ShareDialog.tsx
git commit -m "feat(docmgr): add share dialog, folder picker, batch action bar, and file preview modal"
```

---

## Task 8: Frontend — Integrate Components into DocumentManagement

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`
- Modify: `frontend/src/extensions/docmgr/useDocuments.ts`

- [ ] **Step 1: Add state for new features in DocumentManagement**

Add to the component's state declarations:

```typescript
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
const [showFolderPicker, setShowFolderPicker] = useState(false);
const [showShareDialog, setShowShareDialog] = useState<string | null>(null);
const [previewDoc, setPreviewDoc] = useState<AIDocument | null>(null);
const [batchMode, setBatchMode] = useState(false);
```

- [ ] **Step 2: Wire up BatchActionBar**

Add at the bottom of the component, before closing fragment:

```tsx
{batchMode && (
  <BatchActionBar
    selectedCount={selectedIds.size}
    onMoveToFolder={() => setShowFolderPicker(true)}
    onDelete={async () => {
      await batchDeleteDocs(Array.from(selectedIds));
      setSelectedIds(new Set());
      setBatchMode(false);
    }}
    onStar={async () => {
      for (const id of selectedIds) {
        await toggleStar(id, false);
      }
      setSelectedIds(new Set());
    }}
    onClear={() => { setSelectedIds(new Set()); setBatchMode(false); }}
  />
)}
```

- [ ] **Step 3: Wire up FolderPickerDialog**

```tsx
{showFolderPicker && (
  <FolderPickerDialog
    folders={folders}
    open={showFolderPicker}
    onClose={() => setShowFolderPicker(false)}
    onSelect={async (folder) => {
      for (const id of selectedIds) {
        await moveToFolder(id, folder);
      }
      setSelectedIds(new Set());
      setBatchMode(false);
    }}
  />
)}
```

- [ ] **Step 4: Wire up ShareDialog**

```tsx
{showShareDialog && (
  <ShareDialog
    docId={showShareDialog}
    open={!!showShareDialog}
    onClose={() => setShowShareDialog(null)}
  />
)}
```

- [ ] **Step 5: Wire up FilePreviewModal**

```tsx
<FilePreviewModal
  doc={previewDoc}
  onClose={() => setPreviewDoc(null)}
/>
```

- [ ] **Step 6: Add context menu items for file_ref documents**

In the card context menu, add "移到我的文档" and "分享" options:

```tsx
{doc.doc_type === "file_ref" && (
  <DropdownMenuItem onClick={() => moveToDocuments(doc.id)}>
    {t.docSpace.moveToDocuments}
  </DropdownMenuItem>
)}
<DropdownMenuItem onClick={() => setShowShareDialog(doc.id)}>
  {t.docSpace.share}
</DropdownMenuItem>
```

- [ ] **Step 7: Add batch mode toggle to header**

Add a toggle button in the document list header:

```tsx
<Button variant="ghost" size="sm" onClick={() => { setBatchMode(!batchMode); setSelectedIds(new Set()); }}>
  <CheckSquare className="h-4 w-4 mr-1" />
  {batchMode ? "取消选择" : "多选"}
</Button>
```

- [ ] **Step 8: Verify frontend compiles and run lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx frontend/src/extensions/docmgr/useDocuments.ts
git commit -m "feat(docmgr): integrate share, folder picker, batch ops, and preview into document management"
```

---

## Task 9: Frontend — Sync Button in Artifact Panel

**Files:**
- Modify: `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx` (or equivalent artifact component)

- [ ] **Step 1: Add sync button to artifact panel**

Find the artifact file list or detail component and add a sync button. The button should:

1. Call `docmgrApi.syncThreadFiles(threadId)`
2. Show a toast: "已同步 N 个文件 → [查看]"
3. "查看" link navigates to `/docmgr?folder=<thread-title>`

```tsx
<Button
  variant="outline"
  size="sm"
  onClick={async () => {
    const result = await docmgrApi.syncThreadFiles(threadId);
    toast.success(`已同步 ${result.synced} 个文件`);
  }}
>
  <FolderInput className="h-4 w-4 mr-1" />
  {t.docSpace.syncToDocSpace}
</Button>
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/artifacts/
git commit -m "feat(docmgr): add sync-to-document-space button in artifact panel"
```

---

## Task 10: Integration Testing and Final Verification

**Files:**
- Test: `backend/tests/test_document_space.py`
- Manual testing checklist

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v --timeout=120`
Expected: All tests PASS

- [ ] **Step 2: Run frontend typecheck and lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: No errors

- [ ] **Step 3: Start dev server and manual test**

Run: `make dev`

Manual test checklist:
- [ ] Sidebar shows "我的文件夹" and "AI任务存档" sections
- [ ] Clicking "我的文档" shows only document type docs
- [ ] Clicking "AI任务存档" shows only file_ref type docs
- [ ] Sync button in artifact panel works
- [ ] File ref card opens editor for text files, preview modal for images
- [ ] "移到我的文档" changes doc_type from file_ref to document
- [ ] Batch select mode: move, star, delete work
- [ ] Share dialog generates link and shares to user
- [ ] Shared document accessible via link

- [ ] **Step 4: Commit any fixes from manual testing**

```bash
git add -A
git commit -m "fix(docmgr): integration fixes from manual testing"
```

- [ ] **Step 5: Final commit with all changes**

Ensure all changes are committed and the branch is clean.
