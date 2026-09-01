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


def _json_response(data: dict) -> list[TextContent]:
    """Wrap JSON data in a markdown code block for LLM-friendly consumption."""
    json_text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=f"```json\n{json_text}\n```")]


async def handle_kf_resolve_template(arguments: dict, _run_in_db) -> list[TextContent]:
    """Intelligently match and return the best report template for a given domain/industry/report-type.

    Three-layer matching strategy (descending priority):
      1. Exact match: domain.report_type + industry + template name keywords
      2. Keyword match: template name keywords + (industry or report_type)
      3. Loose match: template name or domain name contains any keyword

    Within each layer, results are sorted by completeness_score DESC, version DESC.
    Only published templates are considered.
    """
    from sqlalchemy import select

    from app.extensions.knowledge_factory.models import ExtractionDomain, ExtractionTemplate
    from app.extensions.knowledge_factory.service import DictionaryService, TemplateService

    domain_keywords = arguments.get("domain_keywords", [])
    industry = arguments.get("industry")
    report_type = arguments.get("report_type")
    min_completeness_score = arguments.get("min_completeness_score", 0)

    # Guard: empty or missing domain_keywords cannot produce a meaningful match.
    # Without keywords the loose fallback returns the highest-scored published
    # template in the entire DB (currently a coal EIA report), which is never
    # what the caller wants.
    if not domain_keywords or (isinstance(domain_keywords, list) and len(domain_keywords) == 0):
        return _json_response(
            {
                "found": False,
                "reason": "missing_keywords",
                "suggestion": "请提供 domain_keywords 参数，例如 ['消防设计专篇', '消防']。空关键词会匹配到无关模板。",
            }
        )

    async def _query(db):
        # bug-3068 枚举统一：report_type/industry 的合法取值真源=业务字典；调用方传 code 或中文 label 均归一化为字典 code
        dict_rts = await DictionaryService.enabled_items(db, "report_type")
        dict_inds = await DictionaryService.enabled_items(db, "industry")
        rt_codes = {r.id for r in dict_rts}
        ind_codes = {i.id for i in dict_inds}
        rt_code = report_type if report_type in rt_codes else next((r.id for r in dict_rts if r.label == report_type), None)
        ind_code = industry if industry in ind_codes else next((i.id for i in dict_inds if i.label == industry), None)

        # Step 1: Find matching domains
        result = await db.execute(select(ExtractionDomain).order_by(ExtractionDomain.id))
        domains = list(result.scalars().all())

        best_domain = None
        best_domain_score = 0

        for d in domains:
            score = 0
            if rt_code and d.report_type and (d.report_type == rt_code or d.report_type == report_type):
                score += 3
            if ind_code and d.industry and (d.industry == ind_code or d.industry == industry):
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

            name_conditions = [ExtractionTemplate.name.ilike(f"%{kw}%") for kw in domain_keywords]

        domain_filter = best_domain.id if best_domain else None

        # Strategy: try domain+name first; if no results, fall back to name-only.
        # This handles the case where keywords match a different domain than the
        # template's actual domain (e.g. keyword "消防设计" matches domain "消防设计专篇大纲"
        # but the template belongs to "environmental_impact_assessment").
        templates = []
        for attempt_filters in [
            {"domain": domain_filter, "name": name_conditions},  # strict: domain AND name
            {"domain": rt_code, "name": name_conditions},  # dict-code domain（bug-3068：模板归属字典码域时直查）
            {"domain": None, "name": name_conditions},  # fallback: name only
        ]:
            query_base = select(ExtractionTemplate).where(ExtractionTemplate.status == "published")
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
            return {"found": False, "reason": "no_template_found", "suggestion": "请先通过知识工厂抽取该领域的报告模板"}

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
            if best_domain and rt_code and best_domain.report_type and (best_domain.report_type == rt_code or best_domain.report_type == report_type):
                match_level = max(match_level, 2)

            candidates.append((match_level, t.completeness_score, t))

        if not candidates:
            return {"found": False, "reason": "low_quality", "suggestion": f"存在模板但完整度评分低于阈值({min_completeness_score})，建议优化模板后再生成"}

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        match_level, _, best = candidates[0]

        # Step 4: Serialize the best match
        match_labels = {0: "loose", 1: "keyword", 2: "exact"}
        result_data = TemplateService.to_template_document(best).model_dump()
        result_data["found"] = True
        result_data["match_level"] = match_labels.get(match_level, "loose")
        return result_data

    result = await _run_in_db(_query)
    return _json_response(result)


async def handle_kf_get_template(arguments: dict, _run_in_db) -> list[TextContent]:
    """Get a specific template by ID with full section metadata."""
    from app.extensions.knowledge_factory.service import TemplateService

    template_id = arguments["template_id"]

    try:
        tid = UUID(template_id)
    except (ValueError, AttributeError):
        return _json_response({"found": False, "reason": "invalid_uuid", "detail": f"Invalid template_id: {template_id}"})

    async def _query(db):
        template = await TemplateService.get_template(db, tid)
        if not template:
            return {"found": False, "reason": "template_not_found", "detail": f"模板 {template_id} 不存在"}
        return TemplateService.to_template_document(template).model_dump() | {"found": True}

    result = await _run_in_db(_query)
    return _json_response(result)


async def handle_kf_extract_template(arguments: dict, _run_in_db) -> list[TextContent]:
    """Run the extraction pipeline on knowledge base documents and return a template.

    Two input modes:
      1. source_report_ids (works now) — UUIDs of documents already uploaded to
         a knowledge base. Pipeline fetches chunks via RAGFlow API.
      2. file_paths (future) — absolute paths to Word/PDF files on the server.
         Requires doc_parser.py implementation. Falls back to plain-text reading
         for .md/.txt files today.

    Pipeline stages: 文档解析→章节推断→元数据抽取→模板融合→合规校验

    Returns the template sections so downstream skills (e.g. coal-eia-report)
    can call kf_resolve_template to consume it.
    """
    import uuid
    from datetime import datetime

    from sqlalchemy import select as sa_select

    from app.extensions.database import get_db_context
    from app.extensions.knowledge_factory.models import ExtractionTask
    from app.extensions.knowledge_factory.pipeline import ExtractionPipeline
    from app.extensions.knowledge_factory.schemas import ExtractionConfig
    from app.extensions.models import Document, KnowledgeBase

    source_report_ids = arguments.get("source_report_ids", [])
    file_paths = arguments.get("file_paths", [])

    if not source_report_ids and not file_paths:
        return _json_response({"success": False, "error": "请提供 source_report_ids（知识库文档 UUID）或 file_paths（文件路径）"})

    domain = arguments.get("domain", "default")
    industry = arguments.get("industry") or None
    report_type = arguments.get("report_type") or None
    template_name = arguments.get("template_name", f"agent-extracted-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    max_depth = arguments.get("max_depth", 4)
    llm_model = arguments.get("llm_model") or None

    config = ExtractionConfig(
        llm_model=llm_model or "",
        max_depth=max(max_depth, 1),
    )

    report_docs = []

    async with get_db_context() as db:
        # Resolve effective model from system config if not provided
        if not llm_model:
            from app.extensions.models import SystemConfig as SC

            result = await db.execute(sa_select(SC.value).where(SC.key == "default_model"))
            row = result.scalar_one_or_none()
            if row:
                llm_model = row

        # Mode 1: source_report_ids — query DB for RAGFlow IDs
        if source_report_ids:
            for rid in source_report_ids:
                try:
                    uid = uuid.UUID(rid) if isinstance(rid, str) else rid
                except (ValueError, AttributeError):
                    return _json_response({"success": False, "error": f"无效的 UUID: {rid}"})
                result = await db.execute(sa_select(Document, KnowledgeBase).join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id).where(Document.id == uid))
                row = result.first()
                if not row:
                    return _json_response({"success": False, "error": f"文档 {rid} 不存在——请先在样例管理 tab 上传到知识库"})
                doc, kb = row
                report_docs.append(
                    {
                        "id": str(doc.id),
                        "name": doc.name,
                        "kb_id": str(kb.id),
                        "ragflow_document_id": doc.ragflow_document_id,
                        "ragflow_dataset_id": kb.ragflow_dataset_id,
                        "file_path": doc.file_path,
                        "file_type": doc.file_type,
                    }
                )

        # Mode 2: file_paths — bare files (plain-text fallback today; doc_parser future)
        if file_paths:
            import os as _os

            for fp in file_paths:
                fname = _os.path.basename(fp)
                ext = _os.path.splitext(fp)[1].lower().lstrip(".")
                report_docs.append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": fname,
                        "kb_id": str(uuid.uuid4()),
                        "ragflow_document_id": None,
                        "ragflow_dataset_id": None,
                        "file_path": fp,
                        "file_type": ext,
                    }
                )

    pipeline = ExtractionPipeline(llm_model=llm_model)

    task_id = str(uuid.uuid4())
    logger.info(f"[kf_extract_template] Starting extraction for {len(report_docs)} documents: {[d['name'] for d in report_docs]}")

    try:
        result = await pipeline.run(
            task_id=task_id,
            report_documents=report_docs,
            config=config,
            domain=domain,
            reference_chapters=None,
        )

        # Persist a minimal task record for audit trail
        async with get_db_context() as db:
            task = ExtractionTask(
                id=uuid.UUID(task_id),
                domain=domain,
                industry=industry,
                report_type=report_type,
                name=template_name,
                source_report_ids=[uuid.UUID(rid) if isinstance(rid, str) else rid for rid in source_report_ids],
                config=config.model_dump(),
                status="completed",
                progress=100,
                result_template_json={
                    "sections": result.sections,
                    "cross_section_rules": result.cross_section_rules,
                },
            )
            db.add(task)
            await db.commit()

        output = {
            "success": True,
            "template_name": template_name,
            "domain": domain,
            "chapters": result.chapters,
            "total_sections": result.total_sections,
            "completeness_score": result.completeness_score,
            "sections": result.sections,
            "cross_section_rules": result.cross_section_rules,
            "step_summaries": result.step_summaries,
        }
        return _json_response(output)
    except Exception as e:
        logger.error(f"[kf_extract_template] Pipeline failed: {e}")
        return _json_response({"success": False, "error": f"模板提取失败: {str(e)}"})


async def handle_kf_query_templates(arguments: dict, _run_in_db) -> list[TextContent]:
    """Search templates by domain, name, status with pagination."""
    from app.extensions.knowledge_factory.service import TemplateService

    domain = arguments.get("domain")
    name = arguments.get("name")
    status = arguments.get("status", "published")
    limit = arguments.get("limit", 10)

    async def _query(db):
        templates, total = await TemplateService.list_templates(db, domain=domain, name=name, status=status, page=1, limit=limit)
        items = []
        for t in templates:
            items.append(
                {
                    "id": str(t.id),
                    "domain": t.domain,
                    "name": t.name,
                    "version": t.version,
                    "status": t.status,
                    "completeness_score": t.completeness_score or 0,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
            )
        return {"templates": items, "total": total}

    result = await _run_in_db(_query)
    return _json_response(result)
