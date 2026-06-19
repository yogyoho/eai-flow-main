"""MCP tool handler for kf_check_compliance — bridges the compliance check engine.

The handler creates a CheckContext from raw chapter content and delegates to the
existing ``ComplianceEngine.check()`` from the knowledge factory service layer.
All heavy logic (rule loading, validation execution, issue aggregation) is
reused — this file is a thin MCP adapter.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from mcp.types import TextContent

logger = logging.getLogger(__name__)

# Use a well-known system UUID so check logs are attributable.
# In the MCP subprocess there is no authenticated HTTP caller.
_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


def _issues_to_dicts(issues: list[Any]) -> list[dict[str, Any]]:
    """Serialize ValidationIssue objects to plain dicts for JSON output."""
    result: list[dict[str, Any]] = []
    for i in issues:
        result.append(
            {
                "rule_id": getattr(i, "rule_id", ""),
                "rule_name": getattr(i, "rule_name", ""),
                "severity": getattr(i, "severity", "info") if not hasattr(i, "severity") else i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "check_result": getattr(i, "check_result", "unknown") if not hasattr(i, "check_result") else i.check_result.value if hasattr(i.check_result, "value") else str(i.check_result),
                "message": getattr(i, "message", ""),
                "field_name": getattr(i, "field_name", None),
                "source_value": str(getattr(i, "source_value", "")) if getattr(i, "source_value", None) is not None else None,
                "target_value": str(getattr(i, "target_value", "")) if getattr(i, "target_value", None) is not None else None,
                "location": getattr(i, "location", None),
                "suggestion": getattr(i, "suggestion", None),
            }
        )
    return result


async def handle_kf_check_compliance(
    arguments: dict[str, Any],
    _run_in_db,
) -> list[TextContent]:
    """Run compliance check against chapter content.

    Expected arguments:
        chapter_content (str) — full Markdown text of the chapter (required)
        rule_ids (list[str], optional) — specific rule IDs; empty/null = check all
        chapter_number (int, optional) — chapter number 1..14 (informational)
        report_type (str, optional) — narrows rules; WARNING: must match the
            rule's stored report_type exactly or it yields 0 rules. Default
            (not passing it) checks ALL enabled rules — usually what you want.
        industry (str, optional) — narrows rules; stored as English keys like
            "environmental", NOT "煤炭". Default (not passing it) checks ALL.

    Default behaviour (no rule_ids / no industry / no report_type): runs ALL
    enabled rules against the chapter — this is the recommended call. Filters
    are opt-in and exact-match; if a filter yields 0 rules the handler
    automatically falls back to check-all so the chapter is never left
    unchecked due to a filter typo.
    """
    chapter_content: str = arguments.get("chapter_content", "")
    chapter_number: int | None = arguments.get("chapter_number")
    rule_ids: list[str] | None = arguments.get("rule_ids")
    report_type: str | None = arguments.get("report_type")
    industry: str | None = arguments.get("industry")

    if not chapter_content:
        return [TextContent(type="text", text=json.dumps({"error": "chapter_content is required"}, ensure_ascii=False))]

    async def _check(session):
        # Lazy import inside the handler — MCP server is a separate process,
        # so importing app.* here is allowed (the harness→app boundary
        # applies to the gateway worker, not this subprocess).
        from app.extensions.knowledge_factory.engine.core import CheckContext
        from app.extensions.knowledge_factory.engine.service import get_engine

        engine = get_engine()
        used_fallback = False

        async def _run(apply_filters: bool):
            context = CheckContext(
                report_data={},
                raw_text=chapter_content,
                report_type=report_type if apply_filters else None,
                industry=industry if apply_filters else None,
                check_all=(rule_ids is None or len(rule_ids) == 0),
                user_id=_SYSTEM_USER_ID,
            )
            return await engine.check(context, rule_ids=rule_ids, db=session)

        result = await _run(apply_filters=True)

        # Footgun guard: a filter typo (e.g. industry="煤炭" vs stored
        # "environmental") silently yields 0 rules. Fall back to check-all
        # so the chapter is never left unchecked. rule_ids was explicit,
        # so do NOT override an empty rule_ids result.
        has_filters = bool(industry or report_type)
        if result.total_rules == 0 and has_filters and not rule_ids:
            result = await _run(apply_filters=False)
            used_fallback = True

        # Build structured response
        response = {
            "success": result.success,
            "total_rules": result.total_rules,
            "passed": result.passed,
            "failed": result.failed,
            "warnings": result.warnings,
            "errors": result.errors,
            "skipped": result.skipped,
            "has_critical_issues": result.has_critical_issues,
            "duration_ms": round(result.duration_ms, 1),
            "issues": _issues_to_dicts(result.issues),
        }
        if used_fallback:
            response["filter_fallback"] = "industry/report_type filter matched 0 rules; re-ran against ALL enabled rules so the chapter is not left unchecked."

        if result.failed > 0:
            response["summary"] = f"{result.failed} of {result.total_rules} rules FAILED (critical: {int(result.has_critical_issues)}). Review issues below and fix the chapter content."
        elif result.total_rules == 0:
            response["summary"] = "No matching compliance rules found for this content."
        else:
            response["summary"] = f"All {result.total_rules} rules passed."

        return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]

    try:
        return await _run_in_db(_check)
    except Exception as exc:
        logger.exception("kf_check_compliance failed")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"Compliance check engine error: {exc}", "passed": 0, "failed": 0, "warnings": 0, "issues": []}, ensure_ascii=False, indent=2))]
