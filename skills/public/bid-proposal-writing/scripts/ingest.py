#!/usr/bin/env python3
"""ingest.py — 投标方案编写技能·阶段1 输入分流与纯结构化解析(确定性, 无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md「阶段1 ingest」。

用法:
    python ingest.py --input 招标文件.docx 技术规范书.pdf --code ZB --out <dir> [--addendum]

职责(设计文档锁定, 不缺不漏不加):
    1. 按章节切块 → <out>/sections.json, 与 T1 锁定契约逐字一致:
         chunk = {chunk_id, source_file, anchor, heading_path, n_paras}
         table = {table_id, source_file, anchor, n_rows, n_cols, caption}
    2. 锚点按来源分流: docx=section+段落序(无 page 键, docx 无分页概念);
       PDF/OCR=page+section(无 para 键)。段落序 = 块(段落/表格)在所在章节内的 1 起序号。
    3. 每张表发放稳定 table_id 并记录行数; 结构行数 vs 抽取行数比对(D5 覆盖度防线,
       防解析器吞表后静默漏检)——不一致进异常项, 退出码 3, 绝不静默。
    4. 定位"投标文件格式"类章节(标题启发式)→ 该子树只产出章节树骨架
       (每个标题成块、n_paras=0), 槽位语义定型留给阶段2。
    5. 补遗/答疑输入: --addendum 标记, 文件代号前缀按 --code 分配, 增量追加进既有
       sections.json(chunk_id/table_id 全局续号)。同名文件重跑按解析产物内容指纹分流:
       未变=保号 no-op(sections.json 字节不变, 摘要计 skipped_unchanged——候选裁决
       台账不孤儿化); 有变=替换旧块发新号, 摘要显式给出 replaced 计数与被替换旧
       id 清单(编排方据此判"候选裁决已失效, 需重跑阶段2 提取")。
    6. docx 无文本层(扫描件)→ 明确提示走 eai-flow-ocr 路径, 退出码 2 区分。
    7. 写盘原子化: 临时文件 + os.replace(D7 状态一致性), 派生字段一律现算不落盘。

脚本纪律: 纯 Python 3.12; 除 docx/pdfplumber(沙箱 venv 已备)外仅 stdlib;
不调用 LLM; 不 import app.*/deerflow.*。

退出码:
    0 = 干净完成(--help 等正常终止亦为 0)
    1 = 用法/文件错误(含 argparse 参数用法错误——argparse 默认退出码 2 与
        EXIT_NEED_OCR 撞号, 此处统一改道 1; 输入缺失、类型不支持、代号非法、
        产物损坏、空文档、写盘目标不可写/被占用、同批输入文件名重复)
    2 = 存在无文本层输入(扫描件)→ 需先走 eai-flow-ocr 全文 OCR 路径
    3 = 完成但有异常项(表行数不一致等, 摘要 JSON 的 anomalies 列出)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import state_guard

# --- 退出码约定 ---------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEED_OCR = 2
EXIT_ANOMALY = 3

# --- OOXML 命名空间与解析规则 ---------------------------------------------------
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 段落样式名 → 标题级别: 匹配 "Heading 1" / "标题 1"(中文 Word 本地化名)
_HEADING_STYLE_NAME = re.compile(r"^(?:heading|标题)\s*(\d)$", re.IGNORECASE)
# 兜底路径按样式 ID(w:val)判定: "Heading1".."Heading9" 或内置数字 ID "1".."9"
_HEADING_STYLE_ID = re.compile(r"^(?:heading)?\s*(\d)$", re.IGNORECASE)

# --- 章节标识/格式章节启发式 -----------------------------------------------------
# 阿拉伯多级编号前缀: "3.2.1 技术参数要求" / "6.1 评分细则" / "2. Technical …"
# 前瞻契约(残留审查 Critical 修复): 编号后必须跟空白/中文分隔符, 或"点+空白"
# ("2. Title"), 或点号收尾/行尾("2."、"2.1")。前瞻里的 ASCII 点不得直接后跟任意
# 字符——否则回溯会把无空格编号截断("1.1项目概况"→"1"、"3.2.1技术参数要求"→"3.2"),
# 不同章节坍缩到同一锚点且 rc=0 完全静默; 无空格多级编号据此回落为全文标识
# (与 docx "一、" 路径同构), 锚点是 T4 条款溯源的全部地基, 绝不截断。
_ARABIC_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)(?=[\s、．,，:：]|\.+\s|\.*$)")
# 中文序号前缀: "一、项目概况"(仅 PDF 来源按序号取段标识)
_CN_ORDINAL_PREFIX = re.compile(r"^([一二三四五六七八九十百]+)、")
# 标题编号后分隔符剥离(任意空白/标点组合, 两端): "2. Title" 类点+空格混合形态
_SEP_STRIP = re.compile(r"^[\s、.．:：]+|[\s、.．:：]+$")

# 格式章节强/弱启发式: 强=标题含"投标文件格式"; 弱=章级(level==1)标题含"格式"
# 且不含评分类字样(防"评分办法及格式说明"误判)
_FORMAT_STRONG = "投标文件格式"
_FORMAT_WEAK_EXCLUDE = ("评分", "评标", "办法")

# 文件代号: 2-4 位大写字母(与 references/clauses.schema.json 契约一致)
_CODE_RE = re.compile(r"^[A-Z]{2,4}$")

# chunk/table id: <前缀>-<3 位序号>(与 sections.json 契约一致)
_ID_RE_CACHE: dict[str, re.Pattern[str]] = {}

# 文首内容(首个标题之前, 如封面表格)的锚点 section: T1 契约要求 section 非空,
# 括号前缀保证该合成值不与任何真实标题文本混淆
_PRE_HEADING_SECTION = "(文首)"


class IngestBaseError(Exception):
    """ingest 可控错误基类(main 统一转退出码)。"""


class IngestError(IngestBaseError):
    """用法/文件错误 → 退出码 1。"""


class NeedOcrError(IngestBaseError):
    """无文本层输入(扫描件)→ 退出码 2, 需走 eai-flow-ocr 路径。"""


# =============================================================================
# 章节标识与格式章节启发式(纯函数, 单测直测)
# =============================================================================


def section_id_for_heading(text: str, source_kind: str) -> str:
    """从标题文本提取章节标识(锚点的 section 值)。

    规则(与 T1 fixture 逐例对齐):
      - 阿拉伯多级编号前缀 → 编号本身("3.2.1 技术参数要求"→"3.2.1", "2. Technical…"→"2");
      - PDF/OCR 来源的中文序号前缀 → 序号("二、补遗内容"→"二");
      - 其余(docx 中文序号标题/无编号标题)→ 标题全文("一、项目概况"、"第一章 投标邀请")。
    """
    text = text.strip()
    m = _ARABIC_PREFIX.match(text)
    if m:
        return m.group(1)
    if source_kind == "pdf":
        m2 = _CN_ORDINAL_PREFIX.match(text)
        if m2:
            return m2.group(1)
    return text


def strip_heading_number(text: str) -> str:
    """去掉标题的编号前缀, 留标题正文(表格 caption 用): "3.2.2 技术参数表"→"技术参数表"。

    编号后的分隔符按任意空白/标点组合两端剥离("2. Title"/"3.2.1. 标题" 的点+空格
    混合形态)——先空白后标点的两次单向 strip 会留下前导空格。
    """
    text = text.strip()
    m = _ARABIC_PREFIX.match(text)
    if m:
        return _SEP_STRIP.sub("", text[m.end() :]) or text
    m2 = _CN_ORDINAL_PREFIX.match(text)
    if m2:
        return text[m2.end() :].strip() or text
    return text


def is_format_heading(level: int, text: str) -> bool:
    """格式章节标题启发式: 含"投标文件格式"任何级别命中; 章级含"格式"且非评分类弱命中。"""
    if _FORMAT_STRONG in text:
        return True
    if level == 1 and "格式" in text and not any(k in text for k in _FORMAT_WEAK_EXCLUDE):
        return True
    return False


def detect_format_regions(headings: list[tuple[int, str]]) -> list[tuple[int, int]]:
    """检出格式章节子树区间。

    入参: [(level, 标题文本), ...] 按文档序。
    出参: [(起始标题下标, 终止标题下标), ...] —— 终止点 = 下一个同级或更高级标题
    (即该标题不属于子树), 子树 = [start, end); 文档末尾则 end == len(headings)。
    """
    regions: list[tuple[int, int]] = []
    for i, (level, text) in enumerate(headings):
        if not is_format_heading(level, text):
            continue
        end = len(headings)
        for j in range(i + 1, len(headings)):
            if headings[j][0] <= level:
                end = j
                break
        regions.append((i, end))
    return regions


def compare_table_rows(table_id: str, structural_rows: int, extracted_rows: int) -> list[dict]:
    """D5 表行数比对: 结构行数(表格几何/XML 行数)与抽取行数(内容解析行数)不一致 → 异常项。

    防线目的: pdfplumber 等解析器吞表后静默漏检——不一致必须显式浮出, 绝不静默。
    """
    if structural_rows == extracted_rows:
        return []
    return [{"table_id": table_id, "kind": "row_count_mismatch", "structural_rows": structural_rows, "extracted_rows": extracted_rows}]


# =============================================================================
# docx 解析: python-docx 主路径 + zipfile/XML 直读兜底(fire-protection 先例)
# =============================================================================


def _heading_level_from_style_name(style_name: str) -> int:
    """样式名("Heading 1"/"标题 1")→ 级别; 非标题样式 → 0。"""
    m = _HEADING_STYLE_NAME.match(style_name.strip())
    return int(m.group(1)) if m else 0


def _heading_level_from_style_id(style_id: str) -> int:
    """样式 ID("Heading1"/"1")→ 级别; 非标题样式 → 0。兜底路径用。"""
    m = _HEADING_STYLE_ID.match(style_id.strip())
    return int(m.group(1)) if m else 0


def _count_tr(element) -> int:
    """统计表格的直接子级 w:tr 行数(结构行数, D5 比对基准)。

    只数直接子级——与 python-docx len(table.rows) 及兜底路径 findall 严格同口径;
    嵌套表格(投标格式模板常见)的内层行归嵌套表自身, 若递归计入外层, 会在与
    n_rows(同样只数直接子级)的 D5 比对中制造 row_count_mismatch 假阳性。
    """
    return len(element.findall(f"{_W_NS}tr"))


def parse_docx_blocks(path: str | Path) -> list[dict]:
    """python-docx 主路径: 按文档体顺序产出块序列。

    块形态(与兜底路径严格同构, 单测逐块比对):
      {"kind": "heading", "level": int, "text": str}
      {"kind": "para", "text": str}                        # 仅非空正文段
      {"kind": "table", "n_rows": int, "n_cols": int, "xml_rows": int}
    python-docx 不可用时自动降级 zipfile+XML 直读。
    """
    try:
        import docx
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph
    except ImportError:
        return parse_docx_blocks_xml(path)

    document = docx.Document(str(path))
    blocks: list[dict] = []
    for child in document.element.body.iterchildren():
        tag = child.tag
        if tag.endswith("}p"):
            para = Paragraph(child, document)
            text = para.text.strip()
            style_name = para.style.name if para.style is not None else ""
            level = _heading_level_from_style_name(style_name) if text else 0
            if level:
                blocks.append({"kind": "heading", "level": level, "text": text})
            elif text:
                blocks.append({"kind": "para", "text": text})
        elif tag.endswith("}tbl"):
            table = DocxTable(child, document)
            blocks.append({"kind": "table", "n_rows": len(table.rows), "n_cols": len(table.columns), "xml_rows": _count_tr(child)})
    return blocks


def parse_docx_blocks_xml(path: str | Path) -> list[dict]:
    """zipfile+ElementTree 直读兜底: python-docx 失效/不可用时仍可解析 docx 结构。

    与主路径产出同构块序列(见 parse_docx_blocks); 表格行列按 XML 网格统计
    (行=直接子级 w:tr 数, 列=各行 w:tc 数最大值)。
    """
    with zipfile.ZipFile(str(path)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{_W_NS}body")
    if body is None:
        raise IngestError(f"docx 结构异常(无 body): {path}")

    blocks: list[dict] = []
    for child in body:
        if child.tag == f"{_W_NS}p":
            text = "".join(t.text or "" for t in child.iter(f"{_W_NS}t")).strip()
            if not text:
                continue
            style_el = child.find(f"{_W_NS}pPr/{_W_NS}pStyle")
            style_id = style_el.get(f"{_W_NS}val", "") if style_el is not None else ""
            level = _heading_level_from_style_id(style_id)
            if level:
                blocks.append({"kind": "heading", "level": level, "text": text})
            else:
                blocks.append({"kind": "para", "text": text})
        elif child.tag == f"{_W_NS}tbl":
            rows = child.findall(f"{_W_NS}tr")
            n_cols = max((len(r.findall(f"{_W_NS}tc")) for r in rows), default=0)
            blocks.append({"kind": "table", "n_rows": len(rows), "n_cols": n_cols, "xml_rows": len(rows)})
    return blocks


def docx_has_images(path: str | Path) -> bool:
    """docx 是否含图片/绘图对象(无文本层时用于判定扫描件)。

    按元素标签(w:drawing/w:pict)判定而非原始字节子串——默认模板的根元素
    命名空间声明本身就含 "drawingml" 字样, 子串匹配会把零图片文档(含空文档、
    仅表格文档)误判成扫描件错走 OCR 分流。
    """
    try:
        with zipfile.ZipFile(str(path)) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError):
        return False
    return any(e.tag.endswith("}drawing") or e.tag.endswith("}pict") for e in root.iter())


# =============================================================================
# PDF 解析: pdfplumber(行→字号分类标题; find_tables → 行数比对)
# =============================================================================

# 标题字号阈值: 行主字号 ≥ 正文字号 + 1.5pt 视为标题行(招标文件标题通常大 2 档以上)
_HEADING_SIZE_DELTA = 1.5
# 标题行长上限(防长正文句被误判)
_HEADING_MAX_LEN = 80


def parse_pdf_pages(path: str | Path) -> list[dict]:
    """pdfplumber 解析 PDF: 每页产出 {page_no, lines, tables, images}。

    lines: [{text, size, top}] —— size = 行内最大字符字号(标题判据);
    tables: [{structural_rows, extracted_rows, n_cols, top}] —— find_tables 的几何行数
    与 extract() 的内容行数并列保留, 供 D5 行数比对;
    images: 该页是否含图片对象(无文本层时区分"扫描件"与"空文档")。
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise IngestError(f"pdfplumber 不可用, 无法解析 PDF({path}): {exc}") from exc

    pages: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            lines: list[dict] = []
            for ln in page.extract_text_lines():
                text = (ln.get("text") or "").strip()
                if not text:
                    continue
                sizes = [round(c.get("size", 0.0), 1) for c in ln.get("chars", [])]
                lines.append({"text": text, "size": max(sizes) if sizes else 0.0, "top": float(ln.get("top", 0.0))})
            lines.sort(key=lambda x: x["top"])

            tables: list[dict] = []
            for t in page.find_tables():
                try:
                    extracted = [r for r in (t.extract() or []) if r is not None]
                except Exception:
                    extracted = []
                tables.append(
                    {
                        "structural_rows": len(t.rows),
                        "extracted_rows": len(extracted),
                        "n_cols": max((len(r) for r in extracted), default=0),
                        "top": float(t.bbox[1]) if t.bbox else 0.0,
                    }
                )
            tables.sort(key=lambda x: x["top"])
            pages.append({"page_no": page_no, "lines": lines, "tables": tables, "images": bool(page.images)})
    return pages


def _pdf_body_size(lines_flat: list[tuple[int, dict]]) -> float:
    """正文字号 = 按字符数加权的最常见行字号(正文行多且长, 标题行少且短)。"""
    counter: Counter[float] = Counter()
    for _page_no, ln in lines_flat:
        counter[ln["size"]] += max(len(ln["text"]), 1)
    if not counter:
        return 10.0
    return counter.most_common(1)[0][0]


def _pdf_numbering_depth(text: str) -> int:
    """PDF 标题层级 = 阿拉伯编号深度("2."→1, "2.1"→2); 无编号 → 0(调用方回退为 1)。"""
    m = _ARABIC_PREFIX.match(text)
    return m.group(1).count(".") + 1 if m else 0


# =============================================================================
# 切块引擎: 块序列/PDF 页 → chunk + table_info(无 id, id 由 main 统一发放)
# =============================================================================


def _format_index_set(headings: list[tuple[int, str]]) -> set[int]:
    """格式子树覆盖的标题下标集合(骨架模式判定)。"""
    covered: set[int] = set()
    for start, end in detect_format_regions(headings):
        covered.update(range(start, end))
    return covered


def chunk_docx(blocks: list[dict], source_file: str) -> tuple[list[dict], list[dict], list[list[str]], list[dict]]:
    """docx 块序列 → (chunks, table_infos, format_paths, anomalies)。

    - chunk 按文档序产出: 常规章节仅当直接正文段 ≥1 时成块(n_paras=正文段数);
      格式章节子树内每个标题都成骨架块(n_paras=0, 只出章节树)。
    - heading_path = 当前标题栈全文链(镜像消费)。
    - 表格锚点 = 所在章节 section + 表格在章节内的块序(段落序); 首个标题前的
      表格(封面表)锚 section 用合成值 "(文首)" 并记 table_before_any_heading 异常项。
    """
    headings_seq = [(b["level"], b["text"]) for b in blocks if b["kind"] == "heading"]
    in_format = _format_index_set(headings_seq)

    chunks: list[dict] = []
    table_infos: list[dict] = []
    format_paths: list[list[str]] = []
    anomalies: list[dict] = []

    stack: list[tuple[int, str]] = []
    current: dict | None = None
    block_ordinal = 0
    heading_index = -1

    def flush() -> None:
        """收口当前章节: 格式子树出骨架块, 常规章节仅在有正文时出块。"""
        if current is None:
            return
        if current["hidx"] in in_format:
            # 骨架块锚点 para: 有正文取首段块序; 无正文回退 1(=该章节标题段自身位置)
            chunks.append({"anchor": {"section": current["section"], "para": current["para"] or 1}, "heading_path": current["heading_path"], "n_paras": 0})
        elif current["n_paras"] >= 1:
            chunks.append({"anchor": {"section": current["section"], "para": current["para"]}, "heading_path": current["heading_path"], "n_paras": current["n_paras"]})

    for block in blocks:
        kind = block["kind"]
        if kind == "heading":
            flush()
            while stack and stack[-1][0] >= block["level"]:
                stack.pop()
            stack.append((block["level"], block["text"]))
            heading_index += 1
            block_ordinal = 0
            current = {"section": section_id_for_heading(block["text"], "docx"), "para": None, "heading_path": [t for _, t in stack], "n_paras": 0, "hidx": heading_index}
            if is_format_heading(block["level"], block["text"]):
                format_paths.append([t for _, t in stack])
        elif kind == "para":
            block_ordinal += 1
            if current is not None:
                current["n_paras"] += 1
                if current["para"] is None:
                    current["para"] = block_ordinal
        elif kind == "table":
            block_ordinal += 1
            if current is None:
                # 文首表格(如封面表): 锚 section 用合成值保证 T1 契约(section 非空),
                # 同时记异常项交确认门1 显式裁决, 绝不静默丢弃
                anomalies.append({"kind": "table_before_any_heading", "source_file": source_file, "para": block_ordinal})
                section = _PRE_HEADING_SECTION
            else:
                section = current["section"]
            caption = strip_heading_number(stack[-1][1]) if stack else ""
            table_infos.append({"anchor": {"section": section, "para": block_ordinal}, "structural_rows": block["xml_rows"], "extracted_rows": block["n_rows"], "n_cols": block["n_cols"], "caption": caption})
    flush()
    return chunks, table_infos, format_paths, anomalies


def chunk_pdf_pages(pages: list[dict], source_file: str) -> tuple[list[dict], list[dict], list[list[str]], list[dict]]:
    """PDF 页序列 → (chunks, table_infos, format_paths, anomalies)。

    - 行按字号分类: 行主字号 ≥ 正文字号+1.5 且长度 ≤80 → 标题; 层级 = 编号深度(无编号回退 1)。
    - 正文行计入当前章节 chunk 的 n_paras; 首个标题前的游离正文无锚可挂, 丢弃。
    - 表格按 (页, top) 插入阅读序, 锚点 = 所在章节 section + 页码; 首个标题前的
      表格锚 section 用合成值 "(文首)" 并记 table_before_any_heading 异常项(与 docx 路径同构)。
    - 格式章节子树同样只出骨架块(n_paras=0)。
    """
    lines_flat = [(p["page_no"], ln) for p in pages for ln in p["lines"]]
    body_size = _pdf_body_size(lines_flat)

    # 阅读序事件流: 标题/正文行与表格按页内 top 交错, 跨页按页序
    events: list[tuple[int, float, str, object]] = []
    headings_seq: list[tuple[int, str]] = []
    for page in pages:
        page_events: list[tuple[float, str, object]] = []
        for ln in page["lines"]:
            if ln["size"] >= body_size + _HEADING_SIZE_DELTA and len(ln["text"]) <= _HEADING_MAX_LEN:
                page_events.append((ln["top"], "heading", ln["text"]))
            else:
                page_events.append((ln["top"], "body", ln["text"]))
        for t in page["tables"]:
            page_events.append((t["top"], "table", t))
        page_events.sort(key=lambda e: e[0])
        for top, etype, payload in page_events:
            if etype == "heading":
                headings_seq.append((_pdf_numbering_depth(str(payload)) or 1, str(payload)))
            events.append((page["page_no"], top, etype, payload))

    in_format = _format_index_set(headings_seq)

    chunks: list[dict] = []
    table_infos: list[dict] = []
    format_paths: list[list[str]] = []
    anomalies: list[dict] = []

    stack: list[tuple[int, str]] = []
    current: dict | None = None
    heading_index = -1

    def flush() -> None:
        if current is None:
            return
        if current["hidx"] in in_format:
            chunks.append({"anchor": {"page": current["page"], "section": current["section"]}, "heading_path": current["heading_path"], "n_paras": 0})
        elif current["n_paras"] >= 1:
            chunks.append({"anchor": {"page": current["page"], "section": current["section"]}, "heading_path": current["heading_path"], "n_paras": current["n_paras"]})

    for page_no, _top, etype, payload in events:
        if etype == "heading":
            flush()
            text = str(payload)
            level = _pdf_numbering_depth(text) or 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            heading_index += 1
            current = {"page": page_no, "section": section_id_for_heading(text, "pdf"), "heading_path": [t for _, t in stack], "n_paras": 0, "hidx": heading_index}
            if is_format_heading(level, text):
                format_paths.append([t for _, t in stack])
        elif etype == "body":
            if current is not None:
                current["n_paras"] += 1
        else:  # table
            table = payload
            if current is None:
                # 文首表格与 docx 路径同构: 合成 section 保锚点契约 + 异常项浮出
                anomalies.append({"kind": "table_before_any_heading", "source_file": source_file, "page": page_no})
                section = _PRE_HEADING_SECTION
            else:
                section = current["section"]
            caption = strip_heading_number(stack[-1][1]) if stack else ""
            table_infos.append({"anchor": {"page": page_no, "section": section}, "structural_rows": table["structural_rows"], "extracted_rows": table["extracted_rows"], "n_cols": table["n_cols"], "caption": caption})
    flush()
    return chunks, table_infos, format_paths, anomalies


# =============================================================================
# sections.json 装载/合并/原子写盘(D7)
# =============================================================================


def load_sections(path: str | Path) -> dict:
    """装载既有 sections.json; 不存在 → 空骨架; 损坏 → 显式报错(绝不静默覆盖状态)。

    校验含值类型: chunks/tables 必须为对象数组——键存在但值类型错(如字符串数组)
    同样拒绝, 否则下游 t.get(...) 会以未捕获 AttributeError 裸崩。
    """
    path = Path(path)
    if not path.is_file():
        return {"chunks": [], "tables": []}
    try:
        # utf-8-sig: 容忍编辑器写入的 UTF-8 BOM(终审 M-BOM 修复, 对齐 extract 全部
        # 装载器与 score_simulate 回传稿读取的既定 BOM 口径; 自产文件无 BOM 不受影响)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IngestError(f"既有 sections.json 不可解析, 拒绝覆盖(先人工核查): {path}: {exc}") from exc
    if not isinstance(data, dict) or "chunks" not in data or "tables" not in data:
        raise IngestError(f"既有 sections.json 结构异常(缺 chunks/tables 键), 拒绝覆盖: {path}")
    for key in ("chunks", "tables"):
        if not isinstance(data[key], list) or not all(isinstance(entry, dict) for entry in data[key]):
            raise IngestError(f"既有 sections.json 结构异常({key} 应为对象数组), 拒绝覆盖: {path}")
    return data


def atomic_write_json(path: str | Path, data: dict) -> None:
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
        # 成功路径 os.replace 后 tmp 已不存在; 异常路径清理残留, 不留半截文件
        if tmp.exists():
            tmp.unlink()


def _next_seq(prefix: str, entries: list[dict], key: str) -> int:
    """续号: 取既有 id 最大序号 +1(重跑/补遗增量接续, 保证全局唯一)。"""
    pattern = _ID_RE_CACHE.get(prefix)
    if pattern is None:
        pattern = re.compile(rf"^{prefix}-(\d+)$")
        _ID_RE_CACHE[prefix] = pattern
    max_no = 0
    for entry in entries:
        m = pattern.match(str(entry.get(key, "")))
        if m:
            max_no = max(max_no, int(m.group(1)))
    return max_no + 1


# 同名重跑比对用契约字段(R2): 指纹只看 T1 锁定的落盘字段, id 是被比对对象本身故排除
_CHUNK_ENTRY_FIELDS = ("source_file", "anchor", "heading_path", "n_paras")
_TABLE_ENTRY_FIELDS = ("source_file", "anchor", "n_rows", "n_cols", "caption")


def _blocks_fingerprint(chunk_entries: list[dict], table_entries: list[dict]) -> str:
    """文件级内容指纹(R2): 对该文件解析产物的落盘形态(chunks+tables, 剥离 id)规范化 JSON 取 sha256。

    - sort_keys/紧凑分隔符规范化: 键序与空白无关, 内容等价即同指纹(与 merge_addenda
      台账 content_hash 同一口径);
    - 只投影契约字段: 存储条目混入的契约外脏字段不误判为内容有变;
    - 缺字段按 None 参与(.get): 手工截断的旧条目自然指纹偏离 → 走替换路径重写干净。
    """
    payload = {
        "chunks": [{k: c.get(k) for k in _CHUNK_ENTRY_FIELDS} for c in chunk_entries],
        "tables": [{k: t.get(k) for k in _TABLE_ENTRY_FIELDS} for t in table_entries],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# =============================================================================
# CLI 入口
# =============================================================================


def _check_docx_text_layer(path: Path, blocks: list[dict]) -> None:
    """docx 文本层检查: 无任何文本时三分流——
    含图片=扫描件走 OCR(退出码 2); 仅表格=受理(表格是有效结构内容);
    全空=空文档(一般文件错误, 退出码 1)——空文档不是扫描件, OCR 无济于事。"""
    has_text = any(b["kind"] in ("heading", "para") for b in blocks)
    if has_text:
        return
    if docx_has_images(path):
        raise NeedOcrError(f"{path.name}: docx 无文本层(疑似扫描件)——请先转 PDF 并走 eai-flow-ocr 全文 OCR 路径, 再对 OCR 产物重新 ingest(设计阶段0 分流)")
    if any(b["kind"] == "table" and b["n_rows"] >= 1 for b in blocks):
        return
    raise IngestError(f"{path.name}: 空文档(无文本/表格/图片)——无可解析内容, 请核查输入文件是否正确")


def _check_pdf_text_layer(path: Path, pages: list[dict]) -> None:
    """PDF 文本层检查: 全部页面零文本行时三分流(与 docx 路径同构)——
    含图片=扫描件走 OCR(退出码 2); 仅表格=受理; 全空=空文档(退出码 1)。"""
    if any(p["lines"] for p in pages):
        return
    if any(p.get("images") for p in pages):
        raise NeedOcrError(f"{path.name}: PDF 无文本层(疑似扫描件)——请走 eai-flow-ocr 全文 OCR 路径, 再对 OCR 产物重新 ingest(设计阶段0 分流)")
    if any(p.get("tables") for p in pages):
        return
    raise IngestError(f"{path.name}: 空文档(PDF 无文本/表格/图片)——无可解析内容, 请核查输入文件是否正确")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="ingest.py",
        description="投标方案编写·阶段1 纯结构化解析: 招标文件(docx/pdf)→ sections.json(章节切块+锚点+表行数, 无 LLM)",
        epilog="示例: python ingest.py --input uploads/招标文件.docx --code ZB --out state ; 补遗: python ingest.py --input uploads/补遗01.pdf --code BY --out state --addendum",
    )
    parser.add_argument("--input", nargs="+", required=True, help="基础招标文件路径(可多份: 招标文件/技术规范书/评分办法分卷; .docx/.pdf)")
    parser.add_argument("--code", required=True, help="文件代号(2-4 位大写字母, 如 ZB/JS/PB; clause_id 复合前缀按此分配)")
    parser.add_argument("--out", required=True, help="产物目录(写 <out>/sections.json; 既有文件增量合并; 同名重跑未变=保号跳过, 有变=替换旧块并在摘要给出 replaced 信号)")
    parser.add_argument("--addendum", action="store_true", help="本次输入为补遗/答疑文件(增量输入, 隐藏废标项主藏身处)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 EXIT_NEED_OCR 撞号——编排方按
        # rc==2 分流会把 CLI 误用误路由进 OCR 路径, 故统一改道 EXIT_ERROR;
        # --help/--version 的正常退出(code 0)原样放行。
        if not exc.code:
            return EXIT_OK
        print(f"[ingest] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        if not _CODE_RE.match(args.code):
            raise IngestError(f"--code 非法: {args.code!r}(必须 2-4 位大写字母, 如 ZB/JS/PB)")
        files = [Path(p) for p in args.input]
        for f in files:
            if not f.is_file():
                raise IngestError(f"输入文件不存在或不是普通文件: {f}")
        # 同批同名(basename)去重: sections.json 以文件名为同名替换键, 同名不同目录
        # 的两份输入会混入同一 source_file 身份且重跑时互相顶替——静默丢数据, 显式拒绝
        names = [f.name for f in files]
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise IngestError(f"同批输入文件名重复: {duplicated}——sections.json 以文件名为替换键, 同名不同目录会互相覆盖丢数据; 请先重命名区分")

        # 第一遍: 解析全部输入(任一无文本层 → OCR 分流退出, 整体不落盘)
        parsed: list[dict] = []
        for f in files:
            suffix = f.suffix.lower()
            if suffix == ".docx":
                try:
                    blocks = parse_docx_blocks(f)
                except IngestBaseError:
                    raise
                except Exception as exc:
                    raise IngestError(f"docx 解析失败 {f}: {exc}") from exc
                _check_docx_text_layer(f, blocks)
                chunks, table_infos, format_paths, anomalies = chunk_docx(blocks, f.name)
            elif suffix == ".pdf":
                try:
                    pages = parse_pdf_pages(f)
                except IngestBaseError:
                    raise
                except Exception as exc:
                    raise IngestError(f"PDF 解析失败 {f}: {exc}") from exc
                _check_pdf_text_layer(f, pages)
                chunks, table_infos, format_paths, anomalies = chunk_pdf_pages(pages, f.name)
            else:
                raise IngestError(f"不支持的输入类型 {f.name}(仅 .docx/.pdf; 扫描件请先走 eai-flow-ocr)")
            parsed.append({"file": f, "chunks": chunks, "table_infos": table_infos, "format_paths": format_paths, "anomalies": anomalies})

        # 第二遍: 合并既有 sections.json, 统一发放 chunk_id/table_id。
        # R2 修复(同名重跑分流): 此前同名重跑一律删旧块后按当前最大序号重发新号
        # (CH-001..005 → CH-009..013), 未修改文件重跑也静默孤儿化候选裁决台账且
        # 摘要零信号(rc=0, anomalies=[]), D5 异常滞后到 extract 层才浮出。现按
        # "解析产物落盘形态(剥 id)规范化哈希"逐文件分流:
        #   指纹未变 → 保号 no-op(sections.json 字节不变, 摘要计 skipped_unchanged);
        #   指纹有变 → 保留删旧块发新号语义, 摘要显式给出 replaced 计数与被替换
        #   旧 id 清单(编排方据此判"候选裁决已失效, 需重跑阶段2 提取")。
        out_path = Path(args.out) / "sections.json"
        # 读盘前校验既有 sections.json 签名(回放实证 bfa917ce: write_file 直写/rm 后
        # 下游只报"缺键/结构异常"等远处症状, agent 靠试错烧掉整轮上下文)
        guard_problems = state_guard.verify_state_files(args.out)
        if guard_problems:
            raise IngestError("既有 sections.json 签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(guard_problems))
        sections = load_sections(out_path)

        rerun: dict[str, dict] = {}
        for item in parsed:
            name = item["file"].name
            old_chunks = [c for c in sections["chunks"] if c.get("source_file") == name]
            old_tables = [t for t in sections["tables"] if t.get("source_file") == name]
            # 本次解析产物的落盘形态(无 id)——tables 的 n_rows 取抽取行数(与正式发放同投影)
            new_chunks = [{"source_file": name, "anchor": c["anchor"], "heading_path": c["heading_path"], "n_paras": c["n_paras"]} for c in item["chunks"]]
            new_tables = [{"source_file": name, "anchor": t["anchor"], "n_rows": t["extracted_rows"], "n_cols": t["n_cols"], "caption": t["caption"]} for t in item["table_infos"]]
            if old_chunks or old_tables:
                status = "kept" if _blocks_fingerprint(old_chunks, old_tables) == _blocks_fingerprint(new_chunks, new_tables) else "replaced"
            else:
                status = "new"
            rerun[name] = {"status": status, "old_chunks": old_chunks, "old_tables": old_tables, "new_chunks": new_chunks, "new_tables": new_tables}

        # 续号基准取"装载态全体条目"(含将被摘除的旧块), 再摘除非保号文件的旧块:
        # 被替换文件的旧号不得在同一状态里复用——单文件重跑时摘除后序号回零, 新块会
        # 顶替旧号(如 CH-001→CH-001), 旧候选裁决静默错挂到新内容上, replaced 信号
        # 形同虚设; 以装载态最大号续发保证被替换 id 永不复用(kept 文件保号不受影响)。
        next_chunk = _next_seq("CH", sections["chunks"], "chunk_id")
        next_table = _next_seq("T", sections["tables"], "table_id")
        drop_names = {name for name, r in rerun.items() if r["status"] != "kept"}
        sections["chunks"] = [c for c in sections["chunks"] if c.get("source_file") not in drop_names]
        sections["tables"] = [t for t in sections["tables"] if t.get("source_file") not in drop_names]

        all_anomalies: list[dict] = []
        file_reports: list[dict] = []
        replaced_reports: list[dict] = []
        for item in parsed:
            f: Path = item["file"]
            r = rerun[f.name]
            if r["status"] == "kept":
                # 保号 no-op: 沿用旧块不重发号; D5 异常项按仍存续的旧 table_id 现算重放(派生字段不落盘)
                for old_t, info in zip(r["old_tables"], item["table_infos"]):
                    all_anomalies.extend(compare_table_rows(old_t["table_id"], info["structural_rows"], info["extracted_rows"]))
                for anomaly in item["anomalies"]:
                    anomaly["file"] = f.name
                    all_anomalies.append(anomaly)
                file_reports.append({"file": f.name, "path": str(f), "code": args.code, "addendum": args.addendum, "status": "kept", "chunks": len(r["old_chunks"]), "tables": len(r["old_tables"])})
                continue
            if r["status"] == "replaced":
                note = "同名文件内容有变, 旧 id 已被替换——其候选裁决已失效, 需重跑阶段2 提取对新 id 重新裁决"
                replaced_reports.append({"file": f.name, "old_chunk_ids": [c["chunk_id"] for c in r["old_chunks"]], "old_table_ids": [t["table_id"] for t in r["old_tables"]], "note": note})
            for entry in r["new_chunks"]:
                sections["chunks"].append({"chunk_id": f"CH-{next_chunk:03d}", **entry})
                next_chunk += 1
            for entry, info in zip(r["new_tables"], item["table_infos"]):
                table_id = f"T-{next_table:03d}"
                sections["tables"].append({"table_id": table_id, **entry})
                all_anomalies.extend(compare_table_rows(table_id, info["structural_rows"], info["extracted_rows"]))
                next_table += 1
            for anomaly in item["anomalies"]:
                anomaly["file"] = f.name
                all_anomalies.append(anomaly)
            file_reports.append({"file": f.name, "path": str(f), "code": args.code, "addendum": args.addendum, "status": r["status"], "chunks": len(item["chunks"]), "tables": len(item["table_infos"])})

        # 块级无变更(全部保号且无实际摘除/追加)→ 不写盘: sections.json 字节不变(idempotent
        # rerun); 产物文件尚不存在时仍写空骨架, 保持"运行即落盘"的既有行为
        sections_changed = any((r["old_chunks"] or r["old_tables"]) or (r["new_chunks"] or r["new_tables"]) for r in rerun.values() if r["status"] != "kept")
        if sections_changed or not out_path.is_file():
            atomic_write_json(out_path, sections)
        # 权威状态文件落盘后登记防篡改签名(kept 保号重跑不写盘时旧签名仍匹配, 无需重登)
        state_guard.sign_state_files(args.out, ["sections.json"])

        summary = {
            "written": str(out_path),
            "code": args.code,
            "addendum": args.addendum,
            "skipped_unchanged": sum(1 for r in rerun.values() if r["status"] == "kept"),
            "replaced": len(replaced_reports),
            "replaced_files": replaced_reports,
            "files": file_reports,
            "format_sections": [p for item in parsed for p in item["format_paths"]],
            "anomalies": all_anomalies,
        }
        print(json.dumps(summary, ensure_ascii=False))
        return EXIT_ANOMALY if all_anomalies else EXIT_OK
    except NeedOcrError as exc:
        print(f"[ingest] 需走 OCR 路径: {exc}", file=sys.stderr)
        return EXIT_NEED_OCR
    except IngestError as exc:
        print(f"[ingest] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        # 写盘/读盘 I/O 失败统一转退出码 1(残留审查 Important 修复): --out 指向普通
        # 文件 → mkdir FileExistsError; 目标 sections.json 被其他程序占用(Windows) →
        # os.replace PermissionError。此前以裸 traceback 逃出 main(), 编排方拿到裸栈
        # 而非干净的 [ingest] 错误行——main 统一转退出码是模块自己的契约。
        print(f"[ingest] 错误: 文件读写失败({exc.__class__.__name__}): {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
