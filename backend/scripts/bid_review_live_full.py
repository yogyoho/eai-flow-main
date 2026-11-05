"""活体全链路回采(EAI-CUSTOM 2026-11-05,M5/R2+ 挂账「活体回采」,plan
docs/superpowers/plans/2026-11-05-bid-review-live-recapture-plan.md)。

walkthrough 双文档 → worker.advance_task 生产管线(首段抽取+M1 附件实体+M2 章节+
M3 表格+M4 业绩+M5 crosscheck;各 stage fn 缺省=worker._default_*_fn 生产装配)
→ 标注集评分 + 各段活体统计 + crosscheck 四指标,JSON 出 stdout 供记档。

一次性运维脚本:sqlite 内存库定点五表(不触生产 postgres);烧一次模型配额;
exit 恒 0(评分判读在调用方——extract.py 的快照地板门不在此复刻)。

容器内运行(gateway 容器,backend 目录 bind-mount 直通):
  cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_live_full.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.extensions.bid_review import crud, models  # noqa: E402
from app.extensions.bid_review.engine.attachments import normalize_name  # noqa: E402
from app.extensions.bid_review.golden import extract as gextract  # noqa: E402
from app.extensions.bid_review.worker import _default_extract_fn, advance_task  # noqa: E402
from app.extensions.database import Base  # noqa: E402

# 定点五表(同 test_bid_review_worker db fixture:共享 Base 跨模块 FK 在 DDL 排序时炸,只建闭包)
_TABLES = [
    models.ReviewTask.__table__,
    models.ReviewIssue.__table__,
    models.BaselinePackage.__table__,
    models.RulePackMeta.__table__,
    models.ReviewFeedback.__table__,
]

_CASES = BACKEND / "app" / "extensions" / "bid_review" / "golden" / "extract_cases"
_DOCS = [("walkthrough-tender.md", "tender"), ("walkthrough-bid.md", "bid")]


def _ratio(hit: int, total: int) -> float | None:
    return round(hit / total, 4) if total else None


def _stage_stats(fields: dict) -> dict:
    att = fields.get("bid.attachments") or []
    sec = fields.get("bid.section_tree") or []
    boq = fields.get("bid.boq_rows") or []
    cells = fields.get("bid.table_cells") or []
    entries = fields.get("bid.performance_entries") or []
    groups = fields.get("bid.performance_groups") or []
    return {
        "m1_attachments": {
            "n": len(att),
            "fingerprint_hit": _ratio(sum(1 for a in att if a.get("type_fingerprint")), len(att)),
            "empty_text_true": sum(1 for a in att if a.get("is_empty_text") is True),
            "names": [normalize_name(a.get("name")) for a in att][:10],
        },
        "m2_sections": {
            "n": len(sec),
            "offset_flag_nonnull": _ratio(sum(1 for s in sec if s.get("offset_flag") is not None), len(sec)),
            "offset_flag_true": sum(1 for s in sec if s.get("offset_flag") is True),
            "is_empty_nonnull": _ratio(sum(1 for s in sec if s.get("is_empty") is not None), len(sec)),
            "is_empty_true": sum(1 for s in sec if s.get("is_empty") is True),
        },
        "m3_tables": {
            "boq_rows": len(boq),
            "price_hit": _ratio(sum(1 for b in boq if b.get("price") is not None), len(boq)),
            "required_true": sum(1 for b in boq if b.get("required") is True),
            "table_cells": len(cells),
        },
        "m4_performance": {"entries": len(entries), "groups": len(groups)},
    }


async def main() -> int:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    docs = [{"doc_id": name, "role": role, "text": (_CASES / name).read_text(encoding="utf-8")} for name, role in _DOCS]
    async with factory() as s:
        t = await crud.create_task(s, owner_id="live-recapture")
        await advance_task(s, t.id, "live-recapture", docs, _default_extract_fn(), True)
        rows = await crud.list_baselines(s, task_id=t.id, owner_id="live-recapture")
        payload = rows[0].payload
    await engine.dispose()
    fields = payload.get("fields") or {}
    score = gextract.score_fields(fields, gextract.load_annotations())
    out = {
        "score_summary": score["summary"],
        "score_fails": [r for r in score["rows"] if r["verdict"] == "fail"],
        "stages": _stage_stats(fields),
        "crosscheck": payload.get("crosscheck"),
        "payload_keys": sorted(payload.keys()),
        "materials_hash": payload.get("materials_hash"),
        "fields": fields,  # 全量留痕(烧配额一次,评注/复盘两用)
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
