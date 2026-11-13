"""埋点六指标(P1-β 批廿三,spec §3;EAI-CUSTOM 2026-11-13)——纯函数,
generate_and_record 计时后调用,落 verdict["metrics"](无新表;gaps 断言维度
读 results 面零影响)。

诚实挂账:manual_edit_ratio=None(编辑面 P1-δ 才有采样源);retry_count=0
(重投循环未建);D0/D1 计数=断言维度(规则层维度挂 L4 激活批,spec §7)。"""

from __future__ import annotations


def compute_metrics(ctx: dict, export: dict, *, duration_ms: int) -> dict:
    """ctx(bl.slots 槽位面)+export(results 断言面)→ 六指标形。
    slot_fill_rate=投标函槽位非空占比(total=0→None 不造空零);
    assertion_pass_rate=PASS/(PASS+FAIL+ERROR) 已裁决集(SKIPPED 不计分母);
    d0/d1_count=非 PASS 结果按 final level 计数。"""
    slots = ((ctx.get("products") or {}).get("bid_letter") or {}).get("slots") or {}
    total = len(slots)
    filled = sum(1 for v in slots.values() if v not in (None, "", []))
    results = export.get("results") or []
    decided = [r for r in results if r.get("status") in ("PASS", "FAIL", "ERROR")]
    return {
        "slot_fill_rate": round(filled / total, 4) if total else None,
        "assertion_pass_rate": round(sum(1 for r in decided if r["status"] == "PASS") / len(decided), 4) if decided else None,
        "d0_count": sum(1 for r in results if r.get("status") != "PASS" and r.get("level") == "D0"),
        "d1_count": sum(1 for r in results if r.get("status") != "PASS" and r.get("level") == "D1"),
        "manual_edit_ratio": None,  # ponytail: 编辑面 P1-δ 落地才有采样源,现挂 None 诚实
        "latency_ms": int(duration_ms),
        "retry_count": 0,  # ponytail: 重投循环未建,恒 0 诚实
        "note": "断言维度计数;规则层维度挂 L4 激活批;manual/retry 诚实零待对应面落地",
    }


__all__ = ["compute_metrics"]
