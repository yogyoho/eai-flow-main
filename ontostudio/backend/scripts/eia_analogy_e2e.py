"""query_analogy + check_consistency(scope) 端到端验证（子项目 4 spec §7 T5）——真实图.

用法（宿主机本地，只读真库；照 eia_rules_baseline.py 生产同路径）:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_analogy_e2e.py

流程 = dg_* 三表 → KernelService.load_from_sql（内存图）→ refresh()（生产同路径）
→ MCP handler 通道指向已装载真图 → query_analogy（waste_stream/treatment_measure 类比
样例，验证 source_report 在场）→ check_consistency scope=sample（样例基线违规复现）/
scope=project（C 库空 → 0）/ scope=all。

EAI-CUSTOM(2026-09-30, 子项目 4): 只读脚本，不写库、不碰容器。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DatabaseConfig  # noqa: E402
from app.ontology import mcp  # noqa: E402
from app.ontology.kernel.service import KernelService  # noqa: E402
from app.ontology.rules_executor import DEFAULT_VIOLATION_LIMIT, execute_rules  # noqa: E402

_iri_bindings = mcp._iri_bindings  # 违规行 IRI 形绑定值判定（与 _check_consistency 同一函数）

OUT_DIR = Path(__file__).parent / "eia_analogy_e2e_out"


async def _call(name: str, args: dict) -> dict:
    result = await mcp.call_tool(name, args)
    return json.loads(result[0].text)


def _compact_entity(e: dict) -> dict:
    return {
        "label": e["label"],
        "etype": e["etype"],
        "source_report": e["source_report"],
        "scope": e["scope"],
        "attrs": e["attrs"],
        "adjacency": {
            "out": [{"predicate": x["predicate"], "peer_name": x["peer_name"], "peer_etype": x["peer_etype"], "peer_attrs": x["peer_attrs"]} for x in e["adjacency"]["out"][:3]],
            "in": [{"predicate": x["predicate"], "peer_name": x["peer_name"]} for x in e["adjacency"]["in"][:3]],
        },
    }


async def main_async() -> int:
    dsn = DatabaseConfig.from_env().url
    kernel = KernelService()  # 内存图（不碰持久化 kernel 路径）

    t0 = time.perf_counter()
    load = await kernel.load_from_sql(dsn=dsn)
    load_ms = round((time.perf_counter() - t0) * 1000, 1)
    t1 = time.perf_counter()
    infer = kernel.refresh()
    infer_ms = round((time.perf_counter() - t1) * 1000, 1)

    # MCP handler 通道（_kernel_store → get_kernel 单例）指向已装载真图
    import app.ontology.kernel.service as svc

    svc._kernel = kernel

    failures: list[str] = []
    analogy_out: dict[str, dict] = {}
    for etype in ("waste_stream", "treatment_measure"):
        d = await _call("query_analogy", {"etype": etype, "limit": 5})
        analogy_out[etype] = d
        if not d.get("success"):
            failures.append(f"query_analogy {etype} success=false: {d.get('error')}")
            continue
        if d["count"] == 0:
            failures.append(f"query_analogy {etype} 零命中（预期样例库有素材）")
        for e in d["entities"]:
            if "source_report" not in e:
                failures.append(f"query_analogy {etype} 出参缺 source_report: {e['label']}")
            if e.get("scope") != "sample":
                failures.append(f"query_analogy {etype} 非 sample 归属混入: {e['label']} scope={e.get('scope')}")

    by_scope: dict[str, dict] = {}
    for scope in ("sample", "project", "all"):
        d = await _call("check_consistency", {"scope": scope})
        by_scope[scope] = d
        if not d.get("success"):
            failures.append(f"check_consistency scope={scope} success=false: {d.get('error')}")
    # project 视角：可归属（有 IRI 绑定）违规必须清零——C 库空；无 IRI 绑定行（不可归属）
    # fail-visible 保留是 _check_consistency 既定设计（如 rule_entity_naming 按归一名分组）
    proj = by_scope.get("project", {})
    if proj:
        full = execute_rules(kernel.store, limit=DEFAULT_VIOLATION_LIMIT)
        proj_rules = {r["rule_id"]: r for r in proj["results"]}
        for r in full["results"]:
            kept = proj_rules.get(r["rule_id"], {}).get("violations", [])
            attributable = [v for v in kept if _iri_bindings(v)]
            if attributable:
                failures.append(f"scope=project 混入可归属违规 {r['rule_id']}: {len(attributable)} 条")
    if by_scope.get("sample", {}).get("total_violations", 0) > by_scope.get("all", {}).get("total_violations", 0):
        failures.append("scope=sample 违规总数 > scope=all（过滤视角应单调不增）")

    report = {
        "load": {"entities": load.get("entities"), "relations": load.get("relations"), "duration_ms": load_ms},
        "infer": {"input_triples": infer.input_triples, "entailment_triples": infer.entailment_triples, "duration_ms": infer_ms},
        "query_analogy": {k: {"count": v.get("count"), "sample_first_entity": _compact_entity(v["entities"][0]) if v.get("entities") else None} for k, v in analogy_out.items()},
        "check_consistency": {s: {"scope": d.get("scope"), "total_violations": d.get("total_violations"), "by_severity": d.get("by_severity")} for s, d in by_scope.items()},
        "failures": failures,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "e2e_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"装载 {load.get('entities')} 实体 / {load.get('relations')} 关系（{load_ms}ms）+ 推理 {infer.entailment_triples} 派生三元组（{infer_ms}ms）")
    for etype, d in analogy_out.items():
        first = d.get("entities", [{}])[0]
        n_edges = len(first.get("adjacency", {}).get("out", [])) + len(first.get("adjacency", {}).get("in", []))
        print(f"query_analogy {etype}: count={d.get('count')}  首条 label={first.get('label')!r} source_report={first.get('source_report')!r} 邻接边={n_edges}")
    for s, d in by_scope.items():
        print(f"check_consistency scope={s}: total={d.get('total_violations')} by_severity={d.get('by_severity')}")
    if failures:
        print(f"FAIL（{len(failures)} 项）：")
        for f in failures:
            print(f"  - {f}")
        print(f"报告落盘: {out_path}")
        return 1
    print("E2E 全部断言通过（query_analogy source_report 在场 + 非 sample 不混入 + project 可归属违规清零 + sample≤all 单调）")
    print(f"报告落盘: {out_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
