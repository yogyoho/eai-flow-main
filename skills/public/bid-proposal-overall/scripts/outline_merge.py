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
import os
import re
import sys
from pathlib import Path

import build_output
import extract
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
    claimed_clauses: dict[str, str] = {}
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
            elif cid in claimed_clauses:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: duplicate_clause——条款已被章「{claimed_clauses[cid]}」挂接(双锚定=响应双渲染)")
            else:
                claimed_clauses[cid] = title
                clean_cids.append(cid)
        if clean_cids:
            normalized.append({"no": no, "title": title, "clause_ids": clean_cids, "notes": ch.get("notes")})
    if problems:
        raise OutlineMergeError("候选校验拒绝(绝不半落地):\n  - " + "\n  - ".join(problems))
    return normalized


def _is_live(clause: dict) -> bool:
    """活条款判定——与 build_output._is_active 同口径(同源委托, 不复制实现)。"""
    return build_output._is_active(clause)


def _restore_structure_bytes(path: Path, data: bytes) -> None:
    """回滚专用字节复原写(家族规范: 点前缀+pid 临时名 .{name}.tmp{pid}, try/finally unlink)。

    仅用于重签失败后恢复旧字节——常规数据写走 extract.atomic_write_json(序列化同源)。
    复原再失败属双故障: 如实报「保留新未签名内容」, 不谎报已回滚。
    """
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as exc:
        raise OutlineMergeError("rollback also failed——structure.json 保留新未签名内容, 恢复=重跑 outline_merge") from exc
    finally:
        tmp.unlink(missing_ok=True)


def _next_node_id(structure: list[dict]) -> str:
    """分配下一个 S-NNN(最低空位——计划规定, 替换式重建下幂等重跑取号稳定)。

    正则守卫同 responses._next_node_id(外来带横线 id 如 MIR-3.2 跳过不计, 不炸 int());
    取号策略有意分叉: 彼处 max+1, 此处最低空位。"""
    used = {int(m.group(1)) for n in structure if isinstance(n, dict) and (m := re.match(r"^S-(\d+)$", str(n.get("node_id", ""))))}
    i = 1
    while i in used:
        i += 1
    return f"S-{i:03d}"


def build_outline_nodes(normalized: list[dict], structure: list[dict], source_pack: str | None) -> list[dict]:
    """大纲章 → self_created group 节点(单段 path `{no:02d} {title}`, 前导数字供领号)。"""
    source = f"pack:{source_pack}" if source_pack else "自由拟"
    nodes = []
    for ch in normalized:
        nodes.append(
            {
                "node_id": _next_node_id(structure + nodes),
                "volume": "technical",
                "path": f"{ch['no']:02d} {ch['title']}",
                "slot_type": "group",
                "required_format": {"desc": f"大纲自拟章(B1 v2; 来源 {source}; 确认后 merge)", "table_spec": None, "template_text": None},
                "linked_clause_ids": list(ch["clause_ids"]),
                "origin": "self_created",
            }
        )
    return nodes


def validate_managed(old_managed, structure: list[dict], assigned: set[str]) -> None:
    """managed 集合 fail-closed 校验(第五道闸): 候选文件在 Agent 可写区, 盲删即静默丢章。
    每个 id 必须存在于 structure 且 origin==self_created; 其 linked_clause_ids ⊆ 本轮大纲
    分配集合(超出者=外部经 responses merge 追加的锚点——删除即静默丢失, 拒绝并提示先重跑
    responses merge 或确认弃锚)。"""
    if not isinstance(old_managed, list):
        raise OutlineMergeError("managed_node_ids 应为数组")
    by_id = {n.get("node_id"): n for n in structure if isinstance(n, dict)}
    problems = []
    for nid in old_managed:
        if not isinstance(nid, str):
            problems.append(f"managed {nid!r}: id 非字符串")
            continue
        n = by_id.get(nid)
        if n is None:
            problems.append(f"managed {nid}: unknown——不存在于 structure")
        elif n.get("origin") != "self_created":
            problems.append(f"managed {nid}: not_self_created——指向 mirror 节点(mirror 零触碰铁律)")
        else:
            extra = set(n.get("linked_clause_ids") or []) - assigned
            if extra:
                problems.append(f"managed {nid}: external_anchors {sorted(extra)}——节点挂接含 responses merge 外加锚点, 删除即静默丢失; 先重跑 responses merge 或确认弃锚后从 managed 移除该 id")
    if problems:
        raise OutlineMergeError("managed 集合校验拒绝:\n  - " + "\n  - ".join(problems))


def merge(structure: list[dict], normalized: list[dict], old_managed: list[str], source_pack: str | None) -> tuple[list[dict], list[str]]:
    """精准替换: 校验 managed → 删旧 managed 节点 → 插新章树(尾部追加) → 返回 (新 structure, 新 managed)。"""
    validate_managed(old_managed, structure, {cid for ch in normalized for cid in ch["clause_ids"]})
    old = set(old_managed)
    kept = [n for n in structure if not (isinstance(n, dict) and n.get("node_id") in old)]
    nodes = build_outline_nodes(normalized, kept, source_pack)
    return kept + nodes, [n["node_id"] for n in nodes]


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
        # managed 集合预剔除: 这些节点本轮即将被替换, 不参与 self_created_path_conflict 检查
        # (同候选重跑幂等的前提); 非 list 的 managed 走空过滤, 由 merge 内 validate_managed 拒绝。
        raw_managed = cand.get("managed_node_ids")
        managed_ids = {m for m in raw_managed if isinstance(m, str)} if isinstance(raw_managed, list) else set()
        check_structure = [n for n in structure if not (isinstance(n, dict) and n.get("node_id") in managed_ids)]
        normalized = validate_candidates(cand, clauses, check_structure)
        old_managed = [] if raw_managed is None else raw_managed  # falsy 非 None(0/""/false)照实入 validate_managed 闸
        new_structure, managed = merge(structure, normalized, old_managed, cand.get("source_pack"))

        # 原子写 structure.json(家族规范写盘) → 重签; 重签失败回滚旧字节并对旧内容重签(恢复原签名态) → exit 1
        structure_path = state_dir / "structure.json"
        old_bytes = structure_path.read_bytes()
        try:
            extract.atomic_write_json(structure_path, new_structure)
        except extract.ExtractError as exc:
            raise OutlineMergeError(f"structure.json 写盘失败({exc})——未落盘零变更, 重建入口=重跑 outline_merge") from exc
        try:
            state_guard.sign_state_files(state_dir, ["structure.json"])
        except Exception as exc:
            _restore_structure_bytes(structure_path, old_bytes)  # 复原失败 → 双故障 OutlineMergeError(如实文案)
            try:
                state_guard.sign_state_files(state_dir, ["structure.json"])  # 对旧内容重签, 恢复原签名态
            except Exception:
                pass  # 字节已复原; 重签再失败交由 verify 侧签名不符拦截, 不静默放行
            raise OutlineMergeError(f"structure.json 重签失败({exc})——已回滚, structure.json 未变更, 重建入口=重跑 outline_merge") from exc

        # 摘要口径: 活技术条款 − 任意节点(含 self_created/兜底)已挂接者
        anchored = {cid for n in new_structure if isinstance(n, dict) for cid in (n.get("linked_clause_ids") or [])}
        live_tech = {c.get("clause_id") for c in clauses if isinstance(c, dict) and _is_live(c) and c.get("category") in TECH_CATEGORIES}

        # 回写候选 managed_node_ids(候选在 Agent 可写区, 非签名五元组; 失败不谎报成功)
        cand["managed_node_ids"] = managed
        try:
            extract.atomic_write_json(cand_path, cand)
        except extract.ExtractError as exc:
            # 重跑会被 self_created_path_conflict 拒死(managed 列表缺新节点 id, 预剔除不生效)——
            # 恢复提示必须携带真实出口: 手动把候选 managed_node_ids 回填为本轮新 managed(json 可直接粘贴)后再重跑。
            raise OutlineMergeError(f"候选回写失败({exc})——structure.json 已更新+签名; 恢复=把候选文件 managed_node_ids 手动设为 {json.dumps(managed)} 后重跑 outline_merge") from exc

        print(
            json.dumps(
                {
                    "command": "outline_merge",
                    "created": len(managed),
                    "replaced": len(old_managed),
                    "remaining_unanchored": len(live_tech - anchored),
                },
                ensure_ascii=False,
            )
        )
        return EXIT_OK
    except OutlineMergeError as exc:
        print(f"[outline_merge] {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
