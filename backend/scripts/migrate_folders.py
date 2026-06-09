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

            # Skip if root folder name matches this folder name (no sub-folder needed)
            if root.name == folder_name:
                # Update documents directly under root
                await db.execute(
                    update(AIDocument)
                    .where(
                        AIDocument.project_id == project_id,
                        AIDocument.folder == folder_name,
                        AIDocument.folder_id.is_(None),
                    )
                    .values(folder_id=root.id)
                )
                logger.info(f"  Project '{project.name}' -> root folder (same name, {folder_name})")
                continue

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

            # Skip if name matches root
            if root.name == folder_name:
                await db.execute(
                    update(AIDocument)
                    .where(
                        AIDocument.user_id == user_id,
                        AIDocument.folder == folder_name,
                        AIDocument.project_id.is_(None),
                        AIDocument.folder_id.is_(None),
                    )
                    .values(folder_id=root.id)
                )
                continue

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
