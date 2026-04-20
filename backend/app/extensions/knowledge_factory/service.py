"""Business logic for knowledge factory extraction."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db_context
from app.extensions.models import Document, KnowledgeBase

from .models import (
    ExtractionDomain,
    ExtractionTask,
    ExtractionTemplate,
    ExtractionTemplateVersion,
    TemplateSection,
)
from .pipeline import ExtractionPipeline
from .schemas import (
    ContentContract,
    CrossSectionRule,
    DomainCreate,
    DomainResponse,
    ExtractionConfig,
    ExtractionTaskCreate,
    ExtractionTaskListResponse,
    ExtractionTaskResponse,
    StepStatusSchema,
    StructureType,
    TemplateDocument,
    TemplateListItem,
    TemplateListResponse,
    TemplateResult,
    TemplateSection,
    TemplateStatus,
    TemplateUpdate,
    TemplateVersionResponse,
)
from .storage import delete_snapshot, save_snapshot

logger = logging.getLogger(__name__)


# ============== Domain Service ==============


class DomainService:
    """领域管理服务"""

    @staticmethod
    async def list_domains(db: AsyncSession) -> list[ExtractionDomain]:
        result = await db.execute(select(ExtractionDomain).order_by(ExtractionDomain.id))
        return list(result.scalars().all())

    @staticmethod
    async def get_domain(db: AsyncSession, domain_id: str) -> Optional[ExtractionDomain]:
        result = await db.execute(select(ExtractionDomain).where(ExtractionDomain.id == domain_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_domain(db: AsyncSession, data: DomainCreate) -> ExtractionDomain:
        domain = ExtractionDomain(
            id=data.id,
            name=data.name,
            description=data.description,
            parent_domain=data.parent_domain,
            standard_chapters=data.standard_chapters,
        )
        db.add(domain)
        await db.commit()
        await db.refresh(domain)
        return domain

    @staticmethod
    async def init_default_domains(db: AsyncSession) -> None:
        """初始化默认领域（如果不存在）"""
        defaults = [
            ExtractionDomain(
                id="environmental_impact_assessment",
                name="环境影响评价报告",
                description="各类建设项目环境影响评价报告书/表",
                standard_chapters={
                    "sections": [
                        {"id": "sec_01", "title": "总则"},
                        {"id": "sec_02", "title": "建设项目概况"},
                        {"id": "sec_03", "title": "工程分析"},
                    ]
                },
            ),
        ]
        for d in defaults:
            existing = await DomainService.get_domain(db, d.id)
            if not existing:
                db.add(d)
        await db.commit()


# ============== Template Service ==============


class TemplateService:
    """模板管理服务"""

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ExtractionTemplate], int]:
        query = select(ExtractionTemplate)
        if domain:
            query = query.where(ExtractionTemplate.domain == domain)
        if status:
            # 支持逗号分隔的多个状态，如 "draft,published"
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                query = query.where(ExtractionTemplate.status == statuses[0])
            elif len(statuses) > 1:
                query = query.where(ExtractionTemplate.status.in_(statuses))

        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        query = query.order_by(ExtractionTemplate.created_at.desc())
        query = query.offset((page - 1) * limit).limit(limit)

        result = await db.execute(query)
        templates = list(result.scalars().all())
        return templates, total

    @staticmethod
    async def get_template(db: AsyncSession, template_id: UUID) -> Optional[ExtractionTemplate]:
        result = await db.execute(select(ExtractionTemplate).where(ExtractionTemplate.id == template_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_template_versions(
        db: AsyncSession, template_id: UUID
    ) -> list[ExtractionTemplateVersion]:
        result = await db.execute(
            select(ExtractionTemplateVersion)
            .where(ExtractionTemplateVersion.template_id == template_id)
            .order_by(ExtractionTemplateVersion.published_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_template(
        db: AsyncSession, template: ExtractionTemplate, data: TemplateUpdate
    ) -> ExtractionTemplate:
        if data.name is not None:
            template.name = data.name
        if data.root_sections_json is not None:
            template.root_sections_json = data.root_sections_json
        if data.cross_section_rules is not None:
            template.cross_section_rules = {"rules": data.cross_section_rules}
        if data.completeness_score is not None:
            template.completeness_score = data.completeness_score
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def publish_template(
        db: AsyncSession, template: ExtractionTemplate, user_id: Optional[UUID] = None
    ) -> ExtractionTemplate:
        """发布模板：创建版本快照 + 更新状态"""
        # 创建版本记录
        version = ExtractionTemplateVersion(
            template_id=template.id,
            version=template.version,
            snapshot_json=template.root_sections_json or {},
            published_by=user_id,
        )
        db.add(version)

        # 保存 JSON 快照
        save_snapshot(
            domain=template.domain,
            template_name=template.name,
            version=template.version,
            template_data=template.root_sections_json or {},
        )

        template.status = "published"
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def delete_template(db: AsyncSession, template: ExtractionTemplate) -> None:
        # 删除 JSON 快照
        delete_snapshot(
            domain=template.domain,
            template_name=template.name,
            version=template.version,
        )
        await db.delete(template)
        await db.commit()

    @staticmethod
    def to_template_document(template: ExtractionTemplate) -> TemplateDocument:
        """将 ORM 模型转为 TemplateDocument 响应"""
        sections = template.root_sections_json or {}
        sec_list = sections.get("sections", [])
        rules = (template.cross_section_rules or {}).get("rules", [])

        return TemplateDocument(
            template_id=template.id,
            name=template.name,
            version=template.version,
            domain=template.domain,
            status=TemplateStatus(template.status),
            completeness_score=template.completeness_score or 0,
            root_sections=[_parse_section(s) for s in sec_list],
            cross_section_rules=[CrossSectionRule(**r) for r in rules],
            created_at=template.created_at.isoformat(),
        )


# ============== Task Service ==============


class TaskService:
    """抽取任务服务"""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        data: ExtractionTaskCreate,
        user_id: Optional[UUID] = None,
    ) -> ExtractionTask:
        config_dict = (data.config or ExtractionConfig()).model_dump()
        task = ExtractionTask(
            name=data.name,
            domain=data.domain,
            source_report_ids=[str(s) for s in data.source_report_ids],
            config=config_dict,
            status="pending",
            progress=0,
            created_by=user_id,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_task(db: AsyncSession, task_id: UUID) -> Optional[ExtractionTask]:
        result = await db.execute(select(ExtractionTask).where(ExtractionTask.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ExtractionTask], int]:
        query = select(ExtractionTask)
        if status:
            query = query.where(ExtractionTask.status == status)

        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        query = query.order_by(ExtractionTask.created_at.desc())
        query = query.offset((page - 1) * limit).limit(limit)

        result = await db.execute(query)
        tasks = list(result.scalars().all())
        return tasks, total

    @staticmethod
    async def update_task_steps(
        db: AsyncSession, task: ExtractionTask, steps: list[dict]
    ) -> None:
        task.steps = steps
        # 计算进度
        completed = sum(1 for s in steps if s.get("status") == "completed")
        task.progress = int((completed / 5) * 100) if steps else 0
        await db.commit()

    @staticmethod
    async def set_task_running(db: AsyncSession, task: ExtractionTask) -> None:
        task.status = "running"
        task.started_at = datetime.utcnow()
        task.progress = 0
        await db.commit()

    @staticmethod
    async def set_task_completed(
        db: AsyncSession, task: ExtractionTask, result_template_json: Optional[dict] = None
    ) -> None:
        task.status = "completed"
        task.progress = 100
        task.completed_at = datetime.utcnow()
        task.result_template_json = result_template_json
        await db.commit()

    @staticmethod
    async def set_task_failed(db: AsyncSession, task: ExtractionTask, error: str) -> None:
        task.status = "failed"
        task.completed_at = datetime.utcnow()
        task.error_message = error
        await db.commit()

    @staticmethod
    async def pause_task(db: AsyncSession, task: ExtractionTask) -> None:
        if task.status == "running":
            task.status = "paused"
            await db.commit()

    @staticmethod
    async def resume_task(db: AsyncSession, task: ExtractionTask) -> None:
        if task.status == "paused":
            task.status = "running"
            await db.commit()

    @staticmethod
    async def cancel_task(db: AsyncSession, task: ExtractionTask) -> None:
        if task.status in ("pending", "running", "paused"):
            task.status = "failed"
            task.error_message = "用户取消"
            task.completed_at = datetime.utcnow()
            await db.commit()


# ============== Helpers ==============


def _parse_section(data: dict) -> TemplateSection:
    """将 dict 解析为 TemplateSection"""
    content = data.get("content_contract") or {}
    if isinstance(content, dict):
        content = ContentContract(
            key_elements=content.get("key_elements", []),
            structure_type=StructureType(content.get("structure_type", "narrative_text")),
            style_rules=content.get("style_rules"),
            min_word_count=content.get("min_word_count"),
            forbidden_phrases=content.get("forbidden_phrases", []),
        )
    children = [_parse_section(c) for c in data.get("children") or []]
    return TemplateSection(
        id=data.get("id", ""),
        title=data.get("title", ""),
        level=data.get("level", 1),
        required=data.get("required", True),
        purpose=data.get("purpose"),
        children=children if children else None,
        content_contract=content,
        compliance_rules=data.get("compliance_rules"),
        rag_sources=data.get("rag_sources"),
        generation_hint=data.get("generation_hint"),
        example_snippet=data.get("example_snippet"),
        completeness_score=data.get("completeness_score"),
    )
