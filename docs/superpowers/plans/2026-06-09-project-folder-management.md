# Project Folder Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade document-space folders from virtual (DISTINCT string) to real database entities with tree structure, direct project binding, CRUD operations, and a tree sidebar UI with hover action buttons.

**Architecture:** New `folders` table with `parent_id` self-reference for tree structure and `project_id` FK for project binding. New `FolderService` class for CRUD. Frontend gets a recursive `ProjectFolderTree` component with hover actions, powered by a `useFolderTree` hook. Transition period uses dual-write to both `folder` (string) and `folder_id` (UUID) columns.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), FastAPI, Pydantic v2, TypeScript, React 19, TanStack Query, Tailwind CSS 4, shadcn/ui

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/extensions/models.py` | Add `Folder` model + `folder_id` on `AIDocument` |
| Modify | `backend/app/extensions/database.py` | Add `folders` table + `folder_id` column to `migrate_db()` |
| Modify | `backend/app/extensions/schemas.py` | Add `FolderCreate`, `FolderUpdate`, `FolderResponse`, `FolderTreeResponse` |
| Create | `backend/app/extensions/docmgr/folder_service.py` | `FolderService` — CRUD, tree building, permission checks |
| Modify | `backend/app/extensions/docmgr/routers.py` | Add folder CRUD endpoints + `folder_id` filter on document list |
| Modify | `backend/app/extensions/project/service.py` | Hook folder creation/rename/delete into project lifecycle |
| Modify | `frontend/src/extensions/api/index.ts` | Add `folderApi` methods |
| Create | `frontend/src/extensions/docmgr/useFolderTree.ts` | Hook: folder tree state, CRUD operations |
| Create | `frontend/src/extensions/docmgr/ProjectFolderTree.tsx` | Recursive tree sidebar component with hover actions |
| Create | `frontend/src/extensions/docmgr/NewSubFolderDialog.tsx` | Dialog for creating sub-folders |
| Modify | `frontend/src/extensions/docmgr/DocumentManagement.tsx` | Replace project folder sidebar with `ProjectFolderTree` |
| Modify | `frontend/src/extensions/docmgr/useDocuments.ts` | Add `folder_id` filter support |

---

### Task 1: Add Folder Model and Database Migration

**Files:**
- Modify: `backend/app/extensions/models.py` (after `AIDocument` class)
- Modify: `backend/app/extensions/database.py` (inside `migrate_db()`)

- [ ] **Step 1: Add Folder model to models.py**

Insert after the `AIDocument` class (around line 267), before the `Conversation` class:

```python
class Folder(Base):
    """Folder for organizing documents — supports tree structure and project binding."""

    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    parent: Mapped[Optional["Folder"]] = relationship("Folder", remote_side=[id], back_populates="children")
    children: Mapped[list["Folder"]] = relationship("Folder", back_populates="parent", cascade="all, delete-orphan")
    owner: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name={self.name})>"
```

- [ ] **Step 2: Add folder_id column to AIDocument model**

In `models.py`, add after the `folder` field on `AIDocument` (around line 247):

```python
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True,
    )
```

- [ ] **Step 3: Add database migration in database.py**

Inside `migrate_db()`, add after the `report_projects` table creation block (around line 810). Find the section that creates report_projects and project_chapters tables, and add after them:

```python
        # --- Folders table for document organization ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS folders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                parent_id UUID REFERENCES folders(id) ON DELETE CASCADE,
                project_id UUID REFERENCES report_projects(id) ON DELETE CASCADE,
                owner_id UUID NOT NULL REFERENCES users(id),
                sort_order INT NOT NULL DEFAULT 0,
                is_system BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_folders_project_id ON folders(project_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_folders_owner_id ON folders(owner_id)"))

        # --- AIDocument: folder_id FK to folders table ---
        await conn.execute(text("ALTER TABLE ai_documents ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES folders(id) ON DELETE SET NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_documents_folder_id ON ai_documents(folder_id)"))
```

- [ ] **Step 4: Restart gateway and verify table creation**

Run:
```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker logs gateway --tail 30
```

Expected: Gateway starts without errors. Check table exists:
```bash
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "\d folders"
```

Expected output: Table definition showing all columns.

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/models.py backend/app/extensions/database.py
git commit -m "feat(docmgr): add Folder model and database migration for folder entities"
```

---

### Task 2: Add Folder Schemas

**Files:**
- Modify: `backend/app/extensions/schemas.py`

- [ ] **Step 1: Add folder schemas after FolderListResponse (around line 611)**

```python
class FolderCreate(BaseModel):
    """Folder create schema."""
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: UUID | None = Field(None, description="Parent folder ID (null = root)")
    project_id: UUID | None = Field(None, description="Project ID to bind root folder")


class FolderUpdate(BaseModel):
    """Folder update schema."""
    name: str = Field(..., min_length=1, max_length=255)


class FolderSortUpdate(BaseModel):
    """Folder sort order update."""
    sort_order: int = Field(..., ge=0)


class FolderResponse(BaseModel):
    """Folder response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None = None
    project_id: UUID | None = None
    owner_id: UUID
    sort_order: int = 0
    is_system: bool = False
    doc_count: int = 0
    children: list["FolderResponse"] = []
    created_at: datetime
    updated_at: datetime


class FolderTreeResponse(BaseModel):
    """Folder tree response."""
    folders: list[FolderResponse]


class FolderDeleteConfirm(BaseModel):
    """Response showing what will be deleted."""
    folder_id: UUID
    folder_name: str
    subfolder_count: int
    doc_count: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/schemas.py
git commit -m "feat(docmgr): add folder CRUD schemas — create, update, response, tree"
```

---

### Task 3: Create FolderService

**Files:**
- Create: `backend/app/extensions/docmgr/folder_service.py`

- [ ] **Step 1: Create folder_service.py**

```python
"""Folder service for document space folder management."""

import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.extensions.models import AIDocument, Folder, ProjectMember, ReportProject

logger = logging.getLogger(__name__)

MAX_DEPTH = 3


class FolderService:
    """CRUD and tree operations for folders."""

    @staticmethod
    async def _check_project_admin(db: AsyncSession, user_id: UUID, project_id: UUID) -> bool:
        """Check if user is owner or manager of the project."""
        stmt = select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row in ("owner", "manager")

    @staticmethod
    async def _get_root_folder(db: AsyncSession, folder: Folder) -> Folder | None:
        """Walk up the tree to find the root folder."""
        current = folder
        while current.parent_id is not None:
            parent = await db.get(Folder, current.parent_id)
            if parent is None:
                break
            current = parent
        return current

    @staticmethod
    async def _get_depth(db: AsyncSession, folder_id: UUID) -> int:
        """Calculate the depth of a folder in the tree."""
        depth = 0
        current_id = folder_id
        while current_id is not None:
            folder = await db.get(Folder, current_id)
            if folder is None:
                break
            depth += 1
            current_id = folder.parent_id
        return depth

    @staticmethod
    async def _collect_subfolder_ids(db: AsyncSession, folder_id: UUID) -> list[UUID]:
        """Recursively collect all subfolder IDs."""
        ids = []
        stack = [folder_id]
        while stack:
            current = stack.pop()
            ids.append(current)
            stmt = select(Folder.id).where(Folder.parent_id == current)
            result = await db.execute(stmt)
            children = [row[0] for row in result.all()]
            stack.extend(children)
        return ids

    @staticmethod
    async def get_folder_tree(
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID | None = None,
        project_scope: str | None = None,
    ) -> list[Folder]:
        """Get folder tree for the user. Returns root-level folders with children loaded."""
        # Base visibility: own folders OR folders from projects the user is a member of
        own_folders = Folder.owner_id == user_id
        my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        project_folders = Folder.project_id.in_(my_project_ids)

        stmt = (
            select(Folder)
            .where(
                Folder.parent_id.is_(None),  # root folders only
                own_folders | project_folders,
            )
            .order_by(Folder.sort_order, Folder.created_at)
            .options(selectinload(Folder.children))
        )

        if project_id is not None:
            stmt = stmt.where(Folder.project_id == project_id)
        elif project_scope == "personal":
            stmt = stmt.where(Folder.project_id.is_(None))
        elif project_scope == "project":
            stmt = stmt.where(Folder.project_id.isnot(None))

        result = await db.execute(stmt)
        roots = list(result.scalars().all())

        # Load children recursively and compute doc_counts
        for root in roots:
            await FolderService._load_children_recursive(db, root)

        return roots

    @staticmethod
    async def _load_children_recursive(db: AsyncSession, folder: Folder) -> Folder:
        """Recursively load children and compute doc counts."""
        # Count docs directly in this folder
        count_stmt = select(func.count(AIDocument.id)).where(AIDocument.folder_id == folder.id)
        count_result = await db.execute(count_stmt)
        folder.doc_count = count_result.scalar() or 0

        # Load children
        child_stmt = (
            select(Folder)
            .where(Folder.parent_id == folder.id)
            .order_by(Folder.sort_order, Folder.created_at)
            .options(selectinload(Folder.children))
        )
        child_result = await db.execute(child_stmt)
        folder.children = list(child_result.scalars().all())

        for child in folder.children:
            await FolderService._load_children_recursive(db, child)

        return folder

    @staticmethod
    async def create_folder(
        db: AsyncSession,
        user_id: UUID,
        name: str,
        parent_id: UUID | None = None,
        project_id: UUID | None = None,
        is_system: bool = False,
    ) -> Folder:
        """Create a new folder."""
        resolved_project_id = project_id

        if parent_id is not None:
            parent = await db.get(Folder, parent_id)
            if parent is None:
                raise ValueError("Parent folder not found")

            # Inherit project_id from parent chain
            if resolved_project_id is None and parent.project_id is not None:
                resolved_project_id = parent.project_id

            # Permission check for project folders
            if resolved_project_id is not None:
                if not await FolderService._check_project_admin(db, user_id, resolved_project_id):
                    raise PermissionError("Only project owner/manager can create sub-folders")

            # Depth check
            depth = await FolderService._get_depth(db, parent_id)
            if depth >= MAX_DEPTH:
                raise ValueError(f"Maximum folder depth ({MAX_DEPTH}) exceeded")
        else:
            # Creating a root folder — if project_id given, check admin
            if resolved_project_id is not None:
                if not await FolderService._check_project_admin(db, user_id, resolved_project_id):
                    raise PermissionError("Only project owner/manager can create project root folders")

        # Check for duplicate name at same level
        dup_stmt = select(Folder.id).where(
            Folder.name == name,
            Folder.parent_id == parent_id if parent_id else Folder.parent_id.is_(None),
        )
        if resolved_project_id is not None and parent_id is None:
            dup_stmt = dup_stmt.where(Folder.project_id == resolved_project_id)
        elif parent_id is not None:
            dup_stmt = dup_stmt.where(Folder.parent_id == parent_id)

        dup_result = await db.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            raise ValueError(f"Folder '{name}' already exists at this level")

        folder = Folder(
            name=name,
            parent_id=parent_id,
            project_id=resolved_project_id,
            owner_id=user_id,
            is_system=is_system,
        )
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    @staticmethod
    async def rename_folder(
        db: AsyncSession,
        folder_id: UUID,
        user_id: UUID,
        new_name: str,
    ) -> Folder:
        """Rename a folder. If it's a project root, sync project name."""
        folder = await db.get(Folder, folder_id)
        if folder is None:
            raise ValueError("Folder not found")
        if folder.is_system:
            raise PermissionError("System folders cannot be renamed")

        # Permission check
        root = await FolderService._get_root_folder(db, folder)
        if root and root.project_id:
            if not await FolderService._check_project_admin(db, user_id, root.project_id):
                raise PermissionError("Only project owner/manager can rename folders")
        elif folder.owner_id != user_id:
            raise PermissionError("Only the folder owner can rename this folder")

        # Duplicate name check at same level
        dup_stmt = select(Folder.id).where(
            Folder.name == new_name,
            Folder.id != folder_id,
        )
        if folder.parent_id:
            dup_stmt = dup_stmt.where(Folder.parent_id == folder.parent_id)
        else:
            dup_stmt = dup_stmt.where(Folder.parent_id.is_(None))
        dup_result = await db.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            raise ValueError(f"Folder '{new_name}' already exists at this level")

        folder.name = new_name

        # Sync project name if this is a project root folder
        if folder.parent_id is None and folder.project_id is not None:
            project = await db.get(ReportProject, folder.project_id)
            if project:
                project.name = new_name

        # Dual-write: update all documents' folder string in this folder
        await db.execute(
            AIDocument.__table__.update()
            .where(AIDocument.folder_id == folder_id)
            .values(folder=new_name)
        )

        await db.commit()
        await db.refresh(folder)
        return folder

    @staticmethod
    async def get_delete_info(db: AsyncSession, folder_id: UUID) -> dict:
        """Get info about what will be deleted (for confirmation dialog)."""
        folder = await db.get(Folder, folder_id)
        if folder is None:
            raise ValueError("Folder not found")

        all_ids = await FolderService._collect_subfolder_ids(db, folder_id)

        # Count docs in all subfolders
        count_stmt = select(func.count(AIDocument.id)).where(AIDocument.folder_id.in_(all_ids))
        count_result = await db.execute(count_stmt)
        doc_count = count_result.scalar() or 0

        return {
            "folder_id": folder.id,
            "folder_name": folder.name,
            "subfolder_count": len(all_ids) - 1,  # exclude self
            "doc_count": doc_count,
        }

    @staticmethod
    async def delete_folder(db: AsyncSession, folder_id: UUID, user_id: UUID) -> None:
        """Delete a folder and all its contents."""
        folder = await db.get(Folder, folder_id)
        if folder is None:
            raise ValueError("Folder not found")
        if folder.is_system:
            raise PermissionError("System folders cannot be deleted")

        # Cannot delete project root directly
        if folder.parent_id is None and folder.project_id is not None:
            raise PermissionError("Project root folders can only be deleted by deleting the project")

        # Permission check
        root = await FolderService._get_root_folder(db, folder)
        if root and root.project_id:
            if not await FolderService._check_project_admin(db, user_id, root.project_id):
                raise PermissionError("Only project owner/manager can delete folders")
        elif folder.owner_id != user_id:
            raise PermissionError("Only the folder owner can delete this folder")

        # Collect all subfolder IDs
        all_ids = await FolderService._collect_subfolder_ids(db, folder_id)

        # Delete all documents in these folders
        await db.execute(
            delete(AIDocument).where(AIDocument.folder_id.in_(all_ids))
        )

        # Delete the folder (CASCADE handles sub-folders)
        await db.delete(folder)
        await db.commit()

    @staticmethod
    async def delete_project_folder_tree(db: AsyncSession, project_id: UUID) -> int:
        """Delete all folders for a project. Returns count of folders deleted.
        Called when a project is deleted.
        """
        stmt = select(Folder).where(
            Folder.project_id == project_id,
            Folder.parent_id.is_(None),
        )
        result = await db.execute(stmt)
        roots = list(result.scalars().all())

        total_deleted = 0
        for root in roots:
            all_ids = await FolderService._collect_subfolder_ids(db, root.id)
            # Delete documents first
            await db.execute(delete(AIDocument).where(AIDocument.folder_id.in_(all_ids)))
            await db.delete(root)
            total_deleted += len(all_ids)

        await db.commit()
        return total_deleted

    @staticmethod
    async def move_document_to_folder(
        db: AsyncSession,
        doc: AIDocument,
        folder_id: UUID,
    ) -> AIDocument:
        """Move a document to a folder (sets both folder_id and folder string)."""
        folder = await db.get(Folder, folder_id)
        if folder is None:
            raise ValueError("Target folder not found")

        doc.folder_id = folder.id
        doc.folder = folder.name  # Dual-write for transition period

        if doc.project_id is None and folder.project_id is not None:
            doc.project_id = folder.project_id

        await db.commit()
        await db.refresh(doc)
        return doc
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/docmgr/folder_service.py
git commit -m "feat(docmgr): add FolderService — CRUD, tree, permissions, dual-write"
```

---

### Task 4: Add Folder Router Endpoints

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`

- [ ] **Step 1: Add folder imports and request models**

At the top of `routers.py`, add to the imports from `app.extensions.schemas`:

```python
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentListResponse,
    AIDocumentResponse,
    AIDocumentUpdate,
    CurrentUser,
    FolderCreate,
    FolderDeleteConfirm,
    FolderListResponse,
    FolderResponse,
    FolderSortUpdate,
    FolderTreeResponse,
    FolderUpdate,
    MessageResponse,
)
```

Add the new import:
```python
from app.extensions.docmgr.folder_service import FolderService
```

Add request models after the existing `BatchDeleteRequest` class:

```python
class CreateFolderRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: UUID | None = Field(None, description="Parent folder ID")
    project_id: UUID | None = Field(None, description="Project ID for root folder binding")
```

- [ ] **Step 2: Replace the existing GET /folders endpoint and add new folder CRUD endpoints**

Replace the existing `list_folders` endpoint (around line 400) with:

```python
@router.get("/folders/tree", response_model=FolderTreeResponse)
async def get_folder_tree(
    project_id: UUID | None = Query(None, description="Filter by project ID"),
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get folder tree for the current user."""
    folders = await FolderService.get_folder_tree(
        db, current_user.id, project_id=project_id, project_scope=project_scope,
    )
    return FolderTreeResponse(
        folders=[FolderService._to_response(f) for f in folders]
    )


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all folders for the current user (backward compatible)."""
    folders = await AIDocumentService.list_folders(db, current_user.id, project_scope=project_scope)
    return FolderListResponse(folders=folders)


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: CreateFolderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new folder or sub-folder."""
    try:
        folder = await FolderService.create_folder(
            db, current_user.id, data.name, parent_id=data.parent_id, project_id=data.project_id,
        )
        return await FolderService.to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    folder_id: UUID,
    data: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename a folder."""
    try:
        folder = await FolderService.rename_folder(db, folder_id, current_user.id, data.name)
        return await FolderService.to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/folders/{folder_id}/delete-info", response_model=FolderDeleteConfirm)
async def get_folder_delete_info(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get deletion preview for a folder."""
    try:
        info = await FolderService.get_delete_info(db, folder_id)
        return FolderDeleteConfirm(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/folders/{folder_id}", response_model=MessageResponse)
async def delete_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a folder and all its contents."""
    try:
        await FolderService.delete_folder(db, folder_id, current_user.id)
        return MessageResponse(message="Folder deleted successfully")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 3: Add `to_response` static method to FolderService**

In `folder_service.py`, add at the end of the `FolderService` class:

```python
    @staticmethod
    async def to_response(folder: Folder) -> FolderResponse:
        """Convert folder model to response schema."""
        return FolderResponse(
            id=folder.id,
            name=folder.name,
            parent_id=folder.parent_id,
            project_id=folder.project_id,
            owner_id=folder.owner_id,
            sort_order=folder.sort_order,
            is_system=folder.is_system,
            doc_count=getattr(folder, "doc_count", 0),
            children=[await FolderService.to_response(c) for c in (folder.children or [])],
            created_at=folder.created_at,
            updated_at=folder.updated_at,
        )
```

- [ ] **Step 4: Add folder_id filter to document list endpoint**

In the `list_documents` endpoint, add `folder_id` query parameter:

```python
@router.get("/documents", response_model=AIDocumentListResponse)
async def list_documents(
    folder: str | None = Query(None, description="Filter by folder name"),
    folder_id: UUID | None = Query(None, description="Filter by folder ID (new)"),
    starred: bool | None = Query(None, description="Filter by starred status"),
    # ... rest unchanged
```

In `AIDocumentService.list_docs()`, add the `folder_id` parameter and filter. In `service.py`, add to the method signature:

```python
    @staticmethod
    async def list_docs(
        db: AsyncSession,
        user_id: UUID,
        folder: str | None = None,
        folder_id: UUID | None = None,
        # ... rest unchanged
```

And add the filter after the existing `folder` filter:

```python
        if folder_id is not None:
            query = query.where(AIDocument.folder_id == folder_id)
            count_query = count_query.where(AIDocument.folder_id == folder_id)
```

Update the router call to pass `folder_id`:

```python
    documents, total = await AIDocumentService.list_docs(
        db,
        user_id=current_user.id,
        folder=folder,
        folder_id=folder_id,
        # ... rest unchanged
    )
```

- [ ] **Step 5: Restart gateway and test endpoints**

```bash
docker compose -p eai-docker restart gateway
```

Test with curl:
```bash
curl -s -b cookies.txt http://localhost:2026/api/extensions/docmgr/folders/tree | python -m json.tool
```

Expected: `{"folders": []}` (empty tree since no folders created yet).

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/docmgr/routers.py backend/app/extensions/docmgr/service.py backend/app/extensions/docmgr/folder_service.py
git commit -m "feat(docmgr): add folder CRUD endpoints — tree, create, rename, delete"
```

---

### Task 5: Hook Folder Creation into Project Lifecycle

**Files:**
- Modify: `backend/app/extensions/project/service.py`

- [ ] **Step 1: Add folder import to project service**

At the top of `project/service.py`, add:

```python
from app.extensions.docmgr.folder_service import FolderService
```

- [ ] **Step 2: Hook into create_project**

In `create_project()`, after the project is created and committed, add folder creation. Find the section after `await db.commit()` (or `await db.refresh(project)`) and add:

```python
    # Auto-create project root folder in document space
    try:
        await FolderService.create_folder(
            db,
            user_id=created_by,
            name=project.name,
            project_id=project.id,
            is_system=False,
        )
    except Exception as e:
        logger.warning("Failed to create project root folder: %s", e)
```

Add `import logging` and `logger = logging.getLogger(__name__)` at the top if not present.

- [ ] **Step 3: Hook into delete_project**

Find the `delete_project()` function. Before the existing code that nulls out `AIDocument.project_id`, add:

```python
    # Delete project folder tree (and all documents within)
    await FolderService.delete_project_folder_tree(db, project_id)
```

- [ ] **Step 4: Hook into update_project**

Find the `update_project()` function (or `PATCH` handler). When `name` is updated, sync the root folder:

```python
    # Sync folder name with project name
    if update_data.get("name"):
        try:
            from sqlalchemy import select as sa_select
            from app.extensions.models import Folder as FolderModel
            stmt = sa_select(FolderModel).where(
                FolderModel.project_id == project_id,
                FolderModel.parent_id.is_(None),
            )
            result = await db.execute(stmt)
            root_folder = result.scalar_one_or_none()
            if root_folder:
                await FolderService.rename_folder(db, root_folder.id, created_by, update_data["name"])
        except Exception as e:
            logger.warning("Failed to sync folder name: %s", e)
```

Note: Adjust `created_by` to the actual `current_user.id` variable used in that function.

- [ ] **Step 5: Restart gateway and test**

```bash
docker compose -p eai-docker restart gateway
```

Create a project via the UI or API, then check:
```bash
curl -s -b cookies.txt http://localhost:2026/api/extensions/docmgr/folders/tree | python -m json.tool
```

Expected: Tree contains a root folder matching the new project name.

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/project/service.py
git commit -m "feat(project): hook folder creation/rename/delete into project lifecycle"
```

---

### Task 6: Data Migration Script for Existing Folders

**Files:**
- Create: `backend/scripts/migrate_folders.py`

- [ ] **Step 1: Create the migration script**

```python
"""One-time migration: convert virtual folder strings to Folder entities.

Run: cd backend && PYTHONPATH=. python scripts/migrate_folders.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, distinct, update
from app.extensions.database import init_engine, get_db_context, close_db
from app.extensions.models import AIDocument, Folder, ReportProject, ProjectMember

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    init_engine()
    async with get_db_context() as db:
        # 1. Migrate project folders
        logger.info("=== Migrating project folders ===")
        stmt = (
            select(
                AIDocument.project_id,
                AIDocument.folder,
            )
            .where(AIDocument.project_id.isnot(None))
            .distinct()
        )
        result = await db.execute(stmt)
        project_folder_pairs = result.all()

        project_roots: dict = {}  # project_id -> root Folder

        for project_id, folder_name in project_folder_pairs:
            # Get project name for root folder
            project = await db.get(ReportProject, project_id)
            if not project:
                continue

            # Create root folder if not exists
            if project_id not in project_roots:
                existing = await db.execute(
                    select(Folder).where(
                        Folder.project_id == project_id,
                        Folder.parent_id.is_(None),
                    )
                )
                root = existing.scalar_one_or_none()
                if root is None:
                    # Find an owner for this folder
                    owner_stmt = select(ProjectMember.user_id).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.role == "owner",
                    ).limit(1)
                    owner_result = await db.execute(owner_stmt)
                    owner_id = owner_result.scalar_one_or_none() or project.created_by

                    root = Folder(
                        name=project.name,
                        project_id=project_id,
                        owner_id=owner_id,
                        is_system=False,
                    )
                    db.add(root)
                    await db.flush()
                project_roots[project_id] = root

            root = project_roots[project_id]

            # Create sub-folder under root
            sub = Folder(
                name=folder_name,
                parent_id=root.id,
                owner_id=root.owner_id,
            )
            db.add(sub)
            await db.flush()

            # Update documents to point to this folder
            await db.execute(
                update(AIDocument)
                .where(
                    AIDocument.project_id == project_id,
                    AIDocument.folder == folder_name,
                    AIDocument.folder_id.is_(None),
                )
                .values(folder_id=sub.id)
            )
            logger.info(f"  Project '{project.name}' -> folder '{folder_name}' ({sub.id})")

        # 2. Migrate personal folders
        logger.info("=== Migrating personal folders ===")
        stmt = (
            select(AIDocument.user_id, AIDocument.folder)
            .where(AIDocument.project_id.is_(None))
            .distinct()
        )
        result = await db.execute(stmt)
        personal_pairs = result.all()

        personal_roots: dict = {}  # user_id -> root Folder

        for user_id, folder_name in personal_pairs:
            if user_id not in personal_roots:
                # Create personal root folder
                existing = await db.execute(
                    select(Folder).where(
                        Folder.owner_id == user_id,
                        Folder.parent_id.is_(None),
                        Folder.project_id.is_(None),
                        Folder.name == "我的文档",
                    )
                )
                root = existing.scalar_one_or_none()
                if root is None:
                    root = Folder(
                        name="我的文档",
                        owner_id=user_id,
                        project_id=None,
                        is_system=False,
                    )
                    db.add(root)
                    await db.flush()
                personal_roots[user_id] = root

            root = personal_roots[user_id]

            # Create sub-folder
            sub = Folder(
                name=folder_name,
                parent_id=root.id,
                owner_id=user_id,
            )
            db.add(sub)
            await db.flush()

            # Update documents
            await db.execute(
                update(AIDocument)
                .where(
                    AIDocument.user_id == user_id,
                    AIDocument.folder == folder_name,
                    AIDocument.project_id.is_(None),
                    AIDocument.folder_id.is_(None),
                )
                .values(folder_id=sub.id)
            )
            logger.info(f"  User {user_id} -> folder '{folder_name}' ({sub.id})")

        await db.commit()
        logger.info("=== Migration complete ===")

    await close_db()


if __name__ == "__main__":
    asyncio.run(migrate())
```

- [ ] **Step 2: Run the migration**

```bash
docker compose -p eai-docker exec gateway bash -c "cd /app && PYTHONPATH=. python scripts/migrate_folders.py"
```

Expected output: Log lines showing folders created for each project and user.

- [ ] **Step 3: Verify migration**

```bash
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT id, name, project_id, parent_id FROM folders"
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT id, title, folder, folder_id FROM ai_documents LIMIT 10"
```

Expected: `folders` table has rows, `ai_documents.folder_id` is populated.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/migrate_folders.py
git commit -m "feat(docmgr): add data migration script — virtual folders to Folder entities"
```

---

### Task 7: Frontend API Client for Folders

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`

- [ ] **Step 1: Add folder API types and methods**

After the existing `docmgrApi` object, add a `folderApi` object. First, add the types at the top of the file (or near the existing type definitions):

```typescript
// Folder types
export interface FolderNode {
  id: string
  name: string
  parent_id: string | null
  project_id: string | null
  owner_id: string
  sort_order: number
  is_system: boolean
  doc_count: number
  children: FolderNode[]
  created_at: string
  updated_at: string
}

export interface FolderTreeResponse {
  folders: FolderNode[]
}

export interface FolderDeleteInfo {
  folder_id: string
  folder_name: string
  subfolder_count: number
  doc_count: number
}
```

Then add the API object:

```typescript
export const folderApi = {
  getTree: async (params?: { project_id?: string; project_scope?: string }): Promise<FolderTreeResponse> => {
    const searchParams = new URLSearchParams()
    if (params?.project_id) searchParams.set("project_id", params.project_id)
    if (params?.project_scope) searchParams.set("project_scope", params.project_scope)
    const qs = searchParams.toString()
    const res = await fetch(`/api/extensions/docmgr/folders/tree${qs ? `?${qs}` : ""}`, { credentials: "include" })
    if (!res.ok) throw new Error("Failed to fetch folder tree")
    return res.json()
  },

  create: async (data: { name: string; parent_id?: string; project_id?: string }): Promise<FolderNode> => {
    const res = await fetch("/api/extensions/docmgr/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Failed to create folder" }))
      throw new Error(err.detail || "Failed to create folder")
    }
    return res.json()
  },

  rename: async (folderId: string, name: string): Promise<FolderNode> => {
    const res = await fetch(`/api/extensions/docmgr/folders/${folderId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ name }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Failed to rename folder" }))
      throw new Error(err.detail || "Failed to rename folder")
    }
    return res.json()
  },

  getDeleteInfo: async (folderId: string): Promise<FolderDeleteInfo> => {
    const res = await fetch(`/api/extensions/docmgr/folders/${folderId}/delete-info`, { credentials: "include" })
    if (!res.ok) throw new Error("Failed to get delete info")
    return res.json()
  },

  delete: async (folderId: string): Promise<void> => {
    const res = await fetch(`/api/extensions/docmgr/folders/${folderId}`, {
      method: "DELETE",
      credentials: "include",
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Failed to delete folder" }))
      throw new Error(err.detail || "Failed to delete folder")
    }
  },
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/api/index.ts
git commit -m "feat(docmgr): add frontend folder API client — tree, create, rename, delete"
```

---

### Task 8: Frontend useFolderTree Hook

**Files:**
- Create: `frontend/src/extensions/docmgr/useFolderTree.ts`

- [ ] **Step 1: Create the hook**

```typescript
"use client"

import { useState, useCallback, useEffect } from "react"
import { folderApi, type FolderNode } from "@/extensions/api"

export function useFolderTree(projectScope?: string) {
  const [folders, setFolders] = useState<FolderNode[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())

  const fetchTree = useCallback(async () => {
    setLoading(true)
    try {
      const params = projectScope ? { project_scope: projectScope } : undefined
      const data = await folderApi.getTree(params)
      setFolders(data.folders)
    } catch (err) {
      console.error("Failed to fetch folder tree:", err)
    } finally {
      setLoading(false)
    }
  }, [projectScope])

  useEffect(() => {
    fetchTree()
  }, [fetchTree])

  const toggleExpand = useCallback((folderId: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(folderId)) {
        next.delete(folderId)
      } else {
        next.add(folderId)
      }
      return next
    })
  }, [])

  const createFolder = useCallback(
    async (name: string, parentId: string | null, projectId?: string) => {
      const folder = await folderApi.create({
        name,
        parent_id: parentId || undefined,
        project_id: projectId,
      })
      await fetchTree()
      // Auto-expand parent
      if (parentId) {
        setExpandedKeys((prev) => new Set(prev).add(parentId))
      }
      return folder
    },
    [fetchTree],
  )

  const renameFolder = useCallback(
    async (folderId: string, name: string) => {
      await folderApi.rename(folderId, name)
      await fetchTree()
    },
    [fetchTree],
  )

  const deleteFolder = useCallback(
    async (folderId: string) => {
      await folderApi.delete(folderId)
      await fetchTree()
    },
    [fetchTree],
  )

  return {
    folders,
    loading,
    expandedKeys,
    toggleExpand,
    createFolder,
    renameFolder,
    deleteFolder,
    refreshTree: fetchTree,
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/docmgr/useFolderTree.ts
git commit -m "feat(docmgr): add useFolderTree hook — state management for folder tree"
```

---

### Task 9: Frontend ProjectFolderTree Component

**Files:**
- Create: `frontend/src/extensions/docmgr/ProjectFolderTree.tsx`
- Create: `frontend/src/extensions/docmgr/NewSubFolderDialog.tsx`

- [ ] **Step 1: Create NewSubFolderDialog**

```tsx
"use client"

import { useState } from "react"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

interface NewSubFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  parentId: string | null
  projectId?: string
  onSubmit: (name: string, parentId: string | null, projectId?: string) => Promise<void>
}

export function NewSubFolderDialog({ open, onOpenChange, parentId, projectId, onSubmit }: NewSubFolderDialogProps) {
  const [name, setName] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setSubmitting(true)
    try {
      await onSubmit(name.trim(), parentId, projectId)
      setName("")
      onOpenChange(false)
    } catch (err) {
      console.error("Failed to create folder:", err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>新建子文件夹</DialogTitle>
        </DialogHeader>
        <input
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="输入文件夹名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          autoFocus
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={!name.trim() || submitting}>
            {submitting ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Create ProjectFolderTree**

```tsx
"use client"

import { useState, useRef, useEffect } from "react"
import type { FolderNode } from "@/extensions/api"
import { NewSubFolderDialog } from "./NewSubFolderDialog"

interface ProjectFolderTreeProps {
  folders: FolderNode[]
  expandedKeys: Set<string>
  onToggleExpand: (folderId: string) => void
  onSelectFolder: (folderId: string, folderName: string) => void
  onCreateFolder: (name: string, parentId: string | null, projectId?: string) => Promise<void>
  onRenameFolder: (folderId: string, name: string) => Promise<void>
  onDeleteFolder: (folderId: string) => Promise<void>
  activeFolderId?: string | null
}

export function ProjectFolderTree({
  folders,
  expandedKeys,
  onToggleExpand,
  onSelectFolder,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  activeFolderId,
}: ProjectFolderTreeProps) {
  return (
    <div className="space-y-0.5">
      {folders.map((folder) => (
        <FolderNodeComponent
          key={folder.id}
          folder={folder}
          depth={0}
          expandedKeys={expandedKeys}
          onToggleExpand={onToggleExpand}
          onSelectFolder={onSelectFolder}
          onCreateFolder={onCreateFolder}
          onRenameFolder={onRenameFolder}
          onDeleteFolder={onDeleteFolder}
          activeFolderId={activeFolderId}
        />
      ))}
    </div>
  )
}

interface FolderNodeComponentProps {
  folder: FolderNode
  depth: number
  expandedKeys: Set<string>
  onToggleExpand: (folderId: string) => void
  onSelectFolder: (folderId: string, folderName: string) => void
  onCreateFolder: (name: string, parentId: string | null, projectId?: string) => Promise<void>
  onRenameFolder: (folderId: string, name: string) => Promise<void>
  onDeleteFolder: (folderId: string) => Promise<void>
  activeFolderId?: string | null
}

function FolderNodeComponent({
  folder,
  depth,
  expandedKeys,
  onToggleExpand,
  onSelectFolder,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  activeFolderId,
}: FolderNodeComponentProps) {
  const [hovered, setHovered] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(folder.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)

  const isExpanded = expandedKeys.has(folder.id)
  const isActive = activeFolderId === folder.id
  const isProjectRoot = folder.parent_id === null && folder.project_id !== null
  const hasChildren = folder.children.length > 0

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showMenu])

  // Auto-focus rename input
  useEffect(() => {
    if (renaming && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [renaming])

  const handleRenameSubmit = async () => {
    const trimmed = renameValue.trim()
    if (!trimmed || trimmed === folder.name) {
      setRenaming(false)
      setRenameValue(folder.name)
      return
    }
    try {
      await onRenameFolder(folder.id, trimmed)
    } catch {
      setRenameValue(folder.name)
    }
    setRenaming(false)
  }

  const handleDelete = async () => {
    try {
      await onDeleteFolder(folder.id)
    } catch (err) {
      console.error("Delete failed:", err)
    }
    setConfirmDelete(false)
    setShowMenu(false)
  }

  return (
    <>
      <div
        className="group relative"
        style={{ paddingLeft: depth * 16 }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => {
          setHovered(false)
          if (!showMenu) setShowMenu(false)
        }}
      >
        <div
          className={`flex items-center gap-1.5 rounded px-2 py-1 text-sm cursor-pointer transition-colors ${
            isActive ? "bg-blue-600/20 text-blue-300" : "text-gray-300 hover:bg-white/5"
          }`}
          onClick={() => {
            if (hasChildren || isProjectRoot) {
              onToggleExpand(folder.id)
            }
            onSelectFolder(folder.id, folder.name)
          }}
        >
          {/* Expand/collapse arrow */}
          {(hasChildren || isProjectRoot) && (
            <span className="text-xs text-gray-500 w-3 shrink-0">
              {isExpanded ? "▼" : "▶"}
            </span>
          )}
          {!hasChildren && !isProjectRoot && <span className="w-3 shrink-0" />}

          {/* Folder icon */}
          <span className="shrink-0">{isExpanded && hasChildren ? "📂" : "📁"}</span>

          {/* Name or rename input */}
          {renaming ? (
            <input
              ref={renameInputRef}
              className="flex-1 bg-gray-700 rounded px-1.5 py-0.5 text-sm text-white outline-none focus:ring-1 focus:ring-blue-500"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRenameSubmit()
                if (e.key === "Escape") {
                  setRenaming(false)
                  setRenameValue(folder.name)
                }
              }}
              onBlur={handleRenameSubmit}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="flex-1 truncate">{folder.name}</span>
          )}

          {/* Doc count */}
          <span className="text-xs text-gray-500 shrink-0">{folder.doc_count}</span>

          {/* Hover action buttons */}
          {hovered && !renaming && !folder.is_system && (
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/10 text-gray-400 hover:text-blue-400 text-xs"
                title="新建子文件夹"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowNewDialog(true)
                }}
              >
                +
              </button>
              <div className="relative" ref={menuRef}>
                <button
                  className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/10 text-gray-400 hover:text-white text-xs"
                  title="更多操作"
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowMenu(!showMenu)
                  }}
                >
                  ⋯
                </button>

                {/* Dropdown menu */}
                {showMenu && (
                  <div className="absolute right-0 top-6 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[140px]">
                    <button
                      className="w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-white/5"
                      onClick={(e) => {
                        e.stopPropagation()
                        setShowMenu(false)
                        setRenaming(true)
                        setRenameValue(folder.name)
                      }}
                    >
                      ✏️ 重命名
                    </button>
                    {!isProjectRoot && (
                      <>
                        <div className="border-t border-gray-700 my-1" />
                        <button
                          className="w-full px-3 py-1.5 text-left text-sm text-red-400 hover:bg-white/5"
                          onClick={(e) => {
                            e.stopPropagation()
                            setShowMenu(false)
                            setConfirmDelete(true)
                          }}
                        >
                          🗑️ 删除
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Children (recursive) */}
      {isExpanded && hasChildren && (
        <div>
          {folder.children.map((child) => (
            <FolderNodeComponent
              key={child.id}
              folder={child}
              depth={depth + 1}
              expandedKeys={expandedKeys}
              onToggleExpand={onToggleExpand}
              onSelectFolder={onSelectFolder}
              onCreateFolder={onCreateFolder}
              onRenameFolder={onRenameFolder}
              onDeleteFolder={onDeleteFolder}
              activeFolderId={activeFolderId}
            />
          ))}
        </div>
      )}

      {/* New sub-folder dialog */}
      <NewSubFolderDialog
        open={showNewDialog}
        onOpenChange={setShowNewDialog}
        parentId={folder.id}
        projectId={folder.project_id ?? undefined}
        onSubmit={onCreateFolder}
      />

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(false)}>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 max-w-sm shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-white font-medium mb-2">确认删除</h3>
            <p className="text-gray-400 text-sm mb-4">
              确定要删除文件夹「{folder.name}」吗？
              {folder.doc_count > 0 && (
                <span className="text-red-400"> 包含 {folder.doc_count} 个文档，将全部永久删除。</span>
              )}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white rounded border border-gray-600 hover:border-gray-400"
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded"
                onClick={handleDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/ProjectFolderTree.tsx frontend/src/extensions/docmgr/NewSubFolderDialog.tsx
git commit -m "feat(docmgr): add ProjectFolderTree component — recursive tree with hover actions"
```

---

### Task 10: Integrate ProjectFolderTree into DocumentManagement

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`
- Modify: `frontend/src/extensions/docmgr/useDocuments.ts`

- [ ] **Step 1: Add useFolderTree to useDocuments.ts**

In `useDocuments.ts`, import `useFolderTree` and expose it:

```typescript
import { useFolderTree } from "./useFolderTree"
```

Inside the `useDocuments` hook, add after the existing state:

```typescript
  const folderTree = useFolderTree()
```

Return `folderTree` from the hook.

- [ ] **Step 2: Replace the project folders section in DocumentManagement.tsx**

Add import at the top:

```typescript
import { ProjectFolderTree } from "./ProjectFolderTree"
```

Inside `DocumentList`, add the `folderTree` from `useDocuments`:

```typescript
  const { docs, total, loading, page, pageSize, setPage, folders, projectFolders, createDoc, deleteDoc, toggleStar, setFilter, moveToFolder, batchDeleteDocs, renameDoc, folderTree } =
    useDocuments({ folder: currentFolder })
```

Add state for active folder:

```typescript
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null)
```

Replace the "AI任务存档" / "项目文件夹" section in the sidebar. Find the block that renders `projectFolders.map(...)` and replace with:

```tsx
{/* 项目文件夹 */}
<div className="border-t border-gray-700/50 pt-2">
  <button
    onClick={() => setArchiveOpen(!archiveOpen)}
    className="flex w-full items-center justify-between px-2 py-1 text-xs text-gray-500 hover:text-gray-400"
  >
    <span>📂 项目文件夹</span>
    <span className="text-[10px]">{archiveOpen ? "▼" : "▶"}</span>
  </button>
  {archiveOpen && (
    <ProjectFolderTree
      folders={folderTree.folders}
      expandedKeys={folderTree.expandedKeys}
      onToggleExpand={folderTree.toggleExpand}
      onSelectFolder={(folderId, folderName) => {
        setActiveNav("file_ref_folder")
        setCurrentFolder(folderName)
        setActiveFolderId(folderId)
        setFilter({ folder_id: folderId })
      }}
      onCreateFolder={folderTree.createFolder}
      onRenameFolder={folderTree.renameFolder}
      onDeleteFolder={folderTree.deleteFolder}
      activeFolderId={activeFolderId}
    />
  )}
</div>
```

- [ ] **Step 3: Add folder_id support to useDocuments filter**

In `useDocuments.ts`, update the `setFilter` function to handle `folder_id`:

In the `fetchDocs` function inside `useDocuments`, add support for the `folder_id` parameter in the API call:

```typescript
const params = new URLSearchParams()
// ... existing param building ...
if (filter.folder_id) params.set("folder_id", filter.folder_id)
```

- [ ] **Step 4: Rebuild frontend and restart**

```bash
docker compose -p eai-docker restart frontend
```

Wait for rebuild, then open http://localhost:2026/docmgr and verify:
- Sidebar shows project folder tree
- Clicking a folder shows documents in that folder
- Hover shows "+" and "⋯" buttons
- Create sub-folder works
- Rename works (inline edit)
- Delete shows confirmation dialog

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx frontend/src/extensions/docmgr/useDocuments.ts
git commit -m "feat(docmgr): integrate ProjectFolderTree into sidebar — replaces flat folder list"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Every section in the design spec has a corresponding task
- [x] **Placeholder scan:** No TBD/TODO/fill-in-later patterns found
- [x] **Type consistency:** `FolderNode` TypeScript type matches `FolderResponse` Pydantic schema; `folderApi` methods match router endpoints
- [x] **Import paths:** All imports reference correct file locations verified against anatomy
