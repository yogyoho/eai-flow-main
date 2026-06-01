"""Services for collaborative editing: comments and versions."""

import json
import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.docmgr.collab_models import CollabComment, CollabVersion
from app.extensions.models import User

logger = logging.getLogger(__name__)


class CommentService:
    @staticmethod
    async def list_comments(db: AsyncSession, doc_id: UUID) -> list[dict]:
        stmt = (
            select(CollabComment, User.username, User.full_name)
            .join(User, CollabComment.user_id == User.id, isouter=True)
            .where(CollabComment.doc_id == doc_id)
            .order_by(CollabComment.created_at)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "block_id": c.block_id,
                "content": c.content,
                "parent_id": c.parent_id,
                "user_id": c.user_id,
                "resolved": c.resolved,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "username": username,
                "full_name": full_name,
            }
            for c, username, full_name in rows
        ]

    @staticmethod
    async def create_comment(
        db: AsyncSession, user_id: UUID, doc_id: UUID, block_id: str, content: str, parent_id: UUID | None = None
    ) -> dict:
        comment = CollabComment(
            doc_id=doc_id,
            block_id=block_id,
            content=content,
            parent_id=parent_id,
            user_id=user_id,
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def update_comment(db: AsyncSession, comment_id: UUID, user_id: UUID, content: str) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment or comment.user_id != user_id:
            return None
        comment.content = content
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def delete_comment(db: AsyncSession, comment_id: UUID, user_id: UUID) -> bool:
        comment = await db.get(CollabComment, comment_id)
        if not comment or comment.user_id != user_id:
            return False
        await db.delete(comment)
        await db.commit()
        return True

    @staticmethod
    async def resolve_comment(db: AsyncSession, comment_id: UUID) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment:
            return None
        comment.resolved = True
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, comment.user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def reopen_comment(db: AsyncSession, comment_id: UUID) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment:
            return None
        comment.resolved = False
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, comment.user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }


class AIReviewService:
    @staticmethod
    async def ai_review_document(db: AsyncSession, doc_id: UUID, content: str, review_type: str) -> dict:
        from deerflow.models import create_chat_model

        from app.extensions.settings.service import SystemConfigService

        sys_config = await SystemConfigService.get_all(db)
        default_model = sys_config.get("default_model") or None
        model = create_chat_model(name=default_model, thinking_enabled=False)

        prompts = {
            "full": "请审查以下文档，从逻辑一致性、语言风格统一性、缺失章节、数据准确性四个维度给出建议。对每个问题指出具体段落位置和修改建议。",
            "style": "请审查以下文档的语言风格是否统一，用词是否专业准确，语气是否一致。",
            "logic": "请审查以下文档的逻辑是否连贯，论证是否有漏洞，结构是否清晰。",
            "completeness": "请检查以下文档是否有缺失的章节、未覆盖的要点、需要补充的内容。",
        }
        prompt = prompts.get(review_type, prompts["full"])

        response = await model.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        f"{prompt}\n\n"
                        '请以 JSON 格式返回，格式为: {{"comments": [{{"block_id": null, "comment": "...", '
                        '"severity": "info|warning|error"}}], "overall_score": 0-100, "summary": "..."}}'
                    ),
                },
                {"role": "user", "content": content[:8000]},
            ]
        )
        try:
            result = json.loads(response.content)
        except (json.JSONDecodeError, AttributeError):
            result = {
                "comments": [
                    {
                        "comment": response.content if isinstance(response.content, str) else str(response.content),
                        "severity": "info",
                    }
                ],
                "overall_score": None,
                "summary": None,
            }

        return {
            "review_id": str(uuid4()),
            "comments": result.get("comments", []),
            "overall_score": result.get("overall_score"),
            "summary": result.get("summary"),
        }


class VersionService:
    @staticmethod
    async def list_versions(db: AsyncSession, doc_id: UUID) -> list[dict]:
        stmt = (
            select(CollabVersion, User.username, User.full_name)
            .join(User, CollabVersion.created_by == User.id, isouter=True)
            .where(CollabVersion.doc_id == doc_id)
            .order_by(CollabVersion.version.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": v.id,
                "doc_id": v.doc_id,
                "version": v.version,
                "summary": v.summary,
                "created_by": v.created_by,
                "created_at": v.created_at,
                "username": username,
                "full_name": full_name,
            }
            for v, username, full_name in rows
        ]

    @staticmethod
    async def create_version(
        db: AsyncSession, doc_id: UUID, user_id: UUID, snapshot: bytes, summary: str | None = None
    ) -> dict:
        stmt = select(func.coalesce(func.max(CollabVersion.version), 0) + 1).where(CollabVersion.doc_id == doc_id)
        result = await db.execute(stmt)
        next_version = result.scalar()

        version = CollabVersion(
            doc_id=doc_id,
            version=next_version,
            snapshot=snapshot,
            summary=summary,
            created_by=user_id,
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)
        user = await db.get(User, user_id)
        return {
            "id": version.id,
            "doc_id": version.doc_id,
            "version": version.version,
            "summary": version.summary,
            "created_by": version.created_by,
            "created_at": version.created_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def get_version(db: AsyncSession, doc_id: UUID, version: int) -> dict | None:
        stmt = select(CollabVersion).where(
            CollabVersion.doc_id == doc_id, CollabVersion.version == version
        )
        result = await db.execute(stmt)
        v = result.scalar_one_or_none()
        if not v:
            return None
        user = await db.get(User, v.created_by) if v.created_by else None
        return {
            "id": v.id,
            "doc_id": v.doc_id,
            "version": v.version,
            "snapshot": v.snapshot,
            "summary": v.summary,
            "created_by": v.created_by,
            "created_at": v.created_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def diff_versions(db: AsyncSession, doc_id: UUID, from_ver: int, to_ver: int) -> dict | None:
        from_meta = await VersionService.get_version(db, doc_id, from_ver)
        to_meta = await VersionService.get_version(db, doc_id, to_ver)
        if not from_meta or not to_meta:
            return None

        from_snap = await VersionService.get_snapshot(db, doc_id, from_ver)
        to_snap = await VersionService.get_snapshot(db, doc_id, to_ver)

        from_lines = (from_snap or b"").decode("utf-8", errors="replace").splitlines()
        to_lines = (to_snap or b"").decode("utf-8", errors="replace").splitlines()

        from_set = set(from_lines)
        to_set = set(to_lines)

        added = to_set - from_set
        removed = from_set - to_set

        diff_blocks = []
        for line in sorted(added):
            diff_blocks.append({"type": "added", "content": line})
        for line in sorted(removed):
            diff_blocks.append({"type": "removed", "content": line})

        return {
            "from_version": from_ver,
            "to_version": to_ver,
            "from_summary": from_meta.get("summary"),
            "to_summary": to_meta.get("summary"),
            "from_created_at": from_meta.get("created_at"),
            "to_created_at": to_meta.get("created_at"),
            "diff_blocks": diff_blocks,
            "ai_summary": None,
        }

    @staticmethod
    async def generate_ai_summary(db: AsyncSession, doc_id: UUID, new_version: int) -> str | None:
        prev_version = new_version - 1
        if prev_version < 1:
            return None

        prev_snap = await VersionService.get_snapshot(db, doc_id, prev_version)
        curr_snap = await VersionService.get_snapshot(db, doc_id, new_version)
        if not prev_snap or not curr_snap:
            return None

        prev_text = prev_snap.decode("utf-8", errors="replace")[:4000]
        curr_text = curr_snap.decode("utf-8", errors="replace")[:4000]

        try:
            from deerflow.models import create_chat_model

            from app.extensions.settings.service import SystemConfigService

            sys_config = await SystemConfigService.get_all(db)
            default_model = sys_config.get("default_model") or None
            model = create_chat_model(name=default_model, thinking_enabled=False)
            response = await model.ainvoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是一个文档变更摘要助手。对比文档的两个版本，用1-2句中文总结主要变更内容。"
                            "只关注实质性内容变化（新增、删除、修改的段落），忽略格式差异。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"【旧版本】\n{prev_text}\n\n【新版本】\n{curr_text}",
                    },
                ]
            )
            summary = response.content if isinstance(response.content, str) else str(response.content)
            return summary[:500] if summary else None
        except Exception:
            logger.warning("AI version summary generation failed for doc %s v%s", doc_id, new_version)
            return None

    @staticmethod
    async def get_snapshot(db: AsyncSession, doc_id: UUID, version: int) -> bytes | None:
        stmt = select(CollabVersion.snapshot).where(
            CollabVersion.doc_id == doc_id, CollabVersion.version == version
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
