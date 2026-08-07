# 封面元素编辑器重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把封面配置从「OOXML 母版透传」重构为「结构化多页元素编辑器」——封面 = 目录前多页元素（文本/表格/图片/间距），导入样例自动提取为可编辑元素，偏差手工改，旧 cover_master 自动迁移。

**Architecture:** 新数据模型 `cover_elements`（`pages[] → elements[]`）存 JSON；导入样例按分节符切页、逐块转元素并启发式绑定变量；生成端从元素构建 docx（段落/表格/图片/分页）；编辑器页签+元素列表+变量绑定下拉。旧 `cover_master` 保留作兜底渲染 + 首次编辑自动转元素。

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 / python-docx / lxml；React 19 / TypeScript / Tailwind；pytest（后端）/ vitest（前端）。

**Spec:** `docs/superpowers/specs/2026-08-07-cover-elements-editor-design.md`
**金标准样例:** `基地项目-消防设计专篇.docx`（1 页，标题横幅+会签表）、`2横城矿区总体规划（修编）环评——报告书报批版2021.1.docx`（3 页：封面/批准页/名单表）。样例复制到 `C:/Temp/eai-cover1-消防.docx`、`C:/Temp/eai-cover2-环评.docx` 供测试。

**Note:** 本文档各任务的运行命令均从 `backend/`（uv run pytest）或 `frontend/`（npx vitest / npx tsc --noEmit / npx eslint）目录执行。

---

## 文件结构

**后端（新增/修改）**
- `backend/app/extensions/output/schemas.py` — 新增 CoverImage/CoverElement/CoverPage/CoverSchema；LayoutTemplate 三 schema 加 `cover_elements`
- `backend/app/extensions/output/layout_import.py` — 新增 `_extract_cover_pages`、`_cover_master_to_elements`、样式/绑定 helpers
- `backend/app/extensions/output/generator.py` — 新增 `_render_cover_elements`；`generate_docx` 封面优先级接线
- `backend/app/extensions/output/service.py` — cover_elements 持久化（create/update/duplicate）
- `backend/app/extensions/output/routers.py` — `_build_template_data` 含 cover_elements
- `backend/tests/test_cover_elements.py`（新）— 提取/生成/往返/迁移/表格金标准测试
- `backend/tests/test_output_routers.py` — cover_elements 数据组装测试

**前端（新增/修改）**
- `frontend/src/extensions/output/types.ts` — Cover/CoverPage/CoverElement；LayoutTemplate.coverElements
- `frontend/src/extensions/output/cover-state.ts` — 元素模型 helpers（patch/binding/有效 slot）
- `frontend/src/extensions/output/transforms.ts` — cover_elements → coverElements
- `frontend/src/extensions/output/api.ts` — create/update 载荷含 cover_elements
- `frontend/src/extensions/output/components/CoverElementsEditor.tsx`（新）— 页签+元素列表+表格编辑器+绑定下拉+添加元素
- `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` — 封面 section 接入 CoverElementsEditor
- `frontend/tests/unit/extensions/output/cover-elements.test.ts`（新）— 纯 helpers

---

### Task 1: 后端数据模型（schemas.py）

**Files:**
- Modify: `backend/app/extensions/output/schemas.py`

- [ ] **Step 1: 写 schema 测试**

Create `backend/tests/test_cover_elements.py`:

```python
"""Tests for the structured cover element model (replaces cover_master passthrough)."""
import pytest
from pydantic import ValidationError

from app.extensions.output.schemas import (
    CoverElementSchema,
    CoverSchema,
    LayoutTemplateCreate,
)


def test_cover_schema_roundtrip():
    cover = CoverSchema(
        sourceFile="x.docx",
        pages=[
            {
                "elements": [
                    {"id": "e1", "type": "text", "text": "项目名", "alignment": "center", "fontSize": 22, "bold": True},
                    {"id": "e2", "type": "table", "rows": 2, "cols": 2, "cells": [["专业名称", "编制"], ["总图", ""]]},
                ]
            }
        ],
    )
    d = cover.model_dump()
    assert d["mode"] == "elements"
    assert d["pages"][0]["elements"][0]["text"] == "项目名"
    assert d["pages"][0]["elements"][1]["cells"][0][0] == "专业名称"


def test_cover_element_type_validated():
    with pytest.raises(ValidationError):
        CoverElementSchema(id="x", type="canvas", text="t")


def test_layout_template_create_accepts_cover_elements():
    tpl = LayoutTemplateCreate(
        name="T",
        report_type="g",
        page_settings={"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        body_styles={"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 0, "firstLineIndent": 2},
        heading_styles=[],
        cover_elements={"sourceFile": "x.docx", "pages": [{"elements": [{"id": "e1", "type": "text", "text": "报告标题"}]}]},
    )
    assert tpl.cover_elements.pages[0].elements[0].text == "报告标题"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_cover_elements.py -q`
Expected: FAIL — `ImportError: cannot import name 'CoverSchema'`

- [ ] **Step 3: 实现 schemas**

在 `schemas.py` 的 `CoverTemplateSchema` 之后新增：

```python
class CoverImageSchema(BaseModel):
    b64: str
    ext: str = "png"


class CoverElementSchema(BaseModel):
    id: str
    type: Literal["text", "table", "image", "spacer", "divider"] = "text"
    # text
    text: str = ""
    fontFamily: str = "宋体"
    fontSize: int = 12
    bold: bool = False
    color: str = "#000000"
    alignment: Literal["left", "center", "right"] = "center"
    spaceBefore: int = 0
    spaceAfter: int = 0
    slotId: str | None = None   # 变量绑定: title/client/project_number/date/project_name/stage/design_unit
    # table
    rows: int = 0
    cols: int = 0
    cells: list[list[str]] = Field(default_factory=list)
    headerBg: str | None = None
    borderColor: str = "#000000"
    # image
    image: CoverImageSchema | None = None
    widthCm: float | None = None
    # spacer
    lines: int = 1


class CoverPageSchema(BaseModel):
    elements: list[CoverElementSchema] = Field(default_factory=list)


class CoverSchema(BaseModel):
    mode: Literal["elements"] = "elements"
    pages: list[CoverPageSchema] = Field(default_factory=list)
    sourceFile: str = ""
```

在 `LayoutTemplateCreate`/`LayoutTemplateUpdate`/`LayoutTemplateResponse` 各加一行 `cover_elements: CoverSchema | None = None`（Response 用 `dict | None`，与其他嵌套 schema 一致）。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cover_elements.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/schemas.py backend/tests/test_cover_elements.py
git commit -m "feat(output): cover_elements 结构化封面数据模型 schema"
```

---

### Task 2: 提取 `_extract_cover_pages`（layout_import.py）

**Files:**
- Modify: `backend/app/extensions/output/layout_import.py`
- Test: `backend/tests/test_cover_elements.py`

- [ ] **Step 1: 写提取金标准测试**

追加到 `test_cover_elements.py`：

```python
from pathlib import Path
from docx import Document
from app.extensions.output.layout_import import _extract_cover_pages

SAMPLE1 = Path("C:/Temp/eai-cover1-消防.docx")   # 基地项目-消防设计专篇
SAMPLE2 = Path("C:/Temp/eai-cover2-环评.docx")   # 横城矿区环评报告


def _cover_of(path):
    return _extract_cover_pages(Document(str(path)))


def test_fire_sample_single_page_with_table_elements():
    """消防设计专篇: 1 页, 含文本元素(标题横幅/项目编号) + 会签表元素."""
    pages = _cover_of(SAMPLE1)
    assert len(pages) == 1, f"消防样例应为 1 页, got {len(pages)}"
    els = pages[0].elements
    texts = [e.text for e in els if e.type == "text"]
    assert any("第三册 消防设计专篇" in t for t in texts), "报告名称文本元素缺失"
    assert any(t.strip() == "项目名" for t in texts), "独立项目名占位元素缺失"
    tables = [e for e in els if e.type == "table"]
    assert tables, "会签表应为表格元素"
    assert tables[0].rows >= 10, f"会签表 rows 应 >=10, got {tables[0].rows}"
    # 绑定启发式: 冒号字段项目编号 → project_number; 日期 → date
    bound = {e.slotId: e for e in els if e.slotId}
    assert bound.get("project_number"), "项目编号:XX 应绑 project_number"
    assert bound.get("date"), "20XX年0X月 应绑 date"


def test_huanping_sample_three_pages():
    """环评报告: 3 页 (封面/批准页/名单页), 含名单表格."""
    pages = _cover_of(SAMPLE2)
    assert len(pages) == 3, f"环评样例应为 3 页, got {len(pages)}"
    # 页1 封面标题
    p1_texts = [e.text for e in pages[0].elements if e.type == "text"]
    assert any("环境影响报告书" in t for t in p1_texts)
    # 页2 批准页: 工程编号 → project_number 绑定
    p2_texts = " ".join(e.text for e in pages[1].elements)
    assert "工程" in p2_texts and "H7367Z" in p2_texts
    # 页3 名单表
    p3_tables = [e for e in pages[2].elements if e.type == "table"]
    assert len(p3_tables) == 2, f"名单页应 2 张表, got {len(p3_tables)}"
    assert p3_tables[1].rows >= 16
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cover_elements.py::test_fire_sample_single_page_with_table_elements -q`
Expected: FAIL — `ImportError: cannot import name '_extract_cover_pages'`

- [ ] **Step 3: 实现提取**

在 `layout_import.py` 新增（模块顶部已有 `_W`/`_DRAWML`/`_REL` 命名空间常量与 `_para_text`）：

```python
# 冒号字段标签 → 变量 id 映射（宽松匹配标签字符，容忍 档 案 号 空格）
_COVER_COLON_SLOT_MAP = [
    (("项目编号", "工程编号"), "project_number"),
    (("档 案 号", "档案号"), "archive_no"),
    (("版    次", "版次", "版"), "version"),
    (("证书号", "资质证书号"), "certificate_no"),
    (("建设单位", "业主单位"), "client"),
    (("设计阶段", "阶段"), "stage"),
    (("日期", "报告日期"), "date"),
]
_DATE_RE = re.compile(r"20\d{2}年\d{1,2}月|20XX年0X月|\d{4}[-/年]\d{1,2}[-/月]\d{0,2}日?")
_TITLE_RE = re.compile(r"第[\d一二三四五六七八九十百两]+\s*[一-龥A-Za-z0-9 ]{0,20}?(?:专篇|报告书|计算书|设计说明)|[一-龥A-Za-z0-9 ]{2,24}?(?:专篇|报告书|计算书|设计说明)")


def _para_style(p_el) -> dict:
    """Best-effort paragraph style: alignment + first run font props (pt)."""
    jc = p_el.find(f"{{{_W}}}pPr/{{{_W}}}jc")
    alignment = {"left": "left", "center": "center", "right": "right"}.get(jc.get(f"{{{_W}}}val") if jc is not None else None, "left")
    fontFamily, fontSize, bold, color = "宋体", 12, False, "#000000"
    r = p_el.find(f"{{{_W}}}r")
    if r is not None:
        rPr = r.find(f"{{{_W}}}rPr")
        if rPr is not None:
            rf = rPr.find(f"{{{_W}}}rFonts")
            if rf is not None:
                fontFamily = rf.get(f"{{{_W}}}eastAsia") or rf.get(f"{{{_W}}}ascii") or "宋体"
            sz = rPr.find(f"{{{_W}}}sz")
            if sz is not None:
                try:
                    fontSize = int(sz.get(f"{{{_W}}}val", "24")) // 2
                except ValueError:
                    fontSize = 12
            bold = rPr.find(f"{{{_W}}}b") is not None
            c = rPr.find(f"{{{_W}}}color")
            if c is not None:
                color = "#" + (c.get(f"{{{_W}}}val") or "000000")
    return {"fontFamily": fontFamily, "fontSize": fontSize, "bold": bold, "color": color, "alignment": alignment}


def _slot_from_colon(text: str) -> str | None:
    """'项目编号：XX' → project_number; 匹配任一标签 → 对应 slot id."""
    for labels, sid in _COVER_COLON_SLOT_MAP:
        for lab in labels:
            if re.search(r"\s*".join(lab) + r"\s*[：:]", text):
                return sid
    return None


def _block_to_element(el) -> dict:
    """Convert a body block (<w:p>|<w:tbl>) to a CoverElementSchema dict."""
    if el.tag == f"{{{_W}}}tbl":
        rows_el = el.findall(f"{{{_W}}}tr")
        cells: list[list[str]] = []
        for tr in rows_el:
            row = [" ".join(_para_text(p).strip() for p in tc.iter(f"{{{_W}}}p") if _para_text(p).strip())
                   for tc in tr.iter(f"{{{_W}}}tc")]
            cells.append(row)
        return {
            "id": f"tbl{len(cells)}x{len(cells[0]) if cells else 0}",
            "type": "table",
            "rows": len(cells),
            "cols": len(cells[0]) if cells else 0,
            "cells": cells,
            "borderColor": "#000000",
        }
    text = _para_text(el).strip()
    if not text:
        return {"id": "sp", "type": "spacer", "lines": 1}
    style = _para_style(el)
    el_dict = {"id": f"p{abs(hash(text)) % 10000}", "type": "text", "text": text, **style}
    # 绑定启发式
    sid = _slot_from_colon(text)
    if sid:
        el_dict["slotId"] = sid
    elif text.strip() in ("项目名", "项目名称"):
        el_dict["slotId"] = "project_name"
    elif _TITLE_RE.search(text) and el_dict.get("fontSize", 12) >= 16:
        el_dict["slotId"] = "title"
    elif _DATE_RE.search(text):
        el_dict["slotId"] = "date"
    return el_dict


def _extract_cover_pages(doc) -> list:
    """封面区(目录/首个Heading前) → 按分节符/分页符切页 → 每页元素列表."""
    body = doc.element.body
    pages: list[dict] = [{"elements": []}]
    heading_ids, toc_ids = _style_id_sets(doc)
    for child in body:
        tag = child.tag
        if tag == f"{{{_W}}}sectPr":
            break
        if tag == f"{{{_W}}}p":
            style_el = child.find(f"{{{_W}}}pPr/{{{_W}}}pStyle")
            style_val = style_el.get(f"{{{_W}}}val") if style_el is not None else None
            text = _para_text(child).strip()
            if _TOC_TEXT_RE.match(text) or style_val in toc_ids or style_val in heading_ids:
                break
            if child.find(f"{{{_W}}}pPr/{{{_W}}}sectPr") is not None:
                pages.append({"elements": []})   # 分节符 → 新页
            if any(br.get(f"{{{_W}}}type") == "page" for br in child.iter(f"{{{_W}}}br")):
                pages.append({"elements": []})   # 显式分页符 → 新页
            pages[-1]["elements"].append(_block_to_element(child))
        elif tag == f"{{{_W}}}tbl":
            pages[-1]["elements"].append(_block_to_element(child))
    # 丢弃全空页（仅空行）
    return [{"elements": [e for e in p["elements"] if not (e["type"] == "spacer" and e.get("lines", 1) <= 0)]} for p in pages if p["elements"]]
```

（注意 `_style_id_sets`、`_TOC_TEXT_RE` 已在 `layout_import.py` 中存在，直接复用。）

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cover_elements.py -q`
Expected: PASS（Task1 3 个 + 本任务 2 个 = 5 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/layout_import.py backend/tests/test_cover_elements.py
git commit -m "feat(output): cover_elements 提取 — 分节符切页 + 块转元素 + 变量绑定启发式"
```

---

### Task 3: 生成 `_render_cover_elements`（generator.py）

**Files:**
- Modify: `backend/app/extensions/output/generator.py`
- Test: `backend/tests/test_cover_elements.py`

- [ ] **Step 1: 写生成测试**

追加到 `test_cover_elements.py`：

```python
import tempfile
from app.extensions.output.generator import generate_docx, _render_cover_elements

def _sample_cover():
    return {
        "mode": "elements",
        "sourceFile": "x.docx",
        "pages": [
            {"elements": [
                {"id": "e1", "type": "text", "text": "项目名", "fontSize": 22, "bold": True, "alignment": "center", "slotId": "project_name"},
                {"id": "e2", "type": "text", "text": "项目编号：XX", "fontSize": 14, "alignment": "center", "slotId": "project_number"},
                {"id": "e3", "type": "text", "text": "环境影响报告书", "fontSize": 22, "alignment": "center"},
                {"id": "e4", "type": "table", "rows": 2, "cols": 2, "cells": [["专业名称", "编制"], ["总图", ""]], "headerBg": "#D9D9D9"},
                {"id": "e5", "type": "spacer", "lines": 2},
            ]},
            {"elements": [
                {"id": "e6", "type": "text", "text": "审定、审查人员名单", "fontSize": 16, "alignment": "center"},
            ]},
        ],
    }


def test_render_cover_elements_slot_replacement_and_pages():
    resolved = {"project_name": "基地项目", "project_number": "P001"}
    doc = Document()
    _render_cover_elements(doc, _sample_cover(), resolved, {})
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert "基地项目" in texts, "项目名绑定应替换为 基地项目"
    assert any("项目编号：P001" in t for t in texts), "冒号字段应保留标签替换值"
    assert any("环境影响报告书" in t for t in texts), "未绑定元素保留原文"
    assert len(doc.tables) == 1, "表格元素应生成 1 张 docx 表"
    assert doc.tables[0].rows[0].cells[0].text.strip() == "专业名称"
    assert len(doc.sections) >= 2, "多页元素应产生分节"


def test_generate_docx_uses_cover_elements_priority():
    tpl = {
        "page_settings": {"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        "body_styles": {"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 0, "firstLineIndent": 2},
        "heading_styles": [],
        "cover_elements": _sample_cover(),
        "cover_master": {"mode": "master", "xml": "<w:p/>", "images": [], "slots": [], "sourceFile": "old", "boundary": "before_toc"},
        "cover_template": None,
        "toc_settings": None,
    }
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.docx"
        generate_docx("# 正文\n", tpl, out, cover_fields={"project_name": "基地项目", "project_number": "P001"})
        doc = Document(str(out))
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        assert "基地项目" in texts, "cover_elements 应优先于 cover_master 渲染"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cover_elements.py::test_render_cover_elements_slot_replacement_and_pages -q`
Expected: FAIL — `ImportError: cannot import name '_render_cover_elements'`

- [ ] **Step 3: 实现生成**

在 `generator.py` 新增 `_render_cover_elements`（放 `_render_cover_master` 之后）：

```python
def _replace_slot_value(text: str, value: str) -> str:
    """绑定文本替换：含冒号保留标签只换值；否则整体替换。"""
    if "：" in text or ":" in text:
        idx = max(text.rfind("："), text.rfind(":"))
        return text[: idx + 1] + value
    return value


def _render_cover_elements(doc, cover: dict, resolved: dict, frontmatter: dict) -> None:
    """从结构化元素构建封面：逐页段落/表格/图片，页间分节；绑定元素用解析值替换."""
    if not cover or cover.get("mode") != "elements":
        return
    slot_value = {
        "title": resolved.get("title"),
        "client": resolved.get("client"),
        "project_number": resolved.get("project_number"),
        "date": resolved.get("date"),
        "project_name": frontmatter.get("project_name") or resolved.get("project_name"),
        "stage": frontmatter.get("stage"),
        "design_unit": frontmatter.get("design_unit"),
    }
    pages = cover.get("pages", [])
    for pi, page in enumerate(pages):
        for el in page.get("elements", []):
            try:
                _render_cover_element(doc, el, slot_value)
            except Exception as exc:
                logger.warning("cover element render failed, skipping: %s", exc)
        if pi < len(pages) - 1:
            doc.add_section(WD_SECTION.NEW_PAGE)


def _render_cover_element(doc, el: dict, slot_value: dict) -> None:
    etype = el.get("type")
    if etype == "text":
        text = el.get("text", "")
        sid = el.get("slotId")
        repl = slot_value.get(sid) if sid else None
        if repl:
            text = _replace_slot_value(text, str(repl))
        p = doc.add_paragraph()
        p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT}.get(el.get("alignment"), WD_ALIGN_PARAGRAPH.CENTER)
        pf = p.paragraph_format
        pf.space_before = Pt(el.get("spaceBefore", 0))
        pf.space_after = Pt(el.get("spaceAfter", 0))
        run = p.add_run(text)
        _set_run_font(run, _resolve_font(el.get("fontFamily", "宋体")))
        run.font.size = Pt(int(el.get("fontSize", 12)))
        run.bold = bool(el.get("bold", False))
        try:
            run.font.color.rgb = RGBColor.from_string(el.get("color", "#000000").lstrip("#"))
        except ValueError:
            pass
    elif etype == "table":
        rows, cols = int(el.get("rows", 0)), int(el.get("cols", 0))
        cells = el.get("cells", [])
        if rows <= 0 or cols <= 0:
            return
        tbl = doc.add_table(rows=rows, cols=cols)
        tbl.style = "Table Grid"
        for ri in range(rows):
            for ci in range(cols):
                cell_text = cells[ri][ci] if ri < len(cells) and ci < len(cells[ri]) else ""
                tbl.rows[ri].cells[ci].text = cell_text
        header_bg = el.get("headerBg")
        if header_bg and rows > 0:
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            for ci in range(cols):
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), header_bg.lstrip("#"))
                tbl.rows[0].cells[ci]._tc.get_or_add_tcPr().append(shd)
    elif etype == "image":
        img = el.get("image")
        if img:
            try:
                blob = base64.b64decode(img["b64"])
                doc.add_picture(BytesIO(blob))
            except Exception as exc:
                logger.warning("cover image element failed: %s", exc)
    elif etype == "spacer":
        for _ in range(int(el.get("lines", 1))):
            doc.add_paragraph()
    # divider: 下边框段落（简化：空段 + 无样式；完整实现见 Step 3 注）
```

**生成接线**：在 `generate_docx` 的封面分支（现有 `if has_cover:` 处，约 `generator.py:1046`）改为：

```python
    cover_elements = template_data.get("cover_elements")
    has_cover = bool(cover_elements or cover_master or template_data.get("cover_template"))
    ...
    cover_rendered = False
    if has_cover:
        try:
            if cover_elements and cover_elements.get("mode") == "elements":
                _render_cover_elements(doc, cover_elements, resolved_cover, frontmatter)
            elif cover_master and cover_master.get("mode") == "master":
                _render_cover_master(doc, cover_master, resolved_cover, frontmatter)
            else:
                _render_cover(doc, template_data.get("cover_template"), resolved_cover)
            cover_rendered = True
        except Exception as exc:
            logger.warning("cover render failed: %s", exc)
        if cover_rendered:
            doc.add_section(WD_SECTION.NEW_PAGE)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cover_elements.py -q`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/generator.py backend/tests/test_cover_elements.py
git commit -m "feat(output): _render_cover_elements 元素生成 + 封面优先级接线"
```

---

### Task 4: 持久化 + 数据组装（service.py / routers.py）

**Files:**
- Modify: `backend/app/extensions/output/service.py`
- Modify: `backend/app/extensions/output/routers.py`
- Test: `backend/tests/test_output_routers.py`

- [ ] **Step 1: 写测试**

追加到 `test_output_routers.py`：

```python
def test_build_template_data_includes_cover_elements():
    from app.extensions.output.routers import _build_template_data
    t = _fake_template()
    t.cover_elements = {"mode": "elements", "pages": [{"elements": [{"id": "e1", "type": "text", "text": "T"}]}]}
    td = _build_template_data(t)
    assert td["cover_elements"]["pages"][0]["elements"][0]["text"] == "T"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_output_routers.py::test_build_template_data_includes_cover_elements -q`
Expected: FAIL — `AttributeError: 'SimpleNamespace' object has no attribute 'cover_elements'`（或 `_build_template_data` 缺 key）

- [ ] **Step 3: 实现**

`service.py`：
- `create_template`（约 L30-44）：在 `cover_master=` 后加 `cover_elements=data.cover_elements.model_dump() if data.cover_elements else None,`
- `update_template`：无需改（`model_dump(exclude_unset=True)` 自动包含 `cover_elements`）。
- `duplicate_template`（约 L75-90）：`cover_elements=dict(template.cover_elements) if template.cover_elements else None,`

`routers.py` `_build_template_data`（约 L40-52）：在 `"cover_master": template.cover_master,` 后加 `"cover_elements": template.cover_elements,`

`schemas.py` `LayoutTemplateResponse`：确认已加 `cover_elements: dict | None = None`（Task 1）。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_output_routers.py tests/test_cover_elements.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/service.py backend/app/extensions/output/routers.py backend/tests/test_output_routers.py
git commit -m "feat(output): cover_elements 持久化 + 模板数据组装"
```

---

### Task 5: 迁移 `_cover_master_to_elements`（旧母版自动转元素）

**Files:**
- Modify: `backend/app/extensions/output/layout_import.py`
- Test: `backend/tests/test_cover_elements.py`

- [ ] **Step 1: 写迁移测试**

追加：

```python
def test_cover_master_to_elements_converts_old_master():
    from lxml import etree
    from app.extensions.output.layout_import import _cover_master_to_elements
    xml = ('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:r><w:t>项目名</w:t></w:r></w:p>')
    master = {"mode": "master", "xml": xml, "images": [], "slots": [], "sourceFile": "old.docx", "boundary": "before_toc"}
    cover = _cover_master_to_elements(master)
    assert cover["mode"] == "elements"
    assert cover["pages"], "应至少 1 页"
    texts = [e["text"] for e in cover["pages"][0]["elements"] if e["type"] == "text"]
    assert "项目名" in texts


def test_cover_master_to_elements_handles_bad_xml():
    from app.extensions.output.layout_import import _cover_master_to_elements
    master = {"mode": "master", "xml": "<w:p>", "images": [], "slots": [], "sourceFile": "bad.docx", "boundary": "before_toc"}
    assert _cover_master_to_elements(master) is None  # 坏 xml → None, 保留旧母版
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cover_elements.py::test_cover_master_to_elements_converts_old_master -q`
Expected: FAIL — ImportError

- [ ] **Step 3: 实现**

在 `layout_import.py` 新增：

```python
def _cover_master_to_elements(master: dict | None) -> dict | None:
    """旧 cover_master（OOXML 片段）→ 元素模型。失败返回 None（保留旧母版）。"""
    if not master or not master.get("xml"):
        return None
    try:
        from lxml import etree as _et
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        root = _et.fromstring(f'<root xmlns:w="{W}">{master["xml"]}</root>')
        blocks = list(root)
        pages = [{"elements": [_block_to_element(b) for b in blocks if b.tag == f"{{{W}}}p" or b.tag == f"{{{W}}}tbl"]}]
        pages = [p for p in pages if p["elements"]]
        if not pages:
            return None
        return {"mode": "elements", "pages": pages, "sourceFile": master.get("sourceFile", "")}
    except Exception:
        return None
```

**迁移接线**：`routers.py` `get_template` 或 `list_templates` 读取时转换——**在 `service.py::get_template`/`list_templates` 返回前**，若 `template.cover_master` 存在且 `template.cover_elements` 为空，调用 `_cover_master_to_elements` 填充（不写库，仅响应时提供，保存时才落 `cover_elements`）。在 `service.py` 的 `list_templates`/`get_template` 各加：

```python
        from app.extensions.output.layout_import import _cover_master_to_elements
        if template.cover_master and not template.cover_elements:
            template.cover_elements = _cover_master_to_elements(template.cover_master)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cover_elements.py tests/test_output_routers.py -q`
Expected: PASS（9+ passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/layout_import.py backend/app/extensions/output/service.py backend/tests/test_cover_elements.py
git commit -m "feat(output): cover_master 自动迁移为 cover_elements（读取时转换, 失败保旧）"
```

---

### Task 6: 前端类型 + 转换 + API

**Files:**
- Modify: `frontend/src/extensions/output/types.ts`
- Modify: `frontend/src/extensions/output/transforms.ts`
- Modify: `frontend/src/extensions/output/api.ts`
- Test: `frontend/tests/unit/extensions/output/cover-elements.test.ts`

- [ ] **Step 1: 写测试**

Create `frontend/tests/unit/extensions/output/cover-elements.test.ts`：

```ts
import { describe, expect, test } from "vitest";
import { transformTemplate } from "@/extensions/output/transforms";

describe("transformTemplate cover_elements", () => {
  test("maps cover_elements → coverElements", () => {
    const tpl = transformTemplate({
      id: "1", name: "T", report_type: "g", is_builtin: false,
      page_settings: {}, body_styles: {}, heading_styles: [], reference_style: "gb7714",
      created_at: "", updated_at: "",
      cover_elements: { mode: "elements", pages: [{ elements: [{ id: "e1", type: "text", text: "报告标题" }] }], sourceFile: "x.docx" },
    });
    expect(tpl.coverElements?.pages[0]?.elements[0]?.text).toBe("报告标题");
  });

  test("defaults coverElements to null when absent", () => {
    const tpl = transformTemplate({ id: "1", name: "T", report_type: "g", is_builtin: false, page_settings: {}, body_styles: {}, heading_styles: [], reference_style: "gb7714", created_at: "", updated_at: "" });
    expect(tpl.coverElements).toBeNull();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run tests/unit/extensions/output/cover-elements.test.ts`
Expected: FAIL — TS 报 `coverElements` 不存在

- [ ] **Step 3: 实现**

`types.ts` 新增：

```ts
export interface CoverImage { b64: string; ext?: string }
export type CoverElementType = "text" | "table" | "image" | "spacer" | "divider";
export interface CoverElement {
  id: string;
  type: CoverElementType;
  text?: string;
  fontFamily?: string;
  fontSize?: number;
  bold?: boolean;
  color?: string;
  alignment?: "left" | "center" | "right";
  spaceBefore?: number;
  spaceAfter?: number;
  slotId?: string | null;
  rows?: number;
  cols?: number;
  cells?: string[][];
  headerBg?: string | null;
  borderColor?: string;
  image?: CoverImage | null;
  widthCm?: number | null;
  lines?: number;
}
export interface CoverPage { elements: CoverElement[] }
export interface Cover { mode: "elements"; pages: CoverPage[]; sourceFile?: string }
```

`LayoutTemplate` 加 `coverElements: Cover | null;`

`transforms.ts` 加：`coverElements: (data.cover_elements as LayoutTemplate["coverElements"]) ?? null,`

`api.ts`：`createTemplate` 载荷加 `if (tpl.coverElements) payload.cover_elements = tpl.coverElements;`；`updateTemplate` 加 `if (tpl.coverElements !== undefined) payload.cover_elements = tpl.coverElements;`

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run tests/unit/extensions/output/ && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/output/types.ts frontend/src/extensions/output/transforms.ts frontend/src/extensions/output/api.ts frontend/tests/unit/extensions/output/cover-elements.test.ts
git commit -m "feat(output-fe): coverElements 前端类型 + 转换 + API"
```

---

### Task 7: cover-state 元素模型 helpers

**Files:**
- Modify: `frontend/src/extensions/output/cover-state.ts`
- Test: `frontend/tests/unit/extensions/output/cover-elements.test.ts`

- [ ] **Step 1: 写 helper 测试**

追加到 `cover-elements.test.ts`：

```ts
import { coverElementSlotOptions, patchCoverElementsPage, COVER_SLOT_OPTIONS } from "@/extensions/output/cover-state";

describe("cover element helpers", () => {
  test("COVER_SLOT_OPTIONS 含全部绑定变量", () => {
    const ids = COVER_SLOT_OPTIONS.map((o) => o.value);
    expect(ids).toEqual(["title", "client", "project_number", "date", "project_name", "stage", "design_unit"]);
  });

  test("patchCoverElementsPage 更新指定页元素", () => {
    const cover = { mode: "elements", pages: [{ elements: [{ id: "e1", type: "text", text: "A" }] }, { elements: [] }] } as const;
    const next = patchCoverElementsPage(cover, 0, (els) => els.map((e) => (e.id === "e1" ? { ...e, text: "B" } : e)));
    expect(next.pages[0].elements[0].text).toBe("B");
    expect(next.pages[1]).toEqual(cover.pages[1]); // 其它页不变
  });
});
```

- [ ] **Step 2: 运行确认失败**

Expected: FAIL — helpers 未定义

- [ ] **Step 3: 实现**

`cover-state.ts` 新增：

```ts
export const COVER_SLOT_OPTIONS: { value: string; label: string }[] = [
  { value: "title", label: "报告标题" },
  { value: "client", label: "建设单位" },
  { value: "project_number", label: "项目编号" },
  { value: "date", label: "日期" },
  { value: "project_name", label: "项目名" },
  { value: "stage", label: "设计阶段" },
  { value: "design_unit", label: "设计单位" },
];

export function patchCoverElementsPage(
  cover: Cover | null,
  pageIndex: number,
  updater: (elements: CoverElement[]) => CoverElement[],
): Cover | null {
  if (!cover) return cover;
  return {
    ...cover,
    pages: cover.pages.map((p, i) => (i === pageIndex ? { ...p, elements: updater(p.elements) } : p)),
  };
}

export const COVER_EMPTY_ELEMENTS: Cover = { mode: "elements", pages: [{ elements: [] }] };
```

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run tests/unit/extensions/output/ && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/output/cover-state.ts frontend/tests/unit/extensions/output/cover-elements.test.ts
git commit -m "feat(output-fe): cover 元素模型纯 helpers"
```

---

### Task 8: CoverElementsEditor 组件（页签 + 元素列表 + 表格编辑器 + 绑定下拉）

**Files:**
- Create: `frontend/src/extensions/output/components/CoverElementsEditor.tsx`
- Test: 本任务 UI 无组件测试基建（`.dom.test.tsx` 缺失），以 `pnpm typecheck` + lint + 手动验证覆盖。

- [ ] **Step 1: 创建组件骨架**

创建 `CoverElementsEditor.tsx`：

```tsx
"use client";

import { Plus, Trash2, Table2, Type, Image as ImageIcon, MoveVertical } from "lucide-react";
import React, { useCallback } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { COVER_SLOT_OPTIONS, patchCoverElementsPage } from "@/extensions/output/cover-state";
import type { Cover, CoverElement, CoverElementType } from "@/extensions/output/types";
import { cn } from "@/lib/utils";

interface CoverElementsEditorProps {
  cover: Cover;
  onChange: (cover: Cover) => void;
}

let _seq = 0;
const nextId = () => `el${++_seq}`;

const ELEMENT_TYPES: { value: CoverElementType; label: string }[] = [
  { value: "text", label: "文本" },
  { value: "table", label: "表格" },
  { value: "image", label: "Logo" },
  { value: "spacer", label: "空行" },
  { value: "divider", label: "分隔线" },
];

export function CoverElementsEditor({ cover, onChange }: CoverElementsEditorProps) {
  const updatePage = useCallback((pi: number, updater: (els: CoverElement[]) => CoverElement[]) => {
    onChange(patchCoverElementsPage(cover, pi, updater)!);
  }, [cover, onChange]);

  const updateElement = useCallback((pi: number, id: string, patch: Partial<CoverElement>) => {
    updatePage(pi, (els) => els.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }, [updatePage]);

  const addElement = useCallback((pi: number, type: CoverElementType) => {
    const base: CoverElement = { id: nextId(), type };
    if (type === "text") base.text = "新文本";
    if (type === "table") { base.rows = 2; base.cols = 2; base.cells = [["", ""], ["", ""]]; }
    if (type === "spacer") base.lines = 1;
    updatePage(pi, (els) => [...els, base]);
  }, [updatePage]);

  const removeElement = useCallback((pi: number, id: string) => {
    updatePage(pi, (els) => els.filter((e) => e.id !== id));
  }, [updatePage]);

  const moveElement = useCallback((pi: number, id: string, dir: -1 | 1) => {
    updatePage(pi, (els) => {
      const i = els.findIndex((e) => e.id === id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= els.length) return els;
      const copy = [...els];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }, [updatePage]);

  const updateTableCell = useCallback((pi: number, id: string, r: number, c: number, v: string) => {
    updatePage(pi, (els) => els.map((e) => {
      if (e.id !== id || e.type !== "table") return e;
      const cells = (e.cells ?? []).map((row) => [...row]);
      while (cells.length <= r) cells.push([]);
      while (cells[r].length <= c) cells[r].push("");
      cells[r][c] = v;
      return { ...e, cells };
    }));
  }, [updatePage]);

  return (
    <div className="space-y-3">
      {cover.pages.map((page, pi) => (
        <div key={pi} className="rounded-lg border border-border bg-background p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">页 {pi + 1}</span>
            <button type="button" onClick={() => updatePage(pi, (els) => els)} className="text-[10px] text-muted-foreground">
              页 {pi + 1}
            </button>
          </div>
          <div className="space-y-1.5">
            {page.elements.map((el) => (
              <div key={el.id} className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5">
                <span className="w-8 shrink-0 text-center text-[10px] text-muted-foreground">
                  {el.type === "table" ? "表" : el.type === "image" ? "图" : el.type === "spacer" ? "空" : "文"}
                </span>
                <div className="min-w-0 flex-1">
                  {el.type === "text" ? (
                    <div className="flex items-center gap-2">
                      <input
                        className="h-6 min-w-0 flex-1 rounded border border-border bg-background px-2 text-xs"
                        value={el.text ?? ""}
                        onChange={(e) => updateElement(pi, el.id, { text: e.target.value })}
                      />
                      <AdminSelect
                        className="w-32"
                        value={el.slotId ?? ""}
                        onChange={(v) => updateElement(pi, el.id, { slotId: v || null })}
                        options={[{ value: "", label: "不绑定" }, ...COVER_SLOT_OPTIONS]}
                      />
                      <input
                        type="number"
                        className="h-6 w-12 rounded border border-border bg-background px-1 text-center text-[10px]"
                        value={el.fontSize ?? 12}
                        onChange={(e) => updateElement(pi, el.id, { fontSize: parseInt(e.target.value) || 12 })}
                        title="字号"
                      />
                      <button
                        type="button"
                        onClick={() => updateElement(pi, el.id, { bold: !el.bold })}
                        className={cn("rounded px-1.5 text-xs", el.bold ? "bg-primary/10 text-primary font-bold" : "text-muted-foreground")}
                      >
                        B
                      </button>
                    </div>
                  ) : el.type === "table" ? (
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-[10px]">
                        <tbody>
                          {(el.cells ?? []).map((row, r) => (
                            <tr key={r}>
                              {row.map((cell, c) => (
                                <td key={c} className="border border-border p-0">
                                  <input
                                    className="h-6 w-full min-w-16 bg-background px-1 text-[10px]"
                                    value={cell}
                                    onChange={(e) => updateTableCell(pi, el.id, r, c, e.target.value)}
                                  />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="mt-1 flex gap-1">
                        <button type="button" className="text-[10px] text-primary" onClick={() => updateElement(pi, el.id, { rows: (el.rows ?? 0) + 1, cells: [...(el.cells ?? []), Array(el.cols ?? 0).fill("")] })}>+行</button>
                        <button type="button" className="text-[10px] text-primary" onClick={() => updateElement(pi, el.id, { cols: (el.cols ?? 0) + 1, cells: (el.cells ?? []).map((r) => [...r, ""]) })}>+列</button>
                      </div>
                    </div>
                  ) : el.type === "spacer" ? (
                    <span className="text-[10px] text-muted-foreground">空行 × {el.lines ?? 1}</span>
                  ) : (
                    <span className="text-[10px] text-muted-foreground">{el.type === "image" ? "Logo（导入时自动填充）" : "分隔线"}</span>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <button type="button" onClick={() => moveElement(pi, el.id, -1)} title="上移" className="rounded p-0.5 text-muted-foreground hover:bg-muted">↑</button>
                  <button type="button" onClick={() => moveElement(pi, el.id, 1)} title="下移" className="rounded p-0.5 text-muted-foreground hover:bg-muted">↓</button>
                  <button type="button" onClick={() => removeElement(pi, el.id)} title="删除" className="rounded p-0.5 text-destructive hover:bg-destructive/10">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground">+ 添加</span>
            {ELEMENT_TYPES.map((t) => (
              <button key={t.value} type="button" onClick={() => addElement(pi, t.value)} className="rounded border border-dashed border-border px-2 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary">
                {t.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange({ ...cover, pages: [...cover.pages, { elements: [] }] })}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
      >
        <Plus className="h-3.5 w-3.5" /> 添加页面
      </button>
    </div>
  );
}
```

> 说明：组件为功能骨架，样式可后续统一。image/divider 元素 v1 展示占位文案（导入时提取填充 image；divider 生成时用下边框段）。

- [ ] **Step 2: typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS（若 `AdminSelect` props 不匹配，按其实际签名调整）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/output/components/CoverElementsEditor.tsx
git commit -m "feat(output-fe): CoverElementsEditor 页签+元素列表+表格网格+绑定下拉"
```

---

### Task 9: LayoutTemplateEditor 接入

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`

- [ ] **Step 1: 接入封面 section**

在 `LayoutTemplateEditor.tsx`：
1. import：`import { CoverElementsEditor } from "./CoverElementsEditor";`
2. state：`const [coverElements, setCoverElements] = useState<Cover | null>(template?.coverElements ?? null);`
3. `handleSave` 载荷加 `coverElements,`
4. 封面 section：当 `coverElements` 存在时渲染 `CoverElementsEditor`（替代母版/开关模式）；否则显示旧的 开关模式 + 「从样例导入」按钮（导入后经 `applyImported` 的 `cover_elements` 分支设置）。在 `applyImportedLayout` 加：
```ts
    const ce = data.cover_elements as Cover | null | undefined;
    if (ce?.mode === "elements") setCoverElements(ce);
    else if (ce) setCoverElements(null);
```
5. 封面区结构：
```tsx
{coverElements ? (
  <>
    <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs">
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate text-muted-foreground">来自样例：{coverElements.sourceFile || "（未命名）"}</span>
      <button type="button" onClick={() => setCoverElements(null)} className="ml-auto shrink-0 rounded-md border border-border px-2 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10">移除封面</button>
    </div>
    <CoverElementsEditor cover={coverElements} onChange={setCoverElements} />
  </>
) : (
  /* 原开关模式 + 从样例导入按钮（保留） */
)}
```

- [ ] **Step 2: typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/extensions/output/components/LayoutTemplateEditor.tsx src/extensions/output/components/CoverElementsEditor.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output-fe): 封面 section 接入 CoverElementsEditor"
```

---

### Task 10: 端到端验证（真实样例）

**Files:**
- Test: `backend/tests/test_cover_elements.py`
- Manual: 浏览器 QA（导入消防 + 环评样例，编辑元素，生成）

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && uv run pytest tests/test_cover_elements.py tests/test_cover_master.py tests/test_output_cover.py tests/test_output_routers.py -q`
Expected: 全 PASS（新旧路径并存不回归）

- [ ] **Step 2: 前端全量验证**

Run: `cd frontend && npx vitest run tests/unit/extensions/output/ && npx tsc --noEmit && npx eslint src/extensions/output/`
Expected: PASS

- [ ] **Step 3: ruff**

Run: `cd backend && uv run ruff check app/extensions/output/ tests/test_cover_elements.py`
Expected: PASS

- [ ] **Step 4: 手工 QA（两个真实样例）**

重启 frontend 容器（`docker compose -p eai-docker restart frontend`），浏览器经 :2026：
1. 新建排版模板 → 封面配置 → 从样例导入 `基地项目-消防设计专篇.docx` → 断言：1 页、标题横幅文本元素、「项目名」独立元素、会签表表格元素、项目编号/日期已绑定。
2. 改一个文本元素（改字号/换绑定）→ 保存 → 编辑再打开 → 断言改动保留。
3. 生成输出 → 下载 docx → 断言封面按元素渲染、绑定替换、会签表在。
4. 再导入 `横城矿区环评报告.docx` → 断言 3 页、名单表元素。
5. 对旧模板（有 cover_master 的）编辑 → 断言自动转为元素（转换成功）。
6. 生成时旧 cover_master 模板仍按旧路径渲染（回归）。

- [ ] **Step 5: Commit（如有 QA 修复）**

```bash
git add -A backend/tests/test_cover_elements.py  # 及修复文件
git commit -m "fix(output): cover_elements 端到端验证修复"
```

---

## Self-Review 记录

- **Spec 覆盖**：数据模型(Task1) / 提取切页+绑定(Task2) / 生成(Task3) / 持久化(Task4) / 迁移(Task5) / 前端类型+API(Task6) / helpers(Task7) / 编辑器(Task8-9) / 错误处理与测试(Task2/3/5/10)。非目标（画布/文本框）未做。
- **占位符**：无 TBD/TODO；表头底纹完整代码已直接写入 Task 3（含 OxmlElement/qn 局部导入）。
- **类型一致性**：`cover_elements`/`coverElements` 前后端一致；`CoverSchema.mode="elements"`；`slotId` 值集 = `COVER_SLOT_OPTIONS` 7 项，与生成端 `slot_value` 键一致（title/client/project_number/date/project_name/stage/design_unit）。
- **已知取舍**：Task 8 组件无 DOM 测试（repo 无 .dom.test.tsx 基建，沿用 P0 记录）；image/divider 元素 v1 为占位展示。
