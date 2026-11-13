"""导出门禁(批二十 M1-c,EAI-CUSTOM 2026-11-13)——blocked=存在 final 级 D0
且 status∈{FAIL,ERROR}(短路 SKIPPED 不重复计——其根因必是某条 D0 FAIL,已入
reasons;CtxMissing ERROR 同为阻断面)。watermark 恒 False:水印是导出器职责,
断言门禁不代管(L4 水印隔离,spec §8)。"""

from __future__ import annotations

from app.extensions.bid_write.executor.models import ST_ERROR, ST_FAIL, RunReport


def gate_verdict(report: RunReport) -> dict:
    """{"blocked": bool, "reasons": [assertion_id…], "watermark": False}。"""
    reasons = [r.assertion_id for r in report.results if r.level == "D0" and r.status in (ST_FAIL, ST_ERROR)]
    return {"blocked": bool(reasons), "reasons": sorted(reasons), "watermark": False}
