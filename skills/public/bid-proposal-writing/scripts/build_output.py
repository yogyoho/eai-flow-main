#!/usr/bin/env python3
"""build_output.py — 投标方案编写技能·阶段4 双卷骨架渲染(无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md
「阶段4 build」+ D2(重灌锚点载体在渲染时埋定)/D7(派生字段现算不落盘/原子写盘)。
本脚本只做确定性渲染; Word 转换由 Agent 另调 markdown-to-docx 技能(强制条款
**加粗**——convert.py 链路仅支持粗体/斜体, 不支持高亮/隐藏标记/HTML注释)。

用法:
    python build_output.py --state-dir <dir> --out <dir>

输出六件套(--out 目录):
    商务卷.md / 技术卷.md / 偏离表.md / 覆盖率报表.md / 人核清单.md / 实体lint报告.md

职责(设计文档锁定, 不缺不漏不加):
    ① 商务卷 = structure.json 镜像渲染: path 标题链 → # 层级章节树, 层级完整,
       只镜像不自创; 每槽位标注 类型/格式要求/待填提示/填写状态(现算);
       image 槽在卷末汇总扫描件清单(图片不经 md 链路插入)。
    ② 技术卷 = 格式章节规定结构部分按镜像渲染 + 逐条款条目: 条目标题嵌 clause_id
       (如 "2.1 响应[ZB-C-001]"——clause_id 入标题是阶段5 重灌唯一可存活的锚点
       载体, 交付物中保留不删, D2); mandatory 条款条目标题整体**加粗**;
       条目体 = 要求原文锚点→响应要点→证据引用→满足状态→suggestion;
       活条款(technical 类)无挂接槽时入卷末"未挂接条款"节, 零遗漏。
    ③ 偏离表 = 仅 class=mandatory 或 response_status=deviation 的活条款。
    ④ 覆盖率报表 = 清单总数/已响应/待确认/未分配(已响应=compliant+deviation,
       待确认=draft+pending_confirm, 未分配=unassigned; superseded/voided 是
       历史条款, 除外列示不计入总数)。
    ⑤ 实体 lint = 白名单 diff 全部 evidence_ref 与引用片段(source_ref.quote):
       确定性模式提取候选(company 工商后缀 / spec_version 型号+V版本), 白名单外
       → 报告[待核对] + 摘要异常; person/project 无确定性提取模式, 只做白名单
       命中统计(出现即核, 无法被动发现)——报告显著标注"LLM辅助抽取白名单，
       非确定性"(白名单本身由 LLM 抽取+人工确认, lint 是确定性 diff 但覆盖
       受白名单与模式能力限制)。
    ⑥ 人核清单 = format_check 槽(签字/盖章/份数/页码)全部入清单不进确定性判定
       + [待人工复刻]表格槽(管道表格无法表达合并单元格/列宽——如实声明渲染
       边界, 所有表格槽均标[待人工复刻]并列头骨架照渲染)。

脚本纪律: 纯 Python 3.12; stdlib only; 不调用 LLM; 不 import app.*/deerflow.*;
    状态目录只读(D7: fill_status 等派生字段渲染时现算不落盘); 输出文件临时
    文件+os.replace 原子写盘; 渲染不含时间戳 → 重跑字节级幂等。

退出码:
    0 = 干净完成(--help 亦为 0)
    1 = 用法/文件错误(状态文件缺失/不可解析/结构损坏; argparse 用法错误统一
        改道 1——2 留给 ingest 的 OCR 分流语义, 防编排方误路由)
    3 = 完成但有异常项(lint 待核对实体/白名单缺失/悬挂外键, 摘要 anomalies 列出)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# --- 退出码约定 -----------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

# --- 契约常量(references/*.schema.json 同款约束; 沙箱无 jsonschema, 内联同子集) ---
CLAUSE_CLASSES = ("mandatory", "scoring", "normal")
CLAUSE_CATEGORIES = ("technical", "commercial", "qualification", "format", "service")
RESPONSE_STATUSES = ("unassigned", "draft", "pending_confirm", "compliant", "deviation")
SLOT_TYPES = ("text", "table", "image", "format_check", "group")
VOLUMES = ("commercial", "technical")

OUTPUT_FILES = ("商务卷.md", "技术卷.md", "偏离表.md", "覆盖率报表.md", "人核清单.md", "实体lint报告.md")

SLOT_TYPE_LABELS = {"text": "文字槽", "table": "表格槽", "image": "图片槽", "format_check": "格式核验槽", "group": "结构组"}
CLASS_LABELS = {"mandatory": "强制条款", "scoring": "评分条款", "normal": "普通条款"}
STATUS_LABELS = {"unassigned": "未分配", "draft": "草稿", "pending_confirm": "待确认", "compliant": "已响应", "deviation": "偏离"}
# 口径桶: 已响应=compliant+deviation 待确认=draft+pending_confirm 未分配=unassigned
RESPONDED_STATUSES = ("compliant", "deviation")
PENDING_STATUSES = ("draft", "pending_confirm")

# 实体 lint 可确定性提取的候选模式(白名单外 → [待核对]);
# person/project 无确定性模式, 由白名单命中统计覆盖——报告如实声明此边界。
LINT_PATTERNS = (
    ("company", re.compile(r"\w{2,30}(?:股份有限公司|有限责任公司|有限公司|集团公司)")),
    ("spec_version", re.compile(r"[A-Z][A-Z0-9]*[0-9][A-Z0-9-]*\s*V\d+(?:\.\d+)+")),
)


class BuildOutputError(Exception):
    """用法/文件错误 → 退出码 1。"""


# =============================================================================
# 基础件: JSON 装载 / 原子写盘 / 派生小函数
# =============================================================================


def _load_json_file(path: Path, what: str):
    """装载 UTF-8 JSON 文件; 缺失/不可解析 → BuildOutputError(退出码 1), 绝不静默。"""
    if not path.is_file():
        raise BuildOutputError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise BuildOutputError(f"{what} 不可读/不可解析(需 UTF-8; 疑似截断或编码错): {path}: {exc}") from exc


def atomic_write_text(path: str | Path, text: str) -> None:
    """原子写盘: 临时文件 + os.replace(D7, 防中断留半截文件)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
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


def _is_active(clause: dict) -> bool:
    """活条款 = 未 superseded 且未 voided(条目/偏离表/覆盖率都以活条款为口径)。"""
    return clause.get("superseded_by") is None and not clause.get("voided")


def _cell(value) -> str:
    """markdown 表格单元格转义: 竖线/换行不得破坏表格。"""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _anchor_line(clause: dict) -> str:
    """要求原文锚点: 「quote」(source_file §section 段para 页page)。"""
    ref = clause.get("source_ref") or {}
    quote = ref.get("quote")
    parts = [str(clause.get("source_file") or "")]
    if ref.get("section"):
        parts.append(f"§{ref['section']}")
    if ref.get("para") is not None:
        parts.append(f"段{ref['para']}")
    if ref.get("page") is not None:
        parts.append(f"页{ref['page']}")
    loc = " ".join(p for p in parts if p)
    quoted = f"「{quote}」" if isinstance(quote, str) and quote.strip() else "(缺原文锚点)"
    return f"{quoted}({loc})" if loc else quoted


def derive_fill_status(node: dict) -> tuple[str, str]:
    """fill_status 现算不落盘(D7): 骨架渲染时 text=unfilled, 其余均含人核成分。"""
    slot_type = node["slot_type"]
    if slot_type == "image":
        return "needs_human_verify", "图片槽——扫描件由用户提供, 不经 md 链路插入"
    if slot_type == "format_check":
        return "needs_human_verify", "format_check——人核项, 不做确定性判定"
    if slot_type == "table":
        return "needs_human_verify", "合并单元格/列宽管道表格无法表达, 标[待人工复刻]"
    return "unfilled", "骨架待填"


# =============================================================================
# 状态装载(状态目录只读, 本脚本不写任何状态文件)
# =============================================================================


def load_clauses(state_dir: Path) -> list[dict]:
    """装载并轻校验 clauses.json(枚举错/缺 clause_id → 拒绝渲染, 退出码 1)。"""
    path = state_dir / "clauses.json"
    data = _load_json_file(path, "clauses.json")
    if not isinstance(data, list) or not all(isinstance(c, dict) for c in data):
        raise BuildOutputError(f"clauses.json 结构异常(应为对象数组), 拒绝渲染(先人工核查): {path}")
    for index, clause in enumerate(data):
        if not isinstance(clause.get("clause_id"), str) or not clause["clause_id"]:
            raise BuildOutputError(f"clauses.json items[{index}] 缺非空字符串 clause_id, 拒绝渲染: {path}")
        if clause.get("class") not in CLAUSE_CLASSES:
            raise BuildOutputError(f"clauses.json items[{index}] class 枚举非法 {clause.get('class')!r}(合法: {list(CLAUSE_CLASSES)}): {path}")
        if clause.get("category") not in CLAUSE_CATEGORIES:
            raise BuildOutputError(f"clauses.json items[{index}] category 枚举非法 {clause.get('category')!r}(合法: {list(CLAUSE_CATEGORIES)}): {path}")
        if clause.get("response_status") not in RESPONSE_STATUSES:
            raise BuildOutputError(f"clauses.json items[{index}] response_status 枚举非法 {clause.get('response_status')!r}(合法: {list(RESPONSE_STATUSES)}): {path}")
        if clause.get("response_skeleton") is not None and not isinstance(clause.get("response_skeleton"), dict):
            raise BuildOutputError(f"clauses.json items[{index}] response_skeleton 应为对象或 null, 拒绝渲染: {path}")
    return data


def load_structure(state_dir: Path) -> list[dict]:
    """装载并轻校验 structure.json(卷/槽位枚举、path 非空 → 拒绝渲染)。"""
    path = state_dir / "structure.json"
    data = _load_json_file(path, "structure.json")
    if not isinstance(data, list) or not all(isinstance(n, dict) for n in data):
        raise BuildOutputError(f"structure.json 结构异常(应为对象数组), 拒绝渲染(先人工核查): {path}")
    for index, node in enumerate(data):
        if not isinstance(node.get("node_id"), str) or not node["node_id"]:
            raise BuildOutputError(f"structure.json items[{index}] 缺非空字符串 node_id, 拒绝渲染: {path}")
        if node.get("volume") not in VOLUMES:
            raise BuildOutputError(f"structure.json items[{index}] volume 枚举非法 {node.get('volume')!r}(合法: {list(VOLUMES)}): {path}")
        if node.get("slot_type") not in SLOT_TYPES:
            raise BuildOutputError(f"structure.json items[{index}] slot_type 枚举非法 {node.get('slot_type')!r}(合法: {list(SLOT_TYPES)}): {path}")
        if not isinstance(node.get("path"), str) or not node["path"].strip():
            raise BuildOutputError(f"structure.json items[{index}] path 应为非空字符串: {path}")
        if not isinstance(node.get("linked_clause_ids") or [], list):
            raise BuildOutputError(f"structure.json items[{index}] linked_clause_ids 应为数组: {path}")
    return data


def load_whitelist(state_dir: Path) -> dict | None:
    """装载实体白名单(确认门1 锁定); 缺失 → None(浮出 whitelist_missing 异常, 按空集 diff)。"""
    path = state_dir / "entities_whitelist.json"
    if not path.is_file():
        return None
    data = _load_json_file(path, "entities_whitelist.json")
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise BuildOutputError(f"entities_whitelist.json 结构异常(应为含 entities 数组的对象), 拒绝渲染(先人工核查): {path}")
    for index, entity in enumerate(data["entities"]):
        if not isinstance(entity, dict) or not isinstance(entity.get("type"), str) or not entity["type"].strip() or not isinstance(entity.get("value"), str) or not entity["value"].strip():
            raise BuildOutputError(f"entities_whitelist.json entities[{index}] 应为含非空 type/value 的对象, 拒绝渲染: {path}")
    return data


# =============================================================================
# ② 条目渲染(技术卷逐条款条目, D2 锚点载体)
# =============================================================================


def render_clause_entry(clause: dict, num: str, level: int = 3) -> list[str]:
    """条目 = 标题(N.M 响应[clause_id], mandatory 整体加粗) + 五字段条目体。"""
    title = f"{num} 响应[{clause['clause_id']}]"
    if clause["class"] == "mandatory":
        title = f"**{title}**"  # convert.py 不支持高亮, 加粗是唯一强调载体
    skeleton = clause.get("response_skeleton") or {}
    lines = ["#" * level + " " + title, ""]
    lines.append(f"- **要求原文锚点**: {_anchor_line(clause)}")
    points = skeleton.get("points") or []
    if points:
        lines.append("- **响应要点**:")
        lines.extend(f"  - {_cell(p)}" for p in points)
    else:
        lines.append("- **响应要点**: (待填)")
    evidence = skeleton.get("evidence_ref")
    lines.append(f"- **证据引用**: {evidence if isinstance(evidence, str) and evidence.strip() else '(待填)'}")
    status = clause["response_status"]
    lines.append(f"- **满足状态**: {status}({STATUS_LABELS.get(status, status)})")
    suggestion = skeleton.get("suggestion")
    lines.append(f"- **suggestion**: {suggestion if isinstance(suggestion, str) and suggestion.strip() else '(待填)'}")
    lines.append("")
    return lines


# =============================================================================
# ①② 双卷渲染(structure.json 镜像 + 技术卷条目挂接)
# =============================================================================


def render_volume_md(volume: str, structure: list[dict], clauses: list[dict], anomalies: list[dict]) -> str:
    """渲染单卷: 镜像章节树(path 标题链→# 层级) + 槽位标注 + 技术卷条目挂接。"""
    clauses_by_id = {c["clause_id"]: c for c in clauses}
    nodes = [n for n in structure if n["volume"] == volume]
    active_tech = [c for c in clauses if _is_active(c) and c.get("category") == "technical"]

    # 活技术条款 → 首个挂接它的非 group 技术卷节点(多处挂接以首处为准渲染, 零遗漏优先)
    linked_map: dict[str, str] = {}
    for node in nodes:
        if node["slot_type"] == "group":
            continue
        for cid in node.get("linked_clause_ids") or []:
            linked_map.setdefault(cid, node["node_id"])

    def _ensure_blank() -> None:
        """块与块之间保证空行分隔(md 解析器/convert.py 对紧跟列表的标题敏感)。"""
        if lines and lines[-1] != "":
            lines.append("")

    lines: list[str] = []
    non_group_count = 0
    for node in nodes:
        segments = [s.strip() for s in node["path"].split("/")]
        title = segments[-1]
        _ensure_blank()
        lines.append("#" * min(len(segments), 6) + " " + title)
        lines.append("")
        required_format = node.get("required_format") or {}
        desc = required_format.get("desc")
        if node["slot_type"] == "group":
            if desc:
                lines.extend([f"> {desc}", ""])
            continue
        non_group_count += 1
        slot_type = node["slot_type"]
        lines.append(f"- **槽位类型**: {SLOT_TYPE_LABELS[slot_type]}")
        if desc:
            lines.append(f"- **格式要求**: {desc}")
        fill, reason = derive_fill_status(node)
        lines.append(f"- **填写状态(现算)**: {fill}({reason})")
        if slot_type == "text":
            lines.append("- **待填提示**: 按格式要求填写正文(格式即合规, 不得自创结构)")
        elif slot_type == "image":
            lines.append("- **待填提示**: 需提供扫描件(见卷末扫描件清单; 图片不经 md 链路插入, 终稿人工替换占位)")

        # 关联条款解析(缺失→异常不静默; superseded/voided→标注历史状态)
        linked_ids = node.get("linked_clause_ids") or []
        if linked_ids:
            parts = []
            for cid in linked_ids:
                clause = clauses_by_id.get(cid)
                if clause is None:
                    message = f"structure {node['node_id']} 悬挂外键 {cid}(reason=missing)——异常不静默, 待人工改链(D7)"
                    anomalies.append({"kind": "clause_fk_invalid", "source": "structure", "item_id": node["node_id"], "clause_id": cid, "reason": "missing", "message": message})
                    parts.append(f"{cid}(不存在——异常, 不静默)")
                elif clause.get("superseded_by") is not None:
                    parts.append(f"{cid}(已被 {clause['superseded_by']} 取代)")
                elif clause.get("voided"):
                    parts.append(f"{cid}(已作废)")
                else:
                    parts.append(f"{cid}({clause['response_status']})")
            lines.append(f"- **关联条款**: {'; '.join(parts)}")

        # 表格槽: 列头骨架照渲染 + [待人工复刻] 渲染边界如实声明
        table_spec = required_format.get("table_spec")
        if slot_type == "table":
            if isinstance(table_spec, dict) and table_spec.get("columns"):
                columns = [str(c) for c in table_spec["columns"]]
                lines.extend(["", "| " + " | ".join(_cell(c) for c in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"])
                for _ in range(int(table_spec.get("rows") or 1)):
                    lines.append("| " + " | ".join("(待填)" for _ in columns) + " |")
                lines.append("")
            lines.append("> [待人工复刻] 合并单元格/列宽等原表格式 markdown 管道无法表达, 须人工按招标文件原样复刻——已入人核清单。")
            lines.append("")
        if slot_type == "format_check":
            lines.append("> 人核项(签字/盖章/份数/页码), 不做确定性判定——已入人核清单, 终稿人工核签。")
            lines.append("")

        # 技术卷: 活技术条款挂接本槽位 → 渲染条目(标题 N.M 响应[clause_id], D2)
        if volume == "technical":
            entries = [c for c in active_tech if linked_map.get(c["clause_id"]) == node["node_id"]]
            if entries:
                matched = re.match(r"\s*(\d+)", title)
                parent_num = matched.group(1) if matched else str(non_group_count)
                for index, clause in enumerate(entries, 1):
                    _ensure_blank()
                    lines.extend(render_clause_entry(clause, f"{parent_num}.{index}"))

    # 技术卷兜底: 未挂接任何槽位的活技术条款 → 卷末专节渲染(逐条款条目零遗漏)
    if volume == "technical":
        orphans = [c for c in active_tech if c["clause_id"] not in linked_map]
        if orphans:
            nums = [int(m.group(1)) for n in nodes if n["slot_type"] != "group" and (m := re.match(r"\s*(\d+)", n["path"].split("/")[-1].strip()))]
            parent_num = str(max(nums) + 1) if nums else "1"
            _ensure_blank()
            lines.append(f"## {parent_num} 未挂接格式槽的技术条款(清单驱动)")
            lines.append("")
            for index, clause in enumerate(orphans, 1):
                lines.extend(render_clause_entry(clause, f"{parent_num}.{index}"))

    # 扫描件清单(image 槽汇总; 图片不经 md 链路插入)
    image_nodes = [n for n in nodes if n["slot_type"] == "image"]
    if image_nodes:
        _ensure_blank()
        lines.extend(["## 扫描件清单(图片槽汇总)", "", "图片不经 md 链路插入: 终稿由 python-docx 后处理插占位图后人工替换。", "", "| 槽位 | 位置 | 要求 |", "| --- | --- | --- |"])
        lines.extend(f"| {n['node_id']} | {_cell(n['path'])} | {_cell((n.get('required_format') or {}).get('desc') or '')} |" for n in image_nodes)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# =============================================================================
# ③ 偏离表 / ④ 覆盖率报表 / ⑥ 人核清单
# =============================================================================


def deviation_rows(clauses: list[dict]) -> list[dict]:
    """偏离表口径: 活条款 且 (强制条款 或 响应状态=deviation)。"""
    return [c for c in clauses if _is_active(c) and (c["class"] == "mandatory" or c["response_status"] == "deviation")]


def render_deviation_md(clauses: list[dict]) -> str:
    rows = deviation_rows(clauses)
    lines = [
        "# 偏离表",
        "",
        "> 口径: 仅强制条款(class=mandatory)与偏离项(response_status=deviation)入表——",
        "> 强制条款即使已响应也须声明零偏离; 其余条款不入表。superseded/voided 历史条款除外。",
        "",
        "| 条款ID | 类别 | 响应状态 | 招标要求 | 原文锚点 | 偏离说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for clause in rows:
        requirement = _cell(clause.get("requirement") or "")
        quote = _cell((clause.get("source_ref") or {}).get("quote") or "")
        lines.append(f"| {clause['clause_id']} | {CLASS_LABELS.get(clause['class'], clause['class'])} | {clause['response_status']}({STATUS_LABELS.get(clause['response_status'], '')}) | {requirement} | {quote} | (待填) |")
    if not rows:
        lines.append("| (无强制条款且无偏离项) | | | | | |")
    lines.append("")
    return "\n".join(lines)


def compute_coverage(clauses: list[dict]) -> dict:
    """覆盖率口径: 已响应=compliant+deviation; 待确认=draft+pending_confirm; 未分配=unassigned。"""
    active = [c for c in clauses if _is_active(c)]

    def count(statuses: tuple[str, ...]) -> int:
        return sum(1 for c in active if c["response_status"] in statuses)

    return {
        "total": len(active),
        "responded": count(RESPONDED_STATUSES),
        "pending": count(PENDING_STATUSES),
        "unassigned": count(("unassigned",)),
        "superseded": sum(1 for c in clauses if c.get("superseded_by") is not None),
        "voided": sum(1 for c in clauses if c.get("voided")),
    }


def _bucket(status: str) -> str:
    if status in RESPONDED_STATUSES:
        return "已响应"
    if status in PENDING_STATUSES:
        return "待确认"
    return "未分配"


def render_coverage_md(clauses: list[dict], coverage: dict) -> str:
    lines = [
        "# 覆盖率报表",
        "",
        "> 口径: 已响应=compliant+deviation; 待确认=draft+pending_confirm; 未分配=unassigned;",
        "> superseded/voided 为历史条款, 除外列示不计入清单总数。",
        "",
        "| 指标 | 数量 |",
        "| --- | --- |",
        f"| 清单总数(活条款) | {coverage['total']} |",
        f"| 已响应(compliant+deviation) | {coverage['responded']} |",
        f"| 待确认(draft+pending_confirm) | {coverage['pending']} |",
        f"| 未分配(unassigned) | {coverage['unassigned']} |",
        f"| 除外: superseded | {coverage['superseded']} |",
        f"| 除外: voided | {coverage['voided']} |",
        "",
        "## 逐条款状态附录",
        "",
        "| 条款ID | 类别 | 分类 | 响应状态 | 口径桶 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for clause in clauses:
        if not _is_active(clause):
            continue
        status = clause["response_status"]
        lines.append(f"| {clause['clause_id']} | {CLASS_LABELS.get(clause['class'], clause['class'])} | {clause.get('category', '')} | {status}({STATUS_LABELS.get(status, '')}) | {_bucket(status)} |")
    if coverage["total"] == 0:
        lines.append("| (无活条款) | | | | |")
    lines.append("")
    return "\n".join(lines)


def render_checklist_md(structure: list[dict]) -> tuple[str, dict]:
    """人核清单: format_check 项(签字/盖章/份数/页码) + [待人工复刻]表格槽, 全部人核。"""
    format_checks = [n for n in structure if n["slot_type"] == "format_check"]
    replica_tables = [n for n in structure if n["slot_type"] == "table"]
    lines = [
        "# 人核清单",
        "",
        "> 以下项**不进确定性判定**, 必须人工逐项核签(确认门2 终稿复核, skill 不做最终承诺):",
        "> format_check 项(签字/盖章/份数/页码)全部人核; [待人工复刻]表格槽=管道表格无法表达合并单元格/列宽。",
        "",
        "## 一、format_check 人核项(签字/盖章/份数/页码)",
        "",
        "| 节点 | 位置 | 要求 |",
        "| --- | --- | --- |",
    ]
    for node in format_checks:
        lines.append(f"| {node['node_id']} | {_cell(node['path'])} | {_cell((node.get('required_format') or {}).get('desc') or '')} |")
    if not format_checks:
        lines.append("| (无) | | |")
    lines.extend(["", "## 二、[待人工复刻] 表格槽(合并单元格/列宽须按招标文件原样复刻)", "", "| 节点 | 位置 | 列头 | 行数 | 格式要求 |", "| --- | --- | --- | --- | --- |"])
    for node in replica_tables:
        spec = (node.get("required_format") or {}).get("table_spec") or {}
        columns = "/".join(str(c) for c in (spec.get("columns") or []))
        lines.append(f"| {node['node_id']} | {_cell(node['path'])} | {_cell(columns)} | {spec.get('rows', '')} | {_cell((node.get('required_format') or {}).get('desc') or '')} |")
    if not replica_tables:
        lines.append("| (无) | | | | |")
    lines.append("")
    return "\n".join(lines), {"format_check": len(format_checks), "replica_tables": len(replica_tables)}


# =============================================================================
# ⑤ 实体一致性 lint(确定性 diff; 白名单=LLM 辅助抽取+人工确认, 非确定性)
# =============================================================================


def run_entity_lint(clauses: list[dict], whitelist: dict | None) -> tuple[list[dict], dict]:
    """白名单 diff 全部 evidence_ref 与引用片段。

    hits = 白名单实体值出现次数(命中统计);
    flagged = 模式提取候选中不在白名单的(疑似上一项目残留)→[待核对]+异常。
    """
    values: set[str] = {e["value"] for e in (whitelist or {}).get("entities", [])}
    hits: dict[str, int] = {}
    flagged: list[dict] = []
    for clause in clauses:
        skeleton = clause.get("response_skeleton") or {}
        texts = (("evidence_ref", skeleton.get("evidence_ref")), ("引用片段", (clause.get("source_ref") or {}).get("quote")))
        for field, text in texts:
            if not isinstance(text, str) or not text.strip():
                continue
            for value in values:
                if value in text:
                    hits[value] = hits.get(value, 0) + 1
            seen: set[str] = set()
            for etype, pattern in LINT_PATTERNS:
                for candidate in pattern.findall(text):
                    if candidate in seen or candidate in values:
                        continue
                    seen.add(candidate)
                    message = f"{clause['clause_id']} {field} 含白名单外实体 {candidate!r}({etype})——疑似上一项目残留, [待核对]"
                    flagged.append({"kind": "entity_unverified", "clause_id": clause["clause_id"], "field": field, "type": etype, "value": candidate, "context": text, "message": message})
    return flagged, hits


def render_lint_md(whitelist: dict | None, flagged: list[dict], hits: dict) -> str:
    lines = [
        "# 实体一致性 lint 报告",
        "",
        "> **LLM辅助抽取白名单，非确定性**: 实体白名单由 LLM 抽取+人工确认(确认门1 锁定)。",
        "> 本 lint 本身是确定性 diff(模式提取候选 ∩ 白名单比对); 可确定性提取的类型仅",
        "> company(工商后缀)/spec_version(型号+V版本)——person/project 等无确定性模式,",
        "> 只做白名单命中统计, 无法被动发现白名单外残留, 覆盖范围受此限制。",
    ]
    if whitelist is None:
        lines.append(">")
        lines.append("> **白名单缺失**: entities_whitelist.json 不存在, 按空集 diff(全部候选进[待核对])——确认门1 未锁定或文件被移动。")
    else:
        lines.append(">")
        lines.append(f"> 白名单锁定: {whitelist.get('locked_at', '(未知)')}({whitelist.get('source', '')})/ 共 {len(whitelist.get('entities', []))} 项实体。")
    lines.extend(
        [
            "",
            "## 白名单命中统计(evidence_ref 与引用片段)",
            "",
        ]
    )
    if hits:
        type_by_value = {e["value"]: e["type"] for e in (whitelist or {}).get("entities", [])}
        lines.extend(["| 实体值 | 类型 | 出现次数 |", "| --- | --- | --- |"])
        lines.extend(f"| {_cell(value)} | {type_by_value.get(value, '')} | {count} |" for value, count in sorted(hits.items()))
    else:
        lines.append("(无命中——白名单实体未出现在任何 evidence_ref/引用片段)")
    lines.extend(["", "## [待核对] 白名单外实体(疑似上一项目残留)", ""])
    if flagged:
        lines.extend(["| 条款 | 字段 | 提取类型 | 提取值 | 上下文 |", "| --- | --- | --- | --- | --- |"])
        lines.extend(f"| {f['clause_id']} | {f['field']} | {f['type']} | {_cell(f['value'])} | {_cell(f['context'])} |" for f in flagged)
    else:
        lines.append("(无——未发现白名单外实体)")
    lines.append("")
    return "\n".join(lines)


# =============================================================================
# 渲染管线 + CLI
# =============================================================================


def run_build(state_dir: Path, out_dir: Path) -> int:
    """读状态(只读) → 渲染六件套 → 原子写盘 → stdout 单行 JSON 摘要; 返回退出码。"""
    clauses = load_clauses(state_dir)
    structure = load_structure(state_dir)
    whitelist = load_whitelist(state_dir)

    anomalies: list[dict] = []
    if whitelist is None:
        anomalies.append({"kind": "whitelist_missing", "message": "entities_whitelist.json 缺失, lint 按空集 diff(全部候选进[待核对])——确认门1 未锁定白名单或文件被移动"})

    commercial_md = render_volume_md("commercial", structure, clauses, anomalies)
    technical_md = render_volume_md("technical", structure, clauses, anomalies)
    deviation_md = render_deviation_md(clauses)
    coverage = compute_coverage(clauses)
    coverage_md = render_coverage_md(clauses, coverage)
    checklist_md, checklist_counts = render_checklist_md(structure)
    flagged, hits = run_entity_lint(clauses, whitelist)
    anomalies.extend(flagged)
    lint_md = render_lint_md(whitelist, flagged, hits)

    outputs = {
        "商务卷.md": commercial_md,
        "技术卷.md": technical_md,
        "偏离表.md": deviation_md,
        "覆盖率报表.md": coverage_md,
        "人核清单.md": checklist_md,
        "实体lint报告.md": lint_md,
    }
    for name in OUTPUT_FILES:
        atomic_write_text(out_dir / name, outputs[name])

    summary = {
        "written": list(OUTPUT_FILES),
        "coverage": coverage,
        "deviation_rows": len(deviation_rows(clauses)),
        "human_checklist": checklist_counts,
        "lint": {"flagged": len(flagged), "entity_hits": len(hits), "whitelist_missing": whitelist is None},
        "anomalies": anomalies,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="build_output.py",
        description="投标方案编写·阶段4 双卷骨架渲染: 商务卷=structure 镜像 / 技术卷=逐条款条目(标题嵌 clause_id, D2) / 偏离表 / 覆盖率报表 / 人核清单 / 实体lint(无 LLM, 不做 Word 转换)",
    )
    parser.add_argument("--state-dir", required=True, help="状态目录(只读: clauses.json / structure.json / entities_whitelist.json; 派生字段现算不落盘)")
    parser.add_argument("--out", required=True, help="输出目录(六件套 md, 临时文件+os.replace 原子写盘, 重跑字节级幂等)")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 ingest 的 OCR 分流退出码撞号——统一改道
        # EXIT_ERROR; --help 等正常退出(code 0)原样放行(同 merge_addenda.py 约定)。
        if not exc.code:
            return EXIT_OK
        print(f"[build_output] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        return run_build(Path(args.state_dir), Path(args.out))
    except BuildOutputError as exc:
        print(f"[build_output] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
