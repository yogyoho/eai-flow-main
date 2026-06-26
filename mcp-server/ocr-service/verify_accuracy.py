"""Phase 0 hit-rate validation for eai-flow-ocr.

Run locally (no container), requires system poppler (pdf2image):
  PYTHONPATH=. python verify_accuracy.py <contract.pdf> [--out ./verify-out]

Dumps every detected table's reconstructed cells + each page PNG so a human
can eyeball: table hit-rate, row/col accuracy, and price-digit OCR accuracy.
See docs/superpowers/specs/2026-06-26-contract-price-analysis-design-v2.md §8.1.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys

from ocr_engine import OcrEngine


def main() -> int:
    ap = argparse.ArgumentParser(description="eai-flow-ocr Phase 0 hit-rate validation")
    ap.add_argument("pdf", help="path to a scanned contract PDF")
    ap.add_argument("--out", default="./verify-out", help="output dir for dumps")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        print(f"not found: {args.pdf}", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)

    eng = OcrEngine()
    resp = eng.ocr_pdf_path(args.pdf)

    print("\n=== eai-flow-ocr 命中率验证报告 ===")
    print(f"文件: {args.pdf}")
    print(f"引擎: {resp.engine}")
    print(f"耗时: {resp.elapsed_ms} ms")
    print(f"页数: {len(resp.pages)}   表格数: {resp.table_count}\n")

    confs: list[float] = []
    for page in resp.pages:
        print(
            f"-- 第 {page.page_no} 页  尺寸 {page.page_width}x{page.page_height}   "
            f"表格 {len(page.tables)} 张"
        )
        for ti, table in enumerate(page.tables):
            print(
                f"     表 {ti + 1}: {table.row_count} 行 x {table.col_count} 列   "
                f"平均置信度 {table.mean_confidence:.3f}   bbox={[round(v, 3) for v in table.bbox]}"
            )
            with open(
                os.path.join(args.out, f"page{page.page_no}_table{ti + 1}.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                for ri, row in enumerate(table.rows, 1):
                    f.write(f"行{ri}: " + " | ".join(c.text for c in row) + "\n")
            confs.extend(c.confidence for row in table.rows for c in row)
        if page.preview_png_b64:
            with open(os.path.join(args.out, f"page{page.page_no}.png"), "wb") as f:
                f.write(base64.b64decode(page.preview_png_b64))

    summary = {
        "pdf": args.pdf,
        "engine": resp.engine,
        "elapsed_ms": resp.elapsed_ms,
        "pages": len(resp.pages),
        "tables": resp.table_count,
        "cell_count": len(confs),
        "mean_confidence": round(statistics.mean(confs), 4) if confs else 0.0,
        "low_confidence_cells": sum(1 for c in confs if c < 0.85),
    }
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(
        f"\n单元格总数: {summary['cell_count']}   "
        f"平均置信度: {summary['mean_confidence']}   "
        f"低置信(<0.85): {summary['low_confidence_cells']}"
    )
    print(f"详细输出目录: {args.out}/")
    print(
        "\n人工核验: 打开 page*_table*.txt 对照 page*.png,逐表检查\n"
        "  1) 应有的表格是否都识别到(命中率)\n"
        "  2) 行列结构是否正确(有无错位/漏行)\n"
        "  3) 价格数字是否识别正确(关键指标)\n"
        "验证通过 → 进入 contract-price-analysis v2 Phase 1。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
