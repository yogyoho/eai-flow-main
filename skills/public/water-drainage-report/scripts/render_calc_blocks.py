#!/usr/bin/env python3
"""traces.json → 「$$公式+结果$$ 可见 + <details>计算过程</details> 折叠」Markdown（反馈3 用户样例格式）。

目标形态（2026-08-28 用户样例，线程 a6aeb9b2 退回后重做）：

    ### [9.1.1] 旁滤处理水量

    $$Q_{sf} = Q \\times sf\\_ratio = 20000 \\times 0.05 = 1000\\ \\text{m}^3/\\text{h}$$

    <details><summary>计算过程</summary>

    - 公式：$Q_{sf} = Q \\times sf\\_ratio$
    - 取值：Q = 20000 m³/h；旁滤比 sf_ratio = 5%【待核实】
    - 代入：$20000 \\times 0.05$
    - 结果：**1000 m³/h**

    </details>

为什么脚本化（R4/R5/R6 三轮实测）：agent 手写从不产 <details>（纯文本约定压不住）；
R6 实测即便生成片段也不逐字粘贴（6K 字符复制不可靠）→ 占位符 + inject 原地注入。

前端契约：workspace Markdown = rehype-raw + GitHub sanitize（显式保留 details/summary 与 KaTeX）。

用法:
  python render_calc_blocks.py --traces $WORK/traces.json --output $WORK/calc_blocks.md
  python render_calc_blocks.py inject --traces $WORK/traces.json --report $OUT/报告.md
  （报告须含占位符 <!-- CALC_BLOCKS -->；缺失时 CALC_INJECT_ERROR 退出 1 不静默）

stdlib only，与 snapshot.py 同风格。
"""

import argparse
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- CALC_BLOCKS -->"
# 注入签名：snapshot.py save 据此校验"公式块确实由脚本注入"（R8 实测 agent 手写 12 块
# 且跳过 inject——文本铁律压不住 flash 模型，快照门禁是 agent 必经的强制点）。
# v2（R9）：签名携带注入块数——门禁比对「签名数之和 == 报告 <details> 总数」，
# 抓"注入了但又在别处手写折叠块"的混合违约（R9 实测 ch6-8 手写 8 块且单位抄错 0.202 h）。
SIGNATURE_PREFIX = "<!-- CALC_BLOCKS_INJECTED:v2 count="


def signature_line(n: int) -> str:
    return f"{SIGNATURE_PREFIX}{n} -->"

# 输出符号（公式左侧）pretty 化映射；未列出的 id 按下划线转下标处理
SYMBOL = {
    "Qe": "Q_{e}", "Qw": "Q_{w}", "Qb": "Q_{b}", "Qm": "Q_{m}",
    "V_pool": "V_{pool}", "V_system": "V_{system}", "V_ratio_check": "V_{ratio}",
    "pump_foundation_L": "L_{pump}", "Qsf": "Q_{sf}",
    "filter_count": "n", "backwash_flow": "q_{bw}", "backwash_volume": "V_{bw}",
}

# latex 单位映射（$$ 内 \text 包裹）；文本态单位（取值/结果行）用 unicode 上标
UNIT_LATEX = {
    "m3/h": r"\text{m}^3/\text{h}", "m3": r"\text{m}^3", "m2": r"\text{m}^2",
    "L/s": r"\text{L/s}", "L/(s·m2)": r"\text{L/(s·m}^2\text{)}",
    "m": r"\text{m}", "台": r"\text{台}", "℃": r"\text{℃}", "1/℃": r"\text{1/℃}",
    "—": "", "": "",
}
UNIT_TEXT = {"m3/h": "m³/h", "m3": "m³", "m2": "m²"}


def _fmt(v) -> str:
    """float 显示层收敛：6 位小数去尾零（210.38400000000001 → 210.384；18.0 → 18；0.001461 保真）。
    # ponytail: 定长 6 位小数——本域量级（m³/h / m / L/s）全覆盖；出现 <1e-6 量级参数时再换有效数字法。
    """
    if isinstance(v, float):
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def _fix_nums(s: str) -> str:
    """字符串内嵌数字收敛： substituted 里 210.38400000000001 → 210.384。"""
    return re.sub(r"\d+\.\d+", lambda m: _fmt(float(m.group())), s)


def _subscript(m: "re.Match") -> str:
    r"""单下划线标识符转下标（sf_ratio → sf_{ratio}）；多下划线保持字面转义（filter\_unit\_capacity）。"""
    tok = m.group(0)
    if tok.count("_") == 1:
        head, tail = tok.split("_")
        return f"{head}_{{{tail}}}"
    return tok.replace("_", r"\_")


def _to_latex(expr: str) -> str:
    """plain 表达式 → latex：* → \\times；math.ceil(a / b) → \\lceil \\frac{a}{b} \\rceil；
    math.ceil(...) → \\lceil ... \\rceil；delta_t → \\Delta t；下划线标识符转下标。"""
    s = _fix_nums(expr.strip())
    s = s.replace("delta_t", r"\Delta t")
    s = re.sub(r"math\.ceil\(([^()/]+) / ([^()/]+)\)", r"\\lceil \\frac{\1}{\2} \\rceil", s)
    s = re.sub(r"math\.ceil\(([^()]*)\)", r"\\lceil \1 \\rceil", s)
    s = s.replace(" * ", " \\times ").replace("*", " \\times ")
    s = re.sub(r"[A-Za-z_]+_[A-Za-z_]+", _subscript, s)
    return s


def _unit_latex(unit: str) -> str:
    return UNIT_LATEX.get(unit, rf"\text{{{unit}}}" if unit else "")


def _unit_text(unit: str) -> str:
    return UNIT_TEXT.get(unit, "" if unit == "—" else unit)


def _values_line(inputs: list) -> str:
    """取值行：Q = 16000 m³/h；旁滤比 sf_ratio = 0.05【待核实】（公式输出参数标注来源公式）。"""
    parts = []
    for i in inputs:
        seg = f"{i.get('name', '?')} = {_fmt(i.get('value', '?'))}"
        u = _unit_text(i.get("unit", ""))
        if u:
            seg += f" {u}"
        src = str(i.get("source", ""))
        if src.startswith("formula:"):
            seg += f"（由 [{src.split(':')[1].split('.')[0]}] 求得）"
        if i.get("needs_verification"):
            seg += "【待核实】"
        parts.append(seg)
    return "；".join(parts)


def render(traces: list) -> str:
    blocks = []
    for t in traces:
        sym = SYMBOL.get(t.get("id", ""), t.get("id", "?").replace("_", "_"))
        rhs = _to_latex(t.get("expression", "?"))
        sub = _to_latex(t.get("substituted", "?"))
        res, ul, ut = _fmt(t.get("result", "?")), _unit_latex(t.get("unit", "")), _unit_text(t.get("unit", ""))
        eq_tail = (rf" = {res}" + (rf"\ {ul}" if ul else ""))
        blocks.append("\n".join([
            f"### [{t.get('section', '?')}] {t.get('name', '?')}",
            "",
            f"$${sym} = {rhs} = {sub}{eq_tail}$$",
            "",
            "<details><summary>计算过程</summary>",
            "",
            f"- 公式：${sym} = {rhs}$",
            f"- 取值：{_values_line(t.get('inputs') or [])}",
            f"- 代入：${sub}$",
            f"- 结果：**{res}{(' ' + ut) if ut else ''}**",
            "",
            "</details>",
            "",
        ]))
    return "\n".join(blocks) + signature_line(len(traces)) + "\n"


def cmd_inject(args: argparse.Namespace) -> int:
    """把报告中的 MARKER 占位符原地替换为公式块（粘贴脚本化——LLM 逐字长拷贝不可靠）。"""
    report = Path(args.report)
    text = report.read_text(encoding="utf-8")
    if MARKER not in text:
        if SIGNATURE_PREFIX in text:
            # 幂等：已注入过（agent 重试 / 二次 inject 不炸、不重复注入）
            print(f"CALC_INJECT_SKIP: 公式块已注入（含 {SIGNATURE_PREFIX}N -->），跳过")
            return 0
        print(f"CALC_INJECT_ERROR: 报告未含占位符 {MARKER}（计算章须以占位符占位，再 inject 注入）")
        return 1
    data = json.loads(Path(args.traces).read_text(encoding="utf-8"))
    traces = data.get("traces", data if isinstance(data, list) else [])
    report.write_text(text.replace(MARKER, render(traces)), encoding="utf-8")
    print(f"CALC_INJECT_READY: {len(traces)} 公式折叠块已注入 {report}")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "inject":
        p = argparse.ArgumentParser(description="报告占位符注入公式折叠块（反馈3）")
        p.add_argument("--traces", required=True)
        p.add_argument("--report", required=True)
        return cmd_inject(p.parse_args(sys.argv[2:]))

    p = argparse.ArgumentParser(description="traces.json → 公式+折叠计算过程块（反馈3 用户样例格式）")
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
