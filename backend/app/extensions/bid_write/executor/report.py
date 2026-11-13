"""RunReport 序列化与待补提取(批二十 M1-c,EAI-CUSTOM 2026-11-13)——报告=
导出物非真相源(skill_run 落库才是,bug-4303 律姊妹口径)。序列化确定性:字段
固定序+报告序(level_rank, assertion_id),20× 字节级一致验收面的组成件。
pending/skipped 提取以 results-dict 为唯一逻辑面:对象面(runner 产物)与落库
面(verdict JSON)共用,gaps 端点直接喂 dict 不重建 dataclass。"""

from __future__ import annotations

from app.extensions.bid_write.executor.models import ST_ERROR, ST_FAIL, RunReport


def to_report_dict(report: RunReport) -> dict:
    """确定性字典形(入库 verdict JSON / API 响应共用;键序=插入序)。"""
    return {
        "schema_version": report.schema_version,
        "skills": list(report.skills) if report.skills is not None else None,
        "results": [
            {
                "assertion_id": r.assertion_id,
                "skill": r.skill,
                "name": r.name,
                "status": r.status,
                "level": r.level,
                "blocks_export": r.blocks_export,
                "deterministic": r.deterministic,
                "message": r.message,
                "human_action": r.human_action,
                "rule_ref": r.rule_ref,
                "note": r.note,
                "skipped_reason": r.skipped_reason,
                "source_id": r.source_id,
            }
            for r in report.results
        ],
    }


def pending_from(results: list[dict]) -> list[dict]:
    """待补清单(FAIL/ERROR 逐条;human_action=null 视为处置自动闭环不挂人工账)。"""
    return [
        {"assertion_id": r["assertion_id"], "skill": r["skill"], "status": r["status"], "message": r["message"], "human_action": r["human_action"]}
        for r in results
        if r["status"] in (ST_FAIL, ST_ERROR) and r.get("human_action") is not None
    ]


def skipped_from(results: list[dict]) -> list[dict]:
    """SKIPPED 注记(可解释跳过:short_circuit 根因/no_signal 特免),零静默。"""
    return [
        {"assertion_id": r["assertion_id"], "level": r["level"], "skipped_reason": r["skipped_reason"], "message": r["message"]}
        for r in results
        if r["status"] == "SKIPPED"
    ]


def pending_items(report: RunReport) -> list[dict]:
    return pending_from(to_report_dict(report)["results"])


def skipped_items(report: RunReport) -> list[dict]:
    return skipped_from(to_report_dict(report)["results"])
