#!/usr/bin/env python3
"""geological-report v2 — chapter_planner.py：章节清单 + 「改参 → 受影响章节」反查中枢。

manifest 生成不再硬编码章节（water 版教训）：直接由 references/stages/{stage}.json 的
chapters（每章 forms/formulas/contracts 声明）驱动。两类伪章节追加：
  front_matter      前置部分（表单渲染，零 LLM）
  compliance_appendix 合规性附录（consistency_check.json 渲染——引用全量公式与合约，
                      任一公式输出变化必受影响，bug-2199 同构）

合约 → 公式覆盖表（CONTRACT_FORMULA_REFS）来自 ch8 走查 §4 与 exploration.json 章级
contracts 声明：XS2（资源量数字族）把 L8-L12 链到 ch1/ch4/ch9/ch10——这是 SC-3
「改小体重 D → impacted ⊇ {ch1,ch4,ch8,ch9,ch10}+附录」的机制来源。

CLI:
  manifest --stage references/stages/exploration.json --output state/chapter_manifest.json
  prompt   --stage references/stages/exploration.json --chapter ch4 --data-dir data/
           --state-dir state [--bank-limit 2000] [--output state/dispatch_ch4.md]
           派发契约内联渲染（硬化 2026-11）：toc 骨架 + 逐节 elements 要点 + 黄金范文切片
           （bank_index 同矿种优先）+ 槽位词汇表 + rubric + 输出契约，全部喂进子代理
           prompt——不再依赖沙箱自读 references（路径不可达时任务面仍完整）。
  impacted --manifest state/chapter_manifest.json --formulas L8,L9 [--families 13a]
       --formulas: 受影响公式 id 逗号清单（formula_runner impacted 的输出直接喂入）
       --families: 受影响表单族名（非公式数据变更路径，如 04_geography 文本改动）
输出打印 IMPACTED_READY + JSON；退出码 0/1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 全量依赖伪章节：任一公式/表单变化都必受影响
ALWAYS_DEPENDENT = ("ch10", "compliance_appendix")

# 与 build_output.MINERAL_ALIASES 同步维护（六处变更面清单；此处仅用于范文切片选源归一化）
_MINERAL_ALIASES = [("copper", ("铜",)), ("coal", ("煤",)), ("gold", ("金",)),
                    ("iron", ("铁",)), ("lead_zinc", ("铅锌", "铅", "锌"))]

# 合约 → 其校验/引用的公式族（exploration.json 章级 contracts 声明的反向边）
CONTRACT_FORMULA_REFS: dict[str, list[str]] = {
    "XS2": ["L7", "L8", "L9", "L10", "L11", "L12"],   # 资源量数字族（表8-2 同源槽位）
    "XS1": ["L3", "L4"],                              # 矿体参数统计
    "FC1": ["L9"],
    "FC2": ["L10"],
    "FC3": ["S1"],
    "FC4": ["C9"],
    "FC5": ["L12"],
    "FC6": ["L11"],
    "FC7": ["E1", "E2", "E3", "E4", "E5", "E6", "E7"],
    "FC8": ["L13"],
    "B1C": ["B1"],
    "CC1": ["S2"],
}


def build_manifest(stage: dict) -> dict:
    chapters = []
    for ch_id, ch in stage.get("chapters", {}).items():
        chapters.append({
            "id": ch_id,
            "title": ch.get("title", ch_id),
            "type": "narrative" if ch_id.startswith("ch") and ch_id != "ch10" else ("projection" if ch_id == "ch10" else "narrative"),
            "formula_ids": list(ch.get("formulas", [])),
            "contract_ids": list(ch.get("contracts", [])),
            "form_families": list(ch.get("forms", [])),
        })
    chapters.insert(0, {
        "id": "front_matter", "title": "前置部分", "type": "table",
        "formula_ids": [], "contract_ids": ["NR3"],
        "form_families": ["figures_tables", "project"],
    })
    chapters.append({
        "id": "compliance_appendix", "title": "合规性附录", "type": "table",
        "formula_ids": [], "contract_ids": [], "form_families": [],
        "always_dependent": True,
    })
    # 每章追加合约反查到的公式（formula_ids ∪ contracts 覆盖的公式）
    for ch in chapters:
        extra = set()
        for cid in ch["contract_ids"]:
            extra.update(CONTRACT_FORMULA_REFS.get(cid, []))
        for f in sorted(extra):
            if f not in ch["formula_ids"]:
                ch["formula_ids"].append(f)
        if ch["id"] == "ch10":
            ch.setdefault("always_dependent", True)
    return {"version": 2, "always_dependent": list(ALWAYS_DEPENDENT), "chapters": chapters}


def impacted_chapters(affected_formulas: list[str], affected_families: list[str], manifest: dict) -> list[str]:
    """反查受影响章节 id（去重保序）。ch10/compliance_appendix 只要非空影响集就追加。"""
    hit: list[str] = []
    formulas = set(affected_formulas)
    families = set(affected_families)
    any_hit = bool(formulas or families)
    for ch in manifest.get("chapters", []):
        fids = set(ch.get("formula_ids", []))
        fams = set(ch.get("form_families", []))
        cids = set(ch.get("contract_ids", []))
        via_contract = any(
            formulas & set(CONTRACT_FORMULA_REFS.get(cid, [])) for cid in cids
        )
        if (formulas & fids) or (families & fams) or via_contract:
            if ch["id"] not in hit:
                hit.append(ch["id"])
    if any_hit:
        for cid in manifest.get("always_dependent", ALWAYS_DEPENDENT):
            if cid not in hit:
                hit.append(cid)
    return hit


def _norm_mineral(commodity):
    """中文 commodity → slug（最早出现位置=主矿种在前；「金属」负向守卫同 build_output）。"""
    if not commodity:
        return None
    s = str(commodity).strip()
    if "非金属" in s:
        return None
    best = None
    for slug, keys in _MINERAL_ALIASES:
        for k in keys:
            pos = s.find(k)
            if pos == -1:
                continue
            if k == "金" and pos + 1 < len(s) and s[pos + 1] == "属":
                continue
            if best is None or pos < best[0]:
                best = (pos, slug)
    return best[1] if best else None


_RUBRIC = """## 写作 rubric（质量在派发时给定，不靠事后字符数门兜底）
- 逐要素成段：下方「逐节内容要点」每个要素 ≥1 段完整专业叙述（定性描述+空间关系+工程意义）；缺数写 [待确认] 占位句，不砍段、不删节、不并节
- 表后五步解读：陈述→规律识别→成因解释→规范对比→勘查意义（规范编号只从 standards_index 实有编号引）
- 数值纪律：正文数值只写 {{SLOT:key}}（词汇表见下），数据表只写 {{TABLE:族}}；范文数值/矿名/地名一律禁抄进正文（只学叙述范式）；真数永不手写
- 判定词（水文/工程/环境/复合类型等）逐字写入正文
- 结构纪律：首行 `## N 章标题`；toc 骨架全覆盖禁自创/并节；复合条目子节号用 #### 标题"""


def build_dispatch_prompt(stage_path, chapter_id, data_dir, state_dir, bank_limit=2000):
    """渲染第 chapter_id 章的内联派发 prompt（纯 stdlib；缺文件逐段降级不致命）。"""
    stage = json.loads(Path(stage_path).read_text(encoding="utf-8"))
    ch = stage.get("chapters", {}).get(chapter_id)
    if not ch:
        sys.stderr.write(f"[planner] 错误: 未知章节 {chapter_id}（stage 在册: {sorted(stage.get('chapters', {}))}）\n")
        raise SystemExit(1)
    no = chapter_id[2:] if chapter_id.startswith("ch") else chapter_id
    refs_dir = Path(stage_path).resolve().parents[1]
    lines = [
        f"# 第 {no} 章撰写任务（geological-report v2 · 派发契约内联版）",
        "",
        f"角色：第 {no} 章撰写者，只产出这一章。本 prompt 已内联全部任务面，不依赖沙箱自读 references（路径不可达时任务仍完整可执行）。",
        "",
        "## 本章目录骨架（硬门：节号必须全覆盖；禁自创节/并节）",
    ]
    lines += [f"- {t}" for t in ch.get("toc", [])]
    lines += ["", "## 逐节内容要点（每节按 elements 逐要素成段）"]
    for sec in ch.get("sections", []):
        lines.append(f"### {sec.get('title', '')}")
        for el in sec.get("elements", []):
            lines.append(f"- {el if isinstance(el, str) else json.dumps(el, ensure_ascii=False)}")
    lines += ["", _RUBRIC]
    # ── 黄金范文切片（bank 同矿种优先 → bank 任一 → 手工样例回退 → 无）──
    lines += ["", "## 黄金范文切片（只学叙述范式；数值/矿名/地名一律禁抄）"]
    mineral = None
    if data_dir:
        proj = Path(data_dir) / "00_project.json"
        if proj.exists():
            try:
                mineral = _norm_mineral(json.loads(proj.read_text(encoding="utf-8")).get("commodity"))
            except (OSError, ValueError):
                mineral = None
    stage_key = Path(stage_path).stem
    entry = None
    bi = refs_dir / "samples_bank" / "bank_index.json"
    if bi.exists():
        try:
            entries = json.loads(bi.read_text(encoding="utf-8")).get(stage_key, {}).get(chapter_id, [])
        except (OSError, ValueError):
            entries = []
        for e in entries:  # 同矿种优先
            if mineral and e.get("mineral") == mineral and (refs_dir / e.get("file", "")).exists():
                entry = e
                break
        if entry is None:
            entry = next((e for e in entries if (refs_dir / e.get("file", "")).exists()), None)
    slice_text = ""
    if entry:
        p = refs_dir / entry["file"]
        slice_text = p.read_text(encoding="utf-8")
        note = f"范文来源: {entry['file']}（mineral={entry.get('mineral')}" + ("；同矿种命中）" if mineral and entry.get("mineral") == mineral else "；跨矿种回退——范式更须谨慎对齐本章矿种术语）")
    else:
        p = refs_dir / "samples" / stage_key / f"{chapter_id}_sample.md"
        if p.exists():
            slice_text = p.read_text(encoding="utf-8")
            note = f"范文来源: samples/{stage_key}/{chapter_id}_sample.md（bank 无切片，手工样例回退）"
        else:
            note = "（无范文切片——按目录骨架与逐节要点独立成文，禁引入任何外部项目内容）"
    if slice_text:
        if len(slice_text) > bank_limit:
            slice_text = slice_text[:bank_limit] + "\n…（切片超限截断——完整范文可自读该文件，仅补范式不作依据）"
        lines.append(note)
        lines.append("")
        lines.append(slice_text)
    else:
        lines.append(note)
    # ── 槽位词汇表 ──
    lines += ["", "## 槽位词汇表（正文数值只写 {{SLOT:key}}；本表=可写数值的全部合法来源）"]
    values = {}
    if state_dir:
        fs = Path(state_dir) / "formula_state.json"
        if fs.exists():
            try:
                values = json.loads(fs.read_text(encoding="utf-8")).get("values", {})
            except (OSError, ValueError):
                values = {}
    if not values:
        lines.append("- （formula_state 不在/为空——冻结层尚未生成；本章数值一律 [待确认]，禁自算禁手写）")
    else:
        for k, v in list(values.items())[:60]:
            unit = str((v or {}).get("unit") or "")
            lines.append(f"- {k}" + (f"（{unit}）" if unit else ""))
        if len(values) > 60:
            lines.append(f"- …共 {len(values)} 槽位，其余自读 formula_state.json（只读，禁改）")
    lines += [
        "",
        "## 深度口径（硬化 2026-11 分级）",
        "- 绝对地板（median×0.4）= 硬 FAIL，低于即整章打回；风格拉伸（median×0.6×覆盖缩放）不足只 STYLE_WARN 不阻断",
        "- 要素链逐段写满自然达标——禁为凑字符重复套话（重复段落会被盯防）",
        "",
        "## 输出契约",
        f"- 直写 /mnt/user-data/workspace/geo-report/state/chapters/{chapter_id}.md（绝对沙箱路径；容器路径以挂载为准）",
        f"- 首行 `## {no} {ch.get('title', '')}`；缺数标 [待确认]/[数据未提供]",
        "- 返回 ≤10 行摘要：结构 / [待确认] 清单 / 数据缺口 / 本章要点 3-5 条（供要点包蒸馏）",
        "- 禁令：不改 data/、不碰 references/、不跑 build、不派 task",
        "",
        "## 补充自读（可选——读不到不影响本任务）",
        "- state/formula_state.json（完整槽位表）· references/chapter_craft.md（写作工艺）· references/samples_bank/bank_index.json",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 章节规划器")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("manifest", help="由 stage 模板生成 chapter_manifest.json")
    m.add_argument("--stage", required=True)
    m.add_argument("--output", required=True)

    i = sub.add_parser("impacted", help="受影响公式/表单族 → 受影响章节反查")
    i.add_argument("--manifest", required=True)
    i.add_argument("--formulas", default="", help="逗号分隔公式 id")
    i.add_argument("--families", default="", help="逗号分隔表单族名")
    i.add_argument("--output", help="结果 JSON 落盘路径（可选）")

    d = sub.add_parser("prompt", help="派发契约内联渲染（toc+要点+范文切片+槽位表+rubric）")
    d.add_argument("--stage", required=True)
    d.add_argument("--chapter", required=True, help="章节 id（如 ch4）")
    d.add_argument("--data-dir", help="data/（读 00_project.commodity 选同矿种范文）")
    d.add_argument("--state-dir", help="state/（读 formula_state.json 出槽位词汇表）")
    d.add_argument("--bank-limit", type=int, default=2000, help="范文切片截断字符数")
    d.add_argument("--output", help="prompt 落盘路径（缺省打印 stdout）")

    args = p.parse_args()
    if args.command == "manifest":
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        manifest = build_manifest(stage)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"MANIFEST_READY: {args.output} chapters={len(manifest['chapters'])}")
        return 0

    if args.command == "prompt":
        text = build_dispatch_prompt(args.stage, args.chapter, args.data_dir, args.state_dir, args.bank_limit)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"PROMPT_READY: {args.output} chars={len(text)}")
        else:
            sys.stdout.write(text)
        return 0

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    formulas = [x for x in args.formulas.split(",") if x.strip()]
    families = [x for x in args.families.split(",") if x.strip()]
    result = {
        "affected_formulas": formulas,
        "affected_families": families,
        "affected_chapters": impacted_chapters(formulas, families, manifest),
    }
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"IMPACTED_READY: {args.output}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
