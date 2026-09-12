"""outline_merge——大纲自拟结构化(B1 v2, spec 2026-09-11-outline-merge-design)。

读确认后的大纲候选(candidates/tech_outline.candidates.json) → fail-closed 校验 →
删旧 managed 集合/插新 origin=self_created 技术章树(精准替换, 幂等) → verify→原子写→
state_guard 重签 structure.json → 回写 managed_node_ids → stdout 单行 JSON 摘要。

纪律: 只新增/替换 self_created 节点(mirror 零触碰); responses.py 兜底自创节点永不入
managed 集合; 不带 --confirm-outline 拒绝执行(确认门纪律, 同 state_guard --confirm-gate1-edit)。
退出码: 0=干净完成; 1=用法/候选/校验拒绝(摘要 stderr 逐条)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import build_output
import state_guard

EXIT_OK = 0
EXIT_ERROR = 1

# 技术卷条目承载口径与 build_output 同源(单一事实源, 不手抄)。
TECH_CATEGORIES = build_output.ENTRY_CATEGORIES
OUTLINE_CONFIRM_FLAG = "--confirm-outline"


class OutlineMergeError(Exception):
    pass


def _load_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise OutlineMergeError(f"{what} 不可解析({path}): {exc}")


def validate_candidates(cand: dict, clauses: list[dict], structure: list[dict]) -> list[dict]:
    """候选+条款 fail-closed 校验; 返回规范化章列表; 违规 raise OutlineMergeError(逐条明细)。"""
    if cand.get("confirmed") is not True:
        raise OutlineMergeError("候选未确认(confirmed 非 true)——确认门纪律")
    problems: list[str] = []
    chapters = cand.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise OutlineMergeError("大纲章列表为空或缺失——空大纲无意义, 拒绝")

    by_id = {c.get("clause_id"): c for c in clauses if isinstance(c, dict)}
    mirror_chapters = {n["path"].split("/")[0].strip() for n in structure if isinstance(n, dict) and n.get("origin") != "self_created"}
    mirror_anchored = {cid for n in structure if isinstance(n, dict) and n.get("origin") != "self_created" for cid in (n.get("linked_clause_ids") or [])}

    seen_chapter_titles: set[str] = set()
    normalized: list[dict] = []
    for idx, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            problems.append(f"chapters[{idx}]: 非对象")
            continue
        no, title, cids = ch.get("no"), str(ch.get("title") or "").strip(), ch.get("clause_ids")
        if not isinstance(no, int) or isinstance(no, bool) or not title or not isinstance(cids, list) or not cids:
            problems.append(f"chapters[{idx}]: no/title/clause_ids 形态不符")
            continue
        if title in mirror_chapters:
            problems.append(f"chapters[{idx}]「{title}」: chapter_name_conflict——自拟章首段与 mirror 章首段同名(防同章组合并歧义)")
        if f"{no:02d} {title}" in {n.get("path") for n in structure if isinstance(n, dict) and n.get("origin") == "self_created"}:
            problems.append(f"chapters[{idx}]「{title}」: self_created_path_conflict——与既有 responses 兜底自创节点同 path(双渲染/接管落空风险); 改章名或先清理该兜底节点")
        if title in seen_chapter_titles:
            problems.append(f"chapters[{idx}]「{title}」: duplicate_chapter——大纲内章名重复")
        seen_chapter_titles.add(title)
        clean_cids: list[str] = []
        for cid in cids:
            if not isinstance(cid, str):
                problems.append(f"chapters[{idx}]「{title}」← {cid!r}: clause_id 非字符串")
                continue
            c = by_id.get(cid)
            if c is None:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: not_found")
            elif c.get("category") not in TECH_CATEGORIES:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: wrong_category({c.get('category')})")
            elif not _is_live(c):
                problems.append(f"chapters[{idx}]「{title}」← {cid}: not_live({c.get('status', c.get('lifecycle', '?'))})")
            elif cid in mirror_anchored:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: mirror_anchored(已由镜像节点挂接)")
            else:
                clean_cids.append(cid)
        if clean_cids:
            normalized.append({"no": no, "title": title, "clause_ids": clean_cids, "notes": ch.get("notes")})
    if problems:
        raise OutlineMergeError("候选校验拒绝(绝不半落地):\n  - " + "\n  - ".join(problems))
    return normalized


def _is_live(clause: dict) -> bool:
    """活条款判定——与 build_output._is_active 同口径(同源委托, 不复制实现)。"""
    return build_output._is_active(clause)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outline_merge.py", description="大纲自拟结构化(B1 v2): 确认后大纲 → structure.json self_created 章树")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--candidates", required=True, help="tech_outline.candidates.json 路径")
    parser.add_argument("--confirm-outline", action="store_true", help="确认门硬闸: 对话口头确认后才可携带")
    args = parser.parse_args(argv)

    if not args.confirm_outline:
        print("[outline_merge] 拒绝执行: 缺 --confirm-outline(对话确认纪律——用户口头确认后才可携带)", file=sys.stderr)
        return EXIT_ERROR

    state_dir = Path(args.state_dir)
    cand_path = Path(args.candidates)
    try:
        problems = state_guard.verify_state_files(state_dir)
        if problems:
            raise OutlineMergeError("权威状态签名校验失败:\n  - " + "\n  - ".join(problems))
        cand = _load_json(cand_path, "大纲候选")
        if not isinstance(cand, dict):
            raise OutlineMergeError("大纲候选形态异常(应为 JSON 对象), 拒绝")
        clauses = _load_json(state_dir / "clauses.json", "clauses.json")
        if not isinstance(clauses, list):
            raise OutlineMergeError("clauses.json 形态异常(应为 JSON 对象数组), 拒绝")
        structure = _load_json(state_dir / "structure.json", "structure.json")
        if not isinstance(structure, list):
            raise OutlineMergeError("structure.json 形态异常(应为 JSON 对象数组), 拒绝")
        validate_candidates(cand, clauses, structure)
    except OutlineMergeError as exc:
        print(f"[outline_merge] {exc}", file=sys.stderr)
        return EXIT_ERROR
    # Task 2 接: 节点生成/精准替换/落盘重签/摘要
    print(json.dumps({"command": "outline_merge", "mode": "validate_only"}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
