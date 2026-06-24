"""Validation — the 2D-drawing self-check (no volume available, unlike 3D).

Reports the checks that actually ran. Only facts the composer can verify
deterministically: entities placed, nothing skipped, symbol ops valid,
title block present, annotations present, drawing has non-zero extent.
Visual correctness still needs the PNG preview (rasterize).
"""
from __future__ import annotations

from .strategies import KNOWN_OPS


def validate(intent: dict, report, msp, pack) -> list[dict]:
    checks: list[dict] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    chk("entities_placed", report.placed > 0, f"placed={report.placed}")
    chk("no_skipped_entities", not report.skipped, f"skipped={report.skipped[:3]}")

    bad_ops = []
    for spec in pack.symbols.specs.values():
        for prim in spec.primitives:
            if prim.get("op") not in KNOWN_OPS:
                bad_ops.append({"symbol": spec.type, "op": prim.get("op")})
    chk("symbol_ops_valid", not bad_ops, f"unknown_ops={bad_ops[:3]}")

    chk("title_block_present", bool(intent.get("title_block")), "intent.title_block empty")
    ann_count = len(intent.get("annotations", []))
    chk("annotations_present", ann_count > 0, f"count={ann_count}")

    extent_detail = ""
    has_extent = False
    try:
        from ezdxf import bbox as _bbox

        ext = _bbox.extents(list(msp), fast=True)
        has_extent = bool(ext.has_data and (ext.extmax.x - ext.extmin.x) > 0)
        if ext.has_data:
            extent_detail = f"{round(ext.extmax.x - ext.extmin.x)}×{round(ext.extmax.y - ext.extmin.y)}"
    except Exception as exc:  # bbox is best-effort; surface the reason, don't crash compose
        extent_detail = f"bbox error: {exc}"
    chk("drawing_has_extent", has_extent, extent_detail)

    return checks
