#!/usr/bin/env python3
"""responses.py — 投标方案编写技能·阶段4a 技术响应候选的确定性校验 + 合并(无 LLM)。

用户反馈(2026-08-18 线程 1a80a1d8 反馈3/4): 此前技术响应只有空骨架, 没有内容生成。
v2 产品方向变化: Agent 在确认门1 后、build 前按三模式供源(kf=知识库扩写/仿写、
uploads=用户参考样例、web=网络搜索深写; self=仅依据条款原文自拟)生成响应正文,
本脚本承接其候选 JSON 的确定性防线——生成是 LLM 的事, 落账是脚本的事(镜像 extract.py 纪律)。

用法:
    python responses.py validate --candidates <候选JSON...> --state-dir <dir>
    python responses.py merge    --candidates <候选JSON...> --state-dir <dir>

候选记录契约(一次生成批次 = 一个文件):
    {"kind": "responses",            // 固定
     "items": [<responses.schema.json 候选项>...],
     "note": "<生成说明, 可选>"}

校验规则:
    1. 状态前置: state_guard 签名复核 + clauses.json/structure.json 必须已存在
       (先跑完 ingest/extract 确认门1 才谈响应生成)。
    2. schema: 逐项对 references/responses.schema.json 校验(复用 extract.py 的
       stdlib mini JSON Schema 校验器)。
    3. 条款 FK: clause_id 必须存在于 clauses.json, 且未被 superseded/voided
       (活条款), category ∈ {technical, service}——商务/资格条款不走本通道
       (它们有格式模板镜像管线)。
    4. 供源留痕一致性: source_mode=web → citations 必须非空(无引用的网搜深写
       不可信, 拒绝落账)。
    5. 元数据 lint: response_text 不得携带管线元数据标记(槽位类型/待填提示/
       填写状态/关联条款/满足状态——回放实证这些 bullet 曾被当正文写进交付物)。
    6. 落位声明: placement 的 anchor_node_id 与 self_created_path 二选一;
       引用的 node_id 必须存在于 structure.json; after_node_id 仅与
       self_created_path 同用。
    7. 跨候选去重: 同一 clause_id 在多个候选文件(或同文件内)重复 → 全部隔离
       [待确认], 绝不静默取首个。

merge 语义(按 clause_id upsert 幂等):
    - responses.json: 干净条目 upsert(缺省归一 points=[]/citations=[]/needs_human_verify=false);
    - 落位: anchor→幂等追加该结构节点 linked_clause_ids; self_created→structure 建
      origin=self_created 的 group 节点(同 path 幂等复用)插到 after_node_id 之后;
    - clauses.json: response_status 仅 unassigned→draft 升级(只升不降);
    - 写盘后登记防篡改签名; 异常块隔离, 干净块照常合并(退出码 3 仍完成)。

脚本纪律: 纯 Python 3.12 stdlib(复用同目录 extract.py 校验器/原子写盘/upsert);
不调用 LLM; 不 import app.*/deerflow.*。

退出码: 0=干净完成(--help 亦 0); 1=用法/文件/签名错误; 3=完成但有异常项(读 stdout
单行 JSON 摘要, anomalies 逐项呈现, 绝不静默)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import extract
import state_guard

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

RESPONSES_STATE_FILE = "responses.json"
SCHEMA_FILE = "responses.schema.json"
DEFAULT_REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

RESPONSE_CATEGORIES = ("technical", "service")
# 元数据 lint 标记(回放实证: 这些管线 bullet 曾被当正文写进交付物)
PIPELINE_METADATA_MARKERS = ("槽位类型", "待填提示", "填写状态", "关联条款", "满足状态")

RESPONSE_PIPELINE_DEFAULTS = {"points": [], "citations": [], "needs_human_verify": False}


class ResponsesError(Exception):
    """用法/文件/签名错误 → 退出码 1。"""


def load_schema(references_dir: str | Path | None = None) -> dict:
    """装载 responses.schema.json; 缺失/不可解析 → ResponsesError。"""
    base = Path(references_dir) if references_dir is not None else DEFAULT_REFERENCES_DIR
    path = base / SCHEMA_FILE
    if not path.is_file():
        raise ResponsesError(f"references 契约缺失: {path}(--references 可指定目录)")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ResponsesError(f"references 契约不可读/不可解析(需 UTF-8): {path}: {exc}") from exc


def _load_json(path: Path, what: str) -> object:
    if not path.is_file():
        raise ResponsesError(f"{what} 不存在: {path}(先跑前序脚本: {path.name} 是本阶段输入)")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ResponsesError(f"{what} 不可读/不可解析(需 UTF-8), 拒绝覆盖(先人工核查): {path}: {exc}") from exc


def load_state(state_dir: str | Path) -> dict:
    """装载 clauses/structure(装载校验对齐 extract._load_state_list); responses 缺失→[]。"""
    state_dir = Path(state_dir)
    clauses = _load_json(state_dir / "clauses.json", "clauses.json")
    structure = _load_json(state_dir / "structure.json", "structure.json")
    for name, data in (("clauses.json", clauses), ("structure.json", structure)):
        if not isinstance(data, list) or not all(isinstance(entry, dict) for entry in data):
            raise ResponsesError(f"{name} 结构异常(应为对象数组), 拒绝覆盖: {state_dir / name}")
    responses: list = []
    responses_existed = (state_dir / RESPONSES_STATE_FILE).is_file()
    if responses_existed:  # 首次 merge 无 responses.json = 正常空态, 不是文件错误
        responses = _load_json(state_dir / RESPONSES_STATE_FILE, RESPONSES_STATE_FILE)
        if not isinstance(responses, list) or not all(isinstance(entry, dict) for entry in responses):
            raise ResponsesError(f"{RESPONSES_STATE_FILE} 结构异常(应为对象数组), 拒绝覆盖: {state_dir / RESPONSES_STATE_FILE}")
    return {"clauses": clauses, "structure": structure, "responses": responses, "responses_existed": responses_existed}


def load_candidate(path: str | Path) -> dict:
    """装载候选记录文件; 缺失/不可解析 → ResponsesError。"""
    path = Path(path)
    if not path.is_file():
        raise ResponsesError(f"候选文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ResponsesError(f"候选文件不可读/不可解析(需 UTF-8; 疑似 LLM 输出截断或编码错, 先补跑该批次): {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResponsesError(f"候选记录应为 JSON 对象: {path}")
    return data


def evaluate(state: dict, schema: dict, records: list[tuple[Path, dict]]) -> dict:
    """确定性校验管线; 出参 report 对齐 extract.evaluate 口径(quarantined/clean/anomalies)。"""
    clauses_by_id = {str(c.get("clause_id")): c for c in state["clauses"]}
    nodes_by_id = {str(n.get("node_id")): n for n in state["structure"]}

    anomalies: list[dict] = []
    quarantined: dict[str, set[str]] = {}

    def quarantine(source: str, kind: str) -> None:
        quarantined.setdefault(source, set()).add(kind)

    # --- 第 1 步: 记录形态 -----------------------------------------------------
    views: list[dict] = []
    for path, record in records:
        problems: list[str] = []
        if record.get("kind") != "responses":
            problems.append(f"kind 非法: {record.get('kind')!r}(必须为 responses)")
        if not isinstance(record.get("items"), list):
            problems.append(f"items 应为数组, 实际 {type(record.get('items')).__name__}")
        if problems:
            anomalies.append({"kind": "malformed_record", "file": path.name, "problems": problems, "message": "候选记录形态不符, [待确认]不合并"})
            quarantine(str(path), "malformed_record")
            continue
        views.append({"path": path, "items": record["items"]})

    # --- 第 2 步: 逐条目 schema + FK + 活条款 + 供源一致性 + 元数据 lint + 落位 ----
    survivors: list[dict] = []
    owners: dict[str, list[dict]] = {}  # clause_id → 条目属主视图(第 3 步去重用)
    for view in views:
        path = view["path"]
        problems: list[dict] = []
        kept: list[dict] = []
        for index, raw_item in enumerate(view["items"]):
            if not isinstance(raw_item, dict):
                problems.append({"kind": "schema_violation", "file": path.name, "item_id": f"items[{index}]", "errors": [f"items[{index}]: 应为对象, 实际 {extract._json_type_name(raw_item)}"]})
                continue
            clause_id = str(raw_item.get("clause_id", f"items[{index}]"))
            errors = extract.validate_against_schema(schema, raw_item, clause_id)
            if errors:
                problems.append({"kind": "schema_violation", "file": path.name, "item_id": clause_id, "errors": errors})
                continue
            clause = clauses_by_id.get(clause_id)
            if clause is None:
                problems.append({"kind": "clause_fk_invalid", "file": path.name, "item_id": clause_id, "message": f"clause_id {clause_id} 不在 clauses.json, [待确认]不合并"})
                continue
            if clause.get("superseded_by") is not None or clause.get("voided"):
                problems.append({"kind": "clause_not_live", "file": path.name, "item_id": clause_id, "message": f"条款 {clause_id} 已被补遗替代/作废, [待确认]不合并(应对新条款生成响应)"})
                continue
            if clause.get("category") not in RESPONSE_CATEGORIES:
                problems.append(
                    {
                        "kind": "clause_category_out_of_scope",
                        "file": path.name,
                        "item_id": clause_id,
                        "category": clause.get("category"),
                        "message": f"条款 {clause_id} category={clause.get('category')!r} 不在 {list(RESPONSE_CATEGORIES)}——商务/资格/格式条款走模板镜像管线, 不走响应生成",
                    }
                )  # noqa: E501
                continue
            text = raw_item.get("response_text") or ""
            hit_markers = [marker for marker in PIPELINE_METADATA_MARKERS if marker in text]
            if hit_markers:
                problems.append(
                    {"kind": "pipeline_metadata_in_text", "file": path.name, "item_id": clause_id, "markers": hit_markers, "message": f"response_text 携带管线元数据标记 {hit_markers}(回放实证曾当正文写进交付物), [待确认]重写后再合并"}
                )  # noqa: E501
                continue
            if raw_item.get("source_mode") == "web" and not raw_item.get("citations"):
                problems.append({"kind": "citations_missing_for_web", "file": path.name, "item_id": clause_id, "message": "source_mode=web 但 citations 为空——网搜深写必须逐条留引用(人核清单第四节消费), [待确认]不合并"})
                continue
            placement = raw_item.get("placement")
            if placement is not None:
                has_anchor = "anchor_node_id" in placement
                has_self = "self_created_path" in placement
                if has_anchor == has_self or (has_anchor and "after_node_id" in placement):  # 同有/同无/after 混用 anchor 都算形态失败
                    problems.append({"kind": "placement_shape", "file": path.name, "item_id": clause_id, "message": "placement 的 anchor_node_id 与 self_created_path 必须恰好提供一个(after_node_id 仅与 self_created_path 同用, 或整体省略)"})
                    continue
                if has_anchor:
                    if placement.get("anchor_node_id") not in nodes_by_id:
                        problems.append(
                            {
                                "kind": "placement_node_missing",
                                "file": path.name,
                                "item_id": clause_id,
                                "node_id": placement.get("anchor_node_id"),
                                "message": f"anchor_node_id {placement.get('anchor_node_id')} 不在 structure.json, [待确认]不合并",
                            }
                        )  # noqa: E501
                        continue
                else:
                    if "after_node_id" in placement and placement.get("after_node_id") not in nodes_by_id:
                        problems.append(
                            {
                                "kind": "placement_node_missing",
                                "file": path.name,
                                "item_id": clause_id,
                                "node_id": placement.get("after_node_id"),
                                "message": f"after_node_id {placement.get('after_node_id')} 不在 structure.json, [待确认]不合并",
                            }
                        )  # noqa: E501
                        continue
            item = dict(raw_item)
            for key, value in RESPONSE_PIPELINE_DEFAULTS.items():
                item.setdefault(key, value)
            kept.append(item)
            owners.setdefault(clause_id, []).append(view)
        view["items"] = kept
        if problems:
            anomalies.extend(problems)
            for problem in problems:
                quarantine(str(path), problem["kind"])
        else:
            survivors.append(view)

    # --- 第 3 步: 跨候选 clause_id 去重 ----------------------------------------
    dup_views: list[dict] = []
    for clause_id, view_list in sorted(owners.items()):
        if len(view_list) > 1:
            files = sorted({v["path"].name for v in view_list})
            anomalies.append({"kind": "duplicate_clause_response", "id": clause_id, "files": files, "message": f"clause_id {clause_id} 有 {len(view_list)} 条响应({', '.join(files)}), 全部[待确认], 请保留唯一最新版"})
            dup_views.extend(view_list)
    clean_views = [v for v in survivors if v not in dup_views]
    for v in dup_views:
        quarantine(str(v["path"]), "duplicate_clause_response")

    clean_items = [item for v in clean_views for item in v["items"]]
    return {
        "clean": clean_items,
        "quarantined": [{"file": source, "kinds": sorted(kinds)} for source, kinds in sorted(quarantined.items())],
        "anomalies": anomalies,
    }


def _next_node_id(structure: list[dict]) -> str:
    """分配下一个 S-NNN(既有最大序号+1, 3 位下限对齐 NODE_ID 约定)。"""
    numbers = [int(m.group(1)) for node in structure if (m := re.match(r"^S-(\d+)$", str(node.get("node_id", ""))))]
    return f"S-{(max(numbers) + 1) if numbers else 1:03d}"


def apply_placements(structure: list[dict], items: list[dict]) -> dict:
    """把干净条目的落位声明应用到结构(就地修改; 幂等); 返回计数摘要。"""
    nodes_by_id = {str(n.get("node_id")): n for n in structure}
    anchored = self_created = 0
    for item in items:
        placement = item.get("placement")
        if placement is None:
            continue
        clause_id = str(item.get("clause_id"))
        if "anchor_node_id" in placement:
            node = nodes_by_id[placement["anchor_node_id"]]
            linked = node.setdefault("linked_clause_ids", [])
            if clause_id not in linked:
                linked.append(clause_id)
            anchored += 1
        else:
            path = placement["self_created_path"]
            node = next((n for n in structure if n.get("path") == path and n.get("origin") == "self_created"), None)
            if node is None:
                node = {
                    "node_id": _next_node_id(structure),
                    "volume": "technical",
                    "path": path,
                    "slot_type": "group",
                    "required_format": {"desc": None, "table_spec": None, "template_text": None},
                    "linked_clause_ids": [],
                    "origin": "self_created",
                }
                after = placement.get("after_node_id")
                position = next((i for i, n in enumerate(structure) if str(n.get("node_id")) == after), None) if after else None
                structure.insert(position + 1 if position is not None else len(structure), node)
                nodes_by_id[str(node["node_id"])] = node
            linked = node.setdefault("linked_clause_ids", [])
            if clause_id not in linked:
                linked.append(clause_id)
            self_created += 1
    return {"anchored": anchored, "self_created": self_created}


def cmd_validate(args) -> int:
    """validate: 只校验不落盘; 异常项交确认门。"""
    _verify_state_guard(args.state_dir, "validate 前置校验")
    schema = load_schema(args.references)
    records = [(Path(p), load_candidate(p)) for p in args.candidates]
    state = load_state(args.state_dir)
    report = evaluate(state, schema, records)
    summary = _base_summary("validate", args, report)
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_ANOMALY if report["anomalies"] else EXIT_OK


def cmd_merge(args) -> int:
    """merge: 校验 + 原子落账(responses/structure/clauses) + 签名登记。"""
    _verify_state_guard(args.state_dir, "merge 前置校验")
    schema = load_schema(args.references)
    records = [(Path(p), load_candidate(p)) for p in args.candidates]
    state = load_state(args.state_dir)
    report = evaluate(state, schema, records)
    summary = _base_summary("merge", args, report)

    state_dir = Path(args.state_dir)
    clean_items = report["clean"]
    structure = [dict(node) for node in state["structure"]]
    placement_summary = apply_placements(structure, clean_items)

    clauses = [dict(clause) for clause in state["clauses"]]
    clauses_by_id = {str(c.get("clause_id")): c for c in clauses}
    merged_ids = {str(item.get("clause_id")) for item in clean_items}
    status_upgraded = 0
    for clause_id in merged_ids:
        clause = clauses_by_id.get(clause_id)
        if clause is not None and clause.get("response_status") == "unassigned":
            clause["response_status"] = "draft"
            status_upgraded += 1

    responses = extract._upsert_by_id(state["responses"], clean_items, "clause_id")
    written: list[str] = []
    if responses or state["responses_existed"]:
        extract.atomic_write_json(state_dir / RESPONSES_STATE_FILE, responses)
        written.append(RESPONSES_STATE_FILE)
    # clauses/structure 在 load_state 已强制在盘, 每次落账后整体重写(未变时字节级不变)并重登签名
    extract.atomic_write_json(state_dir / "structure.json", structure)
    written.append("structure.json")
    extract.atomic_write_json(state_dir / "clauses.json", clauses)
    written.append("clauses.json")

    summary["written"] = sorted(set(written))
    summary["merged"] = {"responses": len(responses), "status_upgraded": status_upgraded, "placement": placement_summary}
    if written:
        state_guard.sign_state_files(state_dir, sorted(set(written)))
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_ANOMALY if report["anomalies"] else EXIT_OK


def _base_summary(command: str, args, report: dict) -> dict:
    return {
        "command": command,
        "candidates": [Path(p).name for p in args.candidates],
        "counts": {"responses": len(report["clean"])},
        "quarantined": report["quarantined"],
        "anomalies": report["anomalies"],
    }


def _verify_state_guard(state_dir: str | Path, context: str) -> None:
    """读盘前校验权威状态签名(与 extract/check_format 同款防线)。"""
    problems = state_guard.verify_state_files(state_dir)
    if problems:
        raise ResponsesError(f"{context}: 权威状态文件签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(problems))


def _add_common_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--candidates", nargs="+", required=True, help="候选响应 JSON 文件(一次生成批次=一个文件, 可多个)")
    sub.add_argument("--state-dir", required=True, help="状态目录(读 clauses.json/structure.json, merge 写 responses.json)")
    sub.add_argument("--references", default=None, help="responses.schema.json 所在目录(默认: 脚本所在技能的 ../references)")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="responses.py",
        description="投标方案编写·阶段4a 技术响应候选校验/合并: 对三模式生成循环产出的响应候选 JSON 做确定性校验(FK/活条款/供源留痕/元数据 lint/落位/去重), merge 原子落账 responses.json 并联动 structure/clauses(无 LLM)",
        epilog="示例: python responses.py validate --candidates candidates/RESP-tech-001.json --state-dir state ; python responses.py merge --candidates candidates/RESP-tech-001.json --state-dir state",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="只校验候选(不落盘), 异常项交确认门")
    _add_common_arguments(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)
    merge_parser = subparsers.add_parser("merge", help="校验后原子落账 responses.json 并联动落位/状态升级(幂等)")
    _add_common_arguments(merge_parser)
    merge_parser.set_defaults(func=cmd_merge)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if not exc.code:
            return EXIT_OK
        print(f"[responses] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}; 用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        return args.func(args)
    except ResponsesError as exc:
        print(f"[responses] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
