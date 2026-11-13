"""批二十 M1-c 执行器负例金标 + 报告/门禁测试(EAI-CUSTOM 2026-11-13)——
golden/cases-write/exec-negatives.yaml 全红面(变异生效=至少一条非 PASS;expect
子集钉防过拟合;gate_blocked 双向一致性)+ report.pending/skipped 单逻辑面 +
gate_verdict 阻断/非阻断/D2 不阻断面。"""

from __future__ import annotations

from pathlib import Path

import yaml
from bid_write_exec_fixtures import green_ctx, statuses

from app.extensions.bid_write import contracts
from app.extensions.bid_write.executor import report as exec_report
from app.extensions.bid_write.executor.gate import gate_verdict
from app.extensions.bid_write.executor.loader import load_registry
from app.extensions.bid_write.executor.runner import run_assertions

NEG_YAML = Path(contracts.__file__).parent / "golden" / "cases-write" / "exec-negatives.yaml"


def _cases() -> list[dict]:
    with open(NEG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def _resolve(root: dict, path: str) -> tuple[object, str | int]:
    """路径→(父节点, 键)。两面键约定:tender 面=扁平点分键(「tender.max_price」
    是一个键,extract LIST_PATHS 口径),products/material/pre 面=真嵌套。逐层
    贪心:先试剩余全串是否为当前 dict 的扁平键,否则按段下钻(数字段=列表下标)。"""
    segs = path.split(".")
    node = root
    for i in range(len(segs) - 1):
        joined = ".".join(segs[i:])
        if isinstance(node, dict) and joined in node:
            return node, joined
        seg = segs[i]
        node = node[int(seg)] if isinstance(node, list) else node[seg]
    return node, segs[-1]


def _apply_mutate(ctx: dict, ops: list[dict]) -> None:
    """路径式变异:op ∈ set/del/append。"""
    for op in ops:
        parent, key = _resolve(ctx, op["path"])
        if op["op"] == "set":
            parent[key] = op["value"]
        elif op["op"] == "del":
            del parent[key]
        elif op["op"] == "append":
            parent[key].append(op["value"])
        else:
            raise AssertionError(f"未知变异 op: {op['op']}")


# ── 金标清单形状 ─────────────────────────────────────────────────────────────


def test_negatives_manifest_shape():
    cases = _cases()
    assert len(cases) >= 18, f"负例覆盖不足: {len(cases)}"
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids)), "case_id 撞号"
    valid = {a.id for a in load_registry().assertions}
    for c in cases:
        assert c["expect"], c["case_id"]
        assert isinstance(c["gate_blocked"], bool)
        for aid in c["expect"]:
            assert aid in valid, (c["case_id"], aid, "幽灵断言钉")


# ── 负例全红 + 门禁一致性 ────────────────────────────────────────────────────


def test_exec_negatives_all_red_and_gate_consistent():
    for case in _cases():
        ctx = green_ctx()
        _apply_mutate(ctx, case["mutate"])
        rep = run_assertions(ctx)
        by_id = {r.assertion_id: r for r in rep.results}
        # 变异必须生效:全绿=假负例
        assert any(r.status != "PASS" for r in rep.results), case["case_id"]
        for aid, pin in case["expect"].items():
            r = by_id[aid]
            assert r.status == pin["status"], (case["case_id"], aid, r.status, r.message)
            if "level" in pin:
                assert r.level == pin["level"], (case["case_id"], aid, r.level)
        gate = gate_verdict(rep)
        assert gate["blocked"] is case["gate_blocked"], (case["case_id"], gate, case["expect"])
        assert gate["watermark"] is False, case["case_id"]
        if case["gate_blocked"]:
            assert gate["reasons"], case["case_id"]


def test_gate_reasons_cover_pinned_d0_faces():
    """blocked 例:reasons 恰含 expect 钉中的 D0 FAIL/ERROR(短路根因已计,SKIPPED 不重复计)。"""
    for case in _cases():
        if not case["gate_blocked"]:
            continue
        ctx = green_ctx()
        _apply_mutate(ctx, case["mutate"])
        rep = run_assertions(ctx)
        gate = gate_verdict(rep)
        pinned_d0 = {aid for aid, pin in case["expect"].items() if pin["status"] in ("FAIL", "ERROR") and pin.get("level", "D0") == "D0"}
        assert pinned_d0 <= set(gate["reasons"]), (case["case_id"], sorted(pinned_d0 - set(gate["reasons"])))


# ── report 单逻辑面(results-dict)───────────────────────────────────────────


def test_pending_skipped_from_dict_faces():
    results = [
        {"assertion_id": "A", "skill": "BL", "status": "FAIL", "message": "m1", "human_action": "去补"},
        {"assertion_id": "B", "skill": "PS", "status": "FAIL", "message": "m2", "human_action": None},  # 处置自动闭环不挂人工账
        {"assertion_id": "C", "skill": "RT", "status": "PASS", "message": "ok", "human_action": "x"},
        {"assertion_id": "D", "skill": "CMN", "status": "ERROR", "message": "m3", "human_action": "y"},
    ]
    assert [p["assertion_id"] for p in exec_report.pending_from(results)] == ["A", "D"]
    extra = results + [{"assertion_id": "E", "skill": "BL", "status": "SKIPPED", "level": "D1", "skipped_reason": "short_circuit", "message": "跳"}]
    skip = exec_report.skipped_from(extra)
    assert [(s["assertion_id"], s["skipped_reason"]) for s in skip] == [("E", "short_circuit")]


def test_to_report_dict_shape_and_live_pending_skipped():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["legal_rep_name"] = ""
    rep = run_assertions(ctx, skills=("BL",))
    d = exec_report.to_report_dict(rep)
    assert set(d) == {"schema_version", "skills", "results"}
    assert d["skills"] == ["BL"]
    shapes = {frozenset(r) for r in d["results"]}
    assert len(shapes) == 1, "结果行同形(13 固定键)"
    pend = exec_report.pending_from(d["results"])
    assert any(p["assertion_id"] == "SK-BL-001" and p["human_action"] == "补全 12 项必填要素" for p in pend)
    skip = exec_report.skipped_from(d["results"])
    assert any(s["assertion_id"] == "SK-BL-002" and s["skipped_reason"] == "short_circuit" for s in skip)


# ── gate 单测 ────────────────────────────────────────────────────────────────


def test_gate_green_run_not_blocked():
    gate = gate_verdict(run_assertions(green_ctx()))
    assert gate == {"blocked": False, "reasons": [], "watermark": False}


def test_gate_d0_fail_blocks_and_d2_fail_does_not():
    ctx = green_ctx()
    ctx["tender"]["tender.max_price"] = 1500000  # 超限价→PS-006 D0(扁平点分键)
    gate = gate_verdict(run_assertions(ctx, skills=("PS",)))
    assert gate["blocked"] is True and "SK-PS-006" in gate["reasons"]

    ctx2 = green_ctx()
    ctx2["products"]["bid_letter"]["extra_commitments"] = [{"text": "无溯源承诺"}]  # BL-010 D2
    rep2 = run_assertions(ctx2, skills=("BL",))
    assert statuses(rep2)["SK-BL-010"] == "FAIL"
    assert gate_verdict(rep2)["blocked"] is False  # 非 D0 失败不阻断导出
