#!/usr/bin/env python3
"""coal-eia-report v2 — mapping.py：门 1 前章树核对（D6 章树绑定协议 × D12 双源归一）。

spec docs/designs/coal-eia-report-v2.md：项目树由 D12 seed 生成后与 stage 天然同构，
绑定退化为平凡映射校验——**核对 = 节序 + 标题一致性**（level2 叶子数/标题逐条比对，
容忍纯空白差异），不是语义匹配（OV#2：stage JSON 是唯一真源，一致性是 seed 管线
正确性的断言，禁模糊匹配承压）。全一致 → 落 state/mapping.json（{section_id:
chapter_uuid} 平面字典，state 序）；不一致 → 逐条列出差异行，rc=2 需人工裁决
（树过期/被人工改动/数据驱动标题——禁静默错写，D6）。

--tree 输入 = list_chapters（project MCP）的 JSON 导出文件：扁平数组 DFS 序
  [{chapter_id, title, level, status, word_count_target, word_count_current,
    assigned_name}, ...]（backend/app/extensions/project/mcp.py::_handle_list_chapters）。
chapters 键包装（{"chapters": [...]}）同样接受。

mapping.json 形状（snapshot 已枚举 state/mapping.json，勿另立路径）：
  {"ch1_S01": "<uuid>", "ch1_S02": "<uuid>", ...}   # 仅 level2 叶子（交付=节级，D9）

CLI:
  mapping.py bind   --tree tree.json --stage references/stages/planning_eia.json
                    --output state/mapping.json
  mapping.py check  --mapping state/mapping.json --tree tree.json [--stage stage.json]
    check 复核已落绑定：mapping 值集 ↔ 树 level2 叶子 chapter_id 集双射（树重建/
    重导入会换 uuid → 立刻暴露陈旧绑定）；给 --stage 时再做全量节序+标题一致性复核。

退出码：0 一致（bind 已落文件 / check 绑定有效）/ 1 用法错误、文件缺失或形状非法 /
2 不一致需人工（bind 不落文件——禁静默；check 绑定失效）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_MISMATCH = 0, 1, 2


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def norm_title(t: str) -> str:
    """容忍纯空白差异：剔除全部空白后比对（标题语义以非空白字符序列为准）。"""
    return "".join(str(t).split())


def load_json(path: Path):
    if not path.exists():
        print(f"MAPPING_ERROR: 文件不存在: {path}")
        raise SystemExit(EXIT_ERROR)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"MAPPING_ERROR: JSON 解析失败 {path}: {e}")
        raise SystemExit(EXIT_ERROR)


def load_tree(path: Path) -> list[dict]:
    """list_chapters 导出 → 扁平章行表（文件序即 DFS 序）。"""
    d = load_json(path)
    if isinstance(d, dict) and isinstance(d.get("chapters"), list):
        d = d["chapters"]
    if not isinstance(d, list) or not d:
        print(f"MAPPING_ERROR: tree 文件须为 list_chapters 扁平数组（非空），收到: {type(d).__name__}")
        raise SystemExit(EXIT_ERROR)
    rows = []
    for i, item in enumerate(d):
        if not isinstance(item, dict) or not item.get("chapter_id") or "title" not in item or "level" not in item:
            print(f"MAPPING_ERROR: tree 第 {i} 行缺 chapter_id/title/level: {str(item)[:120]}")
            raise SystemExit(EXIT_ERROR)
        rows.append(item)
    return rows


def expected_rows(stage: dict) -> list[dict]:
    """stage → 期望行表（数值章序 DFS）：level1 章 + level2 节，与 seed→树同构。"""
    rows: list[dict] = []
    for ch_id in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][ch_id]
        rows.append({"level": 1, "title": ch.get("title", ch_id), "sid": ch_id})
        for s in ch.get("sections", []):
            rows.append({"level": 2, "title": s.get("title", ""), "sid": s.get("id", "")})
    return rows


def diff_rows(expected: list[dict], actual: list[dict]) -> list[str]:
    """逐行核对（数量/层级/标题），返回差异行清单（人读，供人工裁决）。"""
    diffs: list[str] = []
    if len(expected) != len(actual):
        diffs.append(f"DIFF 行数: stage 期望 {len(expected)} 行 vs 树实际 {len(actual)} 行")
    for i in range(max(len(expected), len(actual))):
        exp = expected[i] if i < len(expected) else None
        act = actual[i] if i < len(actual) else None
        if exp is None:
            diffs.append(f"DIFF row {i}: 树多出行 level={act['level']} title={act['title']!r} chapter_id={act['chapter_id']}")
            continue
        if act is None:
            diffs.append(f"DIFF row {i}: 树缺行 stage={exp['sid']} level={exp['level']} title={exp['title']!r}")
            continue
        if exp["level"] != act["level"]:
            diffs.append(f"DIFF row {i}: 层级不符 stage={exp['sid']} level={exp['level']} vs 树 level={act['level']} title={act['title']!r}")
        if norm_title(exp["title"]) != norm_title(act["title"]):
            diffs.append(
                f"DIFF row {i}: 标题不符 stage={exp['sid']} 期望={exp['title']!r} vs 树={act['title']!r} "
                f"chapter_id={act['chapter_id']}"
            )
    return diffs


def cmd_bind(args: argparse.Namespace) -> int:
    tree = load_tree(Path(args.tree))
    stage = load_json(Path(args.stage))
    if not isinstance(stage, dict) or not stage.get("chapters"):
        print("MAPPING_ERROR: stage 文件无 chapters")
        return EXIT_ERROR

    expected = expected_rows(stage)
    diffs = diff_rows(expected, tree)
    if diffs:
        print(f"MAPPING_MISMATCH: {len(diffs)} 处不一致——章树与 stage 不同构，需人工裁决（树过期/被人工改动/数据驱动标题），未落 mapping")
        for d in diffs:
            print(f"  {d}")
        print("MAPPING_HINT: 处置=修正 seed 重导模板重建项目树，或确认差异合法（如 ch6_S08 数据驱动标题）后人工修订 stage/树，再重跑 bind")
        return EXIT_MISMATCH

    # 全一致 → 按对齐行落绑定：键=stage 节 id（state 序），值=项目章节 UUID
    mapping = {exp["sid"]: act["chapter_id"] for exp, act in zip(expected, tree) if exp["level"] == 2}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, out)
    n_ch = sum(1 for row in tree if row["level"] == 1)
    print(f"MAPPING_READY: {len(mapping)} 节已绑定（{n_ch} 章核对一致，序+标题全等——空白容忍）→ {out}")
    print("MAPPING_NEXT: mapping.json 入 snapshot 枚举（续跑不重绑，D6）；门 1 可开")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    mapping = load_json(Path(args.mapping))
    tree = load_tree(Path(args.tree))
    if not isinstance(mapping, dict) or not mapping:
        print("MAPPING_ERROR: mapping 文件须为非空平面字典 {section_id: chapter_uuid}")
        return EXIT_ERROR
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        print("MAPPING_ERROR: mapping 形状非法（键值均须为字符串）")
        return EXIT_ERROR

    problems: list[str] = []
    leaves = [row for row in tree if row["level"] == 2]
    deeper = [row for row in tree if row["level"] > 2]
    if deeper:
        problems.append(f"树出现 level>2 节点 {len(deeper)} 个（seed 仅到节级）：{[r['title'] for r in deeper][:5]}")
    tree_uuids = {row["chapter_id"] for row in leaves}
    map_uuids = set(mapping.values())
    missing = tree_uuids - map_uuids
    stale = map_uuids - tree_uuids
    if missing:
        problems.append(f"树中 {len(missing)} 个叶子未绑定（mapping 值缺失），如: {sorted(missing)[:3]}")
    if stale:
        problems.append(f"mapping 中 {len(stale)} 个 uuid 不在当前树（陈旧绑定——树被重建/重导入？），如: {sorted(stale)[:3]}")
    if not missing and not stale and len(leaves) != len(mapping):
        problems.append(f"叶子数 {len(leaves)} != 绑定数 {len(mapping)}（uuid 一对多？）")

    stage_rows: list[dict] | None = None
    if args.stage:
        stage = load_json(Path(args.stage))
        if isinstance(stage, dict) and stage.get("chapters"):
            expected = expected_rows(stage)
            problems += diff_rows(expected, tree)
            stage_sids = {r["sid"] for r in expected if r["level"] == 2}
            if set(mapping) != stage_sids:
                problems.append(
                    f"mapping 键集与 stage 节集不符：多 {sorted(set(mapping) - stage_sids)[:3]} 少 {sorted(stage_sids - set(mapping))[:3]}"
                )
            stage_rows = expected

    if problems:
        print(f"MAPPING_INVALID: {len(problems)} 处问题——绑定与当前树/stage 不再一致，续跑前需人工处置")
        for p_ in problems:
            print(f"  DIFF {p_}")
        return EXIT_MISMATCH

    extra = f"，stage 全量复核一致（{len(stage_rows)} 行）" if stage_rows else ""
    print(f"MAPPING_OK: {len(mapping)} 节绑定与当前树叶子双射一致{extra}")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 门 1 前章树核对（D6 绑定 × D12 同构断言）")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bind", help="树↔stage 一致性核对，全一致才落 state/mapping.json")
    b.add_argument("--tree", required=True, help="list_chapters 的 JSON 导出文件（扁平数组 DFS 序）")
    b.add_argument("--stage", required=True, help="stage JSON（如 references/stages/planning_eia.json）")
    b.add_argument("--output", required=True, help="state/mapping.json 输出路径")
    b.set_defaults(func=cmd_bind)

    c = sub.add_parser("check", help="复核已落绑定：mapping↔树叶子双射（--stage 再加全量一致性复核）")
    c.add_argument("--mapping", required=True)
    c.add_argument("--tree", required=True)
    c.add_argument("--stage", default=None)
    c.set_defaults(func=cmd_check)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
