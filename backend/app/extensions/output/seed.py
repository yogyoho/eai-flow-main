"""Built-in layout templates — seeded idempotently on first startup."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.output.models import LayoutTemplate

logger = logging.getLogger(__name__)

BUILTIN_TEMPLATES = [
    {
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "环评报告（国标）",
        "report_type": "environmental_assessment",
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
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "黑体", "fontSize": 12, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True,
            "logoPosition": "center",
            "showTitle": True,
            "showClient": True,
            "showDate": True,
            "showProjectNumber": True,
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
            "paperSize": "A4",
            "orientation": "portrait",
            "marginTop": 2.5,
            "marginBottom": 2.5,
            "marginLeft": 2.8,
            "marginRight": 2.8,
        },
        "body_styles": {
            "fontFamily": "仿宋",
            "fontSize": 12,
            "lineHeight": 1.5,
            "paragraphSpacing": 6,
            "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "黑体", "fontSize": 13, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 4, "fontFamily": "楷体", "fontSize": 12, "fontWeight": 700, "color": "#444444", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True,
            "logoPosition": "center",
            "showTitle": True,
            "showClient": True,
            "showDate": True,
            "showProjectNumber": True,
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
            "paperSize": "A4",
            "orientation": "portrait",
            "marginTop": 2.54,
            "marginBottom": 2.54,
            "marginLeft": 3.17,
            "marginRight": 3.17,
        },
        "body_styles": {
            "fontFamily": "微软雅黑",
            "fontSize": 11,
            "lineHeight": 1.75,
            "paragraphSpacing": 8,
            "firstLineIndent": 2,
        },
        "heading_styles": [
            {"level": 1, "fontFamily": "微软雅黑", "fontSize": 15, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 2, "fontFamily": "微软雅黑", "fontSize": 13, "fontWeight": 700, "color": "#333333", "numbering": "decimal"},
            {"level": 3, "fontFamily": "微软雅黑", "fontSize": 12, "fontWeight": 600, "color": "#444444", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True,
            "logoPosition": "left",
            "showTitle": True,
            "showClient": True,
            "showDate": True,
            "showProjectNumber": False,
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
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "none"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "none"},
        ],
        "cover_template": {
            "showLogo": False,
            "logoPosition": "center",
            "showTitle": True,
            "showClient": False,
            "showDate": True,
            "showProjectNumber": False,
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
