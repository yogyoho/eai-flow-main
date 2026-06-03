"""Business logic for layout template CRUD."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
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
