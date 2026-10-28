"""Glossary Excel/CSV import parsing + merge (EAI-CUSTOM, 2026-10-18).

解析在服务端完成（openpyxl 已是既有依赖），前端只上传文件并展示预览。
列契约（表头别名大小写不敏感）：

    源词 / 语言 / 动作 / 目标译法 / 领域（可选）

导入语义为合并（按 ``(源词, 语言)`` upsert）；文件未出现的存量条目保留。
存在非法行时，前端禁用确认；合法行仍会在 ``merged`` 中返回。
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.extensions.translation.glossary import GlossaryEntry

logger = logging.getLogger(__name__)

MAX_IMPORT_BYTES = 2 * 1024 * 1024  # 2 MB（与原型一致）

_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "source": frozenset({"source", "term", "源词", "术语", "原文"}),
    "lang": frozenset({"lang", "language", "语言"}),
    "action": frozenset({"action", "动作", "类型"}),
    "target": frozenset({"target", "translation", "目标译法", "译文", "译法"}),
    "domains": frozenset({"domain", "domains", "领域", "业务领域", "行业"}),
    "notes": frozenset({"notes", "note", "remark", "说明", "备注"}),
}

_ACTION_ALIASES: dict[str, str] = {
    "force": "force",
    "指定译法": "force",
    "指定": "force",
    "强制": "force",
    "forbid": "forbid",
    "保留原文": "forbid",
    "不译": "forbid",
    "keep": "keep",
    "原样保留": "keep",
    "原文保留": "keep",
}

_LANG_ALIASES: dict[str, str] = {
    "en": "en",
    "english": "en",
    "英文": "en",
    "英": "en",
    "fr": "fr",
    "french": "fr",
    "français": "fr",
    "francais": "fr",
    "法文": "fr",
    "法": "fr",
    "any": "any",
    "all": "any",
    "通用": "any",
    "双语": "any",
}


@dataclass
class ParsedRow:
    """文件中的一行（归一化后，含校验错误）。"""

    row: int
    source: str
    lang: str
    action: str
    target: str | None
    domains: list[str] = field(default_factory=list)
    notes: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class RowResult(ParsedRow):
    """合并后的行状态：add | update | unchanged | invalid。"""

    status: str = "invalid"


@dataclass
class ImportResult:
    rows: list[RowResult]
    merged: list[GlossaryEntry]
    summary: dict[str, int]


def _norm(value: object) -> str:
    return str(value).strip().lower() if value is not None else ""


def _split_domains(value: object) -> list[str]:
    """领域单元格支持逗号/顿号/分号/换行分隔的多值。"""
    text = str(value or "").strip()
    if not text:
        return []
    import re

    out: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,，、;；\n]+", text):
        item = item.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out


def _read_xlsx(data: bytes) -> list[list[object]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _read_csv(data: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 编码无法识别，请使用 UTF-8 保存")
    return [row for row in csv.reader(io.StringIO(text))]


def _find_header(rows: list[list[object]]) -> tuple[int, dict[str, int]]:
    """在前 10 行内寻找表头行；至少需要 source + action 两列。"""
    for index, row in enumerate(rows[:10]):
        mapping: dict[str, int] = {}
        for col, cell in enumerate(row):
            key = _norm(cell)
            for field_name, aliases in _HEADER_ALIASES.items():
                if key in aliases and field_name not in mapping:
                    mapping[field_name] = col
        if "source" in mapping and "action" in mapping:
            return index, mapping
    raise ValueError("未找到表头：至少需要「源词」「动作」两列")


def parse_rows(rows: list[list[object]]) -> list[ParsedRow]:
    """把原始表格行解析为校验后的词条行。"""
    header_index, mapping = _find_header(rows)
    parsed: list[ParsedRow] = []
    seen: dict[tuple[str, str], int] = {}

    for offset, raw in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not raw or all(_norm(cell) == "" for cell in raw):
            continue

        def cell(name: str) -> object:
            col = mapping.get(name)
            return raw[col] if col is not None and col < len(raw) else None

        source = str(cell("source") or "").strip()
        action_raw = _norm(cell("action"))
        lang_raw = _norm(cell("lang"))
        target = str(cell("target") or "").strip() or None
        domains = _split_domains(cell("domains"))
        notes = str(cell("notes") or "").strip() or None

        action = _ACTION_ALIASES.get(action_raw, "")
        lang = _LANG_ALIASES.get(lang_raw, "any" if lang_raw == "" else "")

        errors: list[str] = []
        if not source:
            errors.append("源词为空")
        if not action:
            errors.append(f"动作无法识别：{action_raw or '（空）'}；支持 指定译法 / 保留原文 / 原样保留")
        if not lang:
            errors.append(f"语言无法识别：{lang_raw}；支持 EN / FR / ANY")
        if action == "force" and not target:
            errors.append("动作为「指定译法」但缺少目标译法")
        if action and action != "force":
            target = None

        if source and lang and action:
            key = (source.casefold(), lang)
            if key in seen:
                errors.append(f"文件内重复：第 {seen[key]} 行已定义同一源词与语言")
            else:
                seen[key] = offset

        parsed.append(
            ParsedRow(
                row=offset,
                source=source,
                lang=lang or "any",
                action=action,
                target=target,
                domains=domains,
                notes=notes,
                errors=errors,
            )
        )
    return parsed


def parse_file(filename: str, data: bytes) -> list[ParsedRow]:
    """按扩展名解析上传文件；失败抛 ValueError（路由层转 400）。"""
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("文件超过 2 MB 上限")
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".xlsx":
        rows = _read_xlsx(data)
    elif suffix == ".csv":
        rows = _read_csv(data)
    elif suffix == ".xls":
        raise ValueError("不支持 .xls，请另存为 .xlsx 后重试")
    else:
        raise ValueError("仅支持 .xlsx / .csv 文件")
    return parse_rows(rows)


def merge(existing: list[GlossaryEntry], parsed: list[ParsedRow]) -> ImportResult:
    """按 (source, lang) 合并；返回逐行状态与合并后的全表。"""
    merged_list = list(existing)
    index: dict[tuple[str, str], int] = {(e.source.casefold(), e.lang): i for i, e in enumerate(merged_list)}
    rows: list[RowResult] = []
    summary = {"add": 0, "update": 0, "unchanged": 0, "invalid": 0, "total": len(parsed)}

    for item in parsed:
        if item.errors:
            rows.append(RowResult(**item.__dict__, status="invalid"))
            summary["invalid"] += 1
            continue

        entry = GlossaryEntry(
            source=item.source,
            action=item.action,
            target=item.target,
            lang=item.lang,
            domains=item.domains,
            notes=item.notes,
        )
        key = (item.source.casefold(), item.lang)
        old_index = index.get(key)
        if old_index is None:
            index[key] = len(merged_list)
            merged_list.append(entry)
            status = "add"
        else:
            old = merged_list[old_index]
            if (old.action, old.target, tuple(old.domains), old.notes) != (
                entry.action,
                entry.target,
                tuple(entry.domains),
                entry.notes,
            ):
                merged_list[old_index] = entry
                status = "update"
            else:
                status = "unchanged"

        rows.append(RowResult(**item.__dict__, status=status))
        summary[status] += 1

    return ImportResult(rows=rows, merged=merged_list, summary=summary)
