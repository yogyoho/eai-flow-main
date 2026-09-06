#!/usr/bin/env python3
"""coal-eia-report v2 — chapter_planner.py：节清单 manifest + 节级依赖清单编译 + 「改参 → 受影响节」反查中枢。

两层模型改造点（spec docs/designs/coal-eia-report-v2.md「两层模型改造点清单」+ D11）：

  manifest  由 references/stages/{stage}.json 生成节清单 manifest（state/chapter_manifest.json，
            v3 形状）：chapters[] 每章带 sections[]（全部节 id/title/uses/forms/formulas/
            contracts/slots），另有扁平 sections[]（id/title/chapter——「全部节 id/title/所属章」
            的直接索引）。伪章节沿用 geo：front_matter / compliance_appendix；投影章（要点包
            投影结论章）= 最后一个数值章（planning 即 ch13），不再硬编码 ch10（water 版教训：
            章集由 stage 驱动，不写死）。
  deps      解析 sections[].uses{slots/formulas/contracts} 结构化引用（D11）+ 各节自身
            forms/formulas/contracts/slots 声明字段，编译节级依赖清单
            （state/dependency_manifest.json，派生工件可随时重生成）：
              消费反向索引 consumers:  slot/formula/contract → 消费节 id 清单（uses 引用边）
              提供正向索引 owners:     slot/formula/contract → 声明节/章 id 清单
            并 lint：
              orphan_contracts   孤儿合约（章节 contracts 声明在册但零 uses 消费）
              dangling_slots     悬空槽位（uses 引用但无任何节/章 slots 声明=无生产者）
              dangling_formulas  悬空公式（同构——uses 引用但无声明）
            声明/消费语义：节 X 的 forms/formulas/contracts/slots 字段 = X 拥有/产出这些；
            节 X 的 uses.* = X 消费别处产出的这些。改参反查的受影响节 = owners ∪ consumers
            （生产节与消费节都须重生成）。
  impacted  受影响公式/表单族/槽位/合约 → 受影响节集合（沿依赖清单反查，SC#4 落地路径）；
            无 --deps 时退化为章级反查（chapters 的 formula/form 声明交集）再展开到节。

CLI:
  manifest  --stage references/stages/planning_eia.json --output state/chapter_manifest.json
  deps      --stage … --output state/dependency_manifest.json
  impacted  --manifest state/chapter_manifest.json [--deps state/dependency_manifest.json]
            [--formulas L8,L9] [--families 13a] [--slots cap.total_scale] [--contracts XS1]

退出码：0 成功（deps 的 lint 发现只打印 LINT_* 行不阻断——派生工件诊断，非门）。
impacted 兼容：geo 形状 impacted_chapters(formulas, families, manifest) 保留（formula_runner
cmd_impacted 直接调用），v3 manifest 章级 formula_ids/form_families 字段不变。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 全量依赖伪章节：任一公式/表单变化都必受影响（geo 沿用；投影章运行时动态追加）
APPENDIX_ID = "compliance_appendix"

# 合约 → 其校验/引用的公式族：geo 的硬编码反向边。EIA 侧该关系由 stage sections 的
# uses{formulas/contracts} 结构化引用声明（D11），本表留空作兼容占位（手工补录通道仍在）。
CONTRACT_FORMULA_REFS: dict[str, list[str]] = {}


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def projection_chapter(stage: dict) -> str | None:
    """投影章 = 最后一个数值章（wave2 要点包投影结论章；planning=ch13）。无数值章 → None。"""
    nums = [c for c in stage.get("chapters", {}) if c[2:].isdigit()]
    return max(nums, key=lambda c: int(c[2:])) if nums else None


def iter_stage_sections(stage: dict):
    """(章id, 章title, 节dict) 全量遍历（stage 数值章序）。"""
    for ch_id in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][ch_id]
        for s in ch.get("sections", []):
            yield ch_id, ch.get("title", ch_id), s


def build_manifest(stage: dict) -> dict:
    """stage JSON → v3 节清单 manifest（章带节子表 + 扁平节索引）。

    节条目原样携带 uses/forms/formulas/contracts/slots 声明（deps 编译与派发契约注入的事实源）。
    """
    proj = projection_chapter(stage)
    chapters: list[dict] = []
    flat: list[dict] = []
    for ch_id in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][ch_id]
        if ch_id == proj:
            ch_type = "projection"
        elif ch_id.startswith("ch") and ch_id[2:].isdigit():
            ch_type = "narrative"
        else:
            ch_type = "narrative"
        sections = [
            {
                "id": s.get("id", ""),
                "title": s.get("title", ""),
                "forms": list(s.get("forms", [])),
                "formulas": list(s.get("formulas", [])),
                "contracts": list(s.get("contracts", [])),
                "slots": list(s.get("slots", [])),
                "uses": {k: list(v) for k, v in (s.get("uses") or {}).items()},
            }
            for s in ch.get("sections", [])
        ]
        for s in sections:
            flat.append({"id": s["id"], "title": s["title"], "chapter": ch_id, "chapter_title": ch.get("title", ch_id)})
        chapters.append({
            "id": ch_id,
            "title": ch.get("title", ch_id),
            "type": ch_type,
            "optional": bool(ch.get("optional")),
            "formula_ids": list(ch.get("formulas", [])),
            "contract_ids": list(ch.get("contracts", [])),
            "form_families": list(ch.get("forms", [])),
            "sections": sections,
        })
    chapters.insert(0, {
        "id": "front_matter", "title": "前置部分", "type": "table",
        "formula_ids": [], "contract_ids": [], "form_families": ["project"], "sections": [],
    })
    chapters.append({
        "id": APPENDIX_ID, "title": "合规性附录", "type": "table",
        "formula_ids": [], "contract_ids": [], "form_families": [], "sections": [],
        "always_dependent": True,
    })
    always = [c for c in (proj,) if c] + [APPENDIX_ID]
    return {
        "version": 3,
        "stage": stage.get("stage", ""),
        "projection_chapter": proj,
        "always_dependent": always,
        "chapters": chapters,
        "sections": flat,
    }


def _add(index: dict, key: str, owner: str) -> None:
    if not key:
        return
    lst = index.setdefault(key, [])
    if owner not in lst:
        lst.append(owner)


def compile_deps(stage: dict) -> dict:
    """stage JSON → 节级依赖清单（D11 派生工件）。

    consumers[x]：消费 x 的节 id（uses 引用边——改 x 影响谁）。
    owners[x]：声明/产出 x 的节或章 id（声明字段 forms/formulas/contracts/slots；
              章级声明 owner=章 id，反查时展开为该章全部节）。
    lint：orphan_contracts / dangling_slots / dangling_formulas（发现只报告不阻断）。
    """
    consumers: dict[str, list[str]] = {"slots": {}, "formulas": {}, "contracts": {}}
    owners: dict[str, list[str]] = {"slots": {}, "formulas": {}, "contracts": {}}

    def decl(items, owner: str, kind: str) -> None:
        for x in items or []:
            _add(owners[kind], str(x), owner)

    def use(items, consumer: str, kind: str) -> None:
        for x in items or []:
            _add(consumers[kind], str(x), consumer)

    for ch_id in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][ch_id]
        # 章级声明（owner=章 id——反查时由调用方展开为该章全部节；forms 是表单族，
        # 走 manifest 章 form_families 索引，不入 slots/formulas/contracts 三索引）
        for kind in ("slots", "formulas", "contracts"):
            decl(ch.get(kind), ch_id, kind)
        for _cid, _ct, s in iter_stage_sections(stage):
            if _cid != ch_id:
                continue
            sid = s.get("id", "")
            for kind in ("slots", "formulas", "contracts"):
                decl(s.get(kind), sid, kind)
            uses = s.get("uses") or {}
            for kind in ("slots", "formulas", "contracts"):
                use(uses.get(kind), sid, kind)
    lint = {
        "orphan_contracts": sorted(k for k, v in owners["contracts"].items() if not consumers["contracts"].get(k)),
        "dangling_slots": sorted(k for k, v in consumers["slots"].items() if not owners["slots"].get(k)),
        "dangling_formulas": sorted(k for k, v in consumers["formulas"].items() if not owners["formulas"].get(k)),
    }
    return {
        "version": 1,
        "stage": stage.get("stage", ""),
        "derived": True,
        "note": "派生工件（chapter_planner deps 可随时重生成，禁手编）；owners=声明/产出方（节或章 id），consumers=uses 消费节",
        "owners": owners,
        "consumers": consumers,
        "lint": lint,
    }


def _sections_of_chapter(manifest: dict, ch_id: str) -> list[str]:
    for ch in manifest.get("chapters", []):
        if ch.get("id") == ch_id:
            return [s.get("id", "") for s in ch.get("sections", []) if s.get("id")]
    return []


def impacted_sections(
    affected_formulas: list[str],
    affected_families: list[str],
    manifest: dict,
    deps: dict | None = None,
    affected_slots: list[str] | None = None,
    affected_contracts: list[str] | None = None,
) -> dict:
    """受影响公式/表单族/槽位/合约 → 受影响**节**集合（去重保序）+ 受影响章集合。

    deps 在场：沿节级依赖清单精确反查（owners ∪ consumers；章级 owner 展开为该章全部节）；
    缺 deps：退化为章级反查（chapters 声明交集 + 合约→公式覆盖表）再整章展开到节。
    任一非空影响集追加 always_dependent（投影章=结论 + 合规性附录；geo ch10 语义）。
    """
    formulas = set(affected_formulas)
    families = set(affected_families)
    slots = set(affected_slots or [])
    contracts = set(affected_contracts or [])
    any_hit = bool(formulas or families or slots or contracts)

    hits: list[str] = []

    def push(x: str) -> None:
        if x and x not in hits:
            hits.append(x)

    if deps:
        for kind, keys in (("formulas", formulas), ("slots", slots), ("contracts", contracts)):
            for k in keys:
                for owner in deps.get("owners", {}).get(kind, {}).get(k, []):
                    if owner.startswith("ch") and "_S" not in owner:
                        for sid in _sections_of_chapter(manifest, owner):
                            push(sid)
                    else:
                        push(owner)
                for consumer in deps.get("consumers", {}).get(kind, {}).get(k, []):
                    push(consumer)
        for fam in families:  # 表单族：声明章/节为主（manifest form_families）
            for ch in manifest.get("chapters", []):
                if fam in set(ch.get("form_families", [])):
                    for sid in _sections_of_chapter(manifest, ch["id"]) or [ch["id"]]:
                        push(sid)
    else:
        # 章级退化路径（沿 geo 语义）：章声明交集 → 整章展开
        for ch in manifest.get("chapters", []):
            fids = set(ch.get("formula_ids", []))
            fams = set(ch.get("form_families", []))
            cids = set(ch.get("contract_ids", []))
            via_contract = any(formulas & set(CONTRACT_FORMULA_REFS.get(cid, [])) for cid in cids)
            if (formulas & fids) or (families & fams) or (contracts & cids) or via_contract:
                for sid in _sections_of_chapter(manifest, ch["id"]) or [ch["id"]]:
                    push(sid)
                if not ch.get("sections"):
                    push(ch["id"])

    if any_hit:
        for cid in manifest.get("always_dependent", [APPENDIX_ID]):
            push(cid)
            for sid in _sections_of_chapter(manifest, cid):
                push(sid)

    ch_of: dict[str, str] = {}
    for s in manifest.get("sections", []):
        ch_of[s.get("id", "")] = s.get("chapter", "")
    affected_sections = [x for x in hits if x in ch_of or "_S" in x]
    affected_chapters: list[str] = []
    for x in hits:
        c = ch_of.get(x, x if x.startswith("ch") or x == APPENDIX_ID else None)
        if c and c not in affected_chapters:
            affected_chapters.append(c)
    return {
        "affected_formulas": sorted(formulas),
        "affected_families": sorted(families),
        "affected_slots": sorted(slots),
        "affected_contracts": sorted(contracts),
        "affected_sections": affected_sections,
        "affected_chapters": affected_chapters,
        "deps_mode": bool(deps),
    }


def impacted_chapters(affected_formulas: list[str], affected_families: list[str], manifest: dict) -> list[str]:
    """geo 兼容入口（formula_runner cmd_impacted 调用）：受影响章 id 清单（含 always_dependent）。"""
    return impacted_sections(affected_formulas, affected_families, manifest)["affected_chapters"]


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 节清单规划器（manifest/deps/impacted，D11）")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("manifest", help="由 stage 模板生成 v3 节清单 chapter_manifest.json（章带节子表+扁平节索引）")
    m.add_argument("--stage", required=True)
    m.add_argument("--output", required=True)

    d = sub.add_parser("deps", help="编译节级依赖清单（uses 结构化引用反向索引 + 孤儿合约/悬空槽位 lint，派生工件）")
    d.add_argument("--stage", required=True)
    d.add_argument("--output", required=True)

    i = sub.add_parser("impacted", help="受影响公式/表单族/槽位/合约 → 受影响节集合反查（--deps 在场走节级精确反查）")
    i.add_argument("--manifest", required=True)
    i.add_argument("--deps", help="state/dependency_manifest.json（缺省退化为章级反查）")
    i.add_argument("--formulas", default="", help="逗号分隔公式 id")
    i.add_argument("--families", default="", help="逗号分隔表单族名")
    i.add_argument("--slots", default="", help="逗号分隔槽位 key（改参反查，SC#4）")
    i.add_argument("--contracts", default="", help="逗号分隔合约 id")
    i.add_argument("--output", help="结果 JSON 落盘路径（可选）")

    args = p.parse_args()
    if args.command == "manifest":
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        manifest = build_manifest(stage)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"MANIFEST_READY: {args.output} chapters={len(manifest['chapters']) - 2} sections={len(manifest['sections'])}（projection={manifest['projection_chapter']}）")
        return 0

    if args.command == "deps":
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        deps = compile_deps(stage)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(deps, ensure_ascii=False, indent=2), encoding="utf-8")
        n_cons = sum(len(v) for kind in deps["consumers"].values() for v in kind.values())
        lint = deps["lint"]
        print(f"DEPS_READY: {args.output} consumers_edges={n_cons} owners={sum(len(v) for kind in deps['owners'].values() for v in kind.values())}")
        if lint["orphan_contracts"]:
            print(f"LINT_ORPHAN_CONTRACTS: {lint['orphan_contracts']}（声明在册但零 uses 消费——确认是否漏引用或删除声明）")
        if lint["dangling_slots"]:
            print(f"LINT_DANGLING_SLOTS: {lint['dangling_slots']}（uses 引用但无节/章 slots 声明=无生产者）")
        if lint["dangling_formulas"]:
            print(f"LINT_DANGLING_FORMULAS: {lint['dangling_formulas']}（uses 引用但无公式声明）")
        if not any(lint.values()):
            print("LINT_CLEAN: 无孤儿合约/悬空槽位/悬空公式")
        return 0

    # impacted
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    deps = None
    if args.deps:
        deps = json.loads(Path(args.deps).read_text(encoding="utf-8"))
    split = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]
    result = impacted_sections(
        split(args.formulas), split(args.families), manifest, deps,
        affected_slots=split(args.slots), affected_contracts=split(args.contracts),
    )
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"IMPACTED_READY: {args.output}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
