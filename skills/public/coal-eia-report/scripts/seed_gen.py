#!/usr/bin/env python3
"""coal-eia-report v2 — seed_gen.py：stage JSON → KF 模板 seed 单向生成（D12 章树供给）。

spec docs/designs/coal-eia-report-v2.md D12「章树供给与双源归一」：项目章树唯一生产者是
建项目时的 KF 模板导入（backend/app/extensions/project/service.py::_import_template_outline
递归 _create_from_section，读 root_sections_json.sections[].{title, purpose, generation_hint,
content_contract.min_word_count, children}；MCP 工具面无 create/move/delete 章）。
故树粒度问题在模板侧解决：本脚本从 stages/*.json 生成 KF 模板 seed（root_sections_json 树
+ content_contract），stage JSON 是唯一真源，模板是派生工件——消灭语义匹配承压（OV#2）。

seed 树形状（章=level1 → 节=level2，children 仅到节级，对齐 ProjectChapter 两层模型）：
  level1 章  title=章题 | purpose=首个 key_element 摘要 | generation_hint=key_elements+
             writing_patterns 合组 | content_contract.min_word_count=章基线地板
             （references/depth_targets/{stage_id}.json floor_chars，build_output L2 门同源）
  level2 节  title=节题 | purpose=elements 首条摘要 | generation_hint=elements 合组
             （逐条 verbatim）| content_contract.min_word_count=章地板按节要素链长度比例分摊
             （最大余数法，节和恰等于章地板）；conditional 节 required=false 并在 hint 前置
             条件声明（on_absent 语义由 stage 驱动，模板侧仅作提示）

边界（D12 拍板）：
  - **KF 三偏差不进 seed**——D3 的风险降节/补三章/仅适用标注是对既有 published
    「煤炭_环评报告_模板」的数据修正（走 KF 版本机制，另一条线）；本 seed 是
    planning 节级模板重生成 + underground 从无到有的单向派生工件。
  - min_word_count 单位=字符（平台事实：write_chapter 的 word_count_current=len(content)，
    与 depth_targets floor_chars 同量纲；KF 导入器缺省 3000 不适用节级粒度）。
  - 后端零改动：seed 经 KF 模板导入通道人工/API 落库（PUT /templates/{id} 的
    root_sections_json 或重建模板），导入建议值在 metadata.template。

CLI:
  python seed_gen.py gen [--stage references/stages/planning_eia.json]
                         --output state/kf_seed_planning_eia.json
                         [--depth-targets references/depth_targets/planning_eia.json]
  python seed_gen.py selfcheck --seed <seed.json> [--backend <backend目录>]
    装载冒烟：按平台真实消费方断言——_import_template_outline 读取契约（字段级）+
    knowledge_factory/schemas.TemplateSection 形状（能解析——backend 可寻址时直接
    file-load 真模型逐节点验证，不可寻址时按其 schema 字段断言并声明 SKIP）。

退出码：0 成功（selfcheck PASS）/ 1 用法错误、stage/depth_targets 缺字段、selfcheck FAIL。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
DEFAULT_STAGE = SKILL_ROOT / "references" / "stages" / "planning_eia.json"
# KF 真实消费方（平台侧，只读——本脚本零后端改动的证据即只 import 不修改）
KF_SCHEMAS = Path("app/extensions/knowledge_factory/schemas.py")

SLOT_TOKEN_RE = re.compile(r"\{\{[^}]*\}\}")


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def summarize(text: str, limit: int = 80) -> str:
    """首条要素 → 摘要：剥 {{SLOT/TABLE}} 令牌，取第一个句界（。；）内整句，超长截断。"""
    cleaned = SLOT_TOKEN_RE.sub("", text)
    cleaned = " ".join(cleaned.split())
    head = cleaned[:limit]
    cut = max(head.rfind("。"), head.rfind("；"), head.rfind(";"))
    if cut >= 20:
        return head[: cut + 1]
    return head.rstrip("，、（(") + ("……" if len(cleaned) > limit else "")


def largest_remainder(total: int, weights: list[int]) -> list[int]:
    """按权重分摊 total（整数，最大余数法）——份额和恒等于 total，无舍入漂移。"""
    wsum = sum(weights) or 1
    raw = [total * w / wsum for w in weights]
    base = [int(x) for x in raw]
    left = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:left]:
        base[i] += 1
    return base


def load_depth_targets(path: Path, stage_id: str) -> dict[str, int]:
    if not path.exists():
        print(f"SEED_ERROR: 深度基线不存在: {path}（--depth-targets 显式指定；floor 是 min_word_count 分摊真源，禁静默默认）")
        raise SystemExit(EXIT_ERROR)
    d = json.loads(path.read_text(encoding="utf-8"))
    chapters = d.get("chapters") or {}
    floors: dict[str, int] = {}
    for cid, c in chapters.items():
        floor = c.get("floor_chars")
        if not isinstance(floor, int) or floor <= 0:
            print(f"SEED_ERROR: depth_targets {cid}.floor_chars 缺失或非法: {floor!r}")
            raise SystemExit(EXIT_ERROR)
        floors[cid] = floor
    if not floors:
        print(f"SEED_ERROR: depth_targets 无 chapters 条目: {path}")
        raise SystemExit(EXIT_ERROR)
    return floors


def build_seed(stage: dict, stage_relpath: str, floors: dict[str, int], depth_relpath: str) -> tuple[dict, dict]:
    chapters = stage.get("chapters") or {}
    if not chapters:
        print("SEED_ERROR: stage JSON 无 chapters")
        raise SystemExit(EXIT_ERROR)

    sections_out: list[dict] = []
    total_floor = 0
    n_sections = 0
    for ch_id in chapter_order(chapters):
        ch = chapters[ch_id]
        floor = floors.get(ch_id)
        if floor is None:
            print(f"SEED_ERROR: depth_targets 缺章 {ch_id}（stage 与 depth_targets 失配——禁静默默认地板）")
            raise SystemExit(EXIT_ERROR)
        total_floor += floor
        key_elements = [str(x) for x in ch.get("key_elements", [])]
        hints = [f"- {e}" for e in key_elements] + [f"- {p}" for p in ch.get("writing_patterns", [])]
        children: list[dict] = []
        secs = ch.get("sections", [])
        shares = largest_remainder(floor, [max(len(s.get("elements", [])), 1) for s in secs]) if secs else []
        for s, share in zip(secs, shares):
            n_sections += 1
            elements = [str(e) for e in s.get("elements", [])]
            hint_lines: list[str] = []
            cond = s.get("conditional")
            if cond:
                hint_lines.append(
                    f"【条件节 driver={cond.get('driver', '?')} type={cond.get('type', '?')}】"
                    f"{cond.get('title_rule', '')} {cond.get('on_absent', '')}".strip()
                )
            hint_lines += [f"- {e}" for e in elements]
            children.append(
                {
                    "id": s.get("id", ""),
                    "title": s.get("title", ""),
                    "level": 2,
                    "required": cond is None,
                    "purpose": summarize(elements[0]) if elements else None,
                    "generation_hint": "\n".join(hint_lines) or None,
                    "content_contract": {"min_word_count": share},
                }
            )
        sections_out.append(
            {
                "id": ch_id,
                "title": ch.get("title", ch_id),
                "level": 1,
                "required": True,
                "purpose": summarize(key_elements[0]) if key_elements else None,
                "generation_hint": "\n".join(hints) or None,
                "content_contract": {"min_word_count": floor, "key_elements": key_elements},
                "children": children,
            }
        )

    stage_id = stage.get("stage_id", "")
    seed = {
        "kind": "kf_template_seed",
        "metadata": {
            "stage": stage.get("stage", ""),
            "stage_id": stage_id,
            "std_ref": stage.get("std_ref", ""),
            "generated_from": stage_relpath,
            "depth_targets_from": depth_relpath,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "totals": {"chapters": len(sections_out), "sections": n_sections, "floor_chars_total": total_floor},
            "scope_note": "D12 单向派生工件：stage JSON 唯一真源；D3 三偏差（既有 published 模板数据修正）不在本 seed 内",
        },
        "template": {
            "domain": stage_id,
            "name": f"煤矿{stage.get('stage', '')}报告模板（节级·seed 生成）",
            "version": "v1.0",
            "status": "draft",
        },
        "root_sections_json": {"sections": sections_out},
    }
    stats = {"chapters": len(sections_out), "sections": n_sections, "total_floor": total_floor}
    return seed, stats


# ── selfcheck：最小装载冒烟（平台消费方契约断言）──

IMPORTER_FIELDS = ("title", "purpose", "generation_hint")  # _import_template_outline 逐字段读取
TEMPLATE_SECTION_FIELDS = {
    "id", "title", "level", "required", "purpose", "children", "content_contract",
    "generation_hint", "example_snippet", "full_section_example", "compliance_rules",
    "rag_sources", "table_schemas", "figure_requirements", "formula_references",
    "calc_script_bindings", "sub_section_profile",
}


def selfcheck(seed_path: Path, backend_dir: Path | None) -> int:
    assertions = 0
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    sections = seed.get("root_sections_json", {}).get("sections")
    assert isinstance(sections, list) and sections, "root_sections_json.sections 必须为非空数组"
    assertions += 1

    floors: dict[str, int] = {}
    for sec in sections:
        assertions += _check_node(sec, depth=1, floors=floors)
    assertions += 1

    # 章地板合计与 metadata 自洽
    totals = seed.get("metadata", {}).get("totals", {})
    assert totals.get("floor_chars_total") == sum(floors.values()), "metadata.totals.floor_chars_total 与树内分摊和不符"
    assert totals.get("sections") == sum(len(s.get("children", [])) for s in sections), "metadata.totals.sections 与叶数不符"
    assertions += 2

    # 真模型装载（backend 可寻址时）：file-load knowledge_factory/schemas.TemplateSection
    # （schemas.py 仅依赖 pydantic+stdlib，可脱离 app 包独立加载；app/__init__ 链会拉 deerflow，
    #  故不走包导入）。失败即 rc=1——能被平台解析是 seed 的成立条件，不是可选项。
    candidate = (backend_dir / KF_SCHEMAS) if backend_dir else None
    if candidate and candidate.exists():
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("coal_eia_kf_schemas", candidate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for sec in sections:
                children = sec.pop("children", [])
                mod.TemplateSection(**sec)
                for child in children:
                    mod.TemplateSection(**child)
            assertions += len(sections) * 2
            print(f"SEED_PYDANTIC: TemplateSection 真模型验证 PASS（{len(sections)} 章 + 各章节逐节点）")
        except Exception as e:  # 宿主缺 pydantic 等环境限制 → 降级为 schema 字段断言，不静默
            print(f"SEED_PYDANTIC: SKIP（真模型装载不可用: {type(e).__name__}: {e}——按 TemplateSection schema 字段断言 {assertions} 项）")
    else:
        print(f"SEED_PYDANTIC: SKIP（backend 不在 {backend_dir or '(未推断)'}——已按 TemplateSection schema 字段断言 {assertions} 项）")

    print(f"SEED_SELFCHECK: PASS {seed_path}（{assertions} assertions, {len(sections)} 章 {sum(floors.values())} floor_chars）")
    return assertions


def _check_node(sec: dict, depth: int, floors: dict[str, int]) -> int:
    n = 0
    assert isinstance(sec.get("id"), str) and sec["id"], f"节点缺 id: {sec!r:.120}"
    assert isinstance(sec.get("title"), str) and sec["title"], f"{sec['id']}: title 必须非空字符串"
    assert sec.get("level") == depth, f"{sec['id']}: level 应为 {depth}"
    assert set(sec) <= TEMPLATE_SECTION_FIELDS, f"{sec['id']}: 超出 TemplateSection 字段集 {sorted(set(sec) - TEMPLATE_SECTION_FIELDS)}"
    for f in IMPORTER_FIELDS:  # _import_template_outline 直读字段的类型契约
        assert sec.get(f) is None or isinstance(sec.get(f), str), f"{sec['id']}: {f} 必须 str|None"
    cc = sec.get("content_contract")
    assert isinstance(cc, dict) and isinstance(cc.get("min_word_count"), int) and cc["min_word_count"] > 0, (
        f"{sec['id']}: content_contract.min_word_count 必须为正整数（KF 导入器直读；缺省 3000 不可依赖）"
    )
    n += 4
    children = sec.get("children", [])
    if depth == 1:
        assert isinstance(children, list) and children, f"{sec['id']}: 章必须带节级 children（两层模型，禁裸章）"
        floors[sec["id"]] = cc["min_word_count"]
        child_sum = 0
        for child in children:
            n += _check_node(child, depth + 1, floors)
            child_sum += child["content_contract"]["min_word_count"]
        assert child_sum == cc["min_word_count"], (
            f"{sec['id']}: 节地板和 {child_sum} != 章地板 {cc['min_word_count']}（最大余数分摊必须守恒）"
        )
        n += 1
    else:
        assert not children, f"{sec['id']}: children 仅到节级（D6 交付=节级叶子）"
        n += 1
    return n


def rel_to_skill(p: Path) -> str:
    try:
        return p.resolve().relative_to(SKILL_ROOT).as_posix()
    except ValueError:
        return str(p.resolve())


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — stage JSON → KF 模板 seed 单向生成（D12）")
    sub = p.add_subparsers(dest="cmd")

    g = sub.add_parser("gen", help="生成 KF 模板 seed JSON + 自动装载冒烟")
    g.add_argument("--stage", default=str(DEFAULT_STAGE), help="stage JSON（默认 references/stages/planning_eia.json）")
    g.add_argument("--output", required=True, help="seed 输出路径")
    g.add_argument("--depth-targets", default=None, help="深度基线（默认 references/depth_targets/{stage_id}.json）")
    g.add_argument("--backend", default=None, help="backend 目录（selfcheck 真模型装载；默认按仓库布局推断）")
    g.set_defaults(func=cmd_gen)

    c = sub.add_parser("selfcheck", help="对已生成 seed 跑装载冒烟（平台消费方契约断言）")
    c.add_argument("--seed", required=True)
    c.add_argument("--backend", default=None)
    c.set_defaults(func=cmd_selfcheck)

    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help()
        return EXIT_ERROR
    return args.func(args)


def _infer_backend(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    # 技能脚本位于 <repo>/skills/public/coal-eia-report/scripts → 仓库根上溯 4 级
    root = SKILL_ROOT.parent.parent.parent
    cand = root / "backend"
    return cand if (cand / KF_SCHEMAS).exists() else None


def cmd_gen(args: argparse.Namespace) -> int:
    stage_path = Path(args.stage)
    if not stage_path.exists():
        print(f"SEED_ERROR: stage 文件不存在: {stage_path}")
        return EXIT_ERROR
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    stage_id = stage.get("stage_id") or stage_path.stem
    dt_path = Path(args.depth_targets) if args.depth_targets else SKILL_ROOT / "references" / "depth_targets" / f"{stage_id}.json"
    floors = load_depth_targets(dt_path, stage_id)

    seed, stats = build_seed(stage, rel_to_skill(stage_path), floors, rel_to_skill(dt_path))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)  # 原子写（progress/snapshot 同款 tmp+replace）

    print(f"SEED_READY: stage={seed['metadata']['stage']}({stage_id}) chapters={stats['chapters']} sections={stats['sections']}")
    print(f"SEED_FLOOR: total_floor_chars={stats['total_floor']}（分摊守恒：Σ节=Σ章，depth_targets={rel_to_skill(dt_path)}）")
    print(f"SEED_FILE: {out}")

    n_asserts = run_selfcheck(out, _infer_backend(args.backend))
    # selfcheck 返回断言数；0 = 冒烟未执行任何断言 → 失败（seed 不允许无验证落盘）
    return EXIT_OK if n_asserts > 0 else EXIT_ERROR


def run_selfcheck(seed_path: Path, backend_dir: Path | None) -> int:
    try:
        return selfcheck(seed_path, backend_dir)
    except AssertionError as e:
        print(f"SEED_SELFCHECK: FAIL — {e}")
        return 0


def cmd_selfcheck(args: argparse.Namespace) -> int:
    seed_path = Path(args.seed)
    if not seed_path.exists():
        print(f"SEED_ERROR: seed 文件不存在: {seed_path}")
        return EXIT_ERROR
    n = run_selfcheck(seed_path, _infer_backend(args.backend))
    return EXIT_OK if n > 0 else EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
