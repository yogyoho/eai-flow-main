"""Domain listing tools for the Knowledge Factory MCP server."""

from __future__ import annotations

import json
import logging

from mcp.types import TextContent

logger = logging.getLogger(__name__)


async def handle_kf_list_domains(arguments: dict, _run_in_db) -> list[TextContent]:
    """List available extraction domains, optionally filtered by industry.

    Returns domain id, name, industry, report_type, and description
    so the agent can discover what report types are available.
    """
    from app.extensions.knowledge_factory.models import ExtractionDomain
    from sqlalchemy import select

    industry = arguments.get("industry")

    async def _query(db):
        query = select(ExtractionDomain).order_by(ExtractionDomain.id)
        if industry:
            query = query.where(ExtractionDomain.industry == industry)
        result = await db.execute(query)
        domains = list(result.scalars().all())

        items = []
        for d in domains:
            items.append({
                "id": d.id,
                "name": d.name,
                "industry": d.industry,
                "report_type": d.report_type,
                "description": d.description,
                "parent_domain": d.parent_domain,
            })
        return {"domains": items, "total": len(items)}

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
