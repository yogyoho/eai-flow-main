#!/usr/bin/env python3
"""traces.json → 「$$公式+结果$$ 可见 + <details>计算过程</details> 折叠」Markdown（反馈3 用户样例格式）。

目标形态（2026-08-29 用户定案 A：注入块**不带标题**——小节标题由报告自己的 TOC 承担，
如 `#### 5.1.1 蒸发水量计算`；旧版 `### [9.1.1]` 标题印的是公式登记表 section 号，
与报告 TOC 双编号/双标题（R10 实测 5.1.1 与 [6.1.1] 并排），已去除）：

    #### 9.1.1 旁滤处理水量        ← 报告自己的小节标题（write_file 写，编号跟随报告 TOC）
    <!-- CALC:Qsf -->              ← 按公式占位符（write_file 写，id 取自 traces.json）

    （inject 后占位符处变为：）
    $$Q_{sf} = Q \\times sf\\_ratio = 20000 \\times 0.05 = 1000\\ \\text{m}^3/\\text{h}$$

    <details><summary>计算过程</summary>

    - 公式：$Q_{sf} = Q \\times sf\\_ratio$
    - 取值：Q = 20000 m³/h；旁滤比 sf_ratio = 5%【待核实】
    - 代入：$20000 \\times 0.05$
    - 结果：**1000 m³/h**

    </details>

为什么脚本化（R4/R5/R6 三轮实测）：agent 手写从不产 <details>（纯文本约定压不住）；
R6 实测即便生成片段也不逐字粘贴（6K 字符复制不可靠）→ 占位符 + inject 原地注入。

为什么按公式占位（2026-08-29 R10 实测）：单一 <!-- CALC_BLOCKS --> 会把全部块顺序堆到
一处（R10 报告 12 块全挤在 5.1.1 小节下）；`<!-- CALC:公式id -->` 让每块落在报告 TOC
对应小节标题下。旧式单一占位符仍兼容（全块顺序注入），不再推荐。

前端契约：workspace Markdown = rehype-raw + GitHub sanitize（显式保留 details/summary 与 KaTeX）。

用法:
  python render_calc_blocks.py --traces $WORK/traces.json --output $WORK/calc_blocks.md
  python render_calc_blocks.py inject --traces $WORK/traces.json --report $OUT/报告.md
  （报告须含每公式一个 <!-- CALC:id -->（推荐）或旧式 <!-- CALC_BLOCKS -->；
   未知 id / 公式缺标记 / 重复标记 → CALC_INJECT_ERROR 退出 1 不静默）

stdlib only，与 snapshot.py 同风格。
"""

import argparse
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- CALC_BLOCKS -->"
# 按公式占位符（2026-08-29 用户定案 A）：`<!-- CALC:Qe -->` 每公式一个，块落在报告 TOC
# 对应小节标题下；单一 MARKER 会把全部块堆到一处（R10 实测），仅作兼容保留。
PER_FORMULA_RE = re.compile(r"<!-- CALC:([A-Za-z_][A-Za-z0-9_]*) -->")
# 注入签名：snapshot.py save 据此校验"公式块确实由脚本注入"（R8 实测 agent 手写 12 块
# 且跳过 inject——文本铁律压不住 flash 模型，快照门禁是 agent 必经的强制点）。
# v2（R9）：签名携带注入块数——门禁比对「签名数之和 == 报告 <details> 总数」，
# 抓"注入了但又在别处手写折叠块"的混合违约（R9 实测 ch6-8 手写 8 块且单位抄错 0.202 h）。
# v2.1（用户定案 A）：每块尾各带一条 count=1 签名——按公式注入/整组注入两路径下
# 「求和 == <details> 数」恒成立，门禁逻辑零改动。
SIGNATURE_PREFIX = "<!-- CALC_BLOCKS_INJECTED:v2 count="


def signature_line(n: int) -> str:
    return f"{SIGNATURE_PREFIX}{n} -->"

# 输出符号（公式左侧）pretty 化映射；traces 带 symbol 字段时优先用 trace 值（v2 公式库全量带 symbol），
# 旧 traces 回退本映射，仍未命中再按下划线转下标
SYMBOL = {
    "Qe": "Q_{e}", "Qw": "Q_{w}", "Qb": "Q_{b}", "Qm": "Q_{m}",
    "V_pool": "V_{pool}", "V_system": "V_{system}", "V_ratio_check": "V_{ratio}",
    "pump_foundation_L": "L_{pump}", "Qsf": "Q_{sf}",
    "filter_count": "n", "backwash_flow": "q_{bw}", "backwash_volume": "V_{bw}",
}

# latex 单位映射（$$ 内 \text 包裹）；文本态单位（取值/结果行）用 unicode 上标
UNIT_LATEX = {
    "m3/h": r"\text{m}^3/\text{h}", "m3": r"\text{m}^3", "m2": r"\text{m}^2",
    "kg/m3": r"\text{kg/m}^3", "L/s": r"\text{L/s}", "L/s·m2": r"\text{L/(s·m}^2\text{)}",
    "L/(s·m2)": r"\text{L/(s·m}^2\text{)}",
    "m": r"\text{m}", "mm": r"\text{mm}", "kg": r"\text{kg}", "台": r"\text{台}",
    "℃": r"\text{℃}", "1/℃": r"\text{1/℃}", "min": r"\text{min}", "h": r"\text{h}",
    "—": "", "": "",
}
UNIT_TEXT = {"m3/h": "m³/h", "m3": "m³", "m2": "m²", "kg/m3": "kg/m³", "L/s·m2": "L/(s·m²)"}


def _sym_of(t: dict) -> str:
    """公式左侧符号：trace.symbol 优先 → SYMBOL 映射 → id 下划线转下标（pipe_d_makeup → pipe_{d}…）."""
    fid = t.get("id", "?")
    return t.get("symbol") or SYMBOL.get(fid) or re.sub(r"[A-Za-z_]+_[A-Za-z_]+", _subscript, fid)


def _dual_unit(res: str, unit: str) -> str:
    """L/s 瞬时流量补 m³/h 换算（样例形态：84.75L/s=305.1m3/h）；其余单位原样。"""
    if unit == "L/s":
        try:
            return f"（= {_fmt(float(res) * 3.6)} m³/h）"
        except (TypeError, ValueError):
            return ""
    return ""


def _citation_line(citation: list) -> str:
    """依据行：GB/T 50746-2012 第3.3.3条：text（clause 为空只写规范号——绝不编造条号）；无 citation 不出该行。"""
    parts = []
    for c in citation or []:
        code = str(c.get("code", "")).strip()
        clause = str(c.get("clause", "")).strip()
        text = str(c.get("text", "")).strip()
        seg = f"{code} 第{clause}条" if clause else code
        if text:
            seg += f"：{text}"
        if seg:
            parts.append(seg)
    return "；".join(parts)


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


def _param_sym(i: dict) -> str:
    """取值行参数符号：symbol 优先（缺失回退代码键名，兼容旧 traces）；
    仅 symbol 自带 latex 字符（\\ _ { ^）时用 $…$ 包裹——回退的代码键名保持字面（KaTeX 会吃裸下划线）。"""
    s = i.get("symbol") or i.get("name", "?")
    if i.get("symbol") and any(ch in s for ch in "\\_{^"):
        return f"${s}$"
    return s


def _values_line(inputs: list) -> str:
    """取值行：Q = 16000 m³/h（循环水设计水量）；K_{ZF} = 0.001461 1/℃【待核实】。
    symbol 存在则替代代码键名（样例'式中'图例形态），description 存在则补中文括注；
    两者皆缺时输出与旧版逐字节一致（兼容既有快照门禁）。公式输出参数标注来源公式。"""
    parts = []
    for i in inputs:
        seg = f"{_param_sym(i)} = {_fmt(i.get('value', '?'))}"
        u = _unit_text(i.get("unit", ""))
        if u:
            seg += f" {u}"
        desc = str(i.get("description") or "")
        if desc and not str(i.get("source", "")).startswith("formula:"):
            seg += f"（{desc}）"
        src = str(i.get("source", ""))
        if src.startswith("formula:"):
            seg += f"（由 [{src.split(':')[1].split('.')[0]}] 求得）"
        if i.get("needs_verification"):
            seg += "【待核实】"
        parts.append(seg)
    return "；".join(parts)


def block(t: dict) -> str:
    """单个公式块：$$公式=代入=结果$$ + <details>过程</details> + count=1 签名。
    不带标题（用户定案 A）——小节标题由报告自己的 TOC 承担，块紧跟占位符处。
    v2 增量：式中图例（symbol+description 取值行）、依据行（citation）、L/s 双单位（结果行）。"""
    sym = _sym_of(t)
    rhs = _to_latex(t.get("expression", "?"))
    sub = _to_latex(t.get("substituted", "?"))
    unit = t.get("unit", "")
    res, ul, ut = _fmt(t.get("result", "?")), _unit_latex(unit), _unit_text(unit)
    eq_tail = (rf" = {res}" + (rf"\ {ul}" if ul else ""))
    lines = [
        f"$${sym} = {rhs} = {sub}{eq_tail}$$",
        "",
        "<details><summary>计算过程</summary>",
        "",
        f"- 公式：${sym} = {rhs}$",
    ]
    cit = _citation_line(t.get("citation"))
    if cit:
        lines.append(f"- 依据：{cit}")
    lines += [
        f"- 取值：{_values_line(t.get('inputs') or [])}",
        f"- 代入：${sub}$",
        f"- 结果：**{res}{(' ' + ut) if ut else ''}{_dual_unit(res, unit)}**",
        "",
        "</details>",
        "",
        signature_line(1),
    ]
    return "\n".join(lines)


def render(traces: list) -> str:
    return "\n".join(block(t) for t in traces)


def cmd_inject(args: argparse.Namespace) -> int:
    """把报告中的占位符原地替换为公式块（粘贴脚本化——LLM 逐字长拷贝不可靠）。
    首选按公式占位符 `<!-- CALC:id -->`（每公式恰好一个，未知/缺失/重复皆打回）；
    兼容旧式单一 `<!-- CALC_BLOCKS -->`（全部块顺序注入到该处）。"""
    report = Path(args.report)
    text = report.read_text(encoding="utf-8")
    if SIGNATURE_PREFIX in text:
        # 幂等：已注入过（agent 重试 / 二次 inject 不炸、不重复注入）
        print(f"CALC_INJECT_SKIP: 公式块已注入（含 {SIGNATURE_PREFIX}N -->），跳过")
        return 0
    data = json.loads(Path(args.traces).read_text(encoding="utf-8"))
    traces = data.get("traces", data if isinstance(data, list) else [])
    by_id = {t.get("id"): t for t in traces}

    ids = [m.group(1) for m in PER_FORMULA_RE.finditer(text)]
    if ids:
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            print(f"CALC_INJECT_ERROR: 占位符引用未知公式 id {unknown}（合法 id: {sorted(by_id)}）——核对 traces.json")
            return 1
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            print(f"CALC_INJECT_ERROR: 公式 {dup} 的占位符出现多次——每公式恰好一个 <!-- CALC:id -->")
            return 1
        missing = [t.get("id") for t in traces if ids.count(t.get("id")) == 0]
        if missing:
            print(f"CALC_INJECT_ERROR: 公式 {missing} 缺占位符——每个公式的计算块小节都要有 <!-- CALC:id -->，缺块会被门禁数量核对漏检")
            return 1
        new = text
        for i in ids:
            new = new.replace(f"<!-- CALC:{i} -->", block(by_id[i]))
        report.write_text(new, encoding="utf-8")
        print(f"CALC_INJECT_READY: {len(ids)} 公式折叠块已按占位符注入 {report}")
        return 0

    if MARKER not in text:
        print(f"CALC_INJECT_ERROR: 报告未含占位符 <!-- CALC:公式id -->（推荐，每公式一个）或旧式 {MARKER}")
        return 1
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
