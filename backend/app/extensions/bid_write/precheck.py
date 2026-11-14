"""F6 规则层预审查(批廿一 M2,EAI-CUSTOM 2026-11-13)——bid_review 同尺投影。

同源一把尺:bid_review L1/L2 规则消费 bid.* 字段,写侧生成产物即标书本体。
project_bid_fields 把 products 投影到 bid.* 平面字段,复用 rule_runner/eval_core
跑确定性规则子集(det-only:sem 规则不喂模型→零伪 ERROR;L4 全语义→det 视角
零 issue→水印恒加=写侧未跑模型审查的诚实语义)。缺口诚实:未投影路径缺席→
UNKNOWN(计预审查待确认,不阻断)。纯函数零 IO 零时钟。

已知尺差(挂账):审查端 number_to_words 整元截断 vs 写侧 num_to_cn 含角分→
含分总额 L1-010 大写步判 FAIL;本批投影原样透传 amount_cn,修复方向=审查端
升级角分感知。阻断口径=contracts.BLOCK_EXPORT_LEVELS(D0 断言)+L1 fatal det
FAIL;L2 fatal(如 L2-033 保证金凭证缺失)诚实暴露不阻断(spec §8 只 L1)。"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path

from app.extensions.bid_review.engine.eval_core import evaluate_fields
from app.extensions.bid_review.engine.rule_runner import load_rulepack

_CORE_PATH = Path(__file__).parents[1] / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml"
_L4_PATH = Path(__file__).parents[1] / "bid_review" / "engine" / "rulepacks" / "bid-review-l4" / "1.0.0.yaml"
_det_pack = None


def _det_only_pack():
    """core+L4 合包裁到 det-only(module 级缓存;包文件仓库内静态)。"""
    global _det_pack
    if _det_pack is None:
        core = load_rulepack(_CORE_PATH)
        packs = [core]
        if _L4_PATH.exists():
            packs.append(load_rulepack(_L4_PATH))
        rules = [r for p in packs for r in p.rules if r.enabled and r.type == "deterministic"]
        _det_pack = dataclasses.replace(core, rules=rules)
    return _det_pack


def project_bid_fields(ctx: dict) -> dict:
    """products→bid.* 投影(仅产物可推导路径;None/空串=缺席→UNKNOWN 诚实)。"""
    p = (ctx or {}).get("products") or {}
    ps = p.get("price_sheet") or {}
    bl = p.get("bid_letter") or {}
    slots = bl.get("slots") or {}
    rows = [r for r in ps.get("rows") or [] if isinstance(r, dict)]
    out: dict = {}
    if slots.get("valid_days") is not None:
        out["bid.validity_days"] = slots["valid_days"]
    if ps.get("detail_total") is not None:
        out["bid.total_price"] = ps["detail_total"]
    if ps.get("amount_cn"):
        out["bid.total_price_words"] = ps["amount_cn"]  # 原样透传(尺差挂账见模块头)
    if ps.get("summary_total") is not None:
        out["bid.subtotal"] = ps["summary_total"]
    priced = [r for r in rows if r.get("amount") is not None]
    if priced:
        out["bid.detail_rows"] = [{"name": r.get("name"), "amount": r.get("amount")} for r in priced]
    if rows:
        out["bid.boq_items"] = [{"id": r.get("id"), "name": r.get("name"), "qty": r.get("qty"), "unit": r.get("unit")} for r in rows]
    if slots.get("deposit_amount") is not None:
        out["bid.deposit_amount"] = slots["deposit_amount"]
    if slots.get("deposit_form"):
        out["bid.deposit_forms"] = [slots["deposit_form"]]
    out["bid.deposit_receipt_present"] = False  # M0 无凭证;素材联动挂 P1+
    if ps.get("tax_rate") is not None:
        out["bid.tax_rate_occurrences"] = [{"value": ps["tax_rate"]}]
    if ps.get("price_mode"):
        out["bid.price_includes_tax"] = ps["price_mode"] == "含税"
    out["bid.alternative_price_offers"] = []  # 生成器不造替代方案(L1-019 判定面)
    if slots.get("bidder_name"):
        out["bid.entity_name_occurrences"] = [slots["bidder_name"]]
    comms = [c for c in (bl.get("extra_commitments") or []) if isinstance(c, dict) and str(c.get("text") or "").strip()]
    if comms:
        # 批廿四 P1-γ:L4-003/004 语义审查输入面(承诺清单+产物全文投影;无承诺缺席=绿跑零行为)
        out["bid.service_commitments"] = [{"text": str(c["text"]).strip(), "clause_id": str(c.get("clause_id") or "")} for c in comms]
    if bl.get("text"):
        out["bid.full_text"] = bl["text"]
    knob_wp = str(((ctx or {}).get("knobs") or {}).get("warranty_period") or "").strip()
    if knob_wp:
        # 批廿五 P1-δ:L4-001 输入(人工旋钮直通,原样透传不造数)
        out["bid.warranty_period"] = knob_wp
    sections = [
        {"clause_id": r.get("clause_id"), "text": str(r.get("response_text") or ""), "conclusion": r.get("conclusion")}
        for r in ((p.get("response_table") or {}).get("rows") or [])
        if isinstance(r, dict) and str(r.get("response_text") or "").strip()
    ]
    if sections:
        # 批廿五 P1-δ:L4-008 输入(响应表行=产物可推导;空表缺席)
        out["bid.response_sections"] = sections
    return out


async def run_rule_precheck(fields: dict) -> dict:
    """det-only 预审查:issues/counts/l1_fatal_fail/blocked/scope_note。
    blocked=∃ L1∧fatal∧FAIL(UNKNOWN 不阻断;L2 fatal 同不阻断,spec §8)。"""
    issues = await evaluate_fields(_det_only_pack(), dict(fields or {}), model_fn=None)
    counts = Counter(i.get("verdict") for i in issues)
    l1_fatal = sorted({i["rule_id"] for i in issues if i.get("layer") == "L1" and i.get("severity") == "fatal" and i.get("verdict") == "FAIL"})
    return {
        "issues": issues,
        "counts": {k: counts[k] for k in sorted(counts)},
        "l1_fatal_fail": l1_fatal,
        "blocked": bool(l1_fatal),
        "scope_note": {"det_rules": len(_det_only_pack().rules), "sem_excluded": "模型规则不预审(L4 全语义→水印恒加)", "packs": ["bid-review-core/1.0.0", "bid-review-l4/1.0.0"]},
    }


_L4_BLOCKING = {"FAIL", "ERROR", "need_human", "UNKNOWN"}
_l4_pack_cache = None


def _l4_participants(fields: dict):
    """L4 参与卡筛选(P1-γ):enabled ∧ sem/hyb ∧ inputs 全非空。缺输入卡诚实列
    input_missing 不烧模型(sem 卡缺输入仍会模型调用,写侧成本闸;engine 不动,
    写侧本地关切)。返回 (pack|None, 参与卡 id 列表, 缺输入卡 id 列表)。"""
    global _l4_pack_cache
    if not _L4_PATH.exists():
        return None, [], []
    if _l4_pack_cache is None:
        _l4_pack_cache = load_rulepack(_L4_PATH)
    parts: list = []
    missing: list[str] = []
    for r in _l4_pack_cache.rules:
        if not r.enabled or r.type not in ("semantic", "hybrid"):
            continue
        if all(fields.get(p) not in (None, "", [], {}) for p in r.inputs):
            parts.append(r)
        else:
            missing.append(r.id)
    if not parts:
        return None, [], missing
    return dataclasses.replace(_l4_pack_cache, rules=parts), [r.id for r in parts], missing


async def run_l4_review(fields: dict, materials: str, model_fn) -> dict:
    """L4 语义审查面(advisory-only,P1-γ):参与卡(inputs 全非空)过 evaluate_fields
    全引擎语义管线(逐规则隔离;full=干净零条目/partial·none=FAIL·WARN/unclear=
    need_human/基础设施故障=ERROR)。摘除条件=executed ∧ 参与卡零 FAIL/ERROR/
    need_human/UNKNOWN(unclear=未确认→水印保持,诚实)。L4 永不入 gate blocked/
    reasons(pack meta counts_toward_bid_gate=false,advisory-only 铁律)。"""
    pack, parts, missing = _l4_participants(fields)
    if pack is None or model_fn is None:
        return {
            "executed": False,
            "counts": {},
            "issues": [],
            "participants": parts,
            "input_missing": missing,
            "watermark_removed": False,
            "scope_note": "L4 无参与卡或缺模型→未执行(水印恒加)",
        }
    issues = await evaluate_fields(pack, dict(fields or {}), model_fn=model_fn, materials=materials)
    counts = Counter(i.get("verdict") for i in issues)
    removed = not any(i.get("verdict") in _L4_BLOCKING for i in issues)
    return {
        "executed": True,
        "counts": {k: counts[k] for k in sorted(counts)},
        "issues": issues,
        "participants": parts,
        "input_missing": missing,
        "watermark_removed": bool(removed),
        "scope_note": f"L4 模型审查 advisory-only(不阻断;参与卡 {len(parts)},缺输入 {len(missing)})",
    }


async def run_export_gate(ctx: dict, *, l4_model_fn=None, ast: dict | None = None) -> dict:
    """导出前置校验(P0 规格 §8):重跑全量 D0 断言 + det 规则层预审查
    (+批廿四 P1-γ:l4_model_fn 供给时叠加 L4 语义审查面 advisory-only——不入
    blocked/reasons;watermark 摘除条件=参与卡零 FAIL/ERROR/need_human/UNKNOWN,
    摘除即 None,否则恒加 EXPORT_RISK_WATERMARK)。blocked=gate D0 FAIL/ERROR 或
    L1 fatal det FAIL(L4 零贡献,铁律)。

    批三十三:``ast`` 非空时先把冻结 revision AST 覆盖到任务 ctx(price/response/
    letter/slots)再跑断言与投影;导出与编辑器断言共用 ``prepare_editor_ctx``,
    避免「审批冻结的正文」与「导出校验的事实」分叉。"""
    from app.extensions.bid_write.contracts import EXPORT_RISK_WATERMARK, SCHEMA_VERSION
    from app.extensions.bid_write.executor.gate import gate_verdict
    from app.extensions.bid_write.executor.runner import run_assertions

    if ast is not None:
        from app.extensions.bid_write.executor.editor import prepare_editor_ctx

        ctx, _meta = prepare_editor_ctx(ctx, ast)
    report = run_assertions(ctx)
    gate = gate_verdict(report)
    fields = project_bid_fields(ctx)
    pre = await run_rule_precheck(fields)
    l4 = None
    if l4_model_fn is not None:
        # 批廿五 P1-δ:tender 快照全量合并(泛化 substantive_clauses 特例;L4-001 消费
        # tender.min_warranty_period 等;bid.* 投影同键覆盖优先)
        l4_fields = {**((ctx or {}).get("tender") or {}), **fields}
        bl = ((ctx or {}).get("products") or {}).get("bid_letter") or {}
        l4 = await run_l4_review(l4_fields, str(bl.get("text") or ""), l4_model_fn)
    a_counts = Counter(r.status for r in report.results)
    from app.extensions.bid_write.executor.report import to_report_dict

    return {
        "blocked": bool(gate["blocked"] or pre["blocked"]),
        "reasons": sorted(set(gate["reasons"]) | set(pre["l1_fatal_fail"])),
        "watermark": None if l4 is not None and l4["watermark_removed"] else EXPORT_RISK_WATERMARK,
        "assertion_counts": {k: a_counts[k] for k in sorted(a_counts)},
        "rule_counts": pre["counts"],
        "l1_fatal_fail": pre["l1_fatal_fail"],
        "l4": l4,
        "scope_note": pre["scope_note"],
        "schema_version": SCHEMA_VERSION,
        # results=gaps 断言维度消费面(to_report_dict 序列化;报告=导出物非真相源)
        "results": to_report_dict(report)["results"],
    }
