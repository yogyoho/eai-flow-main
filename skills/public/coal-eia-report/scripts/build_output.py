#!/usr/bin/env python3
"""coal-eia-report v2 — build_output.py：单次原子组装（步骤5–7）+ 章门（两层模型）。

组装序：前置部分（表单直出零 LLM；interface_skeleton 无 forms 注册时最小前置不编造数据）
→ ch1..chN（**由 state/sections/chNN_SNN.md 节稿按 stage sections 顺序拼章稿**——章稿落
state/chapters/chNN.md 供门与组装，两层状态模型）→ 合规性附录（consistency_check 渲染）。

注入协议（D5/1A，geo 语义原样）：{{SLOT:key}} → formula_state.values[key].display（未知 key=FAIL）；
{{TABLE:fam}} → data/ 表单族渲染为 markdown 表。原子写 tmp+os.replace；内容不变跳过写盘保 mtime。

章门（--chapter / progress.py gate 批量入口，D9 粒度分层：门禁=章级、节无独立门）：
  节级门（错误**归因到节**，一行一节——OV#7 修复派发不盲）：
    ① 节稿形状：首行 `### <编号> 节标题` 且语义相符 stage 节题（禁 #/## 章级标题——章题由拼装注入）
    ② 节清单约束：一节一稿一 ###（新增小节用 ####；自创节 FAIL——节由 stage sections 清单约束）
    ③ L0 深度门：每个标题块 ≥3 句（表格行不计句；有更深子块的父块豁免——geo 语义节级化）
    ④ 槽位注入：未知 {{SLOT:}} FAIL、display 空/非标量 FAIL、TABLE 未知表单族 FAIL（geo 语义原样）
    ⑤ 残留扫描：槽位标记/脚手架词/合约 ID/XX 占位（geo 语义原样）
  章级门：
    ⑥ L2 深度门对**章**断言：章实有效字符 ≥ 章地板（references/depth_targets/<stage>.json 的
       chapters[ch].floor_chars；缺省默认字符地板 30000——一期绝对地板，二期 calibrate 校准）。
       FAIL 时输出节级 eff 明细（由低到高，修复派发直达最薄节）；覆盖缩放不存在的地板即目标
       （geo median×absolute_floor「地板不可穿透」语义在章级延续）
    ⑦ 章最小有效字符 ≥1000（geo L0 章级保留）
  序无关目录覆盖门（eng-review 拍板，章级）：stage 章集映射 {必备集, 可选集}——实际**章**标题
    覆盖必备集、不得超集（禁契约外自创），**序不校验**（要素章序 4 种排布实证）；ABSENT 章/节
    豁免（stage 条件开关驱动）；**节不参与 toc 覆盖**（节由 stage sections 清单约束=门②）。
    章条目 optional:true 记可选章（回顾/识别互换与可选章缺席记 ABSENT，门/组装/覆盖同语义跳过）。

深度基线装载 resolve_targets：显式 --targets 优先（非技能基准高声警告，geo 反绕语义保留）；
缺省 references/depth_targets/<stage_stem>.json，缺失 → None → 全章走默认地板 30000。

失败一次报齐（geo 哲学不变：不 fail-fast 逐章打回）；--allow-partial 分级交付（批准降档章跳 L2，
L0/toc/槽位门在场）；success 后写 delivery_manifest.json（bug-2225 凭据模型）+ consistency 合约门
（geo 25 条 + 环评注册表 --contracts 注入——references/consistency_contracts.json 在册即自动启用）。

退出码：0 成功 / 1 未知槽位 key、节稿缺失/形状违规、章深度不足、章地板未达、目录覆盖违规
（必备章缺席/契约外自创章）、交付名门、consistency fail>0。
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
# N19 畸形 SLOT 修复（geo T4 页面实测 93 处穿透全门进终稿）：降级写手系统性产出
# 「{{SLOT:key}单位}」错配收形与「{SLOT:key}」单开括号形——SLOT_RE 不匹配 → 不注入
# 也不报 FAIL，静默进交付稿。注入前先归一化为 {{SLOT:key}}（单位等尾缀移到槽外），
# 修复后的键走正常 unknown-key FAIL 门（语义错配照样拦）。
SLOT_DEFORM_CLOSE_RE = re.compile(r"\{\{SLOT:([^{}]+)\}(?!\})([^{}\n]*)\}")
SLOT_DEFORM_OPEN_RE = re.compile(r"(?<!\{)\{SLOT:([^{}]+)\}")  # lookbehind 防 {{SLOT: 被当单括号形

DEFAULT_CHAPTER_FLOOR_CHARS = 30000  # 一期绝对地板（无 depth 基线时的章级默认，spec L2 门）
DEPTH_DIR = Path(__file__).resolve().parent.parent / "references" / "depth_targets"
CONTRACTS_PATH = Path(__file__).resolve().parent.parent / "references" / "consistency_contracts.json"
STANDARDS_PATH = Path(__file__).resolve().parent.parent / "references" / "standards_index.json"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


# ── 交付名门（bug-2223②：规范文件名唯一来源 = 00_project 表单直读）────────────


def expected_deliverable_name(stage: dict, data_dir: Path) -> str:
    """{项目名}-{阶段}-地质勘查报告 → 环评版 {项目名}-{阶段}-环境影响报告.md（00_project 直读；
    缺参不编造，回退字段名提示）。interface_skeleton 骨架（无 forms 注册）回退 {stage 名}报告.md。

    geo bug-3036 P2 语义保留：项目名尾缀已含阶段词不再重复拼接。
    """
    spec = stage.get("forms", {}).get("project")
    if not spec:
        return f"{stage.get('stage', '环评报告')}报告.md"
    p = data_dir / spec["file"]
    proj = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    name = proj.get("project_name") or "未命名项目"
    st = proj.get("stage") or stage.get("stage", "")
    if st and name.endswith(st):
        return f"{name}-环境影响报告.md"
    return f"{name}-{st}-环境影响报告.md" if st else f"{name}-环境影响报告.md"


# ── 前置部分（表单直出；骨架模式最小前置）────────────────────────────────────


def render_front_matter(stage: dict, data_dir: Path) -> str:
    if "forms" not in stage or "project" not in stage.get("forms", {}):
        # interface_skeleton（T1 接口骨架）：无表单注册 → 最小前置（题名+章目录），不编造数据。
        # 真实 stage（T3+）带 forms 后走 geo 完整路径（外封面/签署页/附图附表目录）。
        lines = ["# 前置部分", "", f"## 报告题名", "", f"**{stage.get('stage', '环评报告')}报告**", "", "## 目录", ""]
        lines.append("<!-- 页码列留空：Word 排版阶段由引用自动填充（设计决策 D11），Markdown 禁写页码 -->")
        lines.append("")
        for ch_id in chapter_order(stage.get("chapters", {})):
            lines.append(f"- **{stage['chapters'][ch_id].get('title', ch_id)}**")
        lines.append("")
        return "\n".join(lines)
    fm = stage.get("front_matter", {})
    proj = json.loads((data_dir / stage["forms"]["project"]["file"]).read_text(encoding="utf-8")) if (data_dir / stage["forms"]["project"]["file"]).exists() else {}
    ten = json.loads((data_dir / stage["forms"].get("tenement", {}).get("file", "_")).read_text(encoding="utf-8")) if stage.get("forms", {}).get("tenement") and (data_dir / stage["forms"]["tenement"]["file"]).exists() else {}
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
        val = sig_src.get(label) or ""
        lines.append(f"{label}：{val if val else '＿＿＿＿＿＿'}")
        lines.append("")
    lines.append("## 目录")
    lines.append("")
    lines.append("<!-- 页码列留空：Word 排版阶段由引用自动填充（设计决策 D11），Markdown 禁写页码 -->")
    lines.append("")
    for ch_id in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][ch_id]
        lines.append(f"- **{ch.get('title', ch_id)}**")
        for sub in ch.get("toc", []):
            lines.append(f"  - {sub}")
    lines.append("")
    # 附图附表目录（表单族可缺——骨架渐进）
    ft_spec = stage.get("forms", {}).get("figures_tables")
    if ft_spec:
        ftf = data_dir / ft_spec["file"]
        ft = json.loads(ftf.read_text(encoding="utf-8")) if ftf.exists() else {}
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


# ── 表渲染（geo 语义原样）────────────────────────────────────────────────────


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _dig(doc, segs: list[str]):
    """点号子路径下钻：每步先试剩余全串作扁平点号键（ingest schema 惯例），
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
            f"TABLE 引用未知表单族 {fam!r}（stage 在册: {sorted(stage.get('forms', {}))}）"
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
    if "." in fam:
        doc = _dig(doc, fam.split(".", 1)[1].split("."))
        if doc is None:
            return f"（{fam}: 数据未提供——[待确认] 槽位，缺参不编造）"
    # bug-3018: 清单族经 `ingest.py file` CSV 摄入落成顶层行数组——行数组按单表渲染，
    # 与 dict 分支同构；不回写 data/（唯一写者=ingest.py）。
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
        lines.append(
            f"### 一致性校验汇总：pass {s.get('pass', 0)} / warn {s.get('warn', 0)} / manual {s.get('manual', 0)}"
            f" / skip {s.get('skip', 0)} / fail {s.get('fail', 0)}"
        )
        lines.append("")
        non_pass = [i for i in consistency.get("items", []) if i.get("severity") not in ("pass", "skip")]
        if non_pass:
            lines.append(_md_table(["级别", "合约", "详情"], [[i["severity"], i["contract"], i["detail"]] for i in non_pass]))
        elif s.get("skip", 0):
            lines.append(f"全部激活合约通过（{s.get('skip', 0)} 条条件激活未命中记 skip）。")
        else:
            lines.append("全部合约通过。")
        lines.append("")
    lines.append("<!-- 历史分类编码与既有口径按原样保留，禁现代化改写（红线 P4 同构） -->")
    return "\n".join(lines)


# ── 章节卫生门（geo bug-2220 语义；两层模型下对象=拼装章稿与节稿）──────────────

# 脚本保留标题：前置部分与合规附录由 build_output 统一渲染，章节文件出现即重复源
RESERVED_HEADINGS = ("# 前置部分", "## 外封面", "## 签署页", "## 目录", "## 附图附表目录", "## 合规性附录")


def validate_chapter(ch_id: str, text: str) -> None:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first.startswith("## "):
        raise ValueError(f"{ch_id} 章稿首行必须是 `## N 章标题`（当前: {first[:40]!r}）——章题由拼装按 stage 注入")
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(RESERVED_HEADINGS):
            raise ValueError(f"{ch_id} 含脚本保留标题 {s[:24]!r}——前置部分与合规性附录由 build_output 统一渲染，章节文件禁写（bug-2220 同构）")


def validate_section(sid: str, text: str) -> None:
    """节稿形状门（两层模型改造点①：派发单元=节，形状是拼装与归因的前提）。"""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first.startswith("### "):
        raise ValueError(f"节稿首行必须是 `### <编号> 节标题`（当前: {first[:40]!r}）——章标题由拼装注入，节稿禁写 #/## 级标题")
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#") and not s.startswith("###"):
            raise ValueError(f"含章级标题 {s[:24]!r}——节稿只允许 ###/#### 级（章标题由拼装按 stage 注入）")
        if s.startswith(RESERVED_HEADINGS):
            raise ValueError(f"含脚本保留标题 {s[:24]!r}——前置部分与合规性附录由 build_output 统一渲染（bug-2220 同构）")
    heads = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("### ")]
    if len(heads) > 1:
        raise ValueError(f"多个 ### 标题 {[h[4:16] for h in heads[:3]]}——一节一稿一 ###：新增小节用 ####，或拆为独立节稿（禁自创节——节由 stage sections 清单约束）")


def validate_section_title(sid: str, text: str, want: str) -> None:
    """节题相符门（目录语义的节级形态——序/编号不校验，语义相符即可）。"""
    head = next((ln.strip()[4:] for ln in text.splitlines() if ln.strip().startswith("### ")), "")
    if not _sem_match(head, want):
        raise ValueError(f"首个 ### 标题「{head[:24]}」≠ stage 节题「{want}」——派发契约：节稿以 stage 节题开头（编号自由，语义须相符）")


# ── 深度门（geo bug-2223 语义节级化）────────────────────────────────────────
SENT_RE = re.compile(r"[。；？！]")


def effective_chars(text: str) -> int:
    """有效字符数：排除空行/标题行/表格行，行内剔除空白与 |\\-*#:{} 装饰符（geo 原样）。"""
    return sum(len(re.sub(r"[\s\|\-*#:{}]", "", line)) for line in text.splitlines() if line.strip() and not line.strip().startswith("|") and not line.strip().startswith("#"))


def validate_depth_blocks(owner: str, text: str) -> None:
    """L0 深度门（geo validate_depth 节级化，OV#7 归因到节）：每个标题块（### / ####）正文 ≥3 句；
    表格行不计句、不豁免；有更深子块的父块豁免——geo「## 有 ### 子节豁免」推广到 ###→####
    （正文在子块，防「补句进子块、错误却报父块」修不动假象，geo 线程 03e18e4a 同构）。"""
    blocks: list[tuple[str, list[str], int]] = []
    cur_title, cur_lines, cur_depth = "", [], 0
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            depth = len(s) - len(s.lstrip("#"))
            blocks.append((cur_title, cur_lines, cur_depth))
            cur_title, cur_lines, cur_depth = s, [], depth
        else:
            cur_lines.append(ln)
    blocks.append((cur_title, cur_lines, cur_depth))
    thin = []
    for i, (title, lns, depth) in enumerate(blocks):
        if title == "" and not any(ln.strip() for ln in lns):
            continue  # 首块无标题无内容（节稿以 ### 开头）
        if title and i + 1 < len(blocks) and blocks[i + 1][2] > depth:
            continue  # 父块豁免：正文在更深的子块
        sents = sum(len(SENT_RE.findall(ln)) for ln in lns if ln.strip() and not ln.strip().startswith("|"))
        if sents < 3:
            thin.append(f"{title or '(块首)'}={sents}句")
    if thin:
        raise ValueError(f"深度门 FAIL（每节 ≥3 句——句子写进该节自己的正文、下一级子标题之前；表格行不计句；有子块的父块豁免）瘦块: {'; '.join(thin)}；参照 references/chapter_examples/ 范文补写")


# ── 注入后残留扫描门（geo bug-3036 语义原样）──────────────────────────────────
RESIDUE_RE = re.compile(
    r"\{\{(?:SLOT|TABLE|FORM):[^{}]*\}\}"           # 未注入槽位标记（FORM 族 bug-3027）
    r"|\{+S(?:LOT|FORM):[^{}]*\}+"                  # 畸形槽位（N19 单开括号/错配收形）
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
            f"残留扫描门 FAIL（bug-3036）：注入后正文仍含模板/内部词汇 {hits[:10]}"
            f"——槽位标记、脚手架词、合约 ID 不得出现在交付稿；XX 应写 [待确认]；合约结论只在合规性附录，改写为自然叙述后重跑"
        )


# ── 序无关目录覆盖门（章级，eng-review 拍板）──────────────────────────────────
_TITLE_NORM_RE = re.compile(r"[\s　\-—–·。，,、;；:：!！?？()（）\[\]【】\"'“”‘’/*／]+")


def _norm_title(s: str) -> str:
    """标题规范化：去空白/标点（全半角）/装饰符后小写（geo 原样）；再剥行首编号与尾部章/节通名。"""
    t = _TITLE_NORM_RE.sub("", str(s)).lower()
    t = re.sub(r"^\d+(?:\.\d+)*", "", t)  # 行首编号（12.2 第二次公众参与 → 第二次公众参与）
    if len(t) > 2 and t[-1] in "章节":
        t = t[:-1]
    return t


def _sem_match(a: str, b: str) -> bool:
    """语义标题匹配：规范化后相等或双向包含（序/编号不校验——要素章序 4 种排布实证）。"""
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def validate_toc_chapters(stage: dict, actual: list[tuple[str, str]], absent_ch: set[str] | None = None) -> list[str]:
    """序无关目录覆盖门（两层模型改造点②）：stage 章集映射 {必备集, 可选集}——
    实际**章**标题覆盖必备集、不得超集（禁契约外自创）、序不校验；ABSENT 章豁免；
    节不参与（节由 stage sections 清单约束 = validate_section 门）。
    章条目 `optional:true` 记可选章。返回错误行清单（空 = PASS）。"""
    absent = absent_ch or set()
    stage_chs = [
        (ch_id, stage["chapters"][ch_id].get("title", ch_id), bool(stage["chapters"][ch_id].get("optional")))
        for ch_id in chapter_order(stage.get("chapters", {}))
    ]
    errors: list[str] = []
    matched: set[str] = set()
    for ch_id, title in actual:
        hits = [cid for cid, t, _o in stage_chs if _sem_match(title, t)]
        if not hits:
            errors.append(f"章 {ch_id}: 契约外自创章「{title[:24]}」（不得超集——stage 章集是唯一目录契约，禁自创/并章）")
            continue
        dup = [h for h in hits if h in matched]
        if dup:
            errors.append(f"章 {ch_id}: 章题「{title[:20]}」与已匹配章重复覆盖同一契约章 {dup}")
        matched.update(hits)
    missing = [f"{cid}「{t}」" for cid, t, opt in stage_chs if not opt and cid not in matched and cid not in absent]
    if missing:
        errors.append(
            "目录覆盖门 FAIL：必备章缺席 " + ", ".join(missing)
            + "（必备集须全覆盖、序无关；可选章/条件开关章缺席 = ABSENT 豁免合法）"
        )
    return errors


# ── L2 章级深度地板门（spec：L2 门对章断言，一期绝对地板，二期 calibrate 校准）──


def load_depth(path: Path) -> dict | None:
    """装载章级深度基线 depth_targets/<stage>.json；缺失/损坏 → stderr 提示后退回默认地板（不阻断）。"""
    if not Path(path).exists():
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(doc.get("chapters"), dict):
            raise ValueError("chapters 缺失或非对象")
        return doc
    except (json.JSONDecodeError, ValueError, AttributeError, OSError) as e:
        print(f"[build] 深度基线损坏（{path}: {e}）——退回默认字符地板 {DEFAULT_CHAPTER_FLOOR_CHARS}", file=sys.stderr)
        return None


def resolve_targets(args_targets: str | None, stage_path: Path, data_dir: Path | str | None = None) -> tuple[dict | None, Path]:
    """深度基线装载（章级 floor_chars 形状 {"chapters":{"ch6":{"floor_chars":N,…}}}）：
    显式 --targets 优先（非技能基准高声警告并记入 delivery_manifest——geo 反绕语义保留）；
    缺省 references/depth_targets/<stage_stem>.json；缺失 → (None, 规范路径)——门走默认地板 30000。

    data_dir 参数保留（progress.py 调用方签名兼容；coal 深度基线按 stage 不按矿种分流）。"""
    canonical = DEPTH_DIR / (stage_path.stem + ".json")
    if args_targets:
        src = Path(args_targets)
        if src.exists() and src.resolve() != canonical.resolve():
            print(f"[build] 警告: 深度基线 {src}（sha256 {sha256_file(src)[:12]}…）≠ 技能基线 {canonical}——调试基准仅限调试通道，正式交付绝不换基准绕深度门；本次基准来源已记入 delivery_manifest.json", file=sys.stderr)
        return load_depth(src), src
    if canonical.exists():
        return load_depth(canonical), canonical
    print(f"[build] 深度基线不在册（{canonical}）——全章走默认字符地板 {DEFAULT_CHAPTER_FLOOR_CHARS}（一期绝对地板；calibrate 校准后入库）", file=sys.stderr)
    return None, canonical


def chapter_floor(targets: dict | None, ch_id: str) -> int:
    ch = (targets or {}).get("chapters", {}).get(ch_id) or {}
    return int(ch.get("floor_chars") or DEFAULT_CHAPTER_FLOOR_CHARS)


def validate_chapter_depth(ch_id: str, injected: str, targets: dict | None) -> tuple[int, int]:
    """L2 章级地板门：章实有效字符 ≥ 章地板（floor_chars 或默认 30000）。返回 (eff, floor)。
    地板即目标、覆盖缩放不可穿透（geo median×absolute_floor 语义在章级延续——abs floor 防把越改越薄洗成 PASS）。"""
    eff = effective_chars(injected)
    floor = chapter_floor(targets, ch_id)
    if eff < floor:
        raise ValueError(f"L2 深度门 FAIL：章有效字符 {eff} < 章地板 {floor}（一期绝对地板，缺数写 [待确认] 不砍段；逐要素成段扩写）")
    return eff, floor


# ── 注入闭包（geo 语义原样）──────────────────────────────────────────────────


def load_state_and_check(state_dir: Path) -> tuple[dict, dict | None]:
    """formula_state 装载 + bug-2223 手改检测门 + consistency 装载（assemble 与单章门共用）。"""
    state_path = state_dir / "formula_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    manual_numeric: list[str] = []
    for key, slot in state.get("values", {}).items():
        if not isinstance(slot, dict):
            raise ValueError(f"formula_state 槽位 {key} 不是对象（数值裸写=手改特征，formula_runner 是唯一写者，bug-2223）")
        if isinstance(slot.get("value"), (int, float)) and not isinstance(slot.get("value"), bool) and "source" not in slot:
            raise ValueError(f"formula_state 槽位 {key} 缺 source 键——疑似手改（formula_runner 是唯一写者，数字永不经过 LLM，bug-2223）。改数请走 ingest.py forms → formula_runner execute，勿直接编辑 formula_state.json")
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

    bug-3036 P0：空/缺失 display 静默渲染出「数值空位」——空/非标量 display 记入 slot_errors 硬 FAIL。
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


# ── 两层拼装（节稿 → 章稿）与章门 ────────────────────────────────────────────


def _absent_sets(state_dir: Path) -> tuple[set[str], set[str]]:
    """progress.json 容错读 → (ABSENT 章集, ABSENT 节集)。无 progress 档案 = 无缺席
    （单章门/组装在控制器流程外仍可用——ABSENT 是 progress.py 状态机语义，唯一写者=progress.py）。"""
    p = state_dir / "progress.json"
    if not p.exists():
        return set(), set()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set(), set()
    chs = doc.get("chapters", {}) if isinstance(doc, dict) else {}
    absent_ch = {c for c, e in chs.items() if isinstance(e, dict) and e.get("status") == "ABSENT"}
    absent_sec = {
        s.get("id")
        for e in chs.values() if isinstance(e, dict)
        for s in e.get("sections", []) if isinstance(s, dict) and s.get("status") == "ABSENT"
    }
    return absent_ch, absent_sec


def _chapter_heading(ch_id: str, ch: dict) -> str:
    title = ch.get("title", ch_id)
    n = ch_id[2:] if ch_id[2:].isdigit() else ""
    return f"## {n} {title}".rstrip() if n else f"## {title}"


def build_chapter(stage: dict, data_dir: Path, state_dir: Path, ch_id: str, inject, absent_sections: set[str]) -> tuple[str, str, list[dict], list[str]]:
    """装载 state/sections/chNN_SNN.md 按 stage sections 顺序拼章稿（两层模型改造点①）：
    节级门逐节跑（错误归因到节，一行一节——OV#7），章稿原子写 state/chapters/chNN.md 供门与组装。

    返回 (raw 章稿, injected 章稿, 节行 [{id, eff}], 错误行清单)。
    """
    ch = stage["chapters"][ch_id]
    head = _chapter_heading(ch_id, ch)
    stage_secs = [s for s in ch.get("sections", []) if s.get("id")]
    rows: list[dict] = []
    raws: list[str] = []
    injs: list[str] = []
    errors: list[str] = []
    for s in stage_secs:
        sid = s["id"]
        if sid in absent_sections:
            continue  # ABSENT 节豁免（门/组装/覆盖同语义跳过）
        sf = state_dir / "sections" / f"{sid}.md"
        if not sf.exists():
            errors.append(f"节 {sid}: 节稿缺失 {sf}（派发未完成或文件名不符——不静默跳过）")
            continue
        raw = sf.read_text(encoding="utf-8")
        # 节级门一次报齐该节全部问题（OV#7 修复派发不盲——深度/槽位/残留/节题同轮归因）
        errs_s: list[str] = []
        try:
            validate_section(sid, raw)
            validate_section_title(sid, raw, s.get("title", ""))
        except ValueError as e:
            errs_s.append(str(e))
        try:
            inj_s = inject(raw).rstrip() + "\n"
        except ValueError as e:
            errs_s.append(str(e))
            inj_s = raw  # 注入失败（如 TABLE 未知表单族）——节已记 FAIL，原稿供残留门归并
        try:
            validate_residue(sid, inj_s)
        except ValueError as e:
            errs_s.append(str(e))
        try:
            validate_depth_blocks(sid, raw)
        except ValueError as e:
            errs_s.append(str(e))
        if errs_s:
            errors.extend(f"节 {sid}: {e}" for e in errs_s)
            continue
        rows.append({"id": sid, "eff": effective_chars(inj_s)})
        raws.append(raw.rstrip() + "\n")
        injs.append(inj_s)
    if not raws:
        all_absent = bool(stage_secs) and all(s["id"] in absent_sections for s in stage_secs)
        detail = (
            f"全部 {len(stage_secs)} 节 ABSENT 而章未标 ABSENT——条件开关语义应标章级 ABSENT（progress.py mark {ch_id} ABSENT 级联）"
            if all_absent and not errors
            else f"{len(stage_secs)} 节全部缺失或未过门——先按 progress.py next 指引派发/修复节稿"
        )
        errors.append(f"章 {ch_id}: 可用节稿为空（{detail}）")
        return "", "", rows, errors
    raw_text = head + "\n\n" + "\n\n".join(raws)
    injected = head + "\n\n" + "\n\n".join(injs)
    try:
        (state_dir / "chapters").mkdir(parents=True, exist_ok=True)
        atomic_write(state_dir / "chapters" / f"{ch_id}.md", raw_text if raw_text.endswith("\n") else raw_text + "\n")
    except OSError as e:
        errors.append(f"章 {ch_id}: 章稿缓存写盘失败 {e}")
    return raw_text, injected, rows, errors


def run_chapter_gate(stage: dict, data_dir: Path, state_dir: Path, ch_id: str, targets: dict | None) -> None:
    """--chapter 单章全门（两层模型改造点③：门对象 = 拼装章稿）。

    节级门（形状/节题/深度/槽位/残留）逐节跑 → 错误**归因到节**一行一节（OV#7）；
    章级门（章稿形状/章最小字符/L2 章地板）跑拼装注入稿；L2 FAIL 附节级 eff 明细
    （由低到高——修复派发直达最薄节）。不产交付物、不写 progress.json（唯一写者=progress.py）。
    PASS 打 CHAPTER_GATE_PASS 行（eff/地板/节计数——mark VERIFIED 与重派决策的数据面）。
    ABSENT 章 → CHAPTER_GATE_SKIP（门/组装同语义跳过，rc=0）。
    """
    order = chapter_order(stage.get("chapters", {}))
    if ch_id not in stage.get("chapters", {}):
        raise ValueError(f"未知章节 {ch_id}（stage 在册: {order}）")
    absent_ch, absent_sections = _absent_sets(state_dir)
    if ch_id in absent_ch:
        print(f"CHAPTER_GATE_SKIP: {ch_id}（ABSENT——stage 条件开关驱动，门/组装/目录覆盖同语义豁免）")
        return
    state, _consistency = load_state_and_check(state_dir)
    unknown_keys: set[str] = set()
    slot_errors: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys, slot_errors)
    _raw, injected, rows, errors = build_chapter(stage, data_dir, state_dir, ch_id, inject, absent_sections)
    stage_secs = [s for s in stage["chapters"][ch_id].get("sections", []) if s.get("id")]
    if injected:
        try:
            validate_chapter(ch_id, _raw)
        except ValueError as e:
            errors.append(f"章 {ch_id}: {e}")
        eff = effective_chars(injected)
        if eff < 1000:
            errors.append(f"章 {ch_id}: 章最小有效字符门 FAIL：{eff} <1000（geo bug-2223 章级保留）")
        try:
            eff, floor = validate_chapter_depth(ch_id, injected, targets)
        except ValueError as e:
            thin = sorted(rows, key=lambda r: r["eff"])
            breakdown = "\n".join(f"  节 {r['id']}: eff {r['eff']}" for r in thin) or "  （无有效节行）"
            errors.append(f"章 {ch_id}: {e}\n{breakdown}")
    else:
        eff, floor = 0, chapter_floor(targets, ch_id)
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if slot_errors:
        errors.append("槽位 display 非法（空/非标量，bug-3036）:\n  " + "\n  ".join(sorted(slot_errors)))
    if errors:
        raise ValueError(f"{ch_id} 单章门 FAIL（{len(errors)} 项，一次报齐——按节归因修复后重跑）:\n" + "\n".join(errors))
    n_absent = sum(1 for s in stage_secs if s["id"] in absent_sections)
    src_desc = f"基线 {chapter_floor(targets, ch_id)} 字符" if targets else f"默认地板 {DEFAULT_CHAPTER_FLOOR_CHARS} 字符"
    print(
        f"CHAPTER_GATE_PASS: {ch_id} sections {len(rows)}/{len(stage_secs)}"
        f"（ABSENT 豁免 {n_absent}）eff {eff} ≥ 章地板 {floor}（{src_desc}）"
    )


def atomic_write(path: Path, content: str) -> bool:
    """幂等原子写：内容不变返回 False（保 mtime，SC-4 字节不变断言）。

    bug-2225: 字节精确写（newline="\\n"）——凭据 sha 必须与盘上文件逐字节一致
    （Windows 文本模式 \\n→\\r\\n 翻译会使 sha 与实文件不符）。
    """
    if path.exists() and path.read_bytes() == content.encode("utf-8"):
        return False
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)
    return True


def _depth_row(ch_id: str, injected: str, targets: dict | None, downgraded: bool) -> dict:
    """交付清单逐章深度行（章级地板口径，全量 build 也留痕——geo bug-3036 哲学）。"""
    eff = effective_chars(injected)
    floor = chapter_floor(targets, ch_id)
    return {
        "chapter": ch_id,
        "effective_chars": eff,
        "floor": floor,
        "ratio": round(eff / floor, 2) if floor > 0 else None,
        "status": "DOWNGRADED" if downgraded else "VERIFIED",
    }


def assemble(stage: dict, data_dir: Path, state_dir: Path, targets: dict | None = None, skip_l2: set[str] | None = None, partial: dict | None = None, depth_rows: list | None = None) -> tuple[str, dict[str, dict]]:
    """全书组装：前置部分 → 各章（build_chapter 拼装 + 节级/章级门，一次报齐）→ 序无关目录
    覆盖门 → 合规性附录。ABSENT 章/节同语义跳过（stage 条件开关驱动）。
    targets=None = 默认地板通道（基线装载与防绕在 main()/resolve_targets 收口）。"""
    state_path = state_dir / "formula_state.json"
    state, consistency = load_state_and_check(state_dir)
    unknown_keys: set[str] = set()
    slot_errors: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys, slot_errors)
    absent_ch, absent_sections = _absent_sets(state_dir)
    toc_stats: dict[str, dict] = {}
    actual: list[tuple[str, str]] = []
    depth_rows = depth_rows if depth_rows is not None else (partial["chapter_depth"] if partial is not None else [])
    errors: list[str] = []

    parts = [render_front_matter(stage, data_dir)]
    for ch_id in chapter_order(stage.get("chapters", {})):
        if ch_id in absent_ch:
            continue  # ABSENT 章豁免（门/组装/目录覆盖同语义跳过）
        raw, injected, rows, errs = build_chapter(stage, data_dir, state_dir, ch_id, inject, absent_sections)
        errors.extend(errs)
        if errs or not injected:
            continue
        try:
            validate_chapter(ch_id, raw)
            eff, _floor = validate_chapter_depth(ch_id, injected, targets)
        except ValueError as e:
            thin = sorted(rows, key=lambda r: r["eff"])
            breakdown = "\n".join(f"  节 {r['id']}: eff {r['eff']}" for r in thin)
            errors.append(f"章 {ch_id}: {e}" + (f"\n{breakdown}" if breakdown and "L2" in str(e) else ""))
            continue
        if effective_chars(injected) < 1000:
            errors.append(f"章 {ch_id}: 章最小有效字符门 FAIL：{effective_chars(injected)} <1000（geo bug-2223 章级保留）")
            continue
        parts.append(injected)
        actual.append((ch_id, stage["chapters"][ch_id].get("title", ch_id)))
        toc_stats[ch_id] = {"title": stage["chapters"][ch_id].get("title", ch_id), "sections": len(rows), "effective_chars": eff}
        depth_rows.append(_depth_row(ch_id, injected, targets, bool(skip_l2 and ch_id in skip_l2)))
    errors.extend(validate_toc_chapters(stage, actual, absent_ch))
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
    if not isinstance(appr, list):
        raise ValueError(f"downgrade_approvals 结构损坏（手改特征）——progress.py 是唯一写者: {appr!r}")
    for a in appr:
        if not isinstance(a, dict) or not isinstance(a.get("chapters", []), list) or not all(isinstance(c, str) for c in a["chapters"]):
            raise ValueError(f"downgrade_approvals 结构损坏（手改特征）——progress.py 是唯一写者: {a!r}")
        out.update(a["chapters"])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 单次原子组装 + 章门（两层模型：节稿拼章稿）")
    p.add_argument("--stage", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--state-dir", required=True, help="state/（sections/ + chapters/ + formula_state.json + progress.json）")
    p.add_argument("--targets", help="章级深度基线 depth_targets/<stage>.json 路径（chapters[].floor_chars）；缺省探测技能基准，缺失走默认地板 30000——仅调试换基准")
    p.add_argument("--chapter", help="单章门模式：拼装该章节稿过全门（ch_id 如 ch6），不产交付物/不写 progress.json")
    p.add_argument("--allow-partial", action="store_true", help="分级交付：progress.json 已批准的 BLOCKED 章跳过 L2 章地板门（节级/目录/槽位门仍在场），manifest 留痕")
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
        targets, targets_src = resolve_targets(args.targets, Path(args.stage), data_dir=Path(args.data_dir))
        if args.chapter:
            run_chapter_gate(stage, Path(args.data_dir), Path(args.state_dir), args.chapter, targets)
            return EXIT_OK
        # ── bug-2223 交付名门：文件名规范 + outputs/ 无管线外散文件 ──
        out_path = Path(args.output)
        expected = expected_deliverable_name(stage, Path(args.data_dir))
        if out_path.name != expected:
            print(f"[build] 交付名门 FAIL: 输出 {out_path.name!r} ≠ 规范名 {expected!r}（{{项目名}}-{{阶段}}-环境影响报告.md，bug-2220/2223 同构）", file=sys.stderr)
            return EXIT_ERROR
        stray = sorted(pp.name for pp in out_path.parent.glob("*.md") if pp.name != out_path.name)
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
            skip_l2 = blocked  # 只放行 L2；节级/目录/槽位门在场；节稿缺失章仍由 assemble 硬 FAIL
            partial = {"downgrade_approvals": progress.get("downgrade_approvals", []), "chapter_depth": [], "downgraded": sorted(blocked)}
        depth_rows: list[dict] = partial["chapter_depth"] if partial is not None else []
        content, toc_stats = assemble(stage, Path(args.data_dir), Path(args.state_dir), targets=targets, skip_l2=skip_l2 or None, partial=partial, depth_rows=depth_rows)
        # ── bug-3036：consistency 合约门接入（geo 25 条 + 环评注册表在册自动启用）。
        # fail>0 则报告留盘但 manifest 不写——无清单 = 不可交付（bug-2225 凭据模型）。
        atomic_write(out_path, content)
        m_stale = out_path.parent / "delivery_manifest.json"
        if m_stale.exists():
            m_stale.unlink()
            print("[build] 已作废既有 delivery_manifest.json（报告重写中——旧凭据不得为未过门的新报告放行，bug-3059 同构）", file=sys.stderr)
        import consistency

        # 一致性检查输入 = 去附录正文（附录是脚本生成的结论页，不作为合约检查对象）——
        # geo bug-3058/3059 语义原样：固定检查同一份去附录正文 → 结果逐字节确定 → 收敛。
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
            CONTRACTS_PATH if CONTRACTS_PATH.exists() else None,
        )
        c_path.write_text(json.dumps(c_result, ensure_ascii=False, indent=2), encoding="utf-8")
        c_fails = [i for i in c_result["items"] if i["severity"] == "fail"]
        if c_fails:
            print(f"[build] 一致性合约门 FAIL（{len(c_fails)} 项，bug-3036 接入 consistency.py）:", file=sys.stderr)
            for i in c_fails:
                print(f"  [FAIL] {i['contract']}: {i['detail']}", file=sys.stderr)
            print(f"[build] 报告已落盘 {out_path} 但 delivery_manifest.json 不写——无清单=不可交付（bug-2225）；逐项修复后重跑", file=sys.stderr)
            return EXIT_ERROR
        c_manuals = [i for i in c_result["items"] if i["severity"] == "manual"]
        if c_manuals:
            print(f"[build] MANUAL_PENDING（{len(c_manuals)} 项需人工——交付前逐条核实；run-stage finalize 会以 rc=2 拦停）:", file=sys.stderr)
            for i in c_manuals[:10]:
                print(f"  [MANUAL] {i['contract']}: {i['detail']}", file=sys.stderr)
        # 附录此刻引用的 consistency_check.json 已是本次结果 → 重组装一次使附录与检查同源
        #（geo bug-3058：depth_rows 由引用传入且 assemble 逐章 append——不清空则两套）。
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
        # 基准溯源：正式交付只认技能 depth_targets 基线；他处基准=调试/绕门，事后可查（geo 线程 03e18e4a 伪造基准教训）
        "targets": {"path": str(targets_src), "sha256": sha256_file(targets_src) if targets_src.exists() else None},
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
    print(f"CONSISTENCY: pass {s.get('pass', 0)} / warn {s.get('warn', 0)} / manual {s.get('manual', 0)} / skip {s.get('skip', 0)} / fail 0（fail>0 已在上一步阻断）")
    if partial is not None:
        print(f"PARTIAL_DELIVERY: 分级交付 {len(partial['downgraded'])} 章降档 {partial['downgraded']}（深度未达标明细见 delivery_manifest.json → partial.chapter_depth，交付时向用户如实汇报）")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
