#!/usr/bin/env python3
"""geological-report v2 — build_output.py：单次原子组装（步骤6）。

组装序：前置部分（外封面/签署页/目录/附图附表目录——表单直出零 LLM，页码列留空 D11）
→ ch1..ch9（wave1 产物）→ ch10（wave2 投影章）→ 合规性附录（consistency_check 渲染）。

注入协议（D5/1A）：
  {{SLOT:key}}  → formula_state.values[key].display（数字永不经过 LLM；未知 key=FAIL）
  {{TABLE:fam}} → data/ 表单族渲染为 markdown 表（数组=行表，标量=键值表，CSV=行表）
原子写：tmp + os.replace（bid-proposal 先例）；内容不变跳过写盘保 mtime（SC-4 字节不变）；
全文无时间戳（幂等）。

退出码：0 成功 / 1 未知槽位 key、缺失章节文件、数据缺参、formula_state 数值槽缺 source（手改特征，bug-2223）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1
SLOT_RE = re.compile(r"\{\{SLOT:([^}]+)\}\}")
TABLE_RE = re.compile(r"\{\{TABLE:([^}]+)\}\}")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── 前置部分（表单直出）────────────────────────────────────────────────────

def render_front_matter(stage: dict, data_dir: Path) -> str:
    fm = stage.get("front_matter", {})
    proj = json.loads((data_dir / stage["forms"]["project"]["file"]).read_text(encoding="utf-8")) if (data_dir / stage["forms"]["project"]["file"]).exists() else {}
    ten = json.loads((data_dir / stage["forms"]["tenement"]["file"]).read_text(encoding="utf-8")) if (data_dir / stage["forms"]["tenement"]["file"]).exists() else {}
    sig_src = {**proj, **ten}
    lines: list[str] = []
    lines.append("# 前置部分")
    lines.append("")
    lines.append("## 外封面")
    lines.append("")
    cover_map = {"矿区名": proj.get("project_name", ""),
                 "报告题名（矿种组合+阶段+报告）": (f"{proj.get('commodity', '')}{proj.get('stage', '') or stage.get('stage', '')}勘探报告" if proj.get("commodity") else ""),
                 "编制单位": proj.get("undertaking_unit", ""), "年月": ""}
    for item in fm.get("outer_cover", []):
        lines.append(f"**{item}**：{cover_map.get(item, '') or '　'}")
        lines.append("")
    lines.append("## 签署页")
    lines.append("")
    for label in fm.get("signature_page_fixed_order", []):
        # 签署值可选自 data（如已填）；未填留空线待签
        val = sig_src.get(label) or ""
        lines.append(f"{label}：{val if val else '＿＿＿＿＿＿'}")
        lines.append("")
    lines.append("## 目录")
    lines.append("")
    lines.append("<!-- 页码列留空：Word 排版阶段由引用自动填充（设计决策 D11），Markdown 禁写页码 -->")
    lines.append("")
    for ch_id in sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99):
        ch = stage["chapters"][ch_id]
        lines.append(f"- **{ch.get('title', ch_id)}**")
        for sub in ch.get("toc", []):
            lines.append(f"  - {sub}")
    lines.append("")
    # 附图附表目录（17_figures_tables）
    ft = json.loads((data_dir / stage["forms"]["figures_tables"]["file"]).read_text(encoding="utf-8")) if (data_dir / stage["forms"]["figures_tables"]["file"]).exists() else {}
    lines.append("## 附图附表目录")
    lines.append("")
    for label, key in (("附图", "figures"), ("附表", "tables")):
        items = ft.get(key) or []
        lines.append(f"### {label}目录（{len(items)}）")
        lines.append("")
        if items:
            lines.append("| 序号 | 编号 | 名称 | 比例尺/说明 |")
            lines.append("|---|---|---|---|")
            for i, it in enumerate(items, 1):
                if isinstance(it, dict):
                    lines.append(f"| {i} | {it.get('no', '')} | {it.get('title', '')} | {it.get('scale', it.get('note', ''))} |")
                else:
                    lines.append(f"| {i} |  | {it} |  |")
        lines.append("")
    return "\n".join(lines)


# ── 表渲染 ──────────────────────────────────────────────────────────────────

def _md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def render_family(fam: str, stage: dict, data_dir: Path) -> str:
    spec = stage["forms"].get(fam)
    if not spec:
        return f"（未知表单族 {fam}）"
    p = data_dir / spec["file"]
    if not p.exists():
        return f"（{fam}: 数据未提供——[待确认] 槽位，缺参不编造）"
    if spec.get("format") == "csv" or "columns" in spec:
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.reader(f)]
        if not rows:
            return "（空表）"
        return _md_table(rows[0], rows[1:])
    doc = json.loads(p.read_text(encoding="utf-8"))
    scalars = {k: v for k, v in doc.items() if not isinstance(v, (list, dict)) and not k.startswith("_")}
    parts = []
    if scalars:
        parts.append(_md_table(["字段", "值"], [[k, str(v)] for k, v in scalars.items()]))
    for k, v in doc.items():
        if isinstance(v, list) and v and not k.startswith("_"):
            cols = list(v[0].keys()) if isinstance(v[0], dict) else [k]
            rows = [[str(x.get(c, "")) for c in cols] if isinstance(x, dict) else [str(x)] for x in v]
            parts.append(f"\n**{k}**（{len(v)} 行）\n\n" + _md_table(cols, rows))
    return "\n\n".join(parts) or "（表单无内容）"


# ── 合规性附录 ──────────────────────────────────────────────────────────────

def render_compliance_appendix(consistency: dict | None, state: dict, state_path: Path) -> str:
    lines = ["## 合规性附录（脚本自动生成）", ""]
    lines.append(f"- 数值冻结层：formula_state.json（SHA-256 `{sha256_file(state_path)}`，槽位 {len(state.get('values', {}))} 个）")
    for a in state.get("anomalies", []):
        lines.append(f"- ⚠ 计算异常必读：{a}")
    lines.append("")
    if consistency:
        s = consistency.get("summary", {})
        lines.append(f"### 一致性校验汇总：pass {s.get('pass', 0)} / warn {s.get('warn', 0)} / manual {s.get('manual', 0)} / fail {s.get('fail', 0)}")
        lines.append("")
        non_pass = [i for i in consistency.get("items", []) if i.get("severity") != "pass"]
        if non_pass:
            lines.append(_md_table(["级别", "合约", "详情"], [[i["severity"], i["contract"], i["detail"]] for i in non_pass]))
        else:
            lines.append("全部合约通过。")
        lines.append("")
    lines.append("<!-- 历史分类编码（332/333、B+C+D、111b/122b）按原样保留，禁现代化改写（红线 P4） -->")
    return "\n".join(lines)


# ── 章节卫生门（bug-2220：前置重复/越权块直通最终文件的根因是章节产物零校验）──

# 脚本保留标题：前置部分与合规附录由 build_output 统一渲染，章节文件出现即重复源
RESERVED_HEADINGS = ("# 前置部分", "## 外封面", "## 签署页", "## 目录", "## 附图附表目录", "## 合规性附录")


def validate_chapter(ch_id: str, text: str) -> None:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first.startswith("## "):
        raise ValueError(f"{ch_id}.md 首行必须是 `## N 章标题`（当前: {first[:40]!r}）——前置/目录等内容不得写入章节文件")
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(RESERVED_HEADINGS):
            raise ValueError(f"{ch_id}.md 含脚本保留标题 {s[:24]!r}——前置部分与合规性附录由 build_output 统一渲染，章节文件禁写（bug-2220 前置重复根因）")


# ── 组装 ────────────────────────────────────────────────────────────────────

def assemble(stage: dict, data_dir: Path, state_dir: Path) -> str:
    state_path = state_dir / "formula_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # ── bug-2223 手改检测门：formula_runner.emit() 给每个槽位写 source 键；手改必丢 ──
    for key, slot in state.get("values", {}).items():
        if not isinstance(slot, dict):
            raise ValueError(f"formula_state 槽位 {key} 不是对象（数值裸写=手改特征，formula_runner 是唯一写者，bug-2223）")
        if isinstance(slot.get("value"), (int, float)) and not isinstance(slot.get("value"), bool) and "source" not in slot:
            raise ValueError(f"formula_state 槽位 {key} 缺 source 键——疑似手改（formula_runner 是唯一写者，数字永不经过 LLM，bug-2223）")
    consistency = None
    cc_path = state_dir / "consistency_check.json"
    if cc_path.exists():
        consistency = json.loads(cc_path.read_text(encoding="utf-8"))
    unknown_keys: set[str] = set()

    def inject(text: str) -> str:
        def slot_sub(m: re.Match) -> str:
            key = m.group(1).strip()
            v = state.get("values", {}).get(key)
            if v is None:
                unknown_keys.add(key)
                return m.group(0)
            return v.get("display", str(v.get("value")))

        def table_sub(m: re.Match) -> str:
            return render_family(m.group(1).strip(), stage, data_dir)

        return TABLE_RE.sub(table_sub, SLOT_RE.sub(slot_sub, text))

    parts = [render_front_matter(stage, data_dir)]
    chap_dir = state_dir / "chapters"
    for ch_id in sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99):
        cf = chap_dir / f"{ch_id}.md"
        if not cf.exists():
            raise FileNotFoundError(f"章节产物缺失: {cf}（波次生成未完成，不静默跳过）")
        raw = cf.read_text(encoding="utf-8")
        validate_chapter(ch_id, raw)
        parts.append(inject(raw).rstrip() + "\n")
    parts.append(render_compliance_appendix(consistency, state, state_path))
    if unknown_keys:
        raise KeyError(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    return "\n\n".join(parts) + "\n"


def atomic_write(path: Path, content: str) -> bool:
    """幂等原子写：内容不变返回 False（保 mtime，SC-4 字节不变断言）。"""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 单次原子组装")
    p.add_argument("--stage", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--state-dir", required=True, help="state/（chapters/ + formula_state.json + consistency_check.json）")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    try:
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        content = assemble(stage, Path(args.data_dir), Path(args.state_dir))
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"[build] 错误: {e}", file=sys.stderr)
        return EXIT_ERROR
    wrote = atomic_write(Path(args.output), content)
    print(f"BUILD_READY: {args.output} bytes={len(content.encode('utf-8'))} {'written' if wrote else 'unchanged(skip, idempotent)'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
