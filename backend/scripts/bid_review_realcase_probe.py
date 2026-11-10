"""真实标书件回采探针(EAI-CUSTOM 2026-11-10 一次性运维,批十四前置)。

真实招标/投标 docx(中煤科工·环评报告智能写作平台,辽宁创元)走生产转换链
(deerflow.utils.file_conversion.convert_file_to_markdown,uploads 自动转换同源)
→ advance_task 生产全链路 N 样本,采集:
  1) 21 叶平键逐键值 + 跨样本方差(键级 distinct 值计数——批十三判:值域统计
     不可作硬锚,须多样本;本探针即多样本锚的兑现);
  2) A-ADJ-1 先验:招标原文递交方式线索行 + fields 注册键确认;
  3) stage 统计 + issues 全貌(总数/severity 分布/gate 四态)。

一次性运维:sqlite 内存库定点五表,不触生产 postgres;exit 恒 0(判读在调用方);
进度走 stderr,JSON 走 stdout 重定向落文件(bug-4027 律);per-sample try/except
continue(bug-4086 律);转换一次复用 N 样本。

容器内运行(gateway 容器,docx 先 docker cp 进 /tmp):
  cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_realcase_probe.py \
    > /tmp/realcase.json 2>/tmp/realcase.err
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_TENDER = Path("/tmp/realcase-tender.docx")
_BID = Path("/tmp/realcase-bid.docx")
_SAMPLES = 3

from bid_review_live_leafkeys import LEAF_KEYS, _flatten, _leaf_report, _submit_method_probe  # noqa: E402


async def _load_docs() -> list[dict]:
    from deerflow.utils.file_conversion import convert_file_to_markdown

    docs = []
    for path, role in ((_TENDER, "tender"), (_BID, "bid")):
        md = await convert_file_to_markdown(path)
        text = md.read_text(encoding="utf-8") if md else ""
        docs.append({"doc_id": path.name, "role": role, "text": text})
        print(f"[realcase] {role} converted: {len(text)} chars", file=sys.stderr, flush=True)
    return docs


async def _run_sample(idx: int, docs: list[dict]) -> dict:
    from bid_review_live_full import _TABLES, _stage_stats
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.bid_review import crud
    from app.extensions.bid_review.worker import _default_extract_fn, advance_task, compute_gate_status
    from app.extensions.database import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    t0 = time.perf_counter()
    async with factory() as s:
        t = await crud.create_task(s, owner_id="live-realcase")
        # wait_confirm env 开关(2026-11-11 教训:True=止步确认门,审查段不跑,issues 恒 0
        # 假象;False=全链路 det+sem/hyb 审查。默认 False=全链路)
        wait_confirm = os.environ.get("EAI_BID_REVIEW_PROBE_WAIT_CONFIRM", "0") == "1"
        await advance_task(s, t.id, "live-realcase", docs, _default_extract_fn(), wait_confirm)
        rows = await crud.list_baselines(s, task_id=t.id, owner_id="live-realcase")
        payload = rows[0].payload if rows else {}
        issues = await crud.list_issues(s, task_id=t.id, owner_id="live-realcase")
    await engine.dispose()
    fields = payload.get("fields") or {}
    flat = _flatten(fields)
    tender_text = next(d["text"] for d in docs if d["role"] == "tender")
    sev: dict[str, int] = {}
    verdict: dict[str, int] = {}
    for i in issues:
        k = str(getattr(i, "severity", "") or "")
        sev[k] = sev.get(k, 0) + 1
        k2 = str(getattr(i, "verdict", "") or "")
        verdict[k2] = verdict.get(k2, 0) + 1
    return {
        "sample": idx,
        "seconds": round(time.perf_counter() - t0, 1),
        "stages": _stage_stats(fields),
        "leaf_keys": _leaf_report(flat),
        "leaf_present": sum(1 for v in _leaf_report(flat).values() if v["present"]),
        "adj1": _submit_method_probe(tender_text, flat),
        "issues_total": len(issues),
        "severity_counts": sev,
        "verdict_counts": verdict,
        "gate_status": compute_gate_status(issues),
    }


def _variance(results: list[dict]) -> dict:
    """21 叶键跨样本值方差:distinct 值集 + 值序列(多样本锚——批十三记档的兑现)。"""
    out: dict[str, dict] = {}
    for lk in LEAF_KEYS:
        vals = []
        for r in results:
            v = r.get("leaf_keys", {}).get(lk, {})
            vals.append(v.get("value"))
        out[lk] = {"distinct": len(set(map(str, vals))), "values": [str(v)[:80] for v in vals]}
    return out


async def main() -> int:
    docs = await _load_docs()
    results = []
    for i in range(1, _SAMPLES + 1):
        print(f"[realcase] sample {i}/{_SAMPLES} start", file=sys.stderr, flush=True)
        try:
            results.append(await _run_sample(i, docs))
            print(f"[realcase] sample {i} done in {results[-1]['seconds']}s", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001 — 运维脚本,失败类型不枚举(bug-4086 律)
            results.append({"sample": i, "ok": False, "error": f"{type(e).__name__}: {e}"})
            print(f"[realcase] sample {i} FAILED: {e}", file=sys.stderr, flush=True)
    done = [r for r in results if r.get("ok", True) and "error" not in r]
    print(
        json.dumps(
            {
                "samples_requested": _SAMPLES,
                "samples_done": len(done),
                "leaf_keys_total": len(LEAF_KEYS),
                "results": results,
                "leaf_variance": _variance(done) if done else {},
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
