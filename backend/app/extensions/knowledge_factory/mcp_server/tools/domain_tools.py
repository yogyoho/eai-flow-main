"""Domain listing tools for the Knowledge Factory MCP server."""

from __future__ import annotations

import json
import logging

from mcp.types import TextContent

logger = logging.getLogger(__name__)


def _json_response(data: dict) -> list[TextContent]:
    """Wrap JSON data in a markdown code block for LLM-friendly consumption."""
    json_text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=f"```json\n{json_text}\n```")]


async def handle_kf_list_domains(arguments: dict, _run_in_db) -> list[TextContent]:
    """List available domains for report generation.

    bug-3068 枚举统一：industries / report_types 直接读业务字典（business_dictionaries，
    启用态、sort_order 序）——字典是领域与报告类型的唯一真源；template_domains 保留
    extraction_domains 分组视图并附模板计数，供 agent 判断哪个域已有可解析模板。
    """
    from sqlalchemy import func, select

    from app.extensions.knowledge_factory.models import ExtractionDomain, ExtractionTemplate
    from app.extensions.knowledge_factory.service import DictionaryService

    industry = arguments.get("industry")

    async def _query(db):
        industries = await DictionaryService.enabled_items(db, "industry")
        report_types = await DictionaryService.enabled_items(db, "report_type")
        if industry:
            industries = [i for i in industries if i.id == industry]

        query = select(ExtractionDomain).order_by(ExtractionDomain.id)
        result = await db.execute(query)
        domains = list(result.scalars().all())
        counts = dict((row[0], row[1]) for row in (await db.execute(select(ExtractionTemplate.domain, func.count()).group_by(ExtractionTemplate.domain))).all())

        items = []
        for d in domains:
            items.append(
                {
                    "id": d.id,
                    "name": d.name,
                    "industry": d.industry,
                    "report_type": d.report_type,
                    "description": d.description,
                    "parent_domain": d.parent_domain,
                    "template_count": counts.get(d.id, 0),
                }
            )
        return {
            "industries": [{"code": i.id, "label": i.label} for i in industries],
            "report_types": [{"code": r.id, "label": r.label} for r in report_types],
            "template_domains": items,
            "total": len(items),
            "note": "industries/report_types=业务字典真源（business_dictionaries）；template_domains=模板域分组（附模板数）",
        }

    result = await _run_in_db(_query)
    return _json_response(result)
