#!/usr/bin/env python3
"""geological-report v2 — build_output.py：单次原子组装（步骤6）。

组装序：前置部分（外封面/签署页/目录/附图附表目录——表单直出零 LLM，页码列留空 D11）
→ ch1..ch9（wave1 产物）→ ch10（wave2 投影章）→ 合规性附录（consistency_check 渲染）。

注入协议（D5/1A）：
  {{SLOT:key}}  → formula_state.values[key].display（数字永不经过 LLM；未知 key=FAIL）
  {{TABLE:fam}} → data/ 表单族渲染为 markdown 表（数组=行表，标量=键值表，CSV=行表）
原子写：tmp + os.replace（bid-proposal 先例）；内容不变跳过写盘保 mtime（SC-4 字节不变）；
全文无时间戳（幂等）。成功后写 outputs/delivery_manifest.json（交付清单，确定性幂等——present_files/下载门的放行凭据，bug-2225）。

注入后残留扫描（槽位标记/模板脚手架词/合约 ID/裸数字数组/XX 占位，bug-3036）、TABLE 未知表单族（bug-3036 旧软兜底
「（未知表单族 …）」静默进终稿——现硬 FAIL）、槽位 display 空/非标量（bug-3036 空 display 静默渲染）、目录覆盖门 v2
双向校验（toc 节号未落标题 + 契约外自创节 + 编号同标题不符，bug-3036）、consistency.py 25 合约门（fail>0 阻断，
报告落盘但 manifest 不写=不可交付；bug-3036 此前在盘零调用）、formula_state 数值槽 source=manual 无 via=ingest 溯源
（bug-3036 根因①LLM 直写特征）。

退出码：0 成功 / 1 未知槽位 key、缺失章节文件、数据缺参、formula_state 数值槽缺 source（手改特征，bug-2223）、
章节深度不足（每节 <3 句或每章 <1000 有效字符，bug-2223；有子节的父节豁免 3 句门——正文在子节，防「补句进子节、
错误却报父节」修不动假象，页面实测线程 03e18e4a）、输出文件名 ≠ {项目名}-{阶段}-地质勘查报告.md 或 outputs/ 含
管线外散文件（交付名门，bug-2223）、toc 节号缺失（目录覆盖门，bug-2225）、章节有效字符 < 样例中位 ×0.6×覆盖缩放
（深度目标门 L2；基准只认技能 references/depth_targets.json——--targets 是调试通道，非技能基准 stderr 高声警告并
记入 delivery_manifest；技能基准缺失才回退地板门；目标含绝对地板 median×absolute_floor——覆盖缩放（[待确认] 越多
目标越低）不可把目标压穿地板，bug-3036「堆占位符把越改越薄洗成 PASS」；逐章深度/缩放/地板全量写入 delivery_manifest）。

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
# N19 畸形 SLOT 修复（T4 页面实测 93 处穿透全门进终稿）：降级写手系统性产出
# 「{{SLOT:key}单位}」错配收形与「{SLOT:key}」单开括号形——SLOT_RE 不匹配 → 不注入
# 也不报 FAIL，静默进交付稿。注入前先归一化为 {{SLOT:key}}（单位等尾缀移到槽外），
# 修复后的键走正常 unknown-key FAIL 门（语义错配照样拦）。
SLOT_DEFORM_CLOSE_RE = re.compile(r"\{\{SLOT:([^{}]+)\}(?!\})([^{}\n]*)\}")
SLOT_DEFORM_OPEN_RE = re.compile(r"(?<!\{)\{SLOT:([^{}]+)\}")  # lookbehind 防 {{SLOT: 被当单括号形


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── 交付名门（bug-2223②：规范文件名唯一来源 = 00_project 表单直读）────────────


def expected_deliverable_name(stage: dict, data_dir: Path) -> str:
    """{项目名}-{阶段}-地质勘查报告.md（00_project 直读；缺参不编造，回退字段名提示）。

    bug-3036 P2：项目名尾缀已含阶段词（「…某铜矿勘探」+ 阶段「勘探」）不再重复拼接——旧逻辑产出
    「勘探-勘探-地质勘查报告」双叠名。
    """
    spec = stage.get("forms", {}).get("project", {})
    p = data_dir / spec["file"]
    proj = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    name = proj.get("project_name") or "未命名项目"
    st = proj.get("stage") or stage.get("stage", "")
    if st and name.endswith(st):
        return f"{name}-地质勘查报告.md"
    return f"{name}-{st}-地质勘查报告.md" if st else f"{name}-地质勘查报告.md"


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


def _dig(doc, segs: list[str]):
    """点号子路径下钻：每步先试剩余全串作扁平点号键（ingest schema 惯例，如 hydro.inflow_analogy），
    再试单段嵌套；都不中返回 None（调用方走「数据未提供」，缺参不编造）。"""
    if not segs:
        return doc
    if isinstance(doc, dict):
        if ".".join(segs) in doc:
            return doc[".".join(segs)]
        if segs[0] in doc:
            return _dig(doc[segs[0]], segs[1:])
    return None


def render_family(fam: str, stage: dict, data_dir: Path) -> str:
    base = fam.split(".", 1)[0]
    spec = stage["forms"].get(base)
    if not spec:
        # bug-3036 P0：旧软兜底返回「（未知表单族 …）」字符串静默进终稿——骨架引用了不存在的表单族
        # 是结构错误，必须硬 FAIL（错误信息带 stage 在册族名，一次修对）。
        raise ValueError(
            f"TABLE 引用未知表单族 {fam!r}（stage 在册: {sorted(stage['forms'])}）"
            "——修章节骨架的 {{TABLE:…}} 引用，或先在 stage forms 登记该族（bug-3036）"
        )
    p = data_dir / spec["file"]
    if not p.exists():
        return f"（{fam}: 数据未提供——[待确认] 槽位，缺参不编造）"
    if spec.get("format") == "csv" or "columns" in spec:
        if "." in fam:
            raise ValueError(f"TABLE {fam!r}: CSV 表单族不支持点号子路径（bug-3036）")
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.reader(f)]
        if not rows:
            return "（空表）"
        return _md_table(rows[0], rows[1:])
    doc = json.loads(p.read_text(encoding="utf-8"))
    # bug-3036：点号子路径寻址——骨架可引用表单内扁平点号键/嵌套结构（如 {{TABLE:block_model.aggregates}}、
    # {{TABLE:hydro_eng_env.hydro.mid_level_drainage}}），子键缺失走「数据未提供」不编造。
    # 未注册别名（{{TABLE:hydro.…}}——正族名是 hydro_eng_env）仍走上方未知表单族硬 FAIL。
    if "." in fam:
        doc = _dig(doc, fam.split(".", 1)[1].split("."))
        if doc is None:
            return f"（{fam}: 数据未提供——[待确认] 槽位，缺参不编造）"
    # bug-3018: 清单族经 `ingest.py file` CSV 摄入落成顶层行数组（bug-3004 已让门1容忍此形状），
    # render_family 未同步 → doc.items() AttributeError 单章门崩溃（ch4 实测）。行数组按
    # 单表渲染，与下方 list 分支同构；不回写 data/（唯一写者=ingest.py）。
    if isinstance(doc, list):
        if not doc:
            return "（空表）"
        cols = list(doc[0].keys()) if isinstance(doc[0], dict) else [fam]
        rows = [[str(x.get(c, "")) for c in cols] if isinstance(x, dict) else [str(x)] for x in doc]
        return _md_table(cols, rows)
    if isinstance(doc, dict):
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
    return str(doc)  # 点号路径命中标量 → 单值直出


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
_TOC_PIECE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*")
_TITLE_NORM_RE = re.compile(r"[\s　\-—–·。，,、;；:：!！?？()（）\[\]【】\"'“”‘’/*／]+")


def _norm_title(s: str) -> str:
    """标题规范化：去空白/标点（全半角）/装饰符后小写——防全半角顿号差异误伤。"""
    return _TITLE_NORM_RE.sub("", s).lower()


def _toc_index(toc: list[str]) -> tuple[set[str], dict[str, str]]:
    """toc 条目 →（全部节号, 节号→规范标题）。复合条目「1.5 标题（1.5.1 子题 / 1.5.2 子题）」按 / 拆片解析。"""
    nos: set[str] = set()
    titles: dict[str, str] = {}
    for sub in toc or []:
        nos.update(NUM_RE.findall(sub))
        for piece in re.split(r"[/／]", sub):
            m = _TOC_PIECE_RE.match(piece.strip())
            if m:
                # 复合条目首片「1.5 以往工作评述（1.5.1 …」须在（处截断——否则子题文本混入
                # 父题规范串，正确的父标题反而判不符（bug-3036 v2 自伤修复）
                t = _norm_title(piece.strip()[m.end():].split("（", 1)[0].split("(", 1)[0])
                if t:
                    titles.setdefault(m.group(1), t)
    return nos, titles


def validate_toc(ch_id: str, text: str, toc: list[str]) -> dict:
    """目录覆盖门 v2（bug-3036：旧版纯编号盲检——同名异节/错题/契约外自创节全放行）。

    三向校验：① toc 全部节号（复合条目拆出的子节号也算）必须出现在章节 ##/###/#### 标题（旧有）；
    ② 标题节号不得超出 toc——契约外自创节/并节残留拦截；③ 编号相同则标题必须相符
    （规范化后双向包含即视为相符，防后缀展开误伤）。

    num_re 与 backend/tests/test_geological_report_v2_scripts.py::TestStageSections 同源。
    返回 {"toc_entries": 节号数, "toc_covered": 已落标题数}（供 delivery_manifest.json）。
    """
    toc_nos, toc_titles = _toc_index(toc)
    heading_nos: set[str] = set()
    heading_titles: dict[str, str] = {}
    for ln in text.splitlines():
        m = HEADING_NO_RE.match(ln.strip())
        if m:
            no = m.group(1)
            heading_nos.add(no)
            t = _norm_title(ln.strip()[m.end():])
            if t:
                heading_titles.setdefault(no, t)
    missing = sorted(toc_nos - heading_nos)
    extra = sorted(heading_nos - toc_nos)
    mismatched = [
        f"{no}: 目录「{toc_titles.get(no, '(缺)')}」≠ 标题「{heading_titles.get(no, '(空)')}」"
        for no in sorted(toc_nos & heading_nos)
        if no in toc_titles
        and no in heading_titles
        and toc_titles[no] != heading_titles[no]
        and toc_titles[no] not in heading_titles[no]
        and heading_titles[no] not in toc_titles[no]
    ]
    if missing or extra or mismatched:
        parts = [f"toc 节号未落标题 {missing}"] if missing else []
        if extra:
            parts.append(f"契约外节号 {extra}（禁自创/并节——stage toc 是唯一骨架契约，bug-3036）")
        if mismatched:
            parts.append("编号同但标题不符: " + "; ".join(mismatched[:6]))
        raise ValueError(
            f"{ch_id}.md 目录覆盖门 FAIL：{'；'.join(parts)}"
            f"（骨架全覆盖——动笔前读 STAGE 该章 toc 逐节展开，复合条目子节号须 #### 标题，bug-2221/2225/3036）"
        )
    return {"toc_entries": len(toc_nos), "toc_covered": len(toc_nos & heading_nos)}


# ── 注入后残留扫描门（bug-3036：模板脚手架/槽位标记/合约内部词汇泄漏进交付稿）──────
# 只扫注入后的章节正文——合规性附录由 build_output 脚本渲染（含合约 ID 表），不适用本门。
RESIDUE_RE = re.compile(
    r"\{\{(?:SLOT|TABLE|FORM):[^{}]*\}\}"           # 未注入槽位标记（FORM 族 bug-3027：27 处 {{FORM:…}} 直通终稿）
    r"|\{+S(?:LOT|FORM):[^{}]*\}+"                  # 畸形槽位（N19 单开括号/错配收形；bug-3027/3036）
    r"|（未知表单族"                                 # 旧软兜底字符串残留
    r"|exact_match|type_verdicts|ROUND_HALF_EVEN"   # 公式/校验层内部词汇
    r"|要点包|台账数据句|质量结论模板句|规范引用句"        # 提示词脚手架词
    r"|LLM自算|禁止LLM"
    r"|[（(](?:XS|FC|CC|NR|SL)\d"                   # 合约 ID 内联引用
    r"|\[\d+(?:\s*[,，]\s*\d+)+\]"                  # 裸数字数组（表格粘贴痕迹）
    r"|%%"
    r"|(?<![A-Za-z0-9])XX(?![A-Za-z0-9])"           # XX 占位（规范形是 [待确认]）
)


def validate_residue(ch_id: str, text: str) -> None:
    hits = sorted({m.group(0) for m in RESIDUE_RE.finditer(text)})
    if hits:
        raise ValueError(
            f"{ch_id}.md 残留扫描门 FAIL（bug-3036）：注入后正文仍含模板/内部词汇 {hits[:10]}"
            f"——槽位标记、脚手架词、合约 ID 不得出现在交付稿；XX 应写 [待确认]；合约结论只在合规性附录，改写为自然叙述后重跑"
        )


# ── L2 深度目标门（spec 2026-08-25 §4：eff ≥ 样例 median × coefficient × 覆盖缩放）──


def coverage_scale(text: str, targets: dict) -> float:
    """覆盖缩放：缺数信号越多目标越低，下限 scale_floor（缺数章防误拦）。"""
    signals = text.count("[待确认]") + targets.get("missing_table_weight", 8) * text.count("数据未提供")
    return max(targets.get("scale_floor", 0.25), 1 - targets.get("per_signal_penalty", 0.05) * signals)


def validate_depth_target(ch_id: str, text: str, targets: dict) -> None:
    """L2 深度目标门：inject 后文本 eff ≥ max(样例 median × coefficient × 覆盖缩放, 样例 median × absolute_floor)。

    bug-3036：绝对地板防「堆 [待确认] 压低覆盖缩放把越改越薄洗成 PASS」——缩放再低目标也不得穿地板。
    """
    ch = targets.get("per_chapter", {}).get(ch_id)
    if not ch:
        return  # targets 未覆盖该章 → 不拦（样例库不全时不误伤）
    coeff = targets.get("coefficient", 0.6)
    floor = targets.get("absolute_floor", 0.4)
    scale = coverage_scale(text, targets)
    median = ch.get("median_eff", 0)
    # 目标公式三处同式须同步改（validate_depth_target / _depth_row / run_chapter_gate PASS 行——max(median × coefficient × coverage_scale, median × absolute_floor)）
    target_eff = max(median * coeff * scale, median * floor)
    eff = effective_chars(text)
    if eff < target_eff:
        floor_binding = median * floor > median * coeff * scale
        raise ValueError(
            f"{ch_id}.md 深度目标门 FAIL：eff {eff} < 目标 {target_eff:.0f}"
            f"（样例 median {median} × {coeff} × 覆盖缩放 {scale:.2f}"
            + ("，绝对地板 {ff} 生效——[待确认] 堆叠不再降目标".format(ff=floor) if floor_binding else "")
            + f"）——逐要素成段扩写（缺数写 [待确认] 不砍段）；"
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
STANDARDS_PATH = Path(__file__).resolve().parent.parent / "references" / "standards_index.json"

# EAI-CUSTOM (geo-sample-bank Phase 2 T4): commodity 中文自由串 → 样例库基线 slug 归一化。
# 顺序即优先级：「铜银金」含「铜」→ copper（首命中）；词表外返回 None → 走既有探测链零感知。
MINERAL_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("copper", ("铜",)),
    ("coal", ("煤",)),
    ("gold", ("金",)),
    ("iron", ("铁",)),
    ("lead_zinc", ("铅锌", "铅", "锌")),
]


def normalize_mineral(commodity: str | None) -> str | None:
    """中文 commodity → 矿种 slug；空值/词表外 → None（调用方退回既有探测链）。"""
    if not commodity:
        return None
    for slug, keys in MINERAL_ALIASES:
        if any(k in commodity for k in keys):
            return slug
    return None


def _project_mineral(data_dir: Path | str | None) -> str | None:
    """读 <data_dir>/00_project.json 的 commodity 并归一化；目录缺失/损坏/词表外一律 None。"""
    if data_dir is None:
        return None
    p = Path(data_dir) / "00_project.json"
    if not p.exists():
        return None
    try:
        return normalize_mineral(json.loads(p.read_text(encoding="utf-8")).get("commodity"))
    except (OSError, ValueError):
        return None


def resolve_targets(args_targets: str | None, stage_path: Path, data_dir: Path | str | None = None) -> tuple[dict | None, Path]:
    """--targets 显式路径优先（调试通道）；缺省先按矿种查样例库基线目录，再沿 stage 文件向上三级探测，探测不中兜底技能自身基准。返回 (targets, 来源路径)。

    页面实测线程 03e18e4a 教训：agent 伪造 coefficient=0.01 的 depth_targets.json 显式传入，L2 目标全变 0——
    非技能基准必须醒目可见且留痕，不可静默生效。复核修复（bug-3058）：警告覆盖一切非技能基准来源
    （显式 --targets 与 stage 旁探测一致——stage 落在可写目录时探测路径同样可被投放伪造基准）。

    EAI-CUSTOM (geo-sample-bank Phase 2 T4)：data_dir 给出且 00_project.json 的 commodity 命中词表时，
    优先取 references/depth_targets/<stage_stem>/<mineral>.json（bank_compile 由管理模块门控生成的
    技能自有资产，早于三级探测、不打非技能基准警告，origin 仍由返回值第二元照记）。
    """
    if args_targets:
        src = Path(args_targets)
    else:
        # EAI-CUSTOM (geo-sample-bank Phase 2 T4)：矿种选基线——早于三级探测，命中即返回（技能自有资产无警告）。
        mineral = _project_mineral(data_dir)
        if mineral:
            cand = CANONICAL_TARGETS.parent / "depth_targets" / stage_path.stem / f"{mineral}.json"
            if cand.exists():
                print(f"[build] 深度基准: {cand}（样例库编译产物，来源已记入 delivery_manifest）", file=sys.stderr)
                return load_targets(cand), cand
        src = None
        for anc in (stage_path.parent, stage_path.parent.parent, stage_path.parent.parent.parent):
            cand = anc / "depth_targets.json"
            if cand.exists():
                src = cand
                break
        if src is None:
            print(f"[build] stage 附近未探测到 depth_targets.json——兜底技能自身基准 {CANONICAL_TARGETS}", file=sys.stderr)
            src = CANONICAL_TARGETS
    if src.resolve() != CANONICAL_TARGETS and src.exists():
        origin = "显式 --targets" if args_targets else "stage 旁探测"
        print(f"[build] 警告: 深度基准 {src}（sha256 {sha256_file(src)[:12]}…，来源: {origin}）≠ 技能基准 references/depth_targets.json——调试基准仅限调试通道，正式交付绝不换基准绕深度门；本次基准来源已记入 delivery_manifest.json", file=sys.stderr)
    return load_targets(src), src


# ── 组装 ────────────────────────────────────────────────────────────────────


def load_state_and_check(state_dir: Path) -> tuple[dict, dict | None]:
    """formula_state 装载 + bug-2223 手改检测门 + consistency 装载（assemble 与单章门共用）。"""
    state_path = state_dir / "formula_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # ── bug-2223 手改检测门：formula_runner.emit() 给每个槽位写 source 键；手改必丢 ──
    manual_numeric: list[str] = []
    for key, slot in state.get("values", {}).items():
        if not isinstance(slot, dict):
            raise ValueError(f"formula_state 槽位 {key} 不是对象（数值裸写=手改特征，formula_runner 是唯一写者，bug-2223）")
        if isinstance(slot.get("value"), (int, float)) and not isinstance(slot.get("value"), bool) and "source" not in slot:
            raise ValueError(f"formula_state 槽位 {key} 缺 source 键——疑似手改（formula_runner 是唯一写者，数字永不经过 LLM，bug-2223）。改数请走 ingest.py forms → formula_runner execute，勿直接编辑 formula_state.json")
        # ── bug-3036 根因①防线：数值槽 source=manual = LLM 内联 python 直写特征
        #（实测 201/377 槽如此产生，产出「5210.6 个钻孔」级错值——数值与数字字符串都算）。数字唯一合法通道：
        # ingest.py forms 录入 data/ → formula_runner execute 重算（emit 写 source=formula:*）。
        # 复核定案（bug-3058）：via=ingest 豁免通道无任何合法生产者（管线无脚本写 via）——
        # 保留它只会重演 bug-3049「自证凭据」：豁免条件本身只能靠手改冻结层满足。删除。
        # 一次报齐：收集全部违规键单次抛出（同 assemble 一次报齐哲学，勿逐键打回）。
        _val = slot.get("value")
        _num_like = isinstance(_val, (int, float)) and not isinstance(_val, bool)
        if isinstance(_val, str):
            try:
                float(_val.strip())
                _num_like = True
            except ValueError:
                pass
        if _num_like and slot.get("source") == "manual":
            manual_numeric.append(key)
    if manual_numeric:
        shown = ", ".join(sorted(manual_numeric)[:15])
        more = f" …等共 {len(manual_numeric)} 键" if len(manual_numeric) > 15 else ""
        raise ValueError(
            f"formula_state 数值槽 source=manual——LLM/手改直写特征（bug-3036 根因①）: {shown}{more}。"
            "唯一修复 = ingest.py forms 修数 → formula_runner execute 重算（emit 写 source=formula:*）；冻结层无手改通道"
        )
    consistency = None
    cc_path = state_dir / "consistency_check.json"
    if cc_path.exists():
        consistency = json.loads(cc_path.read_text(encoding="utf-8"))
    return state, consistency


def make_inject(stage: dict, data_dir: Path, state: dict, unknown_keys: set[str], slot_errors: set[str] | None = None):
    """{{SLOT:key}}/{{TABLE:fam}} 注入闭包工厂（assemble 与单章门共用；unknown_keys/slot_errors 就地累积）。

    bug-3036 P0：旧 slot_sub 对空/缺失 display 静默渲染出「数值空位」（正文出现裸单位或空串）——
    空/非标量 display 现记入 slot_errors 由调用方硬 FAIL。默认参数兼容既有测试直调。
    """
    errs = slot_errors if slot_errors is not None else set()

    def inject(text: str) -> str:
        def slot_sub(m: re.Match) -> str:
            key = m.group(1).strip()
            v = state.get("values", {}).get(key)
            if v is None:
                unknown_keys.add(key)
                return m.group(0)
            disp = v.get("display")
            if disp is None:
                disp = v.get("value")
            if isinstance(disp, (list, dict)):
                errs.add(f"{key}: display 为 {type(disp).__name__}（槽位值必须是标量，数组应走 {{TABLE:…}}）")
                return m.group(0)
            s = "" if disp is None else str(disp).strip()
            if not s:
                errs.add(f"{key}: display 为空——空槽位禁渲染（补数重算或改写为 [待确认] 叙述，bug-3036）")
                return m.group(0)
            return s

        def table_sub(m: re.Match) -> str:
            return render_family(m.group(1).strip(), stage, data_dir)

        text = SLOT_DEFORM_CLOSE_RE.sub(r"{{SLOT:\1}}\2", text)  # {{SLOT:k}m} → {{SLOT:k}}m
        text = SLOT_DEFORM_OPEN_RE.sub(r"{{SLOT:\1}}", text)     # {SLOT:k} → {{SLOT:k}}
        return TABLE_RE.sub(table_sub, SLOT_RE.sub(slot_sub, text))

    return inject


def assemble(stage: dict, data_dir: Path, state_dir: Path, targets: dict | None = None, skip_l2: set[str] | None = None, partial: dict | None = None, depth_rows: list | None = None) -> tuple[str, dict[str, dict]]:
    if targets is None:
        # 防绕：直调 assemble（targets=None）也吃技能真基准——页面实测线程 03e18e4a 直调跳过 L2 ~10 次
        targets = load_targets(CANONICAL_TARGETS)
    state_path = state_dir / "formula_state.json"
    state, consistency = load_state_and_check(state_dir)  # 重构：手改检测提取
    unknown_keys: set[str] = set()
    slot_errors: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys, slot_errors)  # 重构：注入闭包提取
    toc_stats: dict[str, dict] = {}
    depth_rows = depth_rows if depth_rows is not None else (partial["chapter_depth"] if partial is not None else [])  # bug-3036：全量 build 也留痕

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
            # 六步门序列与 run_chapter_gate 须同步改（新增校验两处同加）
            validate_chapter(ch_id, raw)
            validate_depth(ch_id, raw)
            toc_stats[ch_id] = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
            injected = inject(raw).rstrip() + "\n"
            validate_residue(ch_id, injected)
            if targets is not None and not (skip_l2 and ch_id in skip_l2):  # skip_l2：--allow-partial 批准集（Task 3）
                validate_depth_target(ch_id, injected, targets)
            depth_rows.append(_depth_row(ch_id, injected, targets, bool(skip_l2 and ch_id in skip_l2)))  # 校验抛错的章进 errors 硬 FAIL，不进表
        except ValueError as e:
            errors.append(str(e))
            continue
        parts.append(injected)
    parts.append(render_compliance_appendix(consistency, state, state_path))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if slot_errors:
        errors.append(f"槽位 display 非法（空/非标量，bug-3036 空槽静默渲染根治）:\n  " + "\n  ".join(sorted(slot_errors)))
    if errors:
        raise ValueError(f"{len(errors)} 项未过门（一次报齐，逐项修完再重跑——勿修一章跑一轮）:\n" + "\n".join(errors))
    return "\n\n".join(parts) + "\n", toc_stats


def load_progress(state_dir: Path) -> dict:
    """progress.json 装载（--allow-partial 前置：进度档案不在场=没走控制器流程，拒绝；chapters 形状损坏=手改特征，同拒）。"""
    p = state_dir / "progress.json"
    if not p.exists():
        raise ValueError(f"{p} 不存在——分级交付需要 progress.py 建立的进度档案（先走步骤4 控制器流程）")
    doc = json.loads(p.read_text(encoding="utf-8"))
    chs = doc.get("chapters", {}) if isinstance(doc, dict) else None
    if not isinstance(chs, dict) or not all(isinstance(s, dict) for s in chs.values()):
        raise ValueError(f"{p} chapters 结构损坏（手改特征）——progress.py 是唯一写者，续跑勿手改")
    return doc


def approved_chapters(progress: dict) -> set[str]:
    out: set[str] = set()
    appr = progress.get("downgrade_approvals", [])
    if not isinstance(appr, list):  # .get 默认值只兜 key 缺席——显式 null 是手改形状，须拒（.get(…, []) 对 null 不生效）
        raise ValueError(f"downgrade_approvals 结构损坏（手改特征）——progress.py 是唯一写者: {appr!r}")
    for a in appr:
        if not isinstance(a, dict) or not isinstance(a.get("chapters", []), list) or not all(isinstance(c, str) for c in a["chapters"]):
            raise ValueError(f"downgrade_approvals 结构损坏（手改特征）——progress.py 是唯一写者: {a!r}")
        out.update(a["chapters"])
    return out


def _depth_row(ch_id: str, injected: str, targets: dict | None, downgraded: bool) -> dict:
    """交付清单逐章深度行（全量 build 也写入 manifest——缩放/地板/达标比全留痕可查，bug-3036）。"""
    eff = effective_chars(injected)
    tg = targets or {}
    ch = tg.get("per_chapter", {}).get(ch_id)
    scale = coverage_scale(injected, tg)
    # 目标公式三处同式须同步改（validate_depth_target / _depth_row / run_chapter_gate PASS 行——max(median × coefficient × coverage_scale, median × absolute_floor)）
    target_eff = max(ch.get("median_eff", 0) * tg.get("coefficient", 0.6) * scale, ch.get("median_eff", 0) * tg.get("absolute_floor", 0.4)) if ch else 0
    return {
        "chapter": ch_id,
        "effective_chars": eff,
        "target": int(round(target_eff)),
        "coverage_scale": round(scale, 2),
        "ratio": round(eff / target_eff, 2) if target_eff > 0 else None,
        "status": "DOWNGRADED" if downgraded else "VERIFIED",
    }


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
    slot_errors: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys, slot_errors)
    cf = state_dir / "chapters" / f"{ch_id}.md"
    if not cf.exists():
        raise ValueError(f"章节产物缺失: {cf}（子代理未完成或未派发——先按 progress.py next 指引派发/重派该章）")
    raw = cf.read_text(encoding="utf-8")
    errors: list[str] = []
    toc: dict = {}
    injected = ""
    try:
        # 六步门序列与 assemble 循环体须同步改（新增校验两处同加）
        validate_chapter(ch_id, raw)
        validate_depth(ch_id, raw)
        toc = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
        injected = inject(raw).rstrip() + "\n"
        validate_residue(ch_id, injected)
        if targets is not None:
            validate_depth_target(ch_id, injected, targets)
    except ValueError as e:
        errors.append(str(e))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if slot_errors:
        errors.append(f"槽位 display 非法（空/非标量，bug-3036）:\n  " + "\n  ".join(sorted(slot_errors)))
    if errors:
        raise ValueError(f"{ch_id} 单章门 FAIL（{len(errors)} 项，一次报齐——补写该章正文后重跑）:\n" + "\n".join(errors))
    ch = (targets or {}).get("per_chapter", {}).get(ch_id)
    if ch:
        scale = coverage_scale(injected, targets)
        # 目标公式三处同式须同步改（validate_depth_target / _depth_row / run_chapter_gate PASS 行——max(median × coefficient × coverage_scale, median × absolute_floor)）
        t = max(ch.get("median_eff", 0) * targets.get("coefficient", 0.6) * scale, ch.get("median_eff", 0) * targets.get("absolute_floor", 0.4))
        print(f"CHAPTER_GATE_PASS: {ch_id} toc {toc['toc_covered']}/{toc['toc_entries']} eff {effective_chars(injected)} ≥ 目标 {t:.0f}（样例 median {ch.get('median_eff')} × {targets.get('coefficient', 0.6)} × 覆盖缩放 {scale:.2f}，地板 {targets.get('absolute_floor', 0.4)}）")
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
        targets, targets_src = resolve_targets(args.targets, Path(args.stage), data_dir=Path(args.data_dir))  # EAI-CUSTOM (geo-sample-bank Phase 2 T4)
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
        partial: dict | None = None
        skip_l2: set[str] = set()
        if args.allow_partial:
            progress = load_progress(Path(args.state_dir))
            blocked = {c for c, s in progress.get("chapters", {}).items() if s.get("status") == "BLOCKED"}
            unapproved = blocked - approved_chapters(progress)
            if unapproved:
                msg = f'[build] 分级交付 FAIL: BLOCKED 章未获用户批准: {sorted(unapproved)}——先走协商（progress.py next 指引）；批准: progress.py approve-downgrade --chapters {",".join(sorted(unapproved))} --note "<用户批准依据>"'
                print(msg, file=sys.stderr)
                return EXIT_ERROR
            skip_l2 = blocked  # 只放行 L2；L0/L1/toc/槽位门在场；产物缺失章仍由 assemble 硬 FAIL（含 PENDING 未派发）
            partial = {"downgrade_approvals": progress.get("downgrade_approvals", []), "chapter_depth": [], "downgraded": sorted(blocked)}
        depth_rows: list[dict] = partial["chapter_depth"] if partial is not None else []
        content, toc_stats = assemble(stage, Path(args.data_dir), Path(args.state_dir), targets=targets, skip_l2=skip_l2 or None, partial=partial, depth_rows=depth_rows)
        # ── bug-3036：consistency.py 25 合约门接入（此前在盘零调用——装配过门 ≠ 交付放行）。
        # 先落盘供 run_checks 读取；检查结果写 state_dir/consistency_check.json（附录读取源），fail>0
        # 则报告留盘但 manifest 不写——无清单 = 不可交付（bug-2225 凭据模型），逐项修复后重跑。
        atomic_write(out_path, content)
        # 复核残留项定案（bug-3059）：报告字节自此刻起重写——旧凭据必须在任何后续失败路径
        # 之前作废。只在 c_fails 分支撤销会漏异常路径（run_checks/c_path.write 抛错由 main
        # except 捕获后直接 EXIT_ERROR：报告已重写而旧 manifest 仍活）。成功路径随后重写新凭据。
        m_stale = out_path.parent / "delivery_manifest.json"
        if m_stale.exists():
            m_stale.unlink()
            print("[build] 已作废既有 delivery_manifest.json（报告重写中——旧凭据不得为未过门的新报告放行，bug-3059）", file=sys.stderr)
        import consistency

        # 一致性检查输入 = 去附录正文（附录是脚本生成的结论页，不作为合约检查对象）。
        # 幂等关键：附录汇总表本身随检查结果变化——若对「含附录全文」重复检查，build2 的
        # 摘要与 build1 落盘附录不一致 → 内容漂移 → 永不收敛（二连 build 不再 unchanged）。
        # 固定检查同一份去附录正文 → 结果逐字节确定 → 收敛。
        # 复核修复（bug-3058）：按行首锚切——无 \n 锚时章节正文行中段出现同款标记会把 body 截在半途，
        # 其后章节整体逃出 25 合约检查（validate_chapter 只拦行首保留标题，拦不住行中段）。
        body_text = content.split("\n## 合规性附录（脚本自动生成）", 1)[0]
        body_path = Path(args.state_dir) / "consistency_body.md"
        body_path.write_text(body_text, encoding="utf-8")
        c_path = Path(args.state_dir) / "consistency_check.json"
        c_result = consistency.run_checks(
            body_path,
            Path(args.data_dir),
            Path(args.stage),
            Path(args.state_dir) / "formula_state.json",
            STANDARDS_PATH if STANDARDS_PATH.exists() else None,
        )
        c_path.write_text(json.dumps(c_result, ensure_ascii=False, indent=2), encoding="utf-8")
        c_fails = [i for i in c_result["items"] if i["severity"] == "fail"]
        if c_fails:
            print(f"[build] 一致性合约门 FAIL（{len(c_fails)} 项，bug-3036 接入 consistency.py）:", file=sys.stderr)
            for i in c_fails:
                print(f"  [FAIL] {i['contract']}: {i['detail']}", file=sys.stderr)
            # 复核修复（bug-3059）：旧凭据已在门前统一作废——此处只报告状态。
            print(f"[build] 报告已落盘 {out_path} 但 delivery_manifest.json 不写——无清单=不可交付（bug-2225）；逐项修复后重跑", file=sys.stderr)
            return EXIT_ERROR
        c_manuals = [i for i in c_result["items"] if i["severity"] == "manual"]
        if c_manuals:
            # 复核修复（bug-3058）：直连 build 的 manual 语义对齐——不阻断（run-stage finalize 会以 rc=2 拦停）
            # 但必须高声可见，绝不静默带 MANUAL 交付。
            print(f"[build] MANUAL_PENDING（{len(c_manuals)} 项需人工——交付前逐条核实；run-stage finalize 会以 rc=2 拦停）:", file=sys.stderr)
            for i in c_manuals[:10]:
                print(f"  [MANUAL] {i['contract']}: {i['detail']}", file=sys.stderr)
        # 附录此刻引用的 consistency_check.json 已是本次结果 → 重组装一次使附录与检查同源
        #（校验对象=附录刷新前装配稿；附录为脚本生成文本，不受合约门约束）。
        # 复核修复（bug-3058）：depth_rows 由引用传入且 assemble 逐章 append——不清空则两次
        # 组装各追加一整套 → manifest.chapter_depth 每章两行（--allow-partial 时 partial 同病）。
        depth_rows.clear()
        content, toc_stats = assemble(stage, Path(args.data_dir), Path(args.state_dir), targets=targets, skip_l2=skip_l2 or None, partial=partial, depth_rows=depth_rows)
    except (FileNotFoundError, KeyError, ValueError, AttributeError, OSError, json.JSONDecodeError) as e:
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
        # bug-3036：全量 build 也逐章披露深度/覆盖缩放/达标比（此前仅 --allow-partial 留痕）
        "chapter_depth": depth_rows,
        "consistency": {"summary": c_result["summary"], "detail_path": str(Path(args.state_dir) / "consistency_check.json")},
    }
    if partial is not None:
        manifest["partial"] = partial  # 仅 --allow-partial 模式加 → 全量 build manifest 字节不变
    m_path = out_path.parent / "delivery_manifest.json"
    m_wrote = atomic_write(m_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"BUILD_READY: {args.output} bytes={len(content.encode('utf-8'))} {'written' if wrote else 'unchanged(skip, idempotent)'}")
    print(f"MANIFEST_READY: {m_path} {'written' if m_wrote else 'unchanged(skip, idempotent)'}")
    s = c_result["summary"]
    print(f"CONSISTENCY: pass {s.get('pass', 0)} / warn {s.get('warn', 0)} / manual {s.get('manual', 0)} / fail 0（fail>0 已在上一步阻断）")
    if partial is not None:
        print(f"PARTIAL_DELIVERY: 分级交付 {len(partial['downgraded'])} 章降档 {partial['downgraded']}（深度未达标明细见 delivery_manifest.json → partial.chapter_depth，交付时向用户如实汇报）")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
