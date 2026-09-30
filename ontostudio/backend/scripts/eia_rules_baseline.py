"""EIA 校验规则基线报告（子项目 3 spec §7）——真实图首轮全量执行.

用法（宿主机本地，只读真库；也可在容器内对 ONTOSTUDIO_KERNEL_PATH 持久图跑）:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_rules_baseline.py

流程 = 生产同路径：dg_* 三表 → KernelService.load_from_sql（内存图）→ refresh()
（schema 重编 → owlrl 闭包 → CONSTRUCT 派生，rule_emission_monitoring 依赖派生图）
→ execute_rules 全量 12 条 → 基线报告落盘 JSON + 控制台表格。

EAI-CUSTOM(2026-09-30, 子项目 3): 只读脚本，不写库、不碰容器。
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DatabaseConfig  # noqa: E402
from app.ontology.kernel.service import KernelService  # noqa: E402
from app.ontology.rules_executor import execute_rules  # noqa: E402

OUT_DIR = Path(__file__).parent / "eia_rules_baseline_out"
BASELINE_LIMIT = 100000  # 基线要全量数字，不截断


def main() -> None:
    dsn = DatabaseConfig.from_env().url
    kernel = KernelService()  # 内存图（不碰持久化 kernel 路径）

    t0 = time.perf_counter()
    load_summary = _run(kernel.load_from_sql(dsn=dsn))
    load_stats = dict(load_summary)
    load_ms = round((time.perf_counter() - t0) * 1000, 1)

    t1 = time.perf_counter()
    infer_summary = _run(kernel.refresh())
    infer_stats = dict(asdict(infer_summary) if not isinstance(infer_summary, dict) else infer_summary)
    infer_ms = round((time.perf_counter() - t1) * 1000, 1)

    t2 = time.perf_counter()
    out = execute_rules(kernel.store, limit=BASELINE_LIMIT)
    rules_ms = round((time.perf_counter() - t2) * 1000, 1)

    report = {
        "executed_at": datetime.now(UTC).isoformat(),
        "scope": "真实 2521 实例图（dg_* 全量装载 → 内存 kernel，生产同路径 load+refresh）",
        "load": load_stats,
        "load_duration_ms": load_ms,
        "infer": {
            "input_triples": infer_stats.get("input_triples"),
            "entailment_triples": infer_stats.get("entailment_triples"),
            "rule_counts": infer_stats.get("rule_counts"),
            "errors": infer_stats.get("errors"),
        },
        "infer_duration_ms": infer_ms,
        "rules_duration_ms": rules_ms,
        "total_violations": out["total_violations"],
        "results": out["results"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "baseline_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"装载 {load_stats.get('entities')} 实体 / {load_stats.get('relations')} 关系（跳过 实体 {len(load_stats.get('skipped_entities', []))} / 关系 {len(load_stats.get('skipped_relations', []))}）")
    print(f"推理 派生三元组 {infer_stats.get('entailment_triples')}，链规则 {infer_stats.get('rule_counts')}")
    print(f"{'规则':<28}{'级别':<7}{'违规数':>7}  {'耗时ms':>9}")
    for r in out["results"]:
        print(f"{r['rule_id']:<28}{r['severity']:<7}{r['violation_count']:>7}  {r['duration_ms']:>9}")
    print(f"合计 {out['total_violations']} 条违规（12 规则，总耗时 规则 {rules_ms}ms）")
    print(f"报告落盘: {out_path}")


def _run(coro_or_value):
    """load_from_sql 是协程、refresh 是同步——统一取值。"""
    import asyncio

    if asyncio.iscoroutine(coro_or_value):
        return asyncio.run(coro_or_value)
    return coro_or_value


if __name__ == "__main__":
    main()
