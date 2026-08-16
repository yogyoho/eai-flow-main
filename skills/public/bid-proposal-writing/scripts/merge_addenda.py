#!/usr/bin/env python3
"""merge_addenda.py — 投标方案编写技能·阶段3 补遗/答疑增量确定性落账(无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md
「阶段3 merge」+ D3(补遗后实体白名单增量)/D7(状态一致性三防线)。
相似度候选映射本身由 Agent 在上下文内产出(同阶段2 循环纪律, 脚本不调 LLM);
本脚本只消费候选映射与人工裁决, 做确定性落账与防线拦截。

用法:
    python merge_addenda.py --addendum-candidates <候选JSON> --state-dir <dir> [--decisions <人工裁决JSON>]

候选契约(一份补遗 = 一次调用 = 一个文件):
    {"addendum_file": "补遗文件-01.pdf",
     "entities": [{"type", "value"}],   # 可选: Agent 从补遗文本观察到的实体(D3 diff 基准)
     "items": [{"mapping_id", "action": "new|modify|void",
                "anchor": {"section"}|null, "target": <clause_id>|null, "clause": {...}|null}]}

三级合并(设计文档锁定, 不缺不漏不加):
    ① 章节锚点在活条款(未 superseded/未 voided)中唯一命中 → 自动落账
      (锚点解析与显式 target 不一致 → 异常, 绝不静默取其一);
    ② 相似度候选(仅 target 无 anchor)→ 脚本不合并, pending 产出新旧并排 diff 交确认门2;
    ③ 平手(锚点多命中)/同目标冲突 → 必须 --decisions 人工裁决, 绝不静默取首个。

落账语义:
    new/modify 新条款强制 from_addendum=true(载荷为 False 也覆盖)+ voided 补缺省 false;
    modify → 旧项标 superseded_by 指向新 id(自指 → self_supersede 异常);
    void → 旧项标 voided(作废落盘不因后续外键异常回滚)。
    new 撞号防线: id 已存在时仅当"库内为补遗条款且载荷内容一致"才算幂等重放(内容口径 =
    source_file/class/category/source_ref/requirement/response_skeleton 撰写字段,
    response_status 等生命周期字段不参与——后续阶段可合法变更); 同候选文件内多条 new
    映射撞号或内容不一致 → duplicate_clause_id 异常, 绝不静默吞第二份载荷。
    modify 幂等重放(锚点层/相似度层)同口径: 重放链命中的库内新条款必须存在、来自补遗且
    载荷内容一致; 不一致(如部分落账后操作者编辑载荷重跑)→ replay_content_mismatch
    异常浮出而非重放, 绝不静默吞掉编辑后的候选(否则陈旧内容永久封存且零信号)。
    幂等台账 merge_ledger.json 按候选内容规范化哈希(sha256, 键序无关): 同 hash 重跑
    整体跳过零写入; 存在 pending/异常时不记台账(重跑须能重新浮出, 已落账项幂等重放
    不产生字节漂移)。

D3 新实体: 补遗实体 diff entities_whitelist.json → 增量清单 addendum_entities_pending.json
    (累积式: 既有 pending ∪ 本次新增 − 当前白名单; 白名单不经本脚本修改, 确认门2 才写入;
    白名单缺失 → whitelist_missing 异常, 按空集 diff 全量进增量清单, 不静默;
    白名单确认后增量出清走删除, 摘要 written 以 "del:<文件名>" 反映, 删除可见)。
D7 悬挂外键: 落账后扫描 structure/rubric 的 linked_clause_ids, 指向缺失/superseded/voided
    条款 → 异常清单不静默(外键异常是扫描型发现, 不阻断落账); linked_clause_ids 装载时
    校验为字符串数组, 畸形拒绝覆盖(先人工核查)退出码 1, 不带病进扫描。
D7 原子写盘: 所有状态文件临时文件+os.replace, 防中断留半截文件。

脚本纪律: 纯 Python 3.12; stdlib only; 不调用 LLM; 不 import app.*/deerflow.*。

退出码:
    0 = 干净完成(--help 亦为 0; 台账命中跳过属正常完成)
    1 = 用法/文件错误(候选/裁决/状态文件缺失、不可解析、结构损坏; argparse 用法错误统一
        改道 1——2 留给 ingest 的 OCR 分流语义, 防编排方误路由)
    3 = 完成但有异常项或待裁决项(摘要 JSON 的 anomalies/pending 列出)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# --- 退出码约定 -----------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

# --- 契约常量 -------------------------------------------------------------------
ACTIONS = ("new", "modify", "void")
DECISION_VALUES = ("apply", "reject")

# 条款载荷校验基准(references/clauses.schema.json 同款约束; 沙箱无 jsonschema, 内联同子集)
CLAUSE_CLASSES = ("mandatory", "scoring", "normal")
CLAUSE_CATEGORIES = ("technical", "commercial", "qualification", "format", "service")
RESPONSE_STATUSES = ("unassigned", "draft", "pending_confirm", "compliant", "deviation")
CLAUSE_ID_RE = re.compile(r"^[A-Z]{2,4}-C-\d{1,6}$")
CLAUSE_KNOWN_FIELDS = ("clause_id", "source_file", "class", "category", "source_ref", "requirement", "response_status", "response_skeleton", "from_addendum", "superseded_by", "voided")

STATE_FILES = {
    "clauses": "clauses.json",
    "structure": "structure.json",
    "rubric": "rubric.json",
    "ledger": "merge_ledger.json",
    "whitelist": "entities_whitelist.json",
    "entities_pending": "addendum_entities_pending.json",
}


class MergeAddendaError(Exception):
    """用法/文件错误 → 退出码 1。"""


# =============================================================================
# 基础件: 规范化哈希 / JSON 装载 / 原子写盘
# =============================================================================


def content_hash(obj) -> str:
    """候选内容规范化哈希: sort_keys 后 sha256(键序/缩进无关, 内容等价即同 hash)。"""
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_json_file(path: Path, what: str):
    """装载 UTF-8 JSON 文件; 缺失/不可解析 → MergeAddendaError(退出码 1), 绝不静默。"""
    if not path.is_file():
        raise MergeAddendaError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise MergeAddendaError(f"{what} 不可读/不可解析(需 UTF-8; 疑似截断或编码错): {path}: {exc}") from exc


def atomic_write_json(path: str | Path, data) -> None:
    """原子写盘: 临时文件 + os.replace(D7 三防线之一, 防中断留半截文件)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        # 成功路径 os.replace 后 tmp 已不存在; 异常路径清理残留。清理失败只吞掉——
        # 不得掩盖触发本 finally 的原始异常(Windows 文件占用场景)。
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def load_candidates(path: str | Path) -> dict:
    """装载补遗候选记录; 缺失/不可解析/非对象 → MergeAddendaError。"""
    data = _load_json_file(Path(path), "补遗候选文件")
    if not isinstance(data, dict):
        raise MergeAddendaError(f"补遗候选记录应为 JSON 对象: {path}")
    return data


def load_decisions(path: str | Path) -> list:
    """装载人工裁决文件 {"decisions": [...]}; 文件级损坏 → 退出码 1(条目级问题走异常项)。"""
    data = _load_json_file(Path(path), "人工裁决文件")
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        raise MergeAddendaError(f"人工裁决文件应为含 decisions 数组的 JSON 对象: {path}")
    return data["decisions"]


def load_ledger(state_dir: Path) -> list[dict]:
    """装载幂等台账; 台账是本脚本自有产物, 损坏 → 拒绝覆盖(先人工核查)。"""
    path = state_dir / STATE_FILES["ledger"]
    if not path.is_file():
        return []
    data = _load_json_file(path, "merge_ledger.json")
    if not isinstance(data, list) or not all(isinstance(entry, dict) and isinstance(entry.get("hash"), str) and entry["hash"] for entry in data):
        raise MergeAddendaError(f"merge_ledger.json 结构异常(应为含 hash 字符串的对象数组), 拒绝覆盖(先人工核查): {path}")
    return data


def _validate_linked_clause_ids(entries: list[dict], source_name: str, path: Path) -> None:
    """D7 外键扫描前置装载校验: linked_clause_ids 存在时必须为字符串数组。

    畸形值(字符串会按字符迭代产出垃圾 clause_fk_invalid; dict/int 元素或非列表会使
    scan_foreign_keys 抛未捕获 TypeError 逃出 main() 的 MergeAddendaError 处理)——
    按状态契约在装载时干净拒绝(退出码 1, 拒绝覆盖先人工核查), 不带病进入落账管线。
    """
    for index, entry in enumerate(entries):
        linked = entry.get("linked_clause_ids")
        if linked is None:
            continue
        if not isinstance(linked, list) or not all(isinstance(item, str) for item in linked):
            raise MergeAddendaError(f"{source_name} items[{index}] linked_clause_ids 应为字符串数组(实际类型 {type(linked).__name__} 或含非字符串元素), 拒绝覆盖(先人工核查): {path}")


def load_state(state_dir: Path) -> dict:
    """装载三状态文件: clauses 必需(阶段2 前提), structure/rubric 可选但损坏即拒绝覆盖。"""
    clauses_path = state_dir / STATE_FILES["clauses"]
    clauses = _load_json_file(clauses_path, "clauses.json")
    if not isinstance(clauses, list) or not all(isinstance(c, dict) for c in clauses):
        raise MergeAddendaError(f"clauses.json 结构异常(应为对象数组), 拒绝覆盖(先人工核查): {clauses_path}")
    for index, clause in enumerate(clauses):
        if not isinstance(clause.get("clause_id"), str) or not clause["clause_id"]:
            raise MergeAddendaError(f"clauses.json items[{index}] 缺非空字符串 clause_id, 拒绝覆盖(先人工核查): {clauses_path}")
        if clause.get("source_ref") is not None and not isinstance(clause.get("source_ref"), dict):
            raise MergeAddendaError(f"clauses.json items[{index}] source_ref 应为对象或 null(锚点匹配依赖其 section 字段), 拒绝覆盖(先人工核查): {clauses_path}")

    structure: list[dict] = []
    structure_path = state_dir / STATE_FILES["structure"]
    if structure_path.is_file():
        data = _load_json_file(structure_path, "structure.json")
        if not isinstance(data, list) or not all(isinstance(node, dict) for node in data):
            raise MergeAddendaError(f"structure.json 结构异常(应为对象数组), 拒绝覆盖(先人工核查): {structure_path}")
        _validate_linked_clause_ids(data, "structure.json", structure_path)
        structure = data

    rubric_items: list[dict] = []
    rubric_path = state_dir / STATE_FILES["rubric"]
    if rubric_path.is_file():
        data = _load_json_file(rubric_path, "rubric.json")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not all(isinstance(item, dict) for item in data["items"]):
            raise MergeAddendaError(f"rubric.json 结构异常(应为含 items 数组的对象), 拒绝覆盖(先人工核查): {rubric_path}")
        _validate_linked_clause_ids(data["items"], "rubric.json", rubric_path)
        rubric_items = data["items"]

    return {"clauses": clauses, "structure": structure, "rubric_items": rubric_items}


def load_whitelist(state_dir: Path) -> set[tuple[str, str]] | None:
    """装载实体白名单(确认门1 锁定); 缺失 → None(交 D3 增量流程按空集 diff 并浮出异常)。"""
    path = state_dir / STATE_FILES["whitelist"]
    if not path.is_file():
        return None
    data = _load_json_file(path, "entities_whitelist.json")
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise MergeAddendaError(f"entities_whitelist.json 结构异常(应为含 entities 数组的对象), 拒绝覆盖(先人工核查): {path}")
    keys: set[tuple[str, str]] = set()
    for index, entity in enumerate(data["entities"]):
        if not isinstance(entity, dict) or not isinstance(entity.get("type"), str) or not entity["type"].strip() or not isinstance(entity.get("value"), str) or not entity["value"].strip():
            raise MergeAddendaError(f"entities_whitelist.json entities[{index}] 应为含非空 type/value 的对象, 拒绝覆盖(先人工核查): {path}")
        keys.add((entity["type"], entity["value"]))
    return keys


def load_entities_pending(state_dir: Path) -> list[dict] | None:
    """装载既有增量实体清单(本脚本自有产物); 缺失 → None; 损坏 → 拒绝覆盖。"""
    path = state_dir / STATE_FILES["entities_pending"]
    if not path.is_file():
        return None
    data = _load_json_file(path, "addendum_entities_pending.json")
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list) or not all(isinstance(e, dict) for e in data["entities"]):
        raise MergeAddendaError(f"addendum_entities_pending.json 结构异常(应为含 entities 数组的对象), 拒绝覆盖(先人工核查): {path}")
    return data["entities"]


# =============================================================================
# 条款载荷校验(内联 clauses.schema.json 同子集) + 落账归一化
# =============================================================================


def validate_clause(clause: dict) -> list[str]:
    """校验补遗新条款载荷, 返回错误消息列表(空 = 通过)。

    子集与 references/clauses.schema.json 对齐: 必填六字段/枚举/复合 ID 模式/
    source_ref 形状(quote ≤50 字)/response_skeleton 形状/未知字段拒绝。
    """
    errors: list[str] = []
    for key in ("clause_id", "source_file", "class", "category", "source_ref", "requirement"):
        if key not in clause:
            errors.append(f"缺必填字段 {key}")
    if "clause_id" in clause and not (isinstance(clause["clause_id"], str) and CLAUSE_ID_RE.match(clause["clause_id"])):
        errors.append(f"clause_id 应为复合 ID(<文件代号>-C-<序号>): {clause.get('clause_id')!r}")
    if clause.get("class") not in CLAUSE_CLASSES:
        errors.append(f"class 枚举非法 {clause.get('class')!r}(合法: {list(CLAUSE_CLASSES)})")
    if clause.get("category") not in CLAUSE_CATEGORIES:
        errors.append(f"category 枚举非法 {clause.get('category')!r}(合法: {list(CLAUSE_CATEGORIES)})")
    if "response_status" in clause and clause["response_status"] not in RESPONSE_STATUSES:
        errors.append(f"response_status 枚举非法 {clause.get('response_status')!r}(合法: {list(RESPONSE_STATUSES)})")
    if "from_addendum" in clause and not isinstance(clause["from_addendum"], bool):
        errors.append(f"from_addendum 应为 bool, 实际 {type(clause['from_addendum']).__name__}")
    if "voided" in clause and not isinstance(clause["voided"], bool):
        errors.append(f"voided 应为 bool, 实际 {type(clause['voided']).__name__}")
    if clause.get("superseded_by") is not None and not (isinstance(clause["superseded_by"], str) and CLAUSE_ID_RE.match(clause["superseded_by"])):
        errors.append(f"superseded_by 应为复合 ID 或 null: {clause.get('superseded_by')!r}")
    if "requirement" in clause and not (isinstance(clause["requirement"], str) and clause["requirement"].strip()):
        errors.append("requirement 应为非空字符串")
    if "source_file" in clause and not (isinstance(clause["source_file"], str) and clause["source_file"].strip()):
        errors.append("source_file 应为非空字符串")

    source_ref = clause.get("source_ref")
    if "source_ref" in clause:
        if not isinstance(source_ref, dict):
            errors.append("source_ref 应为对象")
        else:
            if not (isinstance(source_ref.get("quote"), str) and source_ref["quote"].strip()):
                errors.append("source_ref.quote 应为非空字符串(原文锚点, 绝不编造)")
            elif len(source_ref["quote"]) > 50:
                errors.append(f"source_ref.quote 长度 {len(source_ref['quote'])} 超 maxLength 50")
            if "section" in source_ref and not (isinstance(source_ref["section"], str) and source_ref["section"].strip()):
                errors.append("source_ref.section 应为非空字符串")
            if "page" in source_ref and source_ref["page"] is not None and not (isinstance(source_ref["page"], int) and not isinstance(source_ref["page"], bool)):
                errors.append(f"source_ref.page 应为整数或 null: {source_ref.get('page')!r}")
            if "para" in source_ref and source_ref["para"] is not None and not (isinstance(source_ref["para"], int) and not isinstance(source_ref["para"], bool)):
                errors.append(f"source_ref.para 应为整数或 null: {source_ref.get('para')!r}")
            extra = set(source_ref) - {"page", "section", "para", "quote"}
            if extra:
                errors.append(f"source_ref 未知字段: {sorted(extra)}")

    skeleton = clause.get("response_skeleton")
    if "response_skeleton" in clause:
        if not isinstance(skeleton, dict):
            errors.append("response_skeleton 应为对象")
        else:
            if not isinstance(skeleton.get("points"), list) or not all(isinstance(p, str) for p in skeleton["points"]):
                errors.append("response_skeleton.points 应为字符串数组")
            for key in ("evidence_ref", "suggestion"):
                if key in skeleton and skeleton[key] is not None and not isinstance(skeleton[key], str):
                    errors.append(f"response_skeleton.{key} 应为字符串或 null")
            extra = set(skeleton) - {"points", "evidence_ref", "suggestion"}
            if extra:
                errors.append(f"response_skeleton 未知字段: {sorted(extra)}")

    extra = set(clause) - set(CLAUSE_KNOWN_FIELDS)
    if extra:
        errors.append(f"未知字段: {sorted(extra)}")
    return errors


def normalize_addendum_clause(payload: dict) -> dict:
    """落账归一化: 强制 from_addendum=true + voided 补缺省 false, 字段序稳定(字节级幂等)。"""
    skeleton = payload.get("response_skeleton") or {"points": [], "evidence_ref": None, "suggestion": None}
    return {
        "clause_id": payload["clause_id"],
        "source_file": payload["source_file"],
        "class": payload["class"],
        "category": payload["category"],
        "source_ref": payload.get("source_ref"),
        "requirement": payload["requirement"],
        "response_status": payload.get("response_status", "unassigned"),
        "response_skeleton": skeleton,
        "from_addendum": True,
        "superseded_by": payload.get("superseded_by"),
        "voided": bool(payload.get("voided", False)),
    }


# new 动作幂等重放的内容一致口径: 只比对补遗"撰写内容"字段——response_status/from_addendum/
# voided/superseded_by 是生命周期状态, 后续阶段(填写态)或后续补遗(void/supersede)可合法变更,
# 不参与重放判定; 撰写字段任一不同 = 同 id 不同载荷 = 撞号, 必须浮出异常绝不静默吞载荷。
REPLAY_CONTENT_FIELDS = ("source_file", "class", "category", "source_ref", "requirement", "response_skeleton")


def _authored_content(clause: dict) -> tuple:
    return tuple(json.dumps(clause.get(field), sort_keys=True, ensure_ascii=False) for field in REPLAY_CONTENT_FIELDS)


def resolve_addendum_file(record: dict, record_path: Path) -> str:
    """addendum_file 解析统一口径: 非空字符串(去首尾空白)生效, 否则回退候选文件名。
    落账路径与台账跳过路径共用, 防两处判空口径漂移(纯空白串一处回退一处不回退)。"""
    name = record.get("addendum_file")
    return name.strip() if isinstance(name, str) and name.strip() else record_path.name


def _is_active(clause: dict) -> bool:
    """活条款 = 未 superseded 且未 voided(三级合并锚点只在活条款中解析)。"""
    return clause.get("superseded_by") is None and not clause.get("voided")


# =============================================================================
# D7 悬挂外键扫描(以落账后全量状态为口径)
# =============================================================================


def scan_foreign_keys(clauses: list[dict], structure: list[dict], rubric_items: list[dict]) -> list[dict]:
    """扫描 structure/rubric 的 linked_clause_ids: 缺失/superseded/voided → 异常清单不静默。"""
    by_id = {c.get("clause_id"): c for c in clauses}
    anomalies: list[dict] = []
    for source, entries, id_key in (("structure", structure, "node_id"), ("rubric", rubric_items, "rubric_id")):
        for entry in entries:
            for linked in entry.get("linked_clause_ids") or []:
                clause = by_id.get(linked)
                if clause is None:
                    reason = "missing"
                elif clause.get("superseded_by") is not None:
                    reason = "superseded"
                elif clause.get("voided"):
                    reason = "voided"
                else:
                    continue
                message = f"{source} {entry.get(id_key)} 悬挂外键 {linked}(reason={reason})——异常不静默, 待人工改链(D7)"
                anomalies.append({"kind": "clause_fk_invalid", "source": source, "item_id": entry.get(id_key), "clause_id": linked, "reason": reason, "message": message})
    return sorted(anomalies, key=lambda a: (str(a["source"]), str(a["item_id"]), str(a["clause_id"])))


# =============================================================================
# 落账管线
# =============================================================================


def _pending_entry(item: dict, tier: str, old, new, candidates: list[str] | None = None) -> dict:
    """pending 条目: 新旧并排 diff(确认门2 消费), tie/conflict 额外带候选目标列表。"""
    entry = {"mapping_id": item.get("mapping_id"), "tier": tier, "action": item.get("action"), "old": old, "new": new}
    if candidates is not None:
        entry["candidates"] = candidates
    return entry


def _dedup_entities(entities: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    kept: list[dict] = []
    for entity in entities:
        key = (entity["type"], entity["value"])
        if key in seen:
            continue
        seen.add(key)
        kept.append({"type": entity["type"], "value": entity["value"]})
    return kept


def process_entities(record: dict, whitelist: set[tuple[str, str]], anomalies: list[dict]) -> list[dict]:
    """D3 新实体提取: 补遗实体 diff 白名单 → 本次新增实体列表(增量清单写入由调用方决定)。
    whitelist 由调用方装载一次并传入(缺失时按空集 diff 并已浮出 whitelist_missing 异常)。"""
    raw = record.get("entities")
    if not isinstance(raw, list):
        anomalies.append({"kind": "malformed_record", "message": f"entities 应为数组, 实际 {type(raw).__name__}, 实体 diff 跳过"})
        return []
    valid: list[dict] = []
    for index, entity in enumerate(raw):
        if isinstance(entity, dict) and isinstance(entity.get("type"), str) and entity["type"].strip() and isinstance(entity.get("value"), str) and entity["value"].strip():
            valid.append({"type": entity["type"], "value": entity["value"]})
        else:
            anomalies.append({"kind": "malformed_entity", "index": index, "message": f"entities[{index}] 应为含非空 type/value 的对象, 跳过该实体"})
    return _dedup_entities([e for e in valid if (e["type"], e["value"]) not in whitelist])


def run_merge(state_dir: Path, record: dict, record_path: Path, decisions_entries: list, digest: str, ledger: list[dict]) -> tuple[dict, int]:
    """三级合并 + 落账 + D3/D7 防线; 返回 (摘要 JSON, 退出码)。"""
    state = load_state(state_dir)
    clauses: list[dict] = state["clauses"]
    by_id: dict[str, dict] = {c.get("clause_id"): c for c in clauses}

    anomalies: list[dict] = []
    pending: list[dict] = []
    applied = {"added": [], "superseded": [], "voided": [], "rejected": []}
    written: list[str] = []
    mutated = False
    new_ids_this_run: set[str] = set()  # 本次运行内已落账/重放的 new 条款 id(同候选撞号检测)

    addendum_file = resolve_addendum_file(record, record_path)

    # --- 第 1 步: 记录形态 + 逐条目校验(mapping_id 去重/schema/形态) ---------------
    items = record.get("items")
    if not isinstance(items, list):
        anomalies.append({"kind": "malformed_record", "file": record_path.name, "message": f"items 应为数组, 实际 {type(items).__name__}——候选记录形态不符, 全部[待确认]不落账"})
        items = []

    valid_items: list[dict] = []
    seen_mapping_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            anomalies.append({"kind": "malformed_item", "index": index, "message": f"items[{index}] 应为对象, 实际 {type(item).__name__}"})
            continue
        mapping_id = item.get("mapping_id")
        if not isinstance(mapping_id, str) or not mapping_id.strip():
            anomalies.append({"kind": "malformed_item", "index": index, "message": f"items[{index}] 缺非空字符串 mapping_id"})
            continue
        if mapping_id in seen_mapping_ids:
            anomalies.append({"kind": "duplicate_mapping_id", "mapping_id": mapping_id, "message": f"mapping_id {mapping_id} 重复, 首个映射生效、重复映射跳过(请核查补遗候选生成)"})
            continue
        seen_mapping_ids.add(mapping_id)
        action = item.get("action")
        if action not in ACTIONS:
            anomalies.append({"kind": "malformed_item", "mapping_id": mapping_id, "message": f"action 非法 {action!r}(合法: {list(ACTIONS)})"})
            continue
        clause = item.get("clause")
        anchor = item.get("anchor")
        target = item.get("target")
        anchor_ok = isinstance(anchor, dict) and isinstance(anchor.get("section"), str) and bool(anchor["section"].strip())
        target_ok = isinstance(target, str) and bool(target.strip())
        # 存在但形态非法 → 异常跳过, 绝不静默归一为 None(否则畸形锚点会降级为仅 target 驱动的
        # 相似度候选, 头号安全网"锚点与显式 target 不一致→异常"对该条目完全失效)
        if anchor is not None and not anchor_ok:
            anomalies.append({"kind": "malformed_item", "mapping_id": mapping_id, "message": f"anchor 存在但形态非法 {anchor!r}(应为含非空字符串 section 的对象)——异常, 不降级为相似度候选"})
            continue
        if target is not None and not target_ok:
            anomalies.append({"kind": "malformed_item", "mapping_id": mapping_id, "message": f"target 存在但形态非法 {target!r}(应为非空字符串条款 id)——异常, 不静默忽略"})
            continue
        if action in ("modify", "void") and not (anchor_ok or target_ok):
            anomalies.append({"kind": "malformed_item", "mapping_id": mapping_id, "message": f"{action} 映射必须提供 anchor(章节锚点)或 target(条款 id)之一"})
            continue
        if action in ("new", "modify") and not isinstance(clause, dict):
            anomalies.append({"kind": "malformed_item", "mapping_id": mapping_id, "message": f"{action} 映射必须提供新条款载荷 clause"})
            continue
        if action in ("new", "modify"):
            errors = validate_clause(clause)
            if errors:
                anomalies.append({"kind": "schema_violation", "mapping_id": mapping_id, "item_id": str(clause.get("clause_id", mapping_id)), "errors": errors, "message": "新条款载荷不符合 clauses 契约, [待确认]不落账"})
                continue
        valid_items.append({"item": item, "mapping_id": mapping_id, "action": action, "clause": clause if isinstance(clause, dict) else None, "anchor": anchor, "target": target})

    # --- 第 2 步: 裁决文件条目校验(unknown/duplicate; apply+target 语义在第 3 步) ---
    decision_by_id: dict[str, dict] = {}
    for index, decision in enumerate(decisions_entries):
        if not isinstance(decision, dict) or not isinstance(decision.get("mapping_id"), str) or not decision["mapping_id"].strip() or decision.get("decision") not in DECISION_VALUES:
            anomalies.append({"kind": "malformed_decision", "index": index, "message": f"decisions[{index}] 应为含非空 mapping_id 与 decision(apply|reject)的对象"})
            continue
        mapping_id = decision["mapping_id"]
        if mapping_id in decision_by_id:
            anomalies.append({"kind": "duplicate_decision", "mapping_id": mapping_id, "message": f"mapping_id {mapping_id} 裁决重复, 以首条为准(请核查人工裁决文件)"})
            continue
        decision_by_id[mapping_id] = decision
    for mapping_id in decision_by_id:
        if mapping_id not in seen_mapping_ids:
            anomalies.append({"kind": "unknown_decision", "mapping_id": mapping_id, "message": f"裁决指向不存在的 mapping_id {mapping_id}(候选映射集里没有此项)"})

    # --- 第 3 步: 三级解析(锚点自动/相似度候选/平手) -------------------------------
    resolutions: list[dict] = []
    for entry in valid_items:
        mapping_id, action, clause, anchor, target = entry["mapping_id"], entry["action"], entry["clause"], entry["anchor"], entry["target"]
        res = {"entry": entry, "mode": None, "status": None, "target_id": None, "candidates": None, "replay": False}
        resolutions.append(res)
        if action == "new":
            res["mode"], res["status"] = "new", "apply"
            continue
        if anchor is not None:
            section = anchor["section"]
            matches = [c for c in clauses if (c.get("source_ref") or {}).get("section") == section]
            actives = [c for c in matches if _is_active(c)]
            if len(actives) == 1:
                resolved = actives[0].get("clause_id")
                if entry["target"] is not None and entry["target"] != resolved:
                    mismatch = f"锚点唯一命中 {resolved} 与显式 target {entry['target']} 不一致——异常, 不合并(绝不静默取其一)"
                    anomalies.append({"kind": "anchor_target_mismatch", "mapping_id": mapping_id, "anchor_section": section, "anchor_resolved": resolved, "declared_target": entry["target"], "message": mismatch})
                    res["status"] = "dropped"
                else:
                    res["mode"], res["status"], res["target_id"] = "auto", "apply", resolved
            elif len(actives) >= 2:
                res["mode"], res["candidates"] = "tie", sorted(str(c.get("clause_id")) for c in actives)
            else:
                # 0 活条款: 先判幂等重放(同补遗同映射已落账), 否则锚点落空异常
                replay_id = None
                if action == "modify":
                    replayed = [c for c in matches if c.get("superseded_by") == clause.get("clause_id")]
                    if len(replayed) == 1 and clause["clause_id"] in by_id and by_id[clause["clause_id"]].get("from_addendum"):
                        replay_id = replayed[0].get("clause_id")
                else:
                    replayed = [c for c in matches if c.get("voided")]
                    if len(replayed) == 1:
                        replay_id = replayed[0].get("clause_id")
                if replay_id is not None:
                    res["mode"], res["status"], res["target_id"], res["replay"] = "auto", "apply", replay_id, True
                else:
                    anomalies.append({"kind": "anchor_no_match", "mapping_id": mapping_id, "section": section, "message": f"章节锚点 {section!r} 在活条款中无命中(且非已落账重放)——异常, 不落账"})
                    res["status"] = "dropped"
        else:
            res["mode"], res["target_id"] = "similar", entry["target"]

    # --- 第 4 步: 裁决应用(similar/tie 需裁决; auto/new 上 apply=冗余异常, reject=有效否决) ---
    # reject 对任何层级都是有效否决(人工可不落账任何一条映射)——这也是同目标冲突的
    # 解除手段: 否决其一后, 余者第 5 步不再撞目标, 自动落账(见 TestMergeAddendaConflicts)。
    for res in resolutions:
        entry = res["entry"]
        mapping_id, action, clause = entry["mapping_id"], entry["action"], entry["clause"]
        if res["status"] == "dropped":
            continue
        decision = decision_by_id.get(mapping_id)
        mode = res["mode"]
        if mode in ("new", "auto"):
            if decision is not None:
                if decision["decision"] == "reject":
                    res["status"] = "rejected"
                    applied["rejected"].append(mapping_id)
                else:
                    anomalies.append({"kind": "unnecessary_decision", "mapping_id": mapping_id, "message": f"对自动落账项 {mapping_id} 的 apply 裁决是冗余的(锚点已唯一命中/新增无需裁决; 若需否决请用 reject)——异常浮出, 自动项照常落账"})
            continue
        if mode == "similar":
            target_clause = by_id.get(res["target_id"])
            reason = None
            if target_clause is None:
                reason = "missing"
            elif target_clause.get("superseded_by") is not None:
                if action == "modify" and target_clause.get("superseded_by") == clause.get("clause_id"):
                    res.update(mode="auto", status="apply", replay=True)
                    continue
                reason = "superseded"
            elif target_clause.get("voided"):
                if action == "void":
                    res.update(mode="auto", status="apply", replay=True)
                    continue
                reason = "voided"
            if reason is not None:
                anomalies.append({"kind": "target_inactive", "mapping_id": mapping_id, "target": res["target_id"], "reason": reason, "message": f"目标条款 {res['target_id']} 已不活跃(reason={reason}), 裁决无法执行——条目保持待裁决"})
                res["status"] = "pending"
                pending.append(_pending_entry(entry["item"], "similar", target_clause, clause))
                continue
            if decision is None:
                anomalies.append({"kind": "pending_decision", "mapping_id": mapping_id, "tier": "similar", "message": "相似度候选需 --decisions 人工裁决(确认门2), 脚本不自行合并"})
                res["status"] = "pending"
                pending.append(_pending_entry(entry["item"], "similar", target_clause, clause))
            elif decision["decision"] == "reject":
                res["status"] = "rejected"
                applied["rejected"].append(mapping_id)
            else:
                # 裁决携带 target 时必须与条目 target 一致(与 tie 层对同字段的校验姿态对齐),
                # 不一致 → 异常浮出保持待裁决, 绝不无声背离人工指示落账到别处
                decided_target = decision.get("target")
                if decided_target is not None and decided_target != res["target_id"]:
                    msg = f"相似度裁决 target {decided_target!r} 与候选条目 target {res['target_id']!r} 不一致——条目保持待裁决(裁决 target 仅可与条目一致或省略)"
                    anomalies.append({"kind": "malformed_decision", "mapping_id": mapping_id, "message": msg})
                    res["status"] = "pending"
                    pending.append(_pending_entry(entry["item"], "similar", target_clause, clause))
                else:
                    res["status"] = "apply"
            continue
        # mode == "tie"
        candidates = res["candidates"] or []
        if decision is None:
            anomalies.append({"kind": "pending_decision", "mapping_id": mapping_id, "tier": "tie", "message": f"锚点平手(候选: {candidates})需 --decisions 人工裁决选定 target, 绝不静默取首个"})
            res["status"] = "pending"
            pending.append(_pending_entry(entry["item"], "tie", None, clause, candidates))
        elif decision["decision"] == "reject":
            res["status"] = "rejected"
            applied["rejected"].append(mapping_id)
        else:
            decided_target = decision.get("target")
            if not (isinstance(decided_target, str) and decided_target in candidates):
                anomalies.append({"kind": "malformed_decision", "mapping_id": mapping_id, "message": f"平手裁决 apply 必须提供 target 且属于候选集 {candidates}, 实际 {decided_target!r}——条目保持待裁决"})
                res["status"] = "pending"
                pending.append(_pending_entry(entry["item"], "tie", None, clause, candidates))
            else:
                res["target_id"], res["status"] = decided_target, "apply"

    # --- 第 5 步: 同目标冲突检测(裁决后仍在场的修改/作废映射不得撞目标) ------------
    by_target: dict[str, list[dict]] = {}
    for res in resolutions:
        if res["status"] == "apply" and res["entry"]["action"] in ("modify", "void"):
            by_target.setdefault(str(res["target_id"]), []).append(res)
    for target_id, group in sorted(by_target.items()):
        if len(group) < 2:
            continue
        mapping_ids = [r["entry"]["mapping_id"] for r in group]
        anomalies.append({"kind": "target_conflict", "target": target_id, "mapping_ids": mapping_ids, "message": f"映射 {mapping_ids} 撞同一条款 {target_id}——全部待裁决, 绝不静默取首个"})
        for res in group:
            res["status"] = "pending"
            anomalies.append({"kind": "pending_decision", "mapping_id": res["entry"]["mapping_id"], "tier": "conflict", "message": f"同目标冲突(target={target_id})需 --decisions 裁决否决其一, 余者自动落账"})
            pending.append(_pending_entry(res["entry"]["item"], "conflict", by_id.get(target_id), res["entry"]["clause"], [target_id]))

    # --- 第 6 步: 落账(new 入库/modify supersede/void 作废; 重放幂等零变更) --------
    for res in resolutions:
        if res["status"] != "apply":
            continue
        entry = res["entry"]
        mapping_id, action, clause = entry["mapping_id"], entry["action"], entry["clause"]
        if action == "new":
            new_id = clause["clause_id"]
            if new_id in new_ids_this_run:
                anomalies.append({"kind": "duplicate_clause_id", "mapping_id": mapping_id, "clause_id": new_id, "message": f"同一候选文件内多条 new 映射撞 clause_id {new_id}——候选生成缺陷, 仅首条落账, 绝不静默吞第二份载荷"})
                continue
            existing = by_id.get(new_id)
            if existing is not None:
                # 幂等重放判定: 库内须为补遗条款且载荷撰写内容一致(跨补遗同号不同内容 = 撞号)
                if existing.get("from_addendum") and _authored_content(existing) == _authored_content(normalize_addendum_clause(clause)):
                    new_ids_this_run.add(new_id)
                    applied["added"].append(new_id)  # 幂等重放: 已入库的同载荷补遗条款, 零变更
                    continue
                detail = "且载荷内容与既有补遗条款不一致(同 id 不同载荷, 跨补遗撞号)" if existing.get("from_addendum") else "与既有非补遗条款撞号"
                anomalies.append({"kind": "duplicate_clause_id", "mapping_id": mapping_id, "clause_id": new_id, "message": f"新增条款 id {new_id} 已存在{detail}——异常, 不落账(如需变更既有条款请走 modify)"})
                continue
            normalized = normalize_addendum_clause(clause)
            clauses.append(normalized)
            by_id[new_id] = normalized
            new_ids_this_run.add(new_id)
            applied["added"].append(new_id)
            mutated = True
        elif action == "modify":
            new_id = clause["clause_id"]
            old = by_id.get(str(res["target_id"]))
            if old is None:
                anomalies.append({"kind": "target_inactive", "mapping_id": mapping_id, "target": res["target_id"], "reason": "missing", "message": f"目标条款 {res['target_id']} 不存在——异常, 不落账"})
                continue
            if old.get("clause_id") == new_id:
                anomalies.append({"kind": "self_supersede", "mapping_id": mapping_id, "clause_id": new_id, "message": f"新条款 {new_id} 与被修改条款同 id(自指 supersede)——异常, 不落账"})
                continue
            if res["replay"]:
                # 重放内容一致性(与 new 动作撞号防线同口径 _authored_content): 锚点层/相似度层
                # 重放在此汇流, 库内新条款必须存在、来自补遗且撰写内容与本次候选一致;
                # 不一致(部分落账后操作者编辑载荷重跑)→ 异常浮出而非重放, 绝不静默吞掉
                # 编辑后的候选(否则陈旧内容永久封存且零信号), 待裁决补齐后也不得记台账。
                stored_new = by_id.get(new_id)
                if stored_new is None or not stored_new.get("from_addendum") or _authored_content(stored_new) != _authored_content(normalize_addendum_clause(clause)):
                    detail = "库内不存在(重放链悬挂, 状态疑被人工改动)" if stored_new is None else ("库内条款非补遗来源" if not stored_new.get("from_addendum") else "载荷内容与库内补遗条款不一致(同 id 不同载荷)")
                    anomalies.append({"kind": "replay_content_mismatch", "mapping_id": mapping_id, "clause_id": new_id, "message": f"modify 重放链指向的新条款 {new_id} {detail}——绝不静默吞编辑后的候选, 异常浮出不重放"})
                    continue
                applied["added"].append(new_id)
                applied["superseded"].append({"from": old.get("clause_id"), "to": new_id})
                continue
            if not _is_active(old):
                inactive_reason = "superseded" if old.get("superseded_by") is not None else "voided"
                inactive_msg = f"目标条款 {old.get('clause_id')} 已不活跃(reason={inactive_reason})——异常, 不落账"
                anomalies.append({"kind": "target_inactive", "mapping_id": mapping_id, "target": old.get("clause_id"), "reason": inactive_reason, "message": inactive_msg})
                continue
            if new_id in by_id:
                anomalies.append({"kind": "duplicate_clause_id", "mapping_id": mapping_id, "clause_id": new_id, "message": f"新条款 id {new_id} 已存在(且非本映射的重放链)——异常, 不落账"})
                continue
            old["superseded_by"] = new_id
            normalized = normalize_addendum_clause(clause)
            clauses.append(normalized)
            by_id[new_id] = normalized
            applied["added"].append(new_id)
            applied["superseded"].append({"from": old.get("clause_id"), "to": new_id})
            mutated = True
        else:  # void
            old = by_id.get(str(res["target_id"]))
            if old is None:
                anomalies.append({"kind": "target_inactive", "mapping_id": mapping_id, "target": res["target_id"], "reason": "missing", "message": f"目标条款 {res['target_id']} 不存在——异常, 不落账"})
                continue
            if res["replay"] or old.get("voided"):
                applied["voided"].append(str(old.get("clause_id")))
                continue
            old["voided"] = True
            applied["voided"].append(str(old.get("clause_id")))
            mutated = True

    # --- 第 7 步: D7 悬挂外键扫描(以落账后全量状态为口径, 不阻断落账) -------------
    anomalies.extend(scan_foreign_keys(clauses, state["structure"], state["rubric_items"]))

    # --- 第 8 步: D3 新实体 diff → 增量清单(累积式; 白名单不经本脚本修改) ----------
    # 白名单/既有增量各装载一次, 供 diff 与合并复用(不再二次读盘)。
    new_entities: list[dict] = []
    if "entities" in record:
        whitelist = load_whitelist(state_dir)
        if whitelist is None:
            anomalies.append({"kind": "whitelist_missing", "message": "entities_whitelist.json 缺失, 按空集 diff(全部进增量清单)——确认门1 未锁定白名单或文件被移动, 修复后重跑需重新 diff"})
            whitelist = set()
        new_entities = process_entities(record, whitelist, anomalies)
        if isinstance(record.get("entities"), list):
            existing_pending = load_entities_pending(state_dir) or []
            merged_pending = []
            seen: set[tuple[str, str]] = set()
            for entity in [*existing_pending, *new_entities]:
                if not (isinstance(entity, dict) and isinstance(entity.get("type"), str) and isinstance(entity.get("value"), str)):
                    continue
                key = (entity["type"], entity["value"])
                if key in seen or key in whitelist:
                    continue
                seen.add(key)
                merged_pending.append({"type": entity["type"], "value": entity["value"]})
            pending_path = state_dir / STATE_FILES["entities_pending"]
            if merged_pending:
                if existing_pending != merged_pending:
                    atomic_write_json(pending_path, {"entities": merged_pending})
                    written.append(STATE_FILES["entities_pending"])
            elif pending_path.is_file():
                pending_path.unlink()  # 白名单确认后增量清零: 陈旧清单出清, 不留误导
                written.append(f"del:{STATE_FILES['entities_pending']}")  # 删除亦入摘要(前缀区分写入), 不可见即不透明

    # --- 第 9 步: 写盘(仅变更文件) + 台账(干净完成才记, 重跑可跳过) ----------------
    if mutated:
        atomic_write_json(state_dir / STATE_FILES["clauses"], clauses)
        written.append(STATE_FILES["clauses"])

    clean = not anomalies and not pending
    ledger_recorded = False
    if clean:
        ledger.append({"hash": digest, "addendum_file": addendum_file, "applied_at": datetime.now().isoformat(timespec="seconds"), "applied": applied})
        atomic_write_json(state_dir / STATE_FILES["ledger"], ledger)
        written.append(STATE_FILES["ledger"])
        ledger_recorded = True

    summary = {"addendum_file": addendum_file, "hash": digest, "skipped": False, "written": written, "ledger_recorded": ledger_recorded, "applied": applied, "pending": pending, "anomalies": anomalies, "new_entities": new_entities}
    return summary, (EXIT_OK if clean else EXIT_ANOMALY)


# =============================================================================
# CLI
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="merge_addenda.py",
        description="投标方案编写·阶段3 补遗/答疑确定性落账: 三级合并(锚点自动/相似度候选待人裁/平手须裁决) + 内容哈希幂等台账 + D3 新实体增量 + D7 悬挂外键拦截(无 LLM)",
    )
    parser.add_argument("--addendum-candidates", required=True, help="补遗候选 JSON 文件(一份补遗=一次调用=一个文件: addendum_file/entities/items)")
    parser.add_argument("--state-dir", required=True, help="状态目录(读/写 clauses.json / merge_ledger.json / addendum_entities_pending.json; 原子写盘)")
    parser.add_argument("--decisions", default=None, help="人工裁决 JSON({decisions: [{mapping_id, decision: apply|reject, target?}]}); 相似度候选/平手/冲突必经此门")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 ingest 的 OCR 分流退出码撞号——统一改道
        # EXIT_ERROR; --help 等正常退出(code 0)原样放行(同 extract.py 约定)。
        if not exc.code:
            return EXIT_OK
        print(f"[merge_addenda] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        state_dir = Path(args.state_dir)
        record_path = Path(args.addendum_candidates)
        record = load_candidates(record_path)
        decisions_entries = load_decisions(args.decisions) if args.decisions is not None else []
        ledger = load_ledger(state_dir)
        digest = content_hash(record)

        # 幂等台账: 同 hash 重跑直接跳过, 零写入零变更(状态目录字节级不变)。
        known_hashes = {entry["hash"] for entry in ledger}
        if digest in known_hashes:
            addendum_name = resolve_addendum_file(record, record_path)
            summary = {
                "addendum_file": addendum_name,
                "hash": digest,
                "skipped": True,
                "written": [],
                "ledger_recorded": False,
                "applied": {"added": [], "superseded": [], "voided": [], "rejected": []},
                "pending": [],
                "anomalies": [],
                "new_entities": [],
            }
            print(json.dumps(summary, ensure_ascii=False))
            return EXIT_OK

        summary, rc = run_merge(state_dir, record, record_path, decisions_entries, digest, ledger)
        print(json.dumps(summary, ensure_ascii=False))
        return rc
    except MergeAddendaError as exc:
        print(f"[merge_addenda] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
