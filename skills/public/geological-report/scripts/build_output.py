#!/usr/bin/env python3
"""geological-report v2 — build_output.py：单次原子组装（步骤6）。

组装序：前置部分（外封面/签署页/目录/附图附表目录——表单直出零 LLM，页码列留空 D11）
→ ch1..ch9（wave1 产物）→ ch10（wave2 投影章）→ 合规性附录（consistency_check 渲染）。

注入协议（D5/1A）：
  {{SLOT:key}}  → formula_state.values[key].display（数字永不经过 LLM；未知 key=FAIL）
  {{TABLE:fam}} → data/ 表单族渲染为 markdown 表（数组=行表，标量=键值表，CSV=行表）
原子写：tmp + os.replace（bid-proposal 先例）；内容不变跳过写盘保 mtime（SC-4 字节不变）；
全文无时间戳（幂等）。成功后写 outputs/delivery_manifest.json（交付清单，确定性幂等——present_files/下载门的放行凭据，bug-2225）。

退出码：0 成功 / 1 未知槽位 key、缺失章节文件、数据缺参、formula_state 数值槽缺 source（手改特征，bug-2223）、
章节深度不足（每节 <3 句或每章 <1000 有效字符，bug-2223；有子节的父节豁免 3 句门——正文在子节，防「补句进子节、
错误却报父节」修不动假象，页面实测线程 03e18e4a）、输出文件名 ≠ {项目名}-{阶段}-地质勘查报告.md 或 outputs/ 含
管线外散文件（交付名门，bug-2223）、toc 节号缺失（目录覆盖门，bug-2225）、章节有效字符 < 样例中位 ×0.6×覆盖缩放
（深度目标门 L2；基准只认技能 references/depth_targets.json——--targets 是调试通道，非技能基准 stderr 高声警告并
记入 delivery_manifest；技能基准缺失才回退地板门）。

失败一次报齐（不 fail-fast 逐章打回——那会把一轮扩写切成 N 轮 build 循环，60 次工具熔断的燃料，页面实测线程 03e18e4a）。
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


# ── 交付名门（bug-2223②：规范文件名唯一来源 = 00_project 表单直读）────────────


def expected_deliverable_name(stage: dict, data_dir: Path) -> str:
    """{项目名}-{阶段}-地质勘查报告.md（00_project 直读；缺参不编造，回退字段名提示）。"""
    spec = stage.get("forms", {}).get("project", {})
    p = data_dir / spec["file"]
    proj = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    name = proj.get("project_name") or "未命名项目"
    st = proj.get("stage") or stage.get("stage", "")
    return f"{name}-{st}-地质勘查报告.md"


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
    cover_map = {
        "矿区名": proj.get("project_name", ""),
        "报告题名（矿种组合+阶段+报告）": (f"{proj.get('commodity', '')}{proj.get('stage', '') or stage.get('stage', '')}报告" if proj.get("commodity") else ""),
        "编制单位": proj.get("undertaking_unit", ""),
        "年月": "",
    }
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


# ── 深度门（bug-2223：E2E 实测 ch3 每节 ~41 字符——骨架覆盖了、叙述没写）──
SENT_RE = re.compile(r"[。；？！]")


def effective_chars(text: str) -> int:
    """有效字符数：排除空行/标题行/表格行，行内剔除空白与 |\\-*#:{} 装饰符。"""
    return sum(len(re.sub(r"[\s\|\-*#:{}]", "", line)) for line in text.splitlines() if line.strip() and not line.strip().startswith("|") and not line.strip().startswith("#"))


def validate_depth(ch_id: str, text: str) -> None:
    """每个标题块（## / ###）正文 ≥3 句（表格行不计句、不豁免；有子节的父节豁免——父节块在首个 ### 处截断，正文在子节）；全章有效字符 ≥1000。"""
    blocks: list[tuple[str, list[str]]] = []
    cur_title, cur_lines = "", []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("## ") or s.startswith("### "):
            blocks.append((cur_title, cur_lines))
            cur_title, cur_lines = s, []
        else:
            cur_lines.append(ln)
    blocks.append((cur_title, cur_lines))
    thin = []
    for i, (title, lns) in enumerate(blocks):
        if title == "" and not any(ln.strip() for ln in lns):
            continue  # 首块无标题无内容（章文件以 ## 开头）
        if title.startswith("## ") and i + 1 < len(blocks) and blocks[i + 1][0].startswith("### "):
            continue  # 父节豁免：正文在子节（页面实测线程 03e18e4a「## 5=2句」结构陷阱——往子节补句永远修不掉报在父节的错）
        sents = sum(len(SENT_RE.findall(ln)) for ln in lns if ln.strip() and not ln.strip().startswith("|"))
        if sents < 3:
            thin.append(f"{title or '(章首段)'}={sents}句")
    if thin:
        raise ValueError(f"{ch_id}.md 深度门 FAIL（每节 ≥3 句——句子写进该节自己的正文、下一级子标题之前；表格行不计句；有子节的父节不适用本门）瘦块: {'; '.join(thin)}；参照 references/samples/exploration/{ch_id}_sample.md 范文补写")
    eff = effective_chars(text)
    if eff < 1000:
        raise ValueError(f"{ch_id}.md 有效字符 {eff} <1000——章节单薄（bug-2223），参照 references/samples/exploration/{ch_id}_sample.md 范文扩写")


# ── 目录覆盖门（bug-2225：E2E 实测 toc 覆盖仅 54.7%——bug-2223 遗留项收口）────

NUM_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")
HEADING_NO_RE = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)+)")


def validate_toc(ch_id: str, text: str, toc: list[str]) -> dict:
    """stage toc 全部节号（复合条目拆出的子节号也算）必须出现在章节 ##/###/#### 标题。

    num_re 与 backend/tests/test_geological_report_v2_scripts.py::TestStageSections 同源。
    返回 {"toc_entries": 节号数, "toc_covered": 已落标题数}（供 delivery_manifest.json）。
    """
    toc_nos: set[str] = set()
    for sub in toc or []:
        toc_nos.update(NUM_RE.findall(sub))
    heading_nos = {m.group(1) for ln in text.splitlines() if (m := HEADING_NO_RE.match(ln.strip()))}
    missing = sorted(toc_nos - heading_nos)
    if missing:
        raise ValueError(f"{ch_id}.md 目录覆盖门 FAIL：toc 节号未落标题 {missing}（骨架全覆盖——动笔前读 STAGE 该章 toc 逐节展开，复合条目子节号须 #### 标题，禁删节/并节，bug-2221/2225）")
    return {"toc_entries": len(toc_nos), "toc_covered": len(toc_nos & heading_nos)}


# ── L2 深度目标门（spec 2026-08-25 §4：eff ≥ 样例 median × coefficient × 覆盖缩放）──


def coverage_scale(text: str, targets: dict) -> float:
    """覆盖缩放：缺数信号越多目标越低，下限 scale_floor（缺数章防误拦）。"""
    signals = text.count("[待确认]") + targets.get("missing_table_weight", 8) * text.count("数据未提供")
    return max(targets.get("scale_floor", 0.25), 1 - targets.get("per_signal_penalty", 0.05) * signals)


def validate_depth_target(ch_id: str, text: str, targets: dict) -> None:
    """L2 深度目标门：inject 后文本 eff ≥ 样例 median × coefficient × 覆盖缩放。"""
    ch = targets.get("per_chapter", {}).get(ch_id)
    if not ch:
        return  # targets 未覆盖该章 → 不拦（样例库不全时不误伤）
    coeff = targets.get("coefficient", 0.6)
    scale = coverage_scale(text, targets)
    target_eff = ch.get("median_eff", 0) * coeff * scale
    eff = effective_chars(text)
    if eff < target_eff:
        raise ValueError(
            f"{ch_id}.md 深度目标门 FAIL：eff {eff} < 目标 {target_eff:.0f}"
            f"（样例 median {ch.get('median_eff')} × {coeff} × 覆盖缩放 {scale:.2f}）"
            f"——逐要素成段扩写（缺数写 [待确认] 不砍段，覆盖率不足时门自动放宽）；"
            f"表后五步解读（陈述→规律识别→成因解释→规范对比→勘查意义）；"
            f"范式参照 references/samples/exploration/{ch_id}_sample.md"
        )


def load_targets(path: Path) -> dict | None:
    """装载 depth_targets.json；缺失/损坏 → stderr 提示后退回地板门（不阻断，spec §8）。"""
    if not path.exists():
        print(f"[build] depth_targets 不存在（{path}）——退回地板门（L0 深度门继续生效）", file=sys.stderr)
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc.get("per_chapter"), dict):
            raise ValueError("per_chapter 缺失或非对象")
        return doc
    except (json.JSONDecodeError, ValueError, AttributeError, OSError) as e:
        print(f"[build] depth_targets 损坏（{path}: {e}）——退回地板门（L0 深度门继续生效）", file=sys.stderr)
        return None


CANONICAL_TARGETS = Path(__file__).resolve().parent.parent / "references" / "depth_targets.json"


def resolve_targets(args_targets: str | None, stage_path: Path) -> tuple[dict | None, Path]:
    """--targets 显式路径优先（调试通道：非技能基准 stderr 高声警告 + 记入 delivery_manifest）；缺省沿 stage 文件向上三级探测，探测不中兜底技能自身基准。返回 (targets, 来源路径)。

    页面实测线程 03e18e4a 教训：agent 伪造 coefficient=0.01 的 depth_targets.json 显式传入，L2 目标全变 0——非技能基准必须醒目可见且留痕，不可静默生效。
    """
    if args_targets:
        p = Path(args_targets)
        if p.exists() and p.resolve() != CANONICAL_TARGETS:
            print(f"[build] 警告: --targets 调试基准 {p}（sha256 {sha256_file(p)[:12]}…）≠ 技能基准 references/depth_targets.json——正式交付绝不传 --targets 换基准绕深度门；本次基准来源已记入 delivery_manifest.json", file=sys.stderr)
        return load_targets(p), p
    for anc in (stage_path.parent, stage_path.parent.parent, stage_path.parent.parent.parent):
        cand = anc / "depth_targets.json"
        if cand.exists():
            return load_targets(cand), cand
    print(f"[build] stage 附近未探测到 depth_targets.json——兜底技能自身基准 {CANONICAL_TARGETS}", file=sys.stderr)
    return load_targets(CANONICAL_TARGETS), CANONICAL_TARGETS


# ── 组装 ────────────────────────────────────────────────────────────────────


def load_state_and_check(state_dir: Path) -> tuple[dict, dict | None]:
    """formula_state 装载 + bug-2223 手改检测门 + consistency 装载（assemble 与单章门共用）。"""
    state_path = state_dir / "formula_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # ── bug-2223 手改检测门：formula_runner.emit() 给每个槽位写 source 键；手改必丢 ──
    for key, slot in state.get("values", {}).items():
        if not isinstance(slot, dict):
            raise ValueError(f"formula_state 槽位 {key} 不是对象（数值裸写=手改特征，formula_runner 是唯一写者，bug-2223）")
        if isinstance(slot.get("value"), (int, float)) and not isinstance(slot.get("value"), bool) and "source" not in slot:
            raise ValueError(f"formula_state 槽位 {key} 缺 source 键——疑似手改（formula_runner 是唯一写者，数字永不经过 LLM，bug-2223）。改数请走 ingest.py forms → formula_runner execute，勿直接编辑 formula_state.json")
    consistency = None
    cc_path = state_dir / "consistency_check.json"
    if cc_path.exists():
        consistency = json.loads(cc_path.read_text(encoding="utf-8"))
    return state, consistency


def make_inject(stage: dict, data_dir: Path, state: dict, unknown_keys: set[str]):
    """{{SLOT:key}}/{{TABLE:fam}} 注入闭包工厂（assemble 与单章门共用；unknown_keys 就地累积）。"""

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

    return inject


def assemble(stage: dict, data_dir: Path, state_dir: Path, targets: dict | None = None, skip_l2: set[str] | None = None, partial: dict | None = None) -> tuple[str, dict[str, dict]]:
    if targets is None:
        # 防绕：直调 assemble（targets=None）也吃技能真基准——页面实测线程 03e18e4a 直调跳过 L2 ~10 次
        targets = load_targets(CANONICAL_TARGETS)
    state_path = state_dir / "formula_state.json"
    state, consistency = load_state_and_check(state_dir)  # 重构：手改检测提取
    unknown_keys: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys)  # 重构：注入闭包提取
    toc_stats: dict[str, dict] = {}

    parts = [render_front_matter(stage, data_dir)]
    chap_dir = state_dir / "chapters"
    # 一次报齐：全部章节全部门跑完汇总（页面实测线程 03e18e4a——fail-fast 逐章打回把一轮扩写切成 N 轮 build 循环，60 次工具熔断的燃料）
    errors: list[str] = []
    for ch_id in sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99):
        cf = chap_dir / f"{ch_id}.md"
        if not cf.exists():
            errors.append(f"章节产物缺失: {cf}（波次生成未完成，不静默跳过）")
            continue
        raw = cf.read_text(encoding="utf-8")
        try:
            # 五步门序列与 run_chapter_gate 须同步改（新增校验两处同加）
            validate_chapter(ch_id, raw)
            validate_depth(ch_id, raw)
            toc_stats[ch_id] = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
            injected = inject(raw).rstrip() + "\n"
            if targets is not None and not (skip_l2 and ch_id in skip_l2):  # skip_l2：--allow-partial 批准集（Task 3）
                validate_depth_target(ch_id, injected, targets)
        except ValueError as e:
            errors.append(str(e))
            continue
        parts.append(injected)
    parts.append(render_compliance_appendix(consistency, state, state_path))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if errors:
        raise ValueError(f"{len(errors)} 项未过门（一次报齐，逐项修完再重跑——勿修一章跑一轮）:\n" + "\n".join(errors))
    return "\n\n".join(parts) + "\n", toc_stats


def run_chapter_gate(stage: dict, data_dir: Path, state_dir: Path, ch_id: str, targets: dict | None) -> None:
    """--chapter 单章全门（spec §5.2①）：validate_chapter + validate_depth + validate_toc + inject
    + validate_depth_target，一次报齐该章全部问题（同 assemble 章内块格式）。

    不产交付物（交付名门/散文件门不适用）、不写 progress.json（唯一写者=progress.py）。
    PASS 打 CHAPTER_GATE_PASS 行（eff/目标/覆盖缩放——mark VERIFIED 与重派决策的数据面）。
    """
    if targets is None:
        # 防绕：直调 run_chapter_gate(targets=None) 同 assemble 强制技能真基准（03e18e4a 教训）
        targets = load_targets(CANONICAL_TARGETS)
    order = sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)
    if ch_id not in stage.get("chapters", {}):
        raise ValueError(f"未知章节 {ch_id}（stage 在册: {order}）")
    state, _consistency = load_state_and_check(state_dir)
    unknown_keys: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys)
    cf = state_dir / "chapters" / f"{ch_id}.md"
    if not cf.exists():
        raise ValueError(f"章节产物缺失: {cf}（子代理未完成或未派发——先按 progress.py next 指引派发/重派该章）")
    raw = cf.read_text(encoding="utf-8")
    errors: list[str] = []
    toc: dict = {}
    injected = ""
    try:
        # 五步门序列与 assemble 循环体须同步改（新增校验两处同加）
        validate_chapter(ch_id, raw)
        validate_depth(ch_id, raw)
        toc = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
        injected = inject(raw).rstrip() + "\n"
        if targets is not None:
            validate_depth_target(ch_id, injected, targets)
    except ValueError as e:
        errors.append(str(e))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if errors:
        raise ValueError(f"{ch_id} 单章门 FAIL（{len(errors)} 项，一次报齐——补写该章正文后重跑）:\n" + "\n".join(errors))
    ch = (targets or {}).get("per_chapter", {}).get(ch_id)
    if ch:
        scale = coverage_scale(injected, targets)
        t = ch.get("median_eff", 0) * targets.get("coefficient", 0.6) * scale
        print(f"CHAPTER_GATE_PASS: {ch_id} toc {toc['toc_covered']}/{toc['toc_entries']} eff {effective_chars(injected)} ≥ 目标 {t:.0f}（样例 median {ch.get('median_eff')} × {targets.get('coefficient', 0.6)} × 覆盖缩放 {scale:.2f}）")
    else:
        print(f"CHAPTER_GATE_PASS: {ch_id} toc {toc['toc_covered']}/{toc['toc_entries']} eff {effective_chars(injected)}（L2 基准未覆盖该章，地板门通过）")


def atomic_write(path: Path, content: str) -> bool:
    """幂等原子写：内容不变返回 False（保 mtime，SC-4 字节不变断言）。

    bug-2225: 字节精确写（newline="\\n"，bid-proposal atomic_write_text 同款）——
    delivery_manifest 的 sha256/bytes 必须与盘上文件逐字节一致；Windows 文本模式默认
    \\n→\\r\\n 翻译会使凭据 sha 与实文件不符（后续交付门比对即 FAIL）。
    """
    if path.exists() and path.read_bytes() == content.encode("utf-8"):
        return False
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 单次原子组装")
    p.add_argument("--stage", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--state-dir", required=True, help="state/（chapters/ + formula_state.json + consistency_check.json）")
    p.add_argument("--targets", help="depth_targets.json 路径；缺省探测 stage 同目录/../ ../../")
    p.add_argument("--chapter", help="单章门模式：只验证该章（ch_id 如 ch3），不产交付物/不写 progress.json")
    p.add_argument("--allow-partial", action="store_true", help="分级交付：progress.json 已批准的 BLOCKED 章跳过 L2 深度目标门（L0/L1/toc/槽位门仍在场），manifest 留痕")
    p.add_argument("--output", help="交付物输出路径（--chapter 模式不需要）")
    args = p.parse_args()
    if args.chapter and (args.output or args.allow_partial):
        print("[build] --chapter 与 --output/--allow-partial 互斥（单章门不产交付物）", file=sys.stderr)
        return EXIT_ERROR
    if not args.chapter and not args.output:
        print("[build] 需要 --output（或用 --chapter 走单章门）", file=sys.stderr)
        return EXIT_ERROR
    try:
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        targets, targets_src = resolve_targets(args.targets, Path(args.stage))
        if args.chapter:
            run_chapter_gate(stage, Path(args.data_dir), Path(args.state_dir), args.chapter, targets)
            return EXIT_OK
        # ── bug-2223 交付名门：文件名规范 + outputs/ 无管线外散文件 ──
        out_path = Path(args.output)
        expected = expected_deliverable_name(stage, Path(args.data_dir))
        if out_path.name != expected:
            print(f"[build] 交付名门 FAIL: 输出 {out_path.name!r} ≠ 规范名 {expected!r}（{{项目名}}-{{阶段}}-地质勘查报告.md，bug-2220/2223）", file=sys.stderr)
            return EXIT_ERROR
        stray = sorted(p.name for p in out_path.parent.glob("*.md") if p.name != out_path.name)
        if stray:
            print(f"[build] 交付名门 FAIL: outputs/ 存在管线外散文件 {stray}——唯一交付单文件 {expected!r}，散文件移出或删除（bug-2220 交付回路铁律）", file=sys.stderr)
            return EXIT_ERROR
        content, toc_stats = assemble(stage, Path(args.data_dir), Path(args.state_dir), targets=targets)
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"[build] 错误: {e}", file=sys.stderr)
        return EXIT_ERROR
    wrote = atomic_write(out_path, content)
    # ── bug-2225 交付清单：present_files/artifacts/工作区同步三门的放行凭据。
    # 确定性（sort_keys、无时间戳）→ 二连 build 字节不变（幂等不破坏）。
    manifest = {
        "bug": 2225,
        "deliverable": out_path.name,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "bytes": len(content.encode("utf-8")),
        "formula_state_sha256": sha256_file(Path(args.state_dir) / "formula_state.json"),
        "chapters": toc_stats,
        # 基准溯源：正式交付只认技能 references/depth_targets.json；他处基准=调试/绕门，事后可查（线程 03e18e4a 伪造基准教训）
        "targets": {"path": str(targets_src), "sha256": sha256_file(targets_src) if targets_src.exists() else None},
    }
    m_path = out_path.parent / "delivery_manifest.json"
    m_wrote = atomic_write(m_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"BUILD_READY: {args.output} bytes={len(content.encode('utf-8'))} {'written' if wrote else 'unchanged(skip, idempotent)'}")
    print(f"MANIFEST_READY: {m_path} {'written' if m_wrote else 'unchanged(skip, idempotent)'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
