"""M2-M4 活体方差回采(EAI-CUSTOM 2026-11-06,挂账「M2-M4 方差缺席」兑付)。

2026-11-05 活体回采只单跑:M1 两跑现 n=1→0 抖动;M2 章节段/M3 表格段/M4 业绩段
只有单跑且门信号未触发(walkthrough 夹具无表格无业绩,门开不了)——跨跑方差从未
测过。本脚本对**方差夹具**(variance-tender/bid.md,含必备章节/工程量清单/类似
业绩,五段门全开)跑 N 次 worker.advance_task 生产管线,输出逐键跨跑方差 +
fields 内容 sha1 指纹抖动面。

方差口径(plan 2026-11-06 §R1):测**稳定性**不测正确性——方差夹具无标注集,
不评分不进 live_pass_rate(0.8077 只升不降锚不动);walkthrough 模式可选(--docs
walkthrough,带标注评分,复测分值方差)。

一次性运维脚本:sqlite 内存库定点五表(不触生产 postgres);每跑独立 engine 隔离;
exit 恒 0(判读在调用方)。进度行走 stderr,完整 JSON 走 stdout(重定向落文件,
禁 tail 管道——bug-4027 教训)。

容器内运行(gateway 容器,backend 目录 bind-mount 直通):
  cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_live_variance.py --runs 3 > /tmp/variance.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_CASES = BACKEND / "app" / "extensions" / "bid_review" / "golden" / "extract_cases"

_DOCSETS = {
    "variance": [("variance-tender.md", "tender"), ("variance-bid.md", "bid")],
    "walkthrough": [("walkthrough-tender.md", "tender"), ("walkthrough-bid.md", "bid")],
}


def _flatten(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _variance(flat_runs: list[dict]) -> dict:
    """跨跑逐键方差:收集各跑值,all-equal → stable。"""
    keys = sorted({k for r in flat_runs for k in r})
    return {k: {"values": [r.get(k) for r in flat_runs], "stable": all(r.get(k) == flat_runs[0].get(k) for r in flat_runs)} for k in keys}


def _field_fps(fields: dict) -> dict:
    """fields 内容指纹:每键 canonical-json sha1[:12] + list 键长度——内容抖动即指纹变。"""
    out = {}
    for k, v in sorted(fields.items()):
        blob = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
        out[k] = {"sha": hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12], "n": len(v) if isinstance(v, list) else None}
    return out


async def _run_once(docs: list[dict], run_no: int) -> dict:
    """单跑:独立 sqlite 内存库 → advance_task 生产全链路 → payload 采集。"""
    from bid_review_live_full import _TABLES, _stage_stats  # 同目录运维脚本复用(段统计/定点表)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.bid_review import crud
    from app.extensions.bid_review.worker import _default_extract_fn, advance_task
    from app.extensions.database import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    t0 = time.perf_counter()
    async with factory() as s:
        t = await crud.create_task(s, owner_id="live-variance")
        await advance_task(s, t.id, "live-variance", docs, _default_extract_fn(), True)
        rows = await crud.list_baselines(s, task_id=t.id, owner_id="live-variance")
        payload = rows[0].payload
    await engine.dispose()
    fields = payload.get("fields") or {}
    cross = payload.get("crosscheck") or {}
    out = {
        "run": run_no,
        "seconds": round(time.perf_counter() - t0, 1),
        "stages": _stage_stats(fields),
        "field_fps": _field_fps(fields),
        "crosscheck": {k: cross.get(k) for k in ("declarations_missing", "declarations_extra", "page_offset", "copy_conflicts", "core_success_rate")},
    }
    if docs[0]["doc_id"].startswith("walkthrough"):  # 有标注集才评分(方差夹具无标注,不评分)
        from app.extensions.bid_review.golden import extract as gextract

        score = gextract.score_fields(fields, gextract.load_annotations())
        out["score_pass_rate"] = score["summary"].get("pass_rate")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--docs", choices=sorted(_DOCSETS), default="variance")
    args = ap.parse_args()
    names = _DOCSETS[args.docs]
    docs = [{"doc_id": name, "role": role, "text": (_CASES / name).read_text(encoding="utf-8")} for name, role in names]

    runs: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"[variance] run {i}/{args.runs} start", file=sys.stderr, flush=True)
        runs.append(await _run_once(docs, i))
        print(f"[variance] run {i}/{args.runs} done in {runs[-1]['seconds']}s", file=sys.stderr, flush=True)

    stage_var = _variance([_flatten(r["stages"]) for r in runs])
    fp_keys = sorted({k for r in runs for k in r["field_fps"]})
    fp_var = {}
    for k in fp_keys:
        shas = [r["field_fps"].get(k, {}).get("sha") for r in runs]
        fp_var[k] = {
            "shas": shas,
            "ns": [r["field_fps"].get(k, {}).get("n") for r in runs],
            "stable": len(set(shas)) == 1,
        }
    flapped = sorted(k for k, v in stage_var.items() if not v["stable"])
    fields_flapped = sorted(k for k, v in fp_var.items() if not v["stable"])
    out = {
        "docs": args.docs,
        "runs": args.runs,
        "stage_variance": stage_var,
        "field_variance": fp_var,
        "flapped_stage_keys": flapped,
        "flapped_fields": fields_flapped,
        "run_seconds": [r["seconds"] for r in runs],
        "scores": [r.get("score_pass_rate") for r in runs] if args.docs == "walkthrough" else None,
        "runs_detail": runs,  # 全量留痕(评注/复盘两用)
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
