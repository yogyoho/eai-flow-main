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


async def run_export_gate(ctx: dict) -> dict:
    """导出前置校验(P0 规格 §8):重跑全量 D0 断言 + det 规则层预审查。
    blocked=gate_verdict D0 FAIL/ERROR 或 L1 fatal det FAIL;reasons 并集排序;
    watermark 恒加(L4 未评估语义,contracts.EXPORT_RISK_WATERMARK)。"""
    from app.extensions.bid_write.contracts import EXPORT_RISK_WATERMARK, SCHEMA_VERSION
    from app.extensions.bid_write.executor.gate import gate_verdict
    from app.extensions.bid_write.executor.runner import run_assertions

    report = run_assertions(ctx)
    gate = gate_verdict(report)
    pre = await run_rule_precheck(project_bid_fields(ctx))
    a_counts = Counter(r.status for r in report.results)
    return {
        "blocked": bool(gate["blocked"] or pre["blocked"]),
        "reasons": sorted(set(gate["reasons"]) | set(pre["l1_fatal_fail"])),
        "watermark": EXPORT_RISK_WATERMARK,
        "assertion_counts": {k: a_counts[k] for k in sorted(a_counts)},
        "rule_counts": pre["counts"],
        "l1_fatal_fail": pre["l1_fatal_fail"],
        "scope_note": pre["scope_note"],
        "schema_version": SCHEMA_VERSION,
    }
