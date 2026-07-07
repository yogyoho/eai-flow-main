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
    {
        # 参照样例:基地项目-消防设计专篇.docx(吉林院)
        # 样例无封面(直接从目录开始),封面字段按国标惯例;页面/分节/目录/编号照实测。
        "id": "00000000-0000-4000-8000-000000000005",
        "name": "消防设计专篇",
        "report_type": "fire_protection",
        "page_settings": {
            # 实测:A4 纵向,上下 2.54cm / 左右 3.17cm(1440/1797 twips)
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
            # 样例原值 H1=H2=14pt、自定义"标题3"=16pt 系模板缺陷;此处归一化为递减层级。
            # 编号方案实测为 decimal 多级(1 / 1.1 / 4.2.1),数字直接写在标题文本里。
            {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
            {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
            {"level": 3, "fontFamily": "黑体", "fontSize": 13, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
            {"level": 4, "fontFamily": "宋体", "fontSize": 12, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
        ],
        "cover_template": {
            "showLogo": True,
            "logoPosition": "center",
            "showTitle": True,
            "showClient": True,
            "showDate": True,
            "showProjectNumber": True,
        },
        # 实测目录域:TOC \o "1-2" \h \z \u —— 取 1-2 级
        "toc_settings": {"maxDepth": 2, "showPageNumbers": True, "leaderDots": True},
        "table_styles": {"headerBg": "#2B579A", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": True},
        "figure_styles": {"captionPosition": "below", "numbering": "chapter", "showSource": True},
        "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": False},
        "reference_style": "gb7714",
        "appendix_rules": {"numbering": "A-B-C", "separateToc": False},
    },
]


async def seed_builtin_templates(db: AsyncSession) -> None:
    """Seed built-in templates whose id is not yet present (per-id idempotent).

    Previously this skipped ALL builtins as soon as any existed, which meant a
    newly added builtin never landed in an existing DB. Now we seed only the
    builtins whose id is missing, leaving already-seeded rows untouched.
    """
    existing_ids_stmt = select(LayoutTemplate.id).where(LayoutTemplate.is_builtin.is_(True))
    existing_ids = {row[0] for row in (await db.execute(existing_ids_stmt)).all()}

    added = 0
    for tpl_data in BUILTIN_TEMPLATES:
        if uuid.UUID(tpl_data["id"]) in existing_ids:
            continue
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
        added += 1

    if added:
        await db.commit()
        logger.info("Seeded %d new built-in layout templates", added)
