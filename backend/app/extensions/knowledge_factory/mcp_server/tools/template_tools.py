"""Template resolution tools for the Knowledge Factory MCP server.

These tools allow the DeerFlow lead agent to query and fetch report templates
from the knowledge factory, enabling template-driven report generation.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from mcp.types import TextContent

logger = logging.getLogger(__name__)


async def handle_kf_resolve_template(arguments: dict, _run_in_db) -> list[TextContent]:
    """Intelligently match and return the best report template for a given domain/industry/report-type.

    Three-layer matching strategy (descending priority):
      1. Exact match: domain.report_type + industry + template name keywords
      2. Keyword match: template name keywords + (industry or report_type)
      3. Loose match: template name or domain name contains any keyword

    Within each layer, results are sorted by completeness_score DESC, version DESC.
    Only published templates are considered.
    """
    from app.extensions.knowledge_factory.models import ExtractionDomain, ExtractionTemplate
    from app.extensions.knowledge_factory.service import TemplateService
    from sqlalchemy import select

    domain_keywords = arguments.get("domain_keywords", [])
    industry = arguments.get("industry")
    report_type = arguments.get("report_type")
    min_completeness_score = arguments.get("min_completeness_score", 0)

    async def _query(db):
        # Step 1: Find matching domains
        result = await db.execute(select(ExtractionDomain).order_by(ExtractionDomain.id))
        domains = list(result.scalars().all())

        best_domain = None
        best_domain_score = 0

        for d in domains:
            score = 0
            if report_type and d.report_type == report_type:
                score += 3
            if industry and d.industry == industry:
                score += 2
            if domain_keywords:
                d_name_lower = d.name.lower()
                for kw in domain_keywords:
                    if kw.lower() in d_name_lower:
                        score += 1
                        break
            if score > best_domain_score:
                best_domain_score = score
                best_domain = d

        # Step 2: List templates in matched domain (or all if no domain matched)
        # Build name-ILIKE conditions once if keywords are provided
        name_conditions = None
        if domain_keywords:
            from sqlalchemy import or_
            name_conditions = [
                ExtractionTemplate.name.ilike(f"%{kw}%") for kw in domain_keywords
            ]

        domain_filter = best_domain.id if best_domain else None

        # Strategy: try domain+name first; if no results, fall back to name-only.
        # This handles the case where keywords match a different domain than the
        # template's actual domain (e.g. keyword "消防设计" matches domain "消防设计专篇大纲"
        # but the template belongs to "environmental_impact_assessment").
        templates = []
        for attempt_filters in [
            {"domain": domain_filter, "name": name_conditions},  # strict: domain AND name
            {"domain": None, "name": name_conditions},            # fallback: name only
        ]:
            query_base = select(ExtractionTemplate).where(
                ExtractionTemplate.status == "published"
            )
            if attempt_filters["domain"]:
                query_base = query_base.where(ExtractionTemplate.domain == attempt_filters["domain"])
            if attempt_filters["name"]:
                query_base = query_base.where(or_(*attempt_filters["name"]))

            query_base = query_base.order_by(
                ExtractionTemplate.completeness_score.desc(),
                ExtractionTemplate.created_at.desc(),
            )
            result = await db.execute(query_base)
            templates = list(result.scalars().all())
            if templates:
                break  # found results with this filter level, no need to relax further

        if not templates:
            return {"found": False, "reason": "no_template_found",
                    "suggestion": "请先通过知识工厂抽取该领域的报告模板"}

        # Step 3: Score and rank candidates
        candidates = []
        for t in templates:
            if t.completeness_score < min_completeness_score:
                continue

            match_level = 0  # 0=loose, 1=keyword, 2=exact
            name_lower = t.name.lower()
            for kw in domain_keywords:
                if kw.lower() in name_lower:
                    match_level = max(match_level, 1)
            if best_domain and report_type and best_domain.report_type == report_type:
                match_level = max(match_level, 2)

            candidates.append((match_level, t.completeness_score, t))

        if not candidates:
            return {"found": False, "reason": "low_quality",
                    "suggestion": f"存在模板但完整度评分低于阈值({min_completeness_score})，建议优化模板后再生成"}

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        match_level, _, best = candidates[0]

        # Step 4: Serialize the best match
        match_labels = {0: "loose", 1: "keyword", 2: "exact"}
        result_data = TemplateService.to_template_document(best).model_dump()
        result_data["found"] = True
        result_data["match_level"] = match_labels.get(match_level, "loose")
        return result_data

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]


async def handle_kf_get_template(arguments: dict, _run_in_db) -> list[TextContent]:
    """Get a specific template by ID with full section metadata."""
    from app.extensions.knowledge_factory.service import TemplateService

    template_id = arguments["template_id"]

    try:
        tid = UUID(template_id)
    except (ValueError, AttributeError):
        return [TextContent(type="text", text=json.dumps(
            {"found": False, "reason": "invalid_uuid",
             "detail": f"Invalid template_id: {template_id}"},
            ensure_ascii=False, indent=2
        ))]

    async def _query(db):
        template = await TemplateService.get_template(db, tid)
        if not template:
            return {"found": False, "reason": "template_not_found",
                    "detail": f"模板 {template_id} 不存在"}
        return TemplateService.to_template_document(template).model_dump() | {"found": True}

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]


async def handle_kf_query_templates(arguments: dict, _run_in_db) -> list[TextContent]:
    """Search templates by domain, name, status with pagination."""
    from app.extensions.knowledge_factory.service import TemplateService

    domain = arguments.get("domain")
    name = arguments.get("name")
    status = arguments.get("status", "published")
    limit = arguments.get("limit", 10)

    async def _query(db):
        templates, total = await TemplateService.list_templates(
            db, domain=domain, name=name, status=status, page=1, limit=limit
        )
        items = []
        for t in templates:
            items.append({
                "id": str(t.id),
                "domain": t.domain,
                "name": t.name,
                "version": t.version,
                "status": t.status,
                "completeness_score": t.completeness_score or 0,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            })
        return {"templates": items, "total": total}

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
