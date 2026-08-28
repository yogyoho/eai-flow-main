#!/usr/bin/env python3
"""traces.json → 「摘要行 + <details> 计算过程折叠块」Markdown 片段（反馈3 折叠形态）。

为什么需要这个脚本（2026-08-28 R4/R5 页面实测）：
SKILL 步骤4 约定每公式渲染为「摘要行 + <details><summary>计算过程</summary> 折叠块」，
但两轮实测 agent 全部手写成全展开 KaTeX 块，折叠形态从未出现——纯文本约定压不住。
本脚本把折叠块做成确定性输出，agent 只需粘贴，不得手写替代。

前端契约：workspace Markdown 渲染链 = rehype-raw + GitHub-style sanitize（显式保留
<details>/<summary>），折叠在聊天与文档预览中原生可用。

用法:
  python render_calc_blocks.py --traces $WORK/traces.json --output $WORK/calc_blocks.md
  → CALCBLOCKS_READY: N 公式 → path

stdlib only（json/argparse/pathlib），与 snapshot.py 同风格。
"""

import argparse
import json
import sys
from pathlib import Path


def _fmt(v) -> str:
    """float 显示层收敛：6 位小数去尾零（210.38400000000001 → 210.384；16.0 → 16；0.001461 → 0.001461）。
    # ponytail: 定长 6 位小数——本域量级（m³/h / m / L/s）全覆盖；出现 <1e-6 量级参数时再换有效数字法。
    """
    if isinstance(v, float):
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def render(traces: list) -> str:
    blocks = []
    for t in traces:
        name, fid = t.get("name", t.get("id", "?")), t.get("id", "?")
        result, unit = _fmt(t.get("result", "?")), t.get("unit", "")
        lines = [
            f"**{name}（{fid}）= {result}{(' ' + unit) if unit else ''}**",
            "",
            "<details>",
            "<summary>计算过程：公式来源 · 取值依据 · 代入分步</summary>",
            "",
            f"**公式**：`{fid} = {t.get('expression', '?')}`　**来源**：{t.get('source', '—')}",
            "",
        ]
        inputs = t.get("inputs") or []
        if inputs:
            lines += [
                "**取值依据**：",
                "",
                "| 参数 | 数值 | 单位 | 来源 | 待核实 |",
                "|---|---|---|---|---|",
            ]
            for i in inputs:
                flag = "✅ 待核实" if i.get("needs_verification") else "—"
                lines.append(
                    f"| {i.get('name', '?')} | {_fmt(i.get('value', '?'))} | {i.get('unit', '—')} | {i.get('source', '—')} | {flag} |"
                )
            lines.append("")
        sub = t.get("substituted", "?")
        lines += [
            f"**代入分步**：`{fid} = {t.get('expression', '?')} = {sub} = {result}{(' ' + unit) if unit else ''}`",
            "",
            "</details>",
            "",
        ]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def main() -> int:
    p = argparse.ArgumentParser(description="traces.json → 计算过程折叠块片段（反馈3）")
    p.add_argument("--traces", required=True, help="formula_runner.py trace 输出的 traces.json 路径")
    p.add_argument("--output", required=True, help="Markdown 片段输出路径（如 $WORK/calc_blocks.md）")
    args = p.parse_args()

    data = json.loads(Path(args.traces).read_text(encoding="utf-8"))
    traces = data.get("traces", data if isinstance(data, list) else [])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(traces), encoding="utf-8")
    print(f"CALCBLOCKS_READY: {len(traces)} 公式 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
