"""Business logic for layout template CRUD."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.output.layout_import import _cover_master_to_elements
from app.extensions.output.models import LayoutTemplate
from app.extensions.output.schemas import LayoutTemplateCreate, LayoutTemplateUpdate

logger = logging.getLogger(__name__)


def _migrate_cover_master(template: LayoutTemplate) -> None:
    """读取时把旧 cover_master 自动迁移为 cover_elements（仅内存，不写库）。

    Task 5：老模板只有 cover_master（OOXML 片段）、无 cover_elements 时，读取即用
    ``_cover_master_to_elements`` 现算一份元素模型填充，前端/生成端走统一 elements
    通道；转换失败保留旧母版（返回 None，不覆盖）。不 commit —— 保存时才落库。
    """
    if template.cover_master and not template.cover_elements:
        template.cover_elements = _cover_master_to_elements(template.cover_master)


class LayoutTemplateService:
    @staticmethod
    async def list_templates(db: AsyncSession) -> list[LayoutTemplate]:
        stmt = select(LayoutTemplate).order_by(LayoutTemplate.is_builtin.desc(), LayoutTemplate.created_at.desc())
        result = await db.execute(stmt)
        templates = list(result.scalars().all())
        for t in templates:
            _migrate_cover_master(t)
        return templates

    @staticmethod
    async def get_template(db: AsyncSession, template_id: uuid.UUID) -> LayoutTemplate | None:
        template = await db.get(LayoutTemplate, template_id)
        if template is not None:
            _migrate_cover_master(template)
        return template

    @staticmethod
    async def create_template(db: AsyncSession, data: LayoutTemplateCreate) -> LayoutTemplate:
        template = LayoutTemplate(
            name=data.name,
            report_type=data.report_type,
            page_settings=data.page_settings.model_dump(),
            cover_template=data.cover_template.model_dump() if data.cover_template else None,
            cover_master=data.cover_master.model_dump() if data.cover_master else None,
            cover_elements=data.cover_elements.model_dump() if data.cover_elements else None,
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
            cover_master=dict(template.cover_master) if template.cover_master else None,
            cover_elements=dict(template.cover_elements) if template.cover_elements else None,
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
