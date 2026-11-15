"""招标文件商务卷格式档案(FormatProfile)提取 — P0(EAI-CUSTOM 2026-11-15)。

目标:把招标文件里给定的商务卷/投标文件格式从 raw DOCX 中机器化出来,
供后续「按招标格式填充」而不是套系统预置模板。本模块只读、纯函数、确定性;
不生成正文、不改 AST、不碰审批。

P0 覆盖:
- 定位「投标文件格式/投标文件目录/商务卷」区段;
- 提取章节链、表格列头/合并单元格/空行、固定文字、占位符、签章/贴图位;
- 提取页面设置、页眉页脚、段落/字体摘要;
- 生成与当前 bid_write AST/导出能力的差距清单(blocking_gaps)。

边界(诚实面):P0 只做格式档案与差距清单,不承诺已能 1:1 复刻 DOCX;
合并单元格/列宽/样式已记录但渲染引擎尚未接入。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

FORMAT_PROFILE_SCHEMA_VERSION = "1.1.0"

_ALIGN_NAMES = {
    0: "LEFT",
    1: "CENTER",
    2: "RIGHT",
    3: "JUSTIFY",
    4: "DISTRIBUTE",
    5: "JUSTIFY_MED",
    6: "JUSTIFY_HI",
    7: "JUSTIFY_LOW",
    8: "THAI_JUSTIFY",
}

_PLACEHOLDER_PATTERNS = (
    ("underscore", re.compile(r"[_＿]{2,}")),
    ("blank_parentheses", re.compile(r"[（(]\s*[）)]")),
    ("date_blank", re.compile(r"(?:年\s*月\s*日|年\s{2,}月\s{2,}日)")),
    (
        "bracket_slot",
        re.compile(
            r"[\[【（(][^\]】）)]{0,30}"
            r"(项目名称|采购编号|招标编号|投标人名称|公司名称|姓名|金额|大写|小写|地址|日期)"
            r"[^\]】）)]{0,30}[\]】）)]"
        ),
    ),
)

_SIGNATURE_RE = re.compile(r"(公章|盖章|签字|签署|法定代表人|委托代理人|日期)")
_IMAGE_RE = re.compile(r"(贴|扫描件|身份证|证书|营业执照|截图|照片|图纸)")
_CN_HEADING_RE = re.compile(r"^([一二三四五六七八九十百]+)[、.．]\s*")
_NUM_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)[、.．]?\s*")
_CHAPTER_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百]+[章节]\s*")
_FORMAT_TITLE_RE = re.compile(r"(投标文件格式|投标文件目录|商务卷|商务部分)")
_HEADING_STYLE_RE = re.compile(r"^(?:heading|标题)\s*([1-9])$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[。；;！？!?]$")
_TOC_DOTTED_RE = re.compile(r"[.．·]{3,}\s*\d+\s*$")
_TOC_CN_RE = re.compile(r"^[一二三四五六七八九十百]+\s{2,}\S")
_TOC_NUM_RE = re.compile(r"^\d+(?:\.\d+)*\s{2,}\S")
_SIGNATURE_RESIDUE_RE = re.compile(r"公章|盖章|签字|签署|法定代表人|委托代理人|日期|[：:（）()_＿\s年月日]")


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    raw = getattr(value, "value", None)
    if isinstance(raw, int):
        return _ALIGN_NAMES.get(raw, str(raw))
    return str(value)


def _canonical_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _run_summary(paragraph) -> dict:
    runs = [run for run in paragraph.runs if str(run.text or "").strip()]
    fonts = sorted({str(run.font.name) for run in runs if run.font.name})
    sizes = sorted({_float_or_none(run.font.size.pt if run.font.size else None) for run in runs if run.font.size})
    colors: list[str] = []
    for run in runs:
        try:
            color = run.font.color
            rgb = color.rgb if color is not None else None
            if rgb is not None:
                colors.append(str(rgb))
        except Exception:  # noqa: BLE001  主题色/非法色不影响提取
            continue
    return {
        "fonts": fonts,
        "sizes_pt": [size for size in sizes if size is not None],
        "bold": any(bool(run.bold) for run in runs),
        "italic": any(bool(run.italic) for run in runs),
        "underline": any(bool(run.underline) for run in runs),
        "colors": sorted(set(colors)),
    }


def _outline_level(paragraph) -> int | None:
    try:
        p_pr = paragraph._p.pPr
        node = p_pr.outlineLvl if p_pr is not None else None
        return _int_or_none(node.val) if node is not None else None
    except Exception:  # noqa: BLE001
        return None


def _paragraph_format(paragraph) -> dict:
    fmt = paragraph.paragraph_format
    line_spacing = fmt.line_spacing
    return {
        "alignment": _enum_name(paragraph.alignment),
        "first_line_indent": _int_or_none(fmt.first_line_indent),
        "left_indent": _int_or_none(fmt.left_indent),
        "right_indent": _int_or_none(fmt.right_indent),
        "line_spacing": _float_or_none(line_spacing) if not hasattr(line_spacing, "twips") else _int_or_none(line_spacing),
        "space_before": _int_or_none(fmt.space_before),
        "space_after": _int_or_none(fmt.space_after),
        "keep_with_next": bool(fmt.keep_with_next) if fmt.keep_with_next is not None else None,
        "page_break_before": bool(fmt.page_break_before) if fmt.page_break_before is not None else None,
        "outline_level": _outline_level(paragraph),
    }


def _numbering(paragraph) -> dict | None:
    try:
        p_pr = paragraph._p.pPr
        num_pr = p_pr.numPr if p_pr is not None else None
        if num_pr is None:
            return None
        num_id = num_pr.numId.val if num_pr.numId is not None else None
        ilvl = num_pr.ilvl.val if num_pr.ilvl is not None else None
        if num_id is None and ilvl is None:
            return None
        return {"num_id": _int_or_none(num_id), "ilvl": _int_or_none(ilvl)}
    except Exception:  # noqa: BLE001
        return None


def _placeholders(text: str) -> list[dict]:
    found: list[tuple[int, int, str]] = []
    for kind, pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text):
            found.append((match.start(), match.end(), kind))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    accepted: list[tuple[int, int, str]] = []
    for start, end, kind in found:
        if any(not (end <= a or start >= b) for a, b, _ in accepted):
            continue
        accepted.append((start, end, kind))

    out: list[dict] = []
    for start, end, kind in accepted:
        before_raw = text[max(0, start - 24) : start]
        after_raw = text[end : min(len(text), end + 24)]
        before_parts = [part.strip() for part in re.split(r"[：:，,；;、（）()\[\]【】]", before_raw) if part.strip()]
        before = before_parts[-1] if before_parts else ""
        after_clean = after_raw.lstrip(" \t（(【[")
        after = re.split(r"[：:，,；;、（）()\[\]【】]", after_clean)[0].strip(" \t）)】]")
        label = before or after or ""
        if not label and kind == "bracket_slot":
            label = text[start:end].strip(" \t[]【】（）()")
        out.append(
            {
                "type": kind,
                "text": text[start:end],
                "start": start,
                "end": end,
                "label": label[:40],
                "context": text[max(0, start - 24) : min(len(text), end + 24)],
            }
        )
    return out


def _heading_level(paragraph, text: str) -> int:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    matched = _HEADING_STYLE_RE.match(style_name or "")
    if matched:
        return int(matched.group(1))
    compact = text.strip()
    if not compact or len(compact) > 60 or _SENTENCE_END_RE.search(compact):
        return 0
    if compact in ("投标文件目录", "投标文件格式"):
        return 1
    if _CHAPTER_HEADING_RE.match(compact):
        return 1
    matched = _CN_HEADING_RE.match(compact)
    if matched and len(compact) > len(matched.group(0)):
        return 1
    matched = _NUM_HEADING_RE.match(compact)
    if matched and len(compact) > len(matched.group(0)):
        depth = matched.group(1).count(".") + 1
        if depth >= 2:
            return depth
        # 单级 "2.xxx" 更像清单项;只有显式大纲级别/标题样式才当标题。
        outline = _outline_level(paragraph)
        return 1 if outline is not None and outline >= 0 else 0
    outline = _outline_level(paragraph)
    if outline is not None and outline >= 0:
        return outline + 1
    return 0


def _is_toc_line(text: str) -> bool:
    compact = str(text or "").strip()
    if not compact:
        return False
    if _TOC_DOTTED_RE.search(compact) or re.search(r"\s{2,}\d+\s*$", compact):
        return True
    return bool(_TOC_CN_RE.match(compact) or _TOC_NUM_RE.match(compact))


def _is_format_title(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    return "投标文件格式" in compact or compact in ("商务卷", "商务部分")


def _normalize_title(text: str) -> str:
    compact = re.sub(r"\s+", "", str(text or ""))
    compact = re.sub(r"^第[一二三四五六七八九十百]+[章节、.．]?", "", compact)
    compact = re.sub(r"^\d+(?:\.\d+)*[、.．]?", "", compact)
    compact = re.sub(r"^[一二三四五六七八九十百]+[、.．]?", "", compact)
    return compact.strip("、.．:：-—")


def _is_signature_only(text: str) -> bool:
    if not _SIGNATURE_RE.search(text) or len(text) > 60:
        return False
    if re.search(r"[（(](?:公章|盖章|签字|签署)[）)]\s*[：:]?\s*$", text):
        return True
    residual = _SIGNATURE_RESIDUE_RE.sub("", text)
    return len(residual) <= 8


def _is_fixed_text(
    text: str,
    placeholders: list[dict],
    heading_level: int,
    *,
    is_toc: bool = False,
    is_signature_only: bool = False,
) -> bool:
    if is_toc or is_signature_only:
        return False
    if heading_level or not text or len(text) < 8:
        return False
    if placeholders:
        return False
    if _FORMAT_TITLE_RE.search(text) and len(text) < 20:
        return False
    return True


def _cell_text(cell) -> str:
    return str(cell.text or "").strip().replace("\r\n", "\n").replace("\r", "\n")


def _table_profile(table, table_index: int) -> dict:
    from docx.table import _Cell

    rows: list[dict] = []
    merged_count = 0
    blank_count = 0
    placeholder_count = 0
    fixed_rows: list[list[str]] = []
    blank_rows: list[int] = []
    for row_index, row in enumerate(table.rows):
        cells: list[dict] = []
        texts: list[str] = []
        has_placeholder = False
        for tc in getattr(row._tr, "tc_lst", []):
            cell = _Cell(tc, table)
            text = _cell_text(cell)
            texts.append(text)
            tc_pr = tc.tcPr
            grid_span = 1
            v_merge = None
            if tc_pr is not None:
                if tc_pr.gridSpan is not None and tc_pr.gridSpan.val is not None:
                    grid_span = max(1, int(tc_pr.gridSpan.val))
                if tc_pr.vMerge is not None:
                    v_merge = tc_pr.vMerge.val if tc_pr.vMerge.val is not None else "continue"
            placeholders = _placeholders(text)
            if grid_span > 1 or v_merge is not None:
                merged_count += 1
            if not text:
                blank_count += 1
            if placeholders:
                placeholder_count += 1
                has_placeholder = True
            cells.append(
                {
                    "text": text,
                    "col_span": grid_span,
                    "v_merge": v_merge,
                    "blank": not bool(text),
                    "placeholder_types": [item["type"] for item in placeholders],
                    "width": _int_or_none(cell.width),
                }
            )
        rows.append({"index": row_index, "cells": cells})
        if texts and all(not item for item in texts):
            blank_rows.append(row_index)
        if texts and not has_placeholder and any(item for item in texts):
            fixed_rows.append(texts)

    headers = [cell["text"] for cell in rows[0]["cells"]] if rows else []
    column_widths = [_int_or_none(column.width) for column in table.columns]
    return {
        "table_index": table_index,
        "style": table.style.name if table.style is not None else "",
        "row_count": len(rows),
        "column_count": len(table.columns),
        "column_widths": column_widths,
        "headers": headers,
        "has_merged_cells": merged_count > 0,
        "merged_cell_count": merged_count,
        "blank_cell_count": blank_count,
        "placeholder_cell_count": placeholder_count,
        "blank_rows": blank_rows,
        "fixed_rows": fixed_rows,
        "rows": rows,
    }


def _section_profile(document) -> list[dict]:
    out: list[dict] = []
    for index, section in enumerate(document.sections):
        header_texts = [p.text.strip() for p in section.header.paragraphs if p.text.strip()]
        footer_texts = [p.text.strip() for p in section.footer.paragraphs if p.text.strip()]
        out.append(
            {
                "index": index,
                "start_type": _enum_name(section.start_type),
                "orientation": _enum_name(section.orientation),
                "page_width": _int_or_none(section.page_width),
                "page_height": _int_or_none(section.page_height),
                "top_margin": _int_or_none(section.top_margin),
                "bottom_margin": _int_or_none(section.bottom_margin),
                "left_margin": _int_or_none(section.left_margin),
                "right_margin": _int_or_none(section.right_margin),
                "header_distance": _int_or_none(section.header_distance),
                "footer_distance": _int_or_none(section.footer_distance),
                "header_texts": header_texts,
                "footer_texts": footer_texts,
            }
        )
    return out


def _document_blocks(document) -> list[dict]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks: list[dict] = []
    paragraph_index = 0
    table_index = 0
    for child in document.element.body.iterchildren():
        local = child.tag.rsplit("}", 1)[-1]
        if local == "p":
            paragraph = Paragraph(child, document)
            text = str(paragraph.text or "").strip()
            level = _heading_level(paragraph, text)
            blocks.append(
                {
                    "index": len(blocks),
                    "kind": "paragraph",
                    "paragraph_index": paragraph_index,
                    "text": text,
                    "style": paragraph.style.name if paragraph.style is not None else "",
                    "heading_level": level,
                    "is_heading": level > 0,
                    "format": _paragraph_format(paragraph),
                    "runs": _run_summary(paragraph),
                    "numbering": _numbering(paragraph),
                    "placeholders": _placeholders(text),
                }
            )
            paragraph_index += 1
        elif local == "tbl":
            table = Table(child, document)
            blocks.append(
                {
                    "index": len(blocks),
                    "kind": "table",
                    "table_index": table_index,
                    "table": _table_profile(table, table_index),
                }
            )
            table_index += 1
    return blocks


def _compact(text: str) -> str:
    return "".join(str(text or "").split())


def _find_format_range(blocks: list[dict]) -> tuple[int | None, int | None]:
    toc_index: int | None = None
    for index, block in enumerate(blocks):
        if block.get("kind") != "paragraph":
            continue
        text = str(block.get("text") or "")
        if "投标文件目录" in text:
            toc_index = index
            break
    if toc_index is None:
        for index, block in enumerate(blocks):
            if block.get("kind") != "paragraph":
                continue
            text = str(block.get("text") or "")
            if "投标文件格式" in text and (block.get("is_heading") or "格式" in text):
                toc_index = index
                break
    if toc_index is None:
        return None, None

    start = toc_index
    lower = max(0, toc_index - 30)
    for index in range(toc_index - 1, lower - 1, -1):
        block = blocks[index]
        if block.get("kind") != "paragraph":
            continue
        text = str(block.get("text") or "")
        compact = _compact(text)
        if not compact:
            continue
        if "目录" in compact:
            continue
        if "投标文件" in compact or "项目名称" in compact or "采购编号" in compact:
            start = index
            continue
        if _CHAPTER_HEADING_RE.match(text) and block.get("is_heading"):
            start = index
            break
        break

    end = len(blocks)
    for index in range(start + 1, len(blocks)):
        block = blocks[index]
        if block.get("kind") != "paragraph":
            continue
        text = str(block.get("text") or "")
        if block.get("is_heading") and _CHAPTER_HEADING_RE.match(text) and "投标文件格式" not in text:
            end = index
            break
    return start, end


def _toc_index(blocks: list[dict]) -> int | None:
    for index, block in enumerate(blocks):
        if block.get("kind") == "paragraph" and "投标文件目录" in str(block.get("text") or ""):
            return index
    return None


def _toc_entries_from_blocks(blocks: list[dict], toc_index: int | None) -> list[dict]:
    if toc_index is None:
        return []
    entries: list[dict] = []
    for block in blocks[toc_index + 1 :]:
        if block.get("kind") != "paragraph":
            if entries:
                break
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        level = int(block.get("heading_level") or 0)
        if level > 0 and not _is_toc_line(text):
            break
        if not _is_toc_line(text):
            if level > 0 or len(text) > 40 or _SENTENCE_END_RE.search(text) or _placeholders(text):
                break
        entries.append({"text": text, "paragraph_index": block.get("paragraph_index"), "block_index": block.get("index")})
        if len(entries) >= 80:
            break
    return entries


def _chapters_from_blocks(blocks: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    toc_index = _toc_index(blocks)
    toc_entries = _toc_entries_from_blocks(blocks, toc_index)
    toc_blocks = {entry.get("block_index") for entry in toc_entries}
    toc_titles = {_normalize_title(entry.get("text") or "") for entry in toc_entries}
    toc_titles.discard("")

    chapters: list[dict] = []
    cover_texts: list[str] = []
    in_toc = toc_index is not None
    for position, block in enumerate(blocks):
        if block.get("kind") != "paragraph":
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        block_index = block.get("index")
        if block_index in toc_blocks:
            continue
        if position == toc_index:
            in_toc = True
            chapters.append(
                {
                    "index": len(chapters),
                    "title": text,
                    "level": 0,
                    "kind": "toc",
                    "paragraph_index": block.get("paragraph_index"),
                    "block_index": block_index,
                }
            )
            continue
        level = int(block.get("heading_level") or 0)
        if in_toc and level == 0:
            continue
        if level > 0:
            in_toc = False
            if _is_format_title(text):
                chapters.append(
                    {
                        "index": len(chapters),
                        "title": text,
                        "level": 0,
                        "kind": "format_title",
                        "paragraph_index": block.get("paragraph_index"),
                        "block_index": block_index,
                    }
                )
                continue
            if _normalize_title(text) in toc_titles:
                level = 1
            chapters.append(
                {
                    "index": len(chapters),
                    "title": text,
                    "level": level,
                    "kind": "heading",
                    "paragraph_index": block.get("paragraph_index"),
                    "block_index": block_index,
                }
            )
            continue
        if toc_index is None or position < toc_index:
            cover_texts.append(text)
    return chapters, toc_entries, cover_texts


def _outline(chapters: list[dict]) -> list[dict]:
    roots: list[dict] = []
    stack: list[dict] = []
    for chapter in chapters:
        level = int(chapter.get("level") or 0)
        if level <= 0:
            continue
        node = {
            "title": chapter["title"],
            "level": level,
            "paragraph_index": chapter.get("paragraph_index"),
            "block_index": chapter.get("block_index"),
            "children": [],
        }
        while stack and int(stack[-1].get("level") or 0) >= level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _business_titles(chapters: list[dict], toc_entries: list[dict]) -> list[str]:
    if toc_entries:
        return [str(entry.get("text") or "").strip() for entry in toc_entries if str(entry.get("text") or "").strip()]
    return [str(chapter.get("title") or "").strip() for chapter in chapters if int(chapter.get("level") or 0) == 1]


def _toc_matched_count(chapters: list[dict], toc_entries: list[dict]) -> int:
    if not toc_entries:
        return 0
    toc_titles = {_normalize_title(entry.get("text") or "") for entry in toc_entries}
    toc_titles.discard("")
    return sum(1 for chapter in chapters if int(chapter.get("level") or 0) > 0 and _normalize_title(chapter.get("title") or "") in toc_titles)


def _gap_report(
    *,
    chapters: list[dict],
    toc_entries: list[dict],
    tables: list[dict],
    placeholders: list[dict],
    fixed_texts: list[dict],
    signatures: list[dict],
    image_slots: list[dict],
    page_setup: list[dict],
) -> dict:
    max_columns = max((int(table.get("column_count") or 0) for table in tables), default=0)
    merged_tables = [table.get("table_index") for table in tables if table.get("has_merged_cells")]
    business_titles = _business_titles(chapters, toc_entries)
    heading_count = len([chapter for chapter in chapters if int(chapter.get("level") or 0) > 0])
    toc_matched = _toc_matched_count(chapters, toc_entries)
    capabilities = [
        {
            "id": "chapter_structure",
            "label": "招标章节结构与顺序",
            "tender_demand": f"投标文件目录 {len(toc_entries)} 项,正文解析 {heading_count} 个标题",
            "current_support": "format_profile_to_ast 按招标标题层级生成 section 树;未检测到格式章节时仍走四章节兜底",
            "status": "supported" if business_titles else "missing",
            "evidence": business_titles[:20],
        },
        {
            "id": "fixed_text",
            "label": "招标固定文字 1:1 照抄",
            "tender_demand": f"检测到 {len(fixed_texts)} 段无占位固定文字",
            "current_support": "固定文字写入 locked_paragraph(template_id=tender-format:*),编辑器禁改",
            "status": "supported" if fixed_texts else "missing",
            "evidence": [item.get("text", "")[:50] for item in fixed_texts[:10]],
        },
        {
            "id": "placeholders",
            "label": "表单占位符/待填位",
            "tender_demand": f"检测到 {len(placeholders)} 个占位符",
            "current_support": "placeholder 行内原子节点保留原文占位符,并按任务/素材/报价事实填充;未知字段保留待填",
            "status": "supported" if placeholders else "missing",
            "evidence": [item.get("text") for item in placeholders[:10]],
        },
        {
            "id": "table_structure",
            "label": "招标表格列头/合并单元格/空行",
            "tender_demand": f"{len(tables)} 张表,最大 {max_columns} 列,{len(merged_tables)} 张含合并单元格",
            "current_support": "表格节点支持 col_span/row_span;format_profile_to_ast 将 OOXML gridSpan/vMerge 归一为合并起点单元格",
            "status": "supported" if tables else "missing",
            "evidence": {"max_columns": max_columns, "merged_tables": merged_tables},
        },
        {
            "id": "signature_image",
            "label": "签章位/身份证/证书贴图位",
            "tender_demand": f"{len(signatures)} 个签章/落款位,{len(image_slots)} 个贴图/扫描件位",
            "current_support": "签章/贴图文字位保留为 para(slot_id),尚不能嵌入图片或印章图形",
            "status": "missing" if signatures or image_slots else "supported",
            "evidence": [item.get("text", "")[:50] for item in (signatures + image_slots)[:10]],
        },
        {
            "id": "page_layout",
            "label": "页面设置/页眉页脚/分节",
            "tender_demand": f"{len(page_setup)} 个分节,含页边距/分页设置",
            "current_support": "冻结 FormatProfile 的首个分节页面尺寸/方向/页边距/页眉页脚/页码由 DOCX 渲染器应用",
            "status": "supported" if page_setup else "missing",
            "evidence": page_setup[:3],
        },
        {
            "id": "toc",
            "label": "目录与章节标题一致",
            "tender_demand": f"目录 {len(toc_entries)} 项,正文匹配 {toc_matched} 项" if toc_entries else "未检测到目录",
            "current_support": "format_profile_to_ast 按招标目录项生成 toc_entry,并保留原目录文字",
            "status": "supported" if toc_entries else ("partial" if business_titles else "missing"),
            "evidence": business_titles[:10],
        },
        {
            "id": "export_render",
            "label": "DOCX 版式保真导出",
            "tender_demand": "需保留招标表格/合并单元格/字体/页眉页脚/分节",
            "current_support": "有冻结 FormatProfile 时走 AST→python-docx 直渲染(合并单元格/页面设置/页眉页脚);逐 run 字体细节按段落摘要近似",
            "status": "partial",
            "evidence": [],
        },
        {
            "id": "approval_freeze",
            "label": "审批冻结格式事实",
            "tender_demand": "格式档案必须随正文一起冻结,防止审批后换版",
            "current_support": "审批提交时在同一事务写入 bid_write_revision_format_profiles 快照;导出只读冻结快照",
            "status": "supported",
            "evidence": [],
        },
    ]
    blocking = sorted(capability["id"] for capability in capabilities if capability["status"] != "supported")
    blocking_reasons = {capability["id"]: capability["current_support"] for capability in capabilities if capability["id"] in blocking}
    return {
        "summary": {
            "chapter_count": len(business_titles),
            "heading_count": heading_count,
            "toc_entry_count": len(toc_entries),
            "toc_matched_count": toc_matched,
            "table_count": len(tables),
            "max_table_columns": max_columns,
            "merged_table_count": len(merged_tables),
            "placeholder_count": len(placeholders),
            "fixed_text_count": len(fixed_texts),
            "signature_count": len(signatures),
            "image_slot_count": len(image_slots),
            "blocking_gap_count": len(blocking),
        },
        "capabilities": capabilities,
        "blocking_gaps": blocking,
        "blocking_reasons": blocking_reasons,
        "note": "P1 已接入合并表格、固定文字、占位符、版式渲染与审批冻结;signature_image 与逐 run 字体保真仍有差距,不会宣称 100% 1:1。",
    }


def extract_format_profile(data: bytes, *, doc_id: str = "", source_name: str = "") -> dict:
    """从 DOCX 字节提取 FormatProfile(纯函数、确定性)。非 DOCX/损坏文件返回 supported=false。"""
    raw_sha256 = hashlib.sha256(data or b"").hexdigest()
    base: dict[str, Any] = {
        "schema_version": FORMAT_PROFILE_SCHEMA_VERSION,
        "supported": False,
        "source": {
            "doc_id": doc_id,
            "name": source_name or doc_id,
            "kind": "docx" if (data or b"")[:4] == b"PK\x03\x04" else "unknown",
            "bytes": len(data or b""),
            "sha256": raw_sha256,
        },
    }
    try:
        from docx import Document

        document = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        base["reason"] = f"无法打开 DOCX: {exc}"
        base["profile_hash"] = _canonical_hash(base)
        return base
    try:
        return _profile_from_document(document, base)
    except Exception as exc:  # noqa: BLE001  格式异常不应让解析主流程崩溃
        base["reason"] = f"格式档案提取失败: {exc}"
        base["profile_hash"] = _canonical_hash(base)
        return base


def _profile_from_document(document, base: dict[str, Any]) -> dict:

    blocks = _document_blocks(document)
    start, end = _find_format_range(blocks)
    format_blocks = blocks[start:end] if start is not None and end is not None else []
    chapters, toc_entries, cover_texts = _chapters_from_blocks(format_blocks)
    toc_blocks = {chapter.get("block_index") for chapter in chapters if chapter.get("kind") == "toc"}
    toc_blocks |= {entry.get("block_index") for entry in toc_entries}
    business_titles = _business_titles(chapters, toc_entries)
    heading_count = len([chapter for chapter in chapters if int(chapter.get("level") or 0) > 0])

    fixed_texts: list[dict] = []
    placeholders: list[dict] = []
    signatures: list[dict] = []
    image_slots: list[dict] = []
    tables: list[dict] = []
    for block in format_blocks:
        if block.get("kind") == "table":
            table = dict(block.get("table") or {})
            table["block_index"] = block.get("index")
            tables.append(table)
            continue
        text = str(block.get("text") or "")
        if not text:
            continue
        heading_level = int(block.get("heading_level") or 0)
        is_signature_only = _is_signature_only(text)
        placeholders.extend({**item, "paragraph_index": block.get("paragraph_index"), "block_index": block.get("index")} for item in block.get("placeholders") or [])
        if _is_fixed_text(
            text,
            block.get("placeholders") or [],
            heading_level,
            is_toc=block.get("index") in toc_blocks,
            is_signature_only=is_signature_only,
        ):
            fixed_texts.append(
                {
                    "text": text,
                    "style": block.get("style"),
                    "paragraph_index": block.get("paragraph_index"),
                    "block_index": block.get("index"),
                    "format": block.get("format"),
                }
            )
        if not heading_level and is_signature_only:
            signatures.append(
                {
                    "text": text,
                    "types": sorted(set(_SIGNATURE_RE.findall(text))),
                    "paragraph_index": block.get("paragraph_index"),
                    "block_index": block.get("index"),
                }
            )
        if not heading_level and _IMAGE_RE.search(text):
            image_slots.append(
                {
                    "text": text,
                    "types": sorted(set(_IMAGE_RE.findall(text))),
                    "paragraph_index": block.get("paragraph_index"),
                    "block_index": block.get("index"),
                }
            )

    page_setup = _section_profile(document)
    styles: dict[str, int] = {}
    for paragraph in document.paragraphs:
        style = paragraph.style.name if paragraph.style is not None else ""
        styles[style] = styles.get(style, 0) + 1

    profile: dict[str, Any] = {
        **base,
        "supported": True,
        "document": {
            "paragraph_count": len(document.paragraphs),
            "table_count": len(document.tables),
            "section_count": len(document.sections),
            "heading_count": len([block for block in blocks if block.get("is_heading")]),
            "styles": dict(sorted(styles.items(), key=lambda item: (-item[1], item[0]))[:20]),
            "page_setup": page_setup,
        },
        "format_section": {
            "detected": start is not None,
            "start_block_index": start,
            "end_block_index": end,
            "start_paragraph_index": format_blocks[0].get("paragraph_index") if format_blocks else None,
            "end_paragraph_index": format_blocks[-1].get("paragraph_index") if format_blocks else None,
            "chapter_count": len(business_titles),
            "chapter_titles": business_titles,
            "heading_count": heading_count,
            "toc_entry_count": len(toc_entries),
            "toc_matched_count": _toc_matched_count(chapters, toc_entries),
            "cover_texts": cover_texts,
            "toc_entries": toc_entries,
        },
        "chapters": chapters,
        "outline": _outline(chapters),
        "tables": tables,
        "fixed_texts": fixed_texts,
        "placeholders": placeholders,
        "signatures": signatures,
        "image_slots": image_slots,
        "blocks": format_blocks,
    }
    profile["gap_report"] = _gap_report(
        chapters=chapters,
        toc_entries=toc_entries,
        tables=tables,
        placeholders=placeholders,
        fixed_texts=fixed_texts,
        signatures=signatures,
        image_slots=image_slots,
        page_setup=page_setup,
    )
    profile["profile_hash"] = _canonical_hash(profile)
    return profile


def extract_format_profile_from_path(path: str | Path, *, doc_id: str = "") -> dict:
    source = Path(path)
    return extract_format_profile(source.read_bytes(), doc_id=doc_id or source.name, source_name=source.name)


def summary_of(profile: dict) -> dict:
    return {
        "supported": profile.get("supported"),
        "source": profile.get("source"),
        "format_section": profile.get("format_section"),
        "gap_report": profile.get("gap_report"),
        "profile_hash": profile.get("profile_hash"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="format-profile", description="提取招标文件商务卷 FormatProfile 与差距清单(P0,只读)")
    parser.add_argument("--input", required=True, help="招标文件 DOCX 路径")
    parser.add_argument("--out", default="", help="输出 JSON 路径(缺省 stdout)")
    parser.add_argument("--doc-id", default="", help="来源 doc_id(缺省文件名)")
    parser.add_argument("--summary", action="store_true", help="只输出摘要与差距清单")
    args = parser.parse_args(argv)
    profile = extract_format_profile_from_path(args.input, doc_id=args.doc_id)
    payload = summary_of(profile) if args.summary else profile
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "out": args.out, "profile_hash": profile.get("profile_hash"), "supported": profile.get("supported")}, ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
