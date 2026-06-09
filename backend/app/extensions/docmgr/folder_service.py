"""Folder service for document space folder management."""

import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.extensions.models import AIDocument, Folder, ProjectMember, ReportProject
from app.extensions.schemas import FolderResponse

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
        if parent_id is not None:
            dup_stmt = select(Folder.id).where(
                Folder.name == name,
                Folder.parent_id == parent_id,
            )
        else:
            dup_stmt = select(Folder.id).where(
                Folder.name == name,
                Folder.parent_id.is_(None),
            )
            if resolved_project_id is not None:
                dup_stmt = dup_stmt.where(Folder.project_id == resolved_project_id)

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
        if folder.parent_id:
            dup_stmt = select(Folder.id).where(
                Folder.name == new_name,
                Folder.parent_id == folder.parent_id,
                Folder.id != folder_id,
            )
        else:
            dup_stmt = select(Folder.id).where(
                Folder.name == new_name,
                Folder.parent_id.is_(None),
                Folder.id != folder_id,
            )
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
