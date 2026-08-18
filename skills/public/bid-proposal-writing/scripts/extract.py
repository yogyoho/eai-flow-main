#!/usr/bin/env python3
"""extract.py — 投标方案编写技能·阶段2 候选 JSON 的确定性校验 + 合并(无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md「阶段2 extract」。
LLM 提取循环由 Agent 在上下文内执行(提示词=references/extraction_prompt.md 三个子模板);
本脚本只做循环产物的确定性防线, 不调 LLM。

用法:
    python extract.py validate --candidates <候选JSON...> --sections sections.json [--declared-total N(可为小数)]
    python extract.py merge    --candidates <候选JSON...> --sections sections.json --state-dir <dir> [--declared-total N(可为小数)]

候选记录契约(一次裁决 = 一个文件, 对齐 extraction_prompt.md 循环纪律; 0 条也显式判空):
    {"chunk_id"|"table_id": "<id>",        // 二选一, 必须存在于 sections.json
     "kind": "clauses|structure|rubric",   // ①条款提取 / ②格式章节槽位定型 / ③评分细则表抽取
     "items": [<对应 references/*.schema.json 的候选项>...],
     "note": "<判空理由, 可选>"}

校验规则(设计文档锁定, 不缺不漏不加):
    1. 锚点必须存在于 sections.json: 裁决记录的 chunk_id/table_id 必须已发放;
       clauses 项的 (source_file, source_ref.section) 与 rubric 项的 (所在表 source_file,
       source_ref.section) 必须能落到某个 chunk/table 的 (source_file, anchor.section)。
    2. 枚举合法: 逐项对 references/{clauses,structure,rubric}.schema.json 校验——
       stdlib mini JSON Schema 校验器(沙箱无 jsonschema, 只实现三 schema 用到的子集:
       type/enum/pattern/minLength/maxLength/minimum/required/properties/
       additionalProperties/items)。
    3. 跨块去重: clause_id/node_id/rubric_id 不得跨裁决块重复; 同一 chunk/table 的
       重复裁决记录(检查点分叉)双双隔离, 绝不静默取首个。
    4. rubric Σmax_score 必须等于评分办法声称总分; 校验基准 = --declared-total, merge 未给该
       flag 时回用既有 rubric.json total_score——防重合并把"声称总分"与"实际 Σ"在同一状态里
       无告警分叉; 不一致 → 异常并中止(merge 整体中止、一个状态文件都不写, 防带病状态入库;
       score_simulate.py 纵深复检)。
    5. D5 覆盖度防线: sections.json 里每个 chunk_id/table_id 在候选裁决集中必须有记录;
       未裁决 id → 异常清单"待门1显式判空", 绝不静默跳过。
    6. D7 外键装载校验: structure/rubric 项的 linked_clause_ids 必须存在于 clauses
       (validate=候选集; merge=既有状态∪干净候选)且未被 superseded; 悬挂引用 → 异常项不静默。
    7. D7 状态一致性: 派生字段(fill_status 等)剥离后现算不落盘;
       所有状态文件临时文件+os.replace 原子写; 校验失败的裁决块整体保持[待确认]不合并。

merge 语义: 干净裁决块按 id(clause_id/node_id/rubric_id)upsert 进三状态文件
(clauses.json=list / structure.json=list / rubric.json={total_score, items}),
既有未被覆盖条目原样保留 → 同一候选集重复合并幂等。

脚本纪律: 纯 Python 3.12; stdlib only(ingest.py 可用 pdfplumber, 本脚本无需);
不调用 LLM; 不 import app.*/deerflow.*。

退出码:
    0 = 干净完成(--help 等正常终止亦为 0)
    1 = 用法/文件错误(候选/sections/状态文件缺失、不可解析、结构损坏; argparse 用法错误
        统一改道 1——2 留给 ingest 的 OCR 分流语义, 防编排方误路由)
    3 = 完成但有异常项(摘要 JSON 的 anomalies 列出; merge 时除 Σ 不一致整体中止外,
        异常块隔离、干净块照常合并落盘)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

import state_guard

# --- 退出码约定 -----------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

# --- 候选记录/状态契约 -----------------------------------------------------------
KINDS = ("clauses", "structure", "rubric")
KIND_ID_KEY = {"clauses": "clause_id", "structure": "node_id", "rubric": "rubric_id"}
KIND_SCHEMA_FILE = {"clauses": "clauses.schema.json", "structure": "structure.schema.json", "rubric": "rubric.schema.json"}

# D7 派生字段: 各状态文件落盘前必须剥离的键(schema 仅声明值域供内存态/渲染态校验,
# 候选 JSON 与落盘文件均不得包含)
DERIVED_FIELDS = {"structure": ("fill_status",)}

# references/ 契约目录默认位置: <技能根>/references(沙箱挂载形态 /mnt/skills/public/...)
DEFAULT_REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

STATE_FILES = {"clauses": "clauses.json", "structure": "structure.json", "rubric": "rubric.json"}


class ExtractError(Exception):
    """用法/文件错误 → 退出码 1。"""


# =============================================================================
# stdlib mini JSON Schema 校验器(覆盖三 schema 用到的关键字子集)
# =============================================================================


def _json_type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _json_type_matches(expected, value) -> bool:
    names = [expected] if isinstance(expected, str) else list(expected)
    for name in names:
        if name == "string" and isinstance(value, str):
            return True
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if name == "boolean" and isinstance(value, bool):
            return True
        if name == "null" and value is None:
            return True
        if name == "object" and isinstance(value, dict):
            return True
        if name == "array" and isinstance(value, list):
            return True
    return False


def validate_against_schema(schema: dict, value, path: str = "$") -> list[str]:
    """按 schema 关键字子集校验 value, 返回错误消息列表(空 = 通过)。

    子集: type(单值或数组)/enum/pattern/minimum/minLength/maxLength/required/
    properties/additionalProperties(false)/items; description 忽略。
    bool 不视作 integer/number(JSON Schema 语义), 防候选把 true 混进数值字段。
    """
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None and not _json_type_matches(expected_type, value):
        return [f"{path}: 类型应为 {expected_type}, 实际 {_json_type_name(value)}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 枚举非法 {value!r}(合法: {schema['enum']})")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: 长度 {len(value)} 低于 minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 长度 {len(value)} 超过 maxLength {schema['maxLength']}")
        if "pattern" in schema:
            pattern = schema["pattern"]
            # ECMA-262 语义对齐: Python 的 `$` 额外匹配"末尾换行之前"(ECMA 不允许), id 类字段的
            # 锚定 pattern 会放行 "ZB-C-001\n" 这类含尾随换行的值——尾部追加强断言 \Z 收紧。
            if pattern.endswith("$"):
                pattern += r"\Z"
            if not re.search(pattern, value):
                errors.append(f"{path}: {value!r} 不匹配模式 {schema['pattern']!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} 低于 minimum {schema['minimum']}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 缺必填字段 {key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: 未知字段 {key}")
        for key, sub_schema in properties.items():
            if key in value:
                errors.extend(validate_against_schema(sub_schema, value[key], f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for index, element in enumerate(value):
            errors.extend(validate_against_schema(schema["items"], element, f"{path}[{index}]"))
    return errors


def load_schemas(references_dir: str | Path | None = None) -> dict[str, dict]:
    """装载三份契约 schema; 缺失/不可解析 → ExtractError(退出码 1)。"""
    base = Path(references_dir) if references_dir is not None else DEFAULT_REFERENCES_DIR
    schemas: dict[str, dict] = {}
    for kind, filename in KIND_SCHEMA_FILE.items():
        path = base / filename
        if not path.is_file():
            raise ExtractError(f"references 契约缺失: {path}(--references 可指定目录)")
        try:
            schemas[kind] = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            raise ExtractError(f"references 契约不可读/不可解析(需 UTF-8): {path}: {exc}") from exc
    return schemas


# =============================================================================
# 装载: sections / 候选记录 / 状态文件
# =============================================================================


def load_sections(path: str | Path) -> dict:
    """装载 sections.json(ingest 产物); 不存在/损坏/值类型错/非 UTF-8 → ExtractError, 绝不静默。"""
    path = Path(path)
    if not path.is_file():
        raise ExtractError(f"sections.json 不存在: {path}(先跑 ingest.py 阶段1)")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ExtractError(f"sections.json 不可读/不可解析(需 UTF-8): {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list) or not isinstance(data.get("tables"), list):
        raise ExtractError(f"sections.json 结构异常(应为含 chunks/tables 数组的对象): {path}")
    for key in ("chunks", "tables"):
        if not all(isinstance(entry, dict) for entry in data[key]):
            raise ExtractError(f"sections.json 结构异常({key} 应为对象数组): {path}")
    # 裁决 id 装载校验: 缺 id/类型错的条目会让 evaluate 的 id 集合混入 None/非 str,
    # 在未裁决排序或锚点比对处裸崩 TypeError——装载层直接拒绝。
    for key, id_key in (("chunks", "chunk_id"), ("tables", "table_id")):
        for entry in data[key]:
            value = entry.get(id_key)
            if not isinstance(value, str) or not value:
                raise ExtractError(f"sections.json {key} 条目缺非空字符串 {id_key}: {path}(先人工核查)")
    # anchor 装载校验(与 id 同型防线): evaluate 以 (e.get("anchor") or {}).get("section") 构建
    # D2 锚点覆盖集, anchor 为真值非 dict(str/list)会在该处裸抛 AttributeError 逃出 main();
    # falsy 非 dict 虽不裸崩但同样产出无意义锚点(section=None)——值类型错一律在装载层拒绝。
    # ingest 产物恒为对象 {"section": ..., "para"/"page": ...}; 缺失/显式 null 放行(下游已兜底)。
    for key in ("chunks", "tables"):
        for entry in data[key]:
            anchor = entry.get("anchor")
            if anchor is not None and not isinstance(anchor, dict):
                raise ExtractError(f"sections.json {key} 条目 anchor 应为对象或缺省: {path}(先人工核查)")
    return data


def load_candidate(path: str | Path) -> dict:
    """装载一个候选裁决记录文件; 缺失/不可解析 → ExtractError。"""
    path = Path(path)
    if not path.is_file():
        raise ExtractError(f"候选文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ExtractError(f"候选文件不可读/不可解析(需 UTF-8; 疑似 LLM 输出截断或编码错, 先补跑该 chunk): {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractError(f"候选记录应为 JSON 对象: {path}")
    return data


def strip_derived_fields(item: dict, kind: str | None = None) -> dict:
    """剥离 D7 派生字段(如 structure 的 fill_status)——现算不落盘, 返回浅拷贝不改原对象。

    kind=None 时剥离全部已知派生字段(并集)。
    """
    if kind is None:
        derived = tuple({key for fields in DERIVED_FIELDS.values() for key in fields})
    else:
        derived = DERIVED_FIELDS.get(kind, ())
    if not derived:
        return dict(item)
    return {key: value for key, value in item.items() if key not in derived}


# R1(终审 Chunk 1): 管线归一字段缺省——clauses.schema.json 与 extraction_prompt.md 承诺
# "response_status/response_skeleton/from_addendum/superseded_by 由管线归一, 候选可不填";
# 落盘状态是持久契约(build_output/score_simulate 对 response_status 做硬枚举校验),
# 省略路径漏归一会让合法候选在阶段4/5 硬断。缺省口径对齐 merge_addenda.normalize_addendum_clause。
CLAUSE_PIPELINE_DEFAULTS = {"response_status": "unassigned", "from_addendum": False, "superseded_by": None, "voided": False}


def _normalize_clause_defaults(item: dict) -> dict:
    """补齐候选省略的管线归一字段(setdefault 语义: 绝不覆盖已存在值); 返回浅拷贝不改原对象。"""
    normalized = dict(item)
    for key, value in CLAUSE_PIPELINE_DEFAULTS.items():
        normalized.setdefault(key, value)
    return normalized


def _load_state_list(path: Path) -> list[dict]:
    """装载 list 型状态文件(clauses/structure); 缺失→[]; 损坏/类型错→拒绝覆盖。"""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ExtractError(f"既有 {path.name} 不可读/不可解析(需 UTF-8), 拒绝覆盖(先人工核查): {path}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(entry, dict) for entry in data):
        raise ExtractError(f"既有 {path.name} 结构异常(应为对象数组), 拒绝覆盖: {path}")
    return data


def load_state(state_dir: str | Path) -> dict:
    """装载三状态文件; 返回 {clauses, structure, rubric_items, total_score, existed}。

    既有 rubric 项的 max_score 做装载校验(number: int|float 非 bool): 缺失误按 0 计、bool True
    误按 1 计会让 Σ 摘要失真或制造假 fatal——手工编辑场景的纵深防线, 损坏即拒绝覆盖。
    契约对齐 rubric.schema.json type=number 与 score_simulate._check_rubric_sum: 合法小数
    满分(如 2.5/0.5)不得被自身落盘产物拒绝——那会让幂等重合并自锁(R3, 终审 Chunk 1)。
    """
    state_dir = Path(state_dir)
    clauses_path = state_dir / STATE_FILES["clauses"]
    structure_path = state_dir / STATE_FILES["structure"]
    rubric_path = state_dir / STATE_FILES["rubric"]

    clauses = _load_state_list(clauses_path)
    structure = [strip_derived_fields(node, "structure") for node in _load_state_list(structure_path)]

    rubric_items: list[dict] = []
    total_score = None
    rubric_existed = rubric_path.is_file()
    if rubric_existed:
        try:
            data = json.loads(rubric_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            raise ExtractError(f"既有 rubric.json 不可读/不可解析(需 UTF-8), 拒绝覆盖(先人工核查): {rubric_path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not all(isinstance(entry, dict) for entry in data["items"]):
            raise ExtractError(f"既有 rubric.json 结构异常(应为含 items 数组的对象), 拒绝覆盖: {rubric_path}")
        total_score = data.get("total_score")
        if total_score is not None and not (isinstance(total_score, (int, float)) and not isinstance(total_score, bool)):
            raise ExtractError(f"既有 rubric.json total_score 应为数值(number; int/float 非 bool)或 null: {rubric_path}")
        for index, item in enumerate(data["items"]):
            max_score = item.get("max_score")
            if not isinstance(max_score, (int, float)) or isinstance(max_score, bool):
                raise ExtractError(f"既有 rubric.json items[{index}]({item.get('rubric_id')}) max_score 应为数值(number; int/float 非 bool, Σ 校验基准), 拒绝覆盖(先人工核查): {rubric_path}")
        rubric_items = data["items"]

    return {
        "clauses": clauses,
        "structure": structure,
        "rubric_items": rubric_items,
        "total_score": total_score,
        "existed": {"clauses": clauses_path.is_file(), "structure": structure_path.is_file(), "rubric": rubric_existed},
    }


def atomic_write_json(path: str | Path, data) -> None:
    """原子写盘: 临时文件 + os.replace(D7 三防线之一, 防中断留半截文件)。

    IO 失败(OSError)包成 ExtractError——CLI 契约"文件错误→rc=1 干净消息", 不让裸
    OSError 逃出 main() 留 traceback; 原始异常保留为 __cause__ 供排障。
    """
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            raise ExtractError(f"状态文件写入失败(占用/权限/磁盘满): {path}: {exc}") from exc
    finally:
        # 成功路径 os.replace 后 tmp 已不存在; 异常路径清理残留, 不留半截文件。
        # 清理失败(Windows 文件被占用等)只吞掉——不得掩盖触发本 finally 的原始异常。
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# =============================================================================
# 校验管线(纯函数: sections + schemas + 候选记录 → report)
# =============================================================================


def _record_id(record: dict) -> tuple[str | None, str | None]:
    """候选记录的 (chunk_id, table_id)——恰好一个非空才算有锚。"""
    return record.get("chunk_id"), record.get("table_id")


def evaluate(sections: dict, schemas: dict, records: list[tuple[Path, dict]], declared_total: int | float | None, existing: dict | None = None) -> dict:
    """确定性校验管线。

    入参 records: [(候选文件路径, 候选记录 JSON), ...] 按命令行序;
    existing: merge 模式的既有状态(load_state 产物; validate 传 None=仅候选集)。

    出参 report:
      adjudicated   {chunk 数, table 数}——通过形态与 id 校验的裁决记录数(含后续因条目
                    问题被隔离的: 该 chunk 确实被裁决过, D5 只要求"有记录")
      unadjudicated sections 中无任何裁决记录的 chunk/table id 列表
      clean         {kind: [干净条目...]}(可安全合并)
      quarantined   [{"file"(完整路径), "kinds"}] 被隔离的裁决块([待确认], 不合并; 不同目录
                    同名候选文件按完整路径各占一条)
      anomalies     [{"kind", "message", ...}] 全部异常项
      rubric_sum    {"computed", "declared"}(存在评分项时; declared=校验基准——
                    --declared-total 优先, merge 缺省回用既有 total_score)
      fatal         Σ 不一致=True(merge 必须整体中止)
    """
    merge_mode = existing is not None
    if existing is None:
        existing = {"clauses": [], "structure": [], "rubric_items": [], "total_score": None}
    chunk_entries = [c for c in sections.get("chunks", [])]
    table_entries = [t for t in sections.get("tables", [])]
    chunk_ids = {c.get("chunk_id") for c in chunk_entries}
    table_ids = {t.get("table_id") for t in table_entries}
    # 锚点覆盖集: (source_file, section) —— chunk 与 table 并集
    covered = {(e.get("source_file"), (e.get("anchor") or {}).get("section")) for e in chunk_entries + table_entries}
    table_source = {t.get("table_id"): t.get("source_file") for t in table_entries}

    anomalies: list[dict] = []
    quarantined: dict[str, set[str]] = {}  # 候选文件完整路径 → 异常 kind 集合

    def quarantine(source: str, kind: str) -> None:
        """隔离一个裁决块([待确认]不合并): 按完整路径累计其异常 kind 集合。"""
        quarantined.setdefault(source, set()).add(kind)

    # --- 第 1 步: 记录形态 + 裁决 id 合法性 ------------------------------------
    admitted: list[dict] = []  # 通过形态与 id 校验的记录视图
    adjudicated_ids: set[str] = set()
    by_adjudication_id: dict[str, list[dict]] = {}
    for path, record in records:
        chunk_id, table_id = _record_id(record)
        problems: list[str] = []
        if not isinstance(record.get("kind"), str) or record.get("kind") not in KINDS:
            problems.append(f"kind 非法: {record.get('kind')!r}(合法: {list(KINDS)})")
        if not isinstance(record.get("items"), list):
            problems.append(f"items 应为数组, 实际 {type(record.get('items')).__name__}")
        has_chunk, has_table = isinstance(chunk_id, str) and bool(chunk_id), isinstance(table_id, str) and bool(table_id)
        if has_chunk == has_table:  # 同有/同无都算"二选一"失败
            problems.append("chunk_id/table_id 必须恰好提供一个")
        if problems:
            anomalies.append({"kind": "malformed_record", "file": path.name, "problems": problems, "message": "候选记录形态不符, [待确认]不合并"})
            quarantine(str(path), "malformed_record")
            continue

        rid = chunk_id if has_chunk else table_id
        known = rid in (chunk_ids if has_chunk else table_ids)
        if not known:
            anomalies.append({"kind": "unknown_adjudication_id", "file": path.name, "id": rid, "message": f"裁决 id {rid} 不在 sections.json, [待确认]不合并"})
            quarantine(str(path), "unknown_adjudication_id")
            continue

        view = {"path": path, "rid": rid, "id_type": "chunk" if has_chunk else "table", "kind": record["kind"], "items": record["items"]}
        admitted.append(view)
        by_adjudication_id.setdefault(rid, []).append(view)

    # 同一 id 重复裁决(检查点分叉): 双双隔离, 绝不静默取首个
    dup_views: list[dict] = []
    for rid, views in by_adjudication_id.items():
        if len(views) > 1:
            files = [v["path"].name for v in views]
            anomalies.append({"kind": "duplicate_adjudication", "id": rid, "files": files, "message": f"{rid} 有 {len(views)} 条裁决记录(检查点分叉), 全部[待确认], 请保留唯一最新版"})
            dup_views.extend(views)

    candidates: list[dict] = [v for v in admitted if v not in dup_views]
    for v in dup_views:
        quarantine(str(v["path"]), "duplicate_adjudication")
    # D5 覆盖度: 到达过"已知 id"阶段的记录即算有裁决(条目再差也在异常清单里交门1)
    adjudicated_ids = {v["rid"] for v in admitted}
    adjudicated = {"chunks": sum(1 for rid in adjudicated_ids if rid in chunk_ids), "tables": sum(1 for rid in adjudicated_ids if rid in table_ids)}
    unadjudicated = sorted((chunk_ids | table_ids) - adjudicated_ids)
    for rid in unadjudicated:
        anomalies.append({"kind": "unadjudicated_id", "id": rid, "id_type": "chunk" if rid in chunk_ids else "table", "message": f"{rid} 未裁决——[待确认], 待门1显式判空(零漏检是管线不变量)"})

    # --- 第 2 步: 逐条目 schema + 锚点校验 ------------------------------------
    survivors: list[dict] = []
    for view in candidates:
        path, kind, items = view["path"], view["kind"], view["items"]
        problems: list[dict] = []
        kept_items: list[dict] = []  # 派生字段剥离后的干净条目(新列表, 不回写候选原对象——纯函数契约)
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                problems.append({"kind": "schema_violation", "file": path.name, "item_id": f"items[{index}]", "errors": [f"items[{index}]: 应为对象, 实际 {_json_type_name(raw_item)}"]})
                continue
            item = strip_derived_fields(raw_item, kind)  # D7: 派生字段先剥离(现算不落盘, 也不参与校验噪声)
            item_id = str(item.get(KIND_ID_KEY[kind], f"items[{index}]"))
            errors = validate_against_schema(schemas[kind], item, item_id)
            if errors:
                problems.append({"kind": "schema_violation", "file": path.name, "item_id": item_id, "errors": errors})
                continue
            # 锚点校验(仅 clauses/rubric; structure 无锚点字段, 其锚=裁决记录的 chunk_id, 第 1 步已检)
            if kind == "clauses":
                source_file = item.get("source_file")
                section = (item.get("source_ref") or {}).get("section")
                if (source_file, section) not in covered:
                    problems.append({"kind": "anchor_not_in_sections", "file": path.name, "item_id": item_id, "source_file": source_file, "section": section, "message": f"锚点 ({source_file}, {section}) 不在 sections.json, [待确认]"})
            elif kind == "rubric":
                if view["id_type"] == "chunk":
                    # 评分细则从评分办法表格抽取, 锚点按表源文件解析; 挂 chunk 的 rubric 查不到
                    # 表源(source_file=None)恒报"锚点不在 sections"是误诊——真实原因是应挂表裁决。
                    message = f"评分细则裁决 {view['rid']} 挂了 chunk_id——评分细则应挂表裁决(table_id), [待确认]不合并"
                    problems.append({"kind": "rubric_chunk_anchor", "file": path.name, "item_id": item_id, "adjudication_id": view["rid"], "message": message})
                    continue
                section = (item.get("source_ref") or {}).get("section")
                source_file = table_source.get(view["rid"])
                if (source_file, section) not in covered:
                    problems.append({"kind": "anchor_not_in_sections", "file": path.name, "item_id": item_id, "source_file": source_file, "section": section, "message": f"锚点 ({source_file}, {section}) 不在 sections.json, [待确认]"})
            if kind == "clauses":
                # R1(终审): schema/prompt 允许候选省略管线归一字段; 干净条目在进入
                # clean(合并/落盘口径)前补缺省, 消费方(build_output/score_simulate)的
                # response_status 硬枚举校验才不会在省略路径上拒载。
                item = _normalize_clause_defaults(item)
            kept_items.append(item)
        view["items"] = kept_items
        if problems:
            anomalies.extend(problems)
            for problem in problems:  # 同块多种异常全部入 kinds(汇总不漏报)
                quarantine(str(path), problem["kind"])
        else:
            survivors.append(view)

    # --- 第 3 步: 跨块 id 去重 --------------------------------------------------
    id_owners: dict[tuple[str, str], list[dict]] = {}
    for view in survivors:
        for item in view["items"]:
            id_owners.setdefault((view["kind"], str(item.get(KIND_ID_KEY[view["kind"]]))), []).append(view)
    dup_survivors: list[dict] = []
    for (kind, item_id), views in sorted(id_owners.items()):
        if len(views) > 1:
            files = sorted({v["path"].name for v in views})
            scope = "跨块" if len(files) > 1 else "同一裁决块内"  # 同块撞 id 与跨块分叉归因不同
            anomalies.append({"kind": "duplicate_id", "id": item_id, "id_kind": kind, "files": files, "message": f"{KIND_ID_KEY[kind]} {item_id} {scope}重复({', '.join(files)}), 全部[待确认], 请核查是否同一要求被重复提取"})
            dup_survivors.extend(views)
    clean_views = [v for v in survivors if v not in dup_survivors]
    for v in dup_survivors:
        quarantine(str(v["path"]), "duplicate_id")

    clean = {kind: [item for v in clean_views if v["kind"] == kind for item in v["items"]] for kind in KINDS}

    # --- 第 4 步: D7 外键装载校验(存在 + 未 superseded) --------------------------
    clause_universe: dict[str, dict] = {}
    for clause in existing["clauses"] + clean["clauses"]:
        clause_universe[str(clause.get("clause_id"))] = clause
    superseded_ids = {cid for cid, clause in clause_universe.items() if clause.get("superseded_by") is not None}
    fk_views: list[dict] = []
    for view in clean_views:
        if view["kind"] not in ("structure", "rubric"):
            continue
        problems = []
        for item in view["items"]:
            for linked in item.get("linked_clause_ids") or []:
                if linked not in clause_universe:
                    reason = "missing"
                elif linked in superseded_ids:
                    reason = "superseded"
                else:
                    continue
                item_id = str(item.get(KIND_ID_KEY[view["kind"]]))
                message = f"悬挂外键 {linked}(reason={reason}), [待确认]不合并——引用已 supersede 条款同样非法(D7)"
                problems.append({"kind": "clause_fk_invalid", "file": view["path"].name, "item_id": item_id, "clause_id": linked, "reason": reason, "message": message})
        if problems:
            anomalies.extend(problems)
            fk_views.append(view)
    clean_views = [v for v in clean_views if v not in fk_views]
    for v in fk_views:
        quarantine(str(v["path"]), "clause_fk_invalid")
    clean = {kind: [item for v in clean_views if v["kind"] == kind for item in v["items"]] for kind in KINDS}

    # --- 第 5 步: rubric Σ 校验(以合并终态为口径) --------------------------------
    # 校验基准: --declared-total 优先; merge 未给该 flag 时回用既有 total_score——
    # 否则重合并可静默落盘"声称总分=100 而 items 实际 Σ=97"的带病 rubric.json。
    effective_declared = declared_total
    if merge_mode and effective_declared is None:
        effective_declared = existing["total_score"]
    merged_rubric = _upsert_by_id(existing["rubric_items"], clean["rubric"], "rubric_id")
    rubric_sum: dict | None = None
    fatal = False
    if merged_rubric or effective_declared is not None:
        computed = sum(item.get("max_score", 0) for item in merged_rubric)
        rubric_sum = {"computed": computed, "declared": effective_declared}
        # Σ 比较按数值相等(int/float 跨型相等, 如 3.0==3), 与 score_simulate._check_rubric_sum
        # 同款精确比较——前置拦截与纵深复检两层必须同口径, 不得单边引入容差。
        if effective_declared is not None and computed != effective_declared:
            # 无条件异常并中止(任务T4/设计文档阶段2: 不一致→异常并中止, 不设归因例外)——
            # 即使差额恰可归因于被隔离评分块的分值合计, 合并终态 Σ≠声称总分即带病状态,
            # 不得放行干净块落盘; 隔离块修复后重合并时 Σ 在此自动复检。
            anomalies.append({"kind": "rubric_sum_mismatch", "computed": computed, "declared": effective_declared, "message": f"Σmax_score={computed} 与评分办法声称总分 {effective_declared} 不一致——异常并中止(评分细则表抽取可能缺行/降级)"})
            fatal = True
        elif merge_mode and effective_declared is None and merged_rubric:
            anomalies.append({"kind": "rubric_declared_total_missing", "message": "未提供 --declared-total(且状态无既有总分), Σmax_score 无基准未检——[待确认], 确认门1 请补评分办法声称总分"})

    return {
        "adjudicated": adjudicated,
        "unadjudicated": unadjudicated,
        "clean": clean,
        "clean_views": clean_views,
        "quarantined": [{"file": source, "kinds": sorted(kinds)} for source, kinds in sorted(quarantined.items())],
        "anomalies": anomalies,
        "rubric_sum": rubric_sum,
        "fatal": fatal,
    }


def _upsert_by_id(existing_items: list[dict], new_items: list[dict], id_key: str) -> list[dict]:
    """按 id upsert: 同 id 候选替换旧条目, 未覆盖条目保留, 新条目按序追加。"""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for item in existing_items:
        key = str(item.get(id_key))
        if key not in by_id:
            order.append(key)
        by_id[key] = item
    for item in new_items:
        key = str(item.get(id_key))
        if key not in by_id:
            order.append(key)
        by_id[key] = item
    return [by_id[key] for key in order]


# =============================================================================
# CLI 子命令
# =============================================================================


def _load_inputs(args) -> tuple[dict, dict, list[tuple[Path, dict]]]:
    """公共装载: sections + schemas + 候选记录(任一失败 → ExtractError → 退出码 1)。"""
    sections = load_sections(args.sections)
    schemas = load_schemas(args.references)
    records = [(path, load_candidate(path)) for path in map(Path, args.candidates)]
    return sections, schemas, records


def _base_summary(command: str, args, report: dict) -> dict:
    summary = {
        "command": command,
        "candidates": [Path(p).name for p in args.candidates],
        "adjudicated": report["adjudicated"],
        "unadjudicated": report["unadjudicated"],
        "counts": {kind: len(report["clean"][kind]) for kind in KINDS},
        "quarantined": report["quarantined"],
        "anomalies": report["anomalies"],
    }
    if report["rubric_sum"] is not None:
        summary["rubric_sum"] = report["rubric_sum"]
    return summary


def _verify_state_guard(state_dir: str | Path, context: str) -> None:
    """读盘前校验权威状态签名(回放实证 bfa917ce: write_file 直写/rm 后下游只报远处症状)。"""
    problems = state_guard.verify_state_files(state_dir)
    if problems:
        raise ExtractError(f"{context}: 权威状态文件签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(problems))


def cmd_validate(args) -> int:
    """validate: 只校验不落盘; 异常项交确认门1。"""
    _verify_state_guard(Path(args.sections).parent, "validate 前置校验(sections 所在目录)")
    sections, schemas, records = _load_inputs(args)
    report = evaluate(sections, schemas, records, args.declared_total)
    summary = _base_summary("validate", args, report)
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_ANOMALY if report["anomalies"] else EXIT_OK


def cmd_merge(args) -> int:
    """merge: 校验 + 原子合并进三状态文件; Σ 不一致整体中止(一个文件都不写)。

    Σ 校验基准: --declared-total 优先, 缺省回用既有 rubric.json total_score(evaluate 内统一)。
    """
    _verify_state_guard(Path(args.sections).parent, "merge 前置校验(sections 所在目录)")
    _verify_state_guard(args.state_dir, "merge 前置校验(state-dir)")
    sections, schemas, records = _load_inputs(args)
    state = load_state(args.state_dir)
    report = evaluate(sections, schemas, records, args.declared_total, existing=state)
    summary = _base_summary("merge", args, report)
    summary["aborted"] = report["fatal"]

    if report["fatal"]:
        summary["written"] = []
        summary["message"] = "Σmax_score 与评分办法声称总分不一致——merge 整体中止, 未写任何状态文件"
        print(json.dumps(summary, ensure_ascii=False))
        return EXIT_ANOMALY

    state_dir = Path(args.state_dir)
    written: list[str] = []
    merged_clauses = _upsert_by_id(state["clauses"], report["clean"]["clauses"], "clause_id")
    if merged_clauses or state["existed"]["clauses"]:
        atomic_write_json(state_dir / STATE_FILES["clauses"], merged_clauses)
        written.append(STATE_FILES["clauses"])
    merged_structure = _upsert_by_id(state["structure"], report["clean"]["structure"], "node_id")
    if merged_structure or state["existed"]["structure"]:
        atomic_write_json(state_dir / STATE_FILES["structure"], merged_structure)
        written.append(STATE_FILES["structure"])
    merged_rubric_items = _upsert_by_id(state["rubric_items"], report["clean"]["rubric"], "rubric_id")
    if merged_rubric_items or state["existed"]["rubric"]:
        total_score = args.declared_total if args.declared_total is not None else state["total_score"]
        atomic_write_json(state_dir / STATE_FILES["rubric"], {"total_score": total_score, "items": merged_rubric_items})
        written.append(STATE_FILES["rubric"])

    summary["written"] = sorted(written)
    if written:
        # 权威状态文件写盘后登记防篡改签名(仅本次落盘文件; 未动文件旧签名仍匹配内容)
        state_guard.sign_state_files(state_dir, written)
    summary["merged"] = {"clauses": len(merged_clauses), "structure": len(merged_structure), "rubric": len(merged_rubric_items)}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_ANOMALY if report["anomalies"] else EXIT_OK


def _declared_total_type(text: str) -> int | float:
    """--declared-total 自定义解析(R3, 终审 Chunk 1): 契约=rubric.schema.json type=number,
    整数形态保 int、小数形态 float(合法小数总分如 5.5 不得在 argparse 层被 type=int 拒绝);
    非数值/inf/nan 交 argparse 用法错误(main 统一改道退出码 1, 2 保留给 ingest OCR 分流)。"""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"应为数值(整数或小数), 实际 {text!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"应为有限数值(不接受 inf/nan), 实际 {text!r}")
    return int(value) if value.is_integer() else value


def _add_common_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--candidates", nargs="+", required=True, help="候选裁决 JSON 文件(一次裁决=一个文件, 可多个)")
    sub.add_argument("--sections", required=True, help="sections.json 路径(ingest.py 阶段1 产物, 锚点/裁决 id 的基准)")
    sub.add_argument("--declared-total", type=_declared_total_type, default=None, help="评分办法声称总分(数值, 支持小数如 5.5; Σmax_score 校验基准; 不一致→异常并中止; merge 缺省时回用既有 rubric.json total_score)")
    sub.add_argument("--references", default=None, help="references/ 契约目录(默认: 脚本所在技能的 ../references)")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="extract.py",
        description="投标方案编写·阶段2 候选校验/合并: 对 Agent 分块提取循环产出的候选 JSON 做确定性校验(锚点/枚举/去重/Σ/全量裁决/外键), merge 原子合并进三状态文件(无 LLM)",
        epilog="示例: python extract.py validate --candidates candidates/CH-001.json candidates/TB-001.json --sections state/sections.json --declared-total 100 ; "
        "python extract.py merge --candidates candidates/CH-001.json --sections state/sections.json --state-dir state --declared-total 100",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="只校验候选(不落盘), 异常项交确认门1")
    _add_common_arguments(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)
    merge_parser = subparsers.add_parser("merge", help="校验后原子合并进 <state-dir> 三状态文件(Σ 不一致整体中止)")
    _add_common_arguments(merge_parser)
    merge_parser.add_argument("--state-dir", required=True, help="状态目录(读/写 clauses.json / structure.json / rubric.json, 按 id upsert 幂等)")
    merge_parser.set_defaults(func=cmd_merge)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 ingest 的 OCR 分流退出码撞号——
        # 编排方按 rc==2 分流会把 CLI 误用误路由进 OCR 路径, 故统一改道 EXIT_ERROR;
        # --help/--version 的正常退出(code 0)原样放行。
        if not exc.code:
            return EXIT_OK
        print(f"[extract] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        return args.func(args)
    except ExtractError as exc:
        print(f"[extract] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
