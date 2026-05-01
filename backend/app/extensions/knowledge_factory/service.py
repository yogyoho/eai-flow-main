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
    async def rollback_template(
        db: AsyncSession,
        template: ExtractionTemplate,
        version_id: UUID,
        changelog: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> ExtractionTemplate:
        """回滚模板到指定版本。

        回滚逻辑：
        1. 查找指定版本的历史快照
        2. 恢复模板的 sections 和 cross_section_rules
        3. 创建新版本快照（标记为回滚）
        4. 自动递增版本号（patch + 1）
        """
        from sqlalchemy import select

        # 查找目标版本
        result = await db.execute(
            select(ExtractionTemplateVersion).where(
                ExtractionTemplateVersion.id == version_id,
                ExtractionTemplateVersion.template_id == template.id,
            )
        )
        target_version = result.scalar_one_or_none()

        if not target_version:
            raise ValueError(f"版本 {version_id} 不存在或不属于此模板")

        snapshot = target_version.snapshot_json or {}
        sections = snapshot.get("sections", [])
        cross_rules = snapshot.get("cross_section_rules", [])

        # 计算新版本号（semver patch + 1）
        current_version = template.version.lstrip("v")
        parts = current_version.split(".")
        if len(parts) >= 3:
            patch = int(parts[2]) + 1
            new_version = f"v{parts[0]}.{parts[1]}.{patch}"
        else:
            new_version = f"{current_version}.1"

        # 更新模板内容
        template.root_sections_json = {"sections": sections}
        template.cross_section_rules = {"rules": cross_rules}
        template.version = new_version
        template.status = "draft"  # 回滚后变为草稿状态

        # 重新计算完整度评分
        if sections:
            scored_sections = [
                s for s in _flatten_sections_list(sections)
                if s.get("completeness_score")
            ]
            if scored_sections:
                avg_score = sum(s.get("completeness_score", 0) for s in scored_sections) // len(scored_sections)
                template.completeness_score = avg_score

        # 创建新版本快照（回滚记录）
        rollback_note = f"回滚到 v{target_version.version}" + (f"：{changelog}" if changelog else "")
        new_version_record = ExtractionTemplateVersion(
            template_id=template.id,
            version=new_version,
            changelog=rollback_note,
            snapshot_json={"sections": sections, "cross_section_rules": cross_rules},
            published_by=user_id,
        )
        db.add(new_version_record)

        # 保存新版本的 JSON 快照
        save_snapshot(
            domain=template.domain,
            template_name=template.name,
            version=new_version,
            template_data={"sections": sections, "cross_section_rules": cross_rules},
        )

        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def get_version_by_id(
        db: AsyncSession,
        template_id: UUID,
        version_id: UUID,
    ) -> Optional[ExtractionTemplateVersion]:
        """根据ID获取特定版本"""
        from sqlalchemy import select

        result = await db.execute(
            select(ExtractionTemplateVersion).where(
                ExtractionTemplateVersion.id == version_id,
                ExtractionTemplateVersion.template_id == template_id,
            )
        )
        return result.scalar_one_or_none()

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


# ============== Quality Assessment Service ==============


class QualityService:
    """模板质量评估服务"""

    @staticmethod
    def assess_template_quality(template_data: dict) -> dict:
        """使用 AI 评估模板质量。

        Args:
            template_data: 包含模板信息的字典

        Returns:
            质量评估结果
        """
        from .quality import QualityAssessmentClient

        client = QualityAssessmentClient()
        return client.assess(template_data)

    @staticmethod
    def build_template_data_for_assessment(template: ExtractionTemplate) -> dict:
        """构建用于评估的模板数据"""
        sections_json = template.root_sections_json or {}
        sec_list = sections_json.get("sections", [])
        rules = (template.cross_section_rules or {}).get("rules", [])

        return {
            "name": template.name,
            "domain": template.domain,
            "version": template.version,
            "status": template.status,
            "root_sections": sec_list,
            "cross_section_rules": rules,
        }


# ============== Version Compare Service ==============


class VersionCompareService:
    """版本对比服务"""

    @staticmethod
    def compare_versions(
        version_a_sections: list[dict],
        version_b_sections: list[dict],
        version_a: str,
        version_b: str,
    ) -> dict:
        """对比两个版本的章节结构差异。

        Args:
            version_a_sections: 版本A的章节列表
            version_b_sections: 版本B的章节列表
            version_a: 版本A的版本号
            version_b: 版本B的版本号

        Returns:
            差异结果
        """
        # 构建 ID -> 章节的映射
        section_map_a = {s.get("id"): s for s in _flatten_sections_list(version_a_sections)}
        section_map_b = {s.get("id"): s for s in _flatten_sections_list(version_b_sections)}

        ids_a = set(section_map_a.keys())
        ids_b = set(section_map_b.keys())

        added_ids = ids_b - ids_a
        removed_ids = ids_a - ids_b
        common_ids = ids_a & ids_b

        diffs = []

        # 新增的章节
        for sec_id in added_ids:
            sec = section_map_b[sec_id]
            diffs.append({
                "section_id": sec_id,
                "title": sec.get("title", ""),
                "level": sec.get("level", 1),
                "status": "added",
            })

        # 删除的章节
        for sec_id in removed_ids:
            sec = section_map_a[sec_id]
            diffs.append({
                "section_id": sec_id,
                "title": sec.get("title", ""),
                "level": sec.get("level", 1),
                "status": "removed",
            })

        # 修改/不变的章节
        for sec_id in common_ids:
            sec_a = section_map_a[sec_id]
            sec_b = section_map_b[sec_id]

            # 检查是否有修改
            is_modified = (
                sec_a.get("title") != sec_b.get("title") or
                sec_a.get("required") != sec_b.get("required") or
                sec_a.get("purpose") != sec_b.get("purpose") or
                sec_a.get("content_contract") != sec_b.get("content_contract")
            )

            diffs.append({
                "section_id": sec_id,
                "title": sec_b.get("title", ""),
                "level": sec_b.get("level", 1),
                "status": "modified" if is_modified else "unchanged",
            })

        # 按状态和层级排序
        status_order = {"removed": 0, "added": 1, "modified": 2, "unchanged": 3}
        diffs.sort(key=lambda x: (status_order.get(x["status"], 4), x["level"], x["title"]))

        return {
            "version_a": version_a,
            "version_b": version_b,
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "modified_count": sum(1 for d in diffs if d["status"] == "modified"),
            "unchanged_count": sum(1 for d in diffs if d["status"] == "unchanged"),
            "sections": diffs,
        }


# ============== Helpers ==============


def _flatten_sections_list(sections: list[dict]) -> list[dict]:
    """将嵌套的章节树扁平化为列表"""
    flat = []
    for sec in sections:
        flat.append(sec)
        children = sec.get("children") or []
        if children:
            flat.extend(_flatten_sections_list(children))
    return flat


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
