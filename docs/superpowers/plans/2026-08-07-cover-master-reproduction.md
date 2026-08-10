# 封面母版 OOXML 透传 + 槽位绑定 (B1) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「排版模板」对话框的封面配置能真实还原样例 .docx 的表格类封面（标题横幅表 + 编制会签表），生成报告时只替换项目变量槽位。

**Architecture:** 提取端把封面区（目录/首标题前的 `<w:p>`/`<w:tbl>`）deep-copy + 序列化为 OOXML 片段存成 `cover_master`（JSONB 列）；生成端把该片段注入新文档首页，对"变量"槽位做段落级文本替换，图片按 base64 重嵌入。老的 6 布尔 `cover_template` 完整保留兜底。

**Tech Stack:** python-docx + lxml（OOXML 透传），Pydantic schema，Next.js/React 19，TanStack Query。无新依赖（lxml/python-docx 已在用）。

**分支：所有提交进入 `main-dev-fork`，绝不提交 `main`。** EAI-CUSTOM 注释规则**不适用**——这些是 `extensions/output/` 手写应用代码，非 deer-flow 核心/harness。

---

## 设计依据与 spec 偏差（实施前必读）

设计文档：`docs/superpowers/specs/2026-08-07-cover-master-reproduction-design.md`。本计划在核实真实代码后对 spec 做以下**更正**（spec 的伪代码部分假设有误，以本计划为准）：

1. **需要 DB 列变更（spec 说"无 DB 迁移"是错的）。** `models.py` 中每个字段都是独立 JSONB 列，**不存在**单一 `template_data` JSON 列。`cover_master` 必须新增 JSONB 列；由于 `layout_templates` 表已存在，`Base.metadata.create_all` **不会**给它加列——必须走 `database.py::migrate_db()` 里幂等的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（该项目既有模式，见 `database.py:1237-1247` 的 `data_sources.description`/`cpa_documents.project_name`）。`migrate_db()` 在每次 gateway 启动时由 `app.py:258` 调用。

2. **嵌套 JSON 键统一 camelCase（spec 伪代码用了 snake_case）。** 现有约定：`CoverTemplateSchema` 字段名 `showLogo`/`logoPosition`（camelCase），`body_styles` 内 `fontSize`/`lineHeight`。故 `CoverMasterSchema` 字段、提取 dict、生成器读取、前端类型**全部 camelCase**：`sampleValue`/`defaultFrom`/`sourceFile`/`origRid`。这样 `transforms.ts` 只需映射顶层 `cover_master → coverMaster`，无需深度 snake↔camel 转换。

3. **生成器接线点 = `routers.py::_build_template_data`（spec 未指明）。** 该函数（`routers.py:40-51`）拼装交给 `generate_docx` 的 dict，必须加 `"cover_master": template.cover_master`，否则生成端永远拿不到母版。

4. **`_render_cover_master` 签名需 frontmatter**（用于 `project_name`/`stage` 槽位），即 `_render_cover_master(doc, master, resolved, frontmatter)`。

5. **真实样例测试用 `skipif`**（样例文件在用户数据目录、未入库，CI 拿不到）；主测试用**合成 docx** 复刻样例结构（标题横幅表 + 会签表 + 目录段 + 正文标题），与既有 `test_output_layout_import.py` 风格一致。

6. **真实样例路径**：`backend/data/users/f8766d55-2b1b-422e-a945-5fcf268a8a39/knowledge/8376f624-95de-47b1-b871-0bb000b5a934/基地项目-消防设计专篇.docx`（已确认存在，75KB）。

---

## File Structure

| 文件 | 责任 | 改动类型 |
|------|------|---------|
| `backend/app/extensions/output/schemas.py` | 新增 `CoverSlotSchema`/`CoverMasterSchema`；三 LayoutTemplate schema 加 `cover_master` | 改 |
| `backend/app/extensions/output/models.py` | `LayoutTemplate` 加 `cover_master` JSONB 列 | 改 |
| `backend/app/extensions/database.py` | `migrate_db()` 加幂等 ALTER | 改 |
| `backend/app/extensions/output/service.py` | `create_template`/`duplicate_template` 持久化 `cover_master` | 改 |
| `backend/app/extensions/output/routers.py` | `_build_template_data` 透传 `cover_master` | 改 |
| `backend/app/extensions/output/layout_import.py` | 新增 `_extract_cover_master` + 槽位预填 + 图片提取 + 组装 | 改 |
| `backend/app/extensions/output/generator.py` | 新增 `_render_cover_master` + 槽位替换 + 图片重嵌入 + 分支优先级 | 改 |
| `backend/tests/test_cover_master.py` | 提取/生成/边界/替换/图片 单测 | 新建 |
| `frontend/src/extensions/output/types.ts` | 新增 `CoverSlot`/`CoverMaster`；`LayoutTemplate.coverMaster` | 改 |
| `frontend/src/extensions/output/transforms.ts` | `cover_master → coverMaster` 映射 | 改 |
| `frontend/src/extensions/output/api.ts` | create/update 载荷加 `cover_master` | 改 |
| `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` | 封面配置区：母版来源 + 槽位列表 + 导入按钮（无母版则旧 5 开关） | 改 |

---

## Task 1: 后端数据模型（schema + 列 + 迁移 + 持久化 + 接线）

**Files:**
- Modify: `backend/app/extensions/output/schemas.py`
- Modify: `backend/app/extensions/output/models.py`
- Modify: `backend/app/extensions/database.py`
- Modify: `backend/app/extensions/output/service.py`
- Modify: `backend/app/extensions/output/routers.py`
- Test: `backend/tests/test_cover_master.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_cover_master.py`，写入（仅 Task 1 部分，后续 task 追加）：

```python
"""Tests for cover-master OOXML passthrough + slot binding (B1)."""

import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.extensions.output.layout_import import extract_layout_from_docx
from app.extensions.output.schemas import CoverMasterSchema, CoverSlotSchema

SAMPLE = Path(
    "backend/data/users/f8766d55-2b1b-422e-a945-5fcf268a8a39/knowledge/"
    "8376f624-95de-47b1-b871-0bb000b5a934/基地项目-消防设计专篇.docx"
)


def _docx_bytes(doc: Document) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Task 1: schema + wiring ────────────────────────────────────────────────

def test_cover_master_schema_camelcase_and_defaults():
    m = CoverMasterSchema(
        xml="<w:p/>",
        slots=[CoverSlotSchema(id="client", label="建设单位", sampleValue="甲公司", defaultFrom="frontmatter:client")],
    )
    d = m.model_dump()
    assert d["mode"] == "master"
    assert d["sourceFile"] == ""
    assert d["boundary"] == "before_toc"
    assert d["images"] == []
    assert d["slots"][0]["sampleValue"] == "甲公司"
    assert d["slots"][0]["defaultFrom"] == "frontmatter:client"
    assert d["slots"][0]["kind"] == "variable"


def test_build_template_data_includes_cover_master():
    from app.extensions.output.routers import _build_template_data

    tpl = SimpleNamespace(
        page_settings={}, body_styles={}, heading_styles=[], table_styles=None,
        figure_styles=None, header_footer=None, reference_style="gb7714",
        appendix_rules=None, cover_template=None, toc_settings=None,
        cover_master={"mode": "master", "xml": "<w:p/>", "images": [], "slots": [], "sourceFile": "x.docx", "boundary": "before_toc"},
    )
    td = _build_template_data(tpl)
    assert td["cover_master"]["mode"] == "master"
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 下，容器内或本机 venv 任一；本机命令如下，容器内去掉 `PYTHONPATH=.` 前缀亦可）:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -v
```
Expected: FAIL — `ImportError: cannot import name 'CoverMasterSchema'`（schema 还没建）。

- [ ] **Step 3: 实现 schema**

编辑 `backend/app/extensions/output/schemas.py`，在 `CoverTemplateSchema` 之后（约第 30 行后）插入两个 schema，**字段名 camelCase**：

```python
class CoverSlotSchema(BaseModel):
    id: str  # "title"|"project_name"|"client"|"project_number"|"stage"|"date"
    label: str
    kind: str = "variable"  # "variable"(生成时替换) | "literal"(原样保留)
    sampleValue: str
    defaultFrom: str | None = None  # "doc_title"|"today"|"frontmatter:client"|None


class CoverMasterSchema(BaseModel):
    mode: str = "master"
    xml: str  # 封面区序列化的 <w:p>/<w:tbl> 片段
    images: list[dict] = []  # [{"origRid": str, "ext": str, "b64": str}]
    slots: list[CoverSlotSchema] = []
    sourceFile: str = ""
    boundary: str = "before_toc"  # "before_toc"|"before_first_heading"
```

在三个 LayoutTemplate schema 上各加一行。`LayoutTemplateCreate`（约第 87 行 `cover_template` 下）与 `LayoutTemplateUpdate`（约第 102 行）用强类型：
```python
    cover_master: CoverMasterSchema | None = None
```
`LayoutTemplateResponse`（约第 121 行 `cover_template` 下）用 dict（与既有 `cover_template: dict | None` 一致）：
```python
    cover_master: dict | None = None
```

- [ ] **Step 4: 加 ORM 列**

编辑 `backend/app/extensions/output/models.py`，在 `cover_template` 行（第 23 行）下加：
```python
    cover_master: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: 加幂等迁移**

编辑 `backend/app/extensions/database.py` 的 `migrate_db()`。在该函数内既有 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 语句附近（如 `cpa_documents.project_name` 那条之后），加：
```python
        # output: cover_master JSONB — create_all won't add columns to the
        # pre-existing layout_templates table.
        await conn.execute(text(
            "ALTER TABLE layout_templates ADD COLUMN IF NOT EXISTS cover_master JSONB"
        ))
```

- [ ] **Step 6: 持久化层**

编辑 `backend/app/extensions/output/service.py`：
- `create_template`：在 `cover_template=...` 行（第 34 行）下加：
  ```python
            cover_master=data.cover_master.model_dump() if data.cover_master else None,
  ```
- `duplicate_template`：在 `cover_template=dict(...)` 行（第 79 行）下加：
  ```python
            cover_master=dict(template.cover_master) if template.cover_master else None,
  ```
- `update_template` **无需改**：它用 `model_dump(exclude_unset=True)` + `setattr` 循环，`cover_master` 已是 dict（Pydantic 递归 dump），自动落库。

- [ ] **Step 7: 接线生成端**

编辑 `backend/app/extensions/output/routers.py` 的 `_build_template_data`（第 40-51 行返回 dict），在 `"cover_template": template.cover_template,` 行下加：
```python
        "cover_master": template.cover_master,
```

- [ ] **Step 8: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -v
```
Expected: PASS（2 个 Task 1 测试通过）。

- [ ] **Step 9: 提交**

```bash
git add backend/app/extensions/output/schemas.py backend/app/extensions/output/models.py backend/app/extensions/database.py backend/app/extensions/output/service.py backend/app/extensions/output/routers.py backend/tests/test_cover_master.py
git commit -m "feat(output): cover_master 数据模型 (schema/列/迁移/持久化/生成端接线)"
```

---

## Task 2: 封面母版提取（`_extract_cover_master` + 槽位 + 图片）

**Files:**
- Modify: `backend/app/extensions/output/layout_import.py`
- Test: `backend/tests/test_cover_master.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `test_cover_master.py` 末尾追加（合成 doc 复刻样例：标题横幅表 + 客户段 + 会签表 + 目录段 + 正文标题）：

```python
# ── Task 2: extraction ────────────────────────────────────────────────────

def _make_table_cover_docx() -> bytes:
    """Synthetic replica of the real sample's cover: empty spacer, title-banner
    table, a 建设单位 line, a 会签 table, a 目录 marker, then the body heading."""
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)

    doc.add_paragraph()  # leading blank spacer

    # table[0]: title banner (single merged-ish cell, big font)
    t1 = doc.add_table(rows=1, cols=1)
    banner = t1.rows[0].cells[0].paragraphs[0]
    run = banner.add_run("基地项目 消防设计专篇")
    run.font.size = Pt(22)
    run.bold = True

    doc.add_paragraph("建设单位：甲公司")  # client line (body-level paragraph)

    # table[1]: 编制会签表
    doc.add_table(rows=2, cols=2)

    doc.add_paragraph("目录")  # TOC marker (Normal style, text-based)
    doc.add_heading("第一章 概述", level=1)  # body
    return _docx_bytes(doc)


def test_extract_cover_master_table_cover():
    data = extract_layout_from_docx(_make_table_cover_docx(), source_file="sample.docx")
    cm = data["cover_master"]
    assert cm is not None
    assert cm["boundary"] == "before_toc"
    assert cm["xml"].count("<w:tbl") == 2  # banner + 会签
    assert cm["images"] == []
    assert cm["sourceFile"] == "sample.docx"
    ids = {s["id"] for s in cm["slots"]}
    assert "client" in ids
    assert "title" in ids
    assert data["cover_detected"] is True


def test_extract_cover_master_none_for_plain_doc():
    """Body starts with a Heading, nothing before → no cover master."""
    doc = Document()
    doc.add_heading("第一章 概述", level=1)
    doc.add_paragraph("正文。")
    assert extract_layout_from_docx(_docx_bytes(doc))["cover_master"] is None


def test_extract_cover_master_none_for_toc_pre_region():
    """TOC-styled entries before the heading → no cover (regression guard)."""
    from docx.enum.style import WD_STYLE_TYPE

    doc = Document()
    try:
        toc = doc.styles.add_style("toc 1", WD_STYLE_TYPE.PARAGRAPH)
    except ValueError:
        toc = doc.styles["toc 1"]
    doc.add_paragraph("第一章 概述 .......... 1", style=toc)
    doc.add_heading("第一章 概述", level=1)
    assert extract_layout_from_docx(_docx_bytes(doc))["cover_master"] is None


@pytest.mark.skipif(not SAMPLE.exists(), reason="real sample not checked into repo")
def test_extract_real_sample_cover_master():
    data = extract_layout_from_docx(SAMPLE.read_bytes(), source_file="基地项目-消防设计专篇.docx")
    cm = data["cover_master"]
    assert cm is not None, "real sample should yield a cover master"
    assert cm["xml"].count("<w:tbl") >= 2
    assert cm["images"] == []
    assert cm["boundary"] in ("before_toc", "before_first_heading")
    assert cm["sourceFile"] == "基地项目-消防设计专篇.docx"
    assert "title" in {s["id"] for s in cm["slots"]}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -k "extract" -v
```
Expected: FAIL — `KeyError: 'cover_master'`（提取函数还没产出该键）。

- [ ] **Step 3: 实现提取**

编辑 `backend/app/extensions/output/layout_import.py`：

(a) 顶部 import 区（第 11-16 行附近）加：
```python
import base64
from copy import deepcopy
from lxml import etree
```

(b) 在常量区（`_DRAWML = ...` 第 24 行附近）加：
```python
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TOC_TEXT_RE = re.compile(r"^目\s*录$|^contents$", re.I)
_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}")
```

(c) 在 `_detect_cover` 函数**之后**（约第 532 行后）插入三个函数：

```python
def _style_id_sets(doc) -> tuple[set[str], set[str]]:
    """Precompute (heading_style_ids, toc_style_ids) from doc.styles."""
    heading_ids: set[str] = set()
    toc_ids: set[str] = set()
    try:
        for st in doc.styles:
            name = (getattr(st, "name", "") or "").lower()
            sid = getattr(st, "style_id", None)
            if not sid:
                continue
            if name.startswith("heading"):
                heading_ids.add(sid)
            if "toc" in name:
                toc_ids.add(sid)
    except Exception:
        pass
    return heading_ids, toc_ids


def _max_run_font_pt(p_el) -> float:
    """Largest <w:sz w:val=...> (half-points) among runs in a <w:p> element."""
    best = 0.0
    for r in p_el.findall(f"{{{_W}}}r"):
        rpr = r.find(f"{{{_W}}}rPr")
        if rpr is None:
            continue
        sz = rpr.find(f"{{{_W}}}sz")
        val = sz.get(f"{{{_W}}}val") if sz is not None else None
        if val and val.isdigit():
            best = max(best, int(val) / 2.0)
    return best


def _para_text(p_el) -> str:
    return "".join((t.text or "") for t in p_el.findall(f"{{{_W}}}t"))


def _prefill_cover_slots(cover_blocks) -> list[dict]:
    """Prefill standard variable slots by scanning cover-region text. camelCase keys."""
    paras: list[tuple] = []  # (p_el, text) incl. paragraphs inside tables
    for b in cover_blocks:
        for p in b.iter(f"{{{_W}}}p"):
            txt = _para_text(p)
            if txt.strip():
                paras.append((p, txt))
    full = "\n".join(t for _, t in paras)

    slots: list[dict] = []

    def add(slot_id: str, label: str, value, default_from: str | None = None) -> None:
        if value:
            slots.append({"id": slot_id, "label": label, "kind": "variable", "sampleValue": str(value).strip(), "defaultFrom": default_from})

    # title: largest-font paragraph, else 专篇/报告书/计算书 keyword
    title, best_sz = "", 0.0
    for p, txt in paras:
        sz = _max_run_font_pt(p)
        if sz > best_sz and len(txt.strip()) >= 2:
            best_sz, title = sz, txt.strip()
    if not title:
        m = re.search(r"(.{2,40}?(?:专篇|报告书|计算书|设计说明).{0,20})", full)
        if m:
            title = m.group(1).strip()
    add("title", "报告标题", title, "doc_title")

    m = re.search(r"项目名(?:称)?[:：\s]*(\S.{0,39})", full)
    add("project_name", "项目名", m.group(1) if m else None)

    m = re.search(r"(?:建设单位|业主单位|业主)[:：]\s*(\S.{0,39})", full)
    add("client", "建设单位", m.group(1) if m else None, "frontmatter:client")

    m = re.search(r"(?:项目编号|工程编号|编号)[:：\s]*(\S.{0,39})", full)
    add("project_number", "项目编号", m.group(1) if m else None)

    m = re.search(r"(?:设计阶段|阶段)[:：\s]*(\S.{0,29})", full)
    add("stage", "设计阶段", m.group(1) if m else None)

    m = _DATE_RE.search(full)
    add("date", "日期", m.group(0) if m else None, "today")

    return slots


def _extract_cover_master(doc, source_file: str = "") -> dict | None:
    """Extract the cover region (blocks before the TOC marker or first Heading) as
    a reusable OOXML master + prefilled slots. Returns None when no meaningful
    cover exists (degrades to the legacy cover_template fallback)."""
    body = doc.element.body
    heading_ids, toc_ids = _style_id_sets(doc)

    cover_blocks: list = []
    boundary: str | None = None

    for child in body.iterchildren():
        tag = child.tag
        if tag == f"{{{_W}}}sectPr":  # final section properties — body content ended
            break
        if tag == f"{{{_W}}}p":
            style_el = child.find(f"{{{_W}}}pPr/{{{_W}}}pStyle")
            style_val = style_el.get(f"{{{_W}}}val") if style_el is not None else None
            text = _para_text(child).strip()
            if _TOC_TEXT_RE.match(text) or style_val in toc_ids:
                boundary = "before_toc"
                break
            if style_val in heading_ids:
                boundary = "before_first_heading"
                break
            cover_blocks.append(child)
        elif tag == f"{{{_W}}}tbl":
            cover_blocks.append(child)
        # other elements (bookmarkStart, etc.) ignored

    if boundary is None:
        return None

    has_table = any(b.tag == f"{{{_W}}}tbl" for b in cover_blocks)
    has_text = any(_para_text(b).strip() for b in cover_blocks if b.tag == f"{{{_W}}}p")
    if not has_table and not has_text:
        return None

    xml = "".join(etree.tostring(deepcopy(b), encoding="unicode") for b in cover_blocks)

    images: list[dict] = []
    seen: set[str] = set()
    for b in cover_blocks:
        for blip in b.iter(f"{{{_DRAWML}}}blip"):
            rid = blip.get(f"{{{_REL}}}embed")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            part = doc.part.related_parts.get(rid)
            blob = getattr(part, "blob", None)
            if not blob:
                continue
            ext = "png"
            partname = getattr(part, "partname", None)
            if partname and "." in str(partname):
                ext = str(partname).rsplit(".", 1)[-1].lower()
            images.append({"origRid": rid, "ext": ext, "b64": base64.b64encode(blob).decode("ascii")})

    return {
        "mode": "master",
        "xml": xml,
        "images": images,
        "slots": _prefill_cover_slots(cover_blocks),
        "sourceFile": source_file,
        "boundary": boundary,
    }
```

(d) 改 `extract_layout_from_docx`（第 577 行）签名与组装。把签名改为：
```python
def extract_layout_from_docx(data: bytes, source_file: str = "") -> dict:
```
在 `cover = _detect_cover(doc)` 行（第 589 行）下加：
```python
    cover_master = _extract_cover_master(doc, source_file=source_file)
```
在返回 dict 里把 `"cover_template": cover,` 行下加 `"cover_master": cover_master,`，并把 `"cover_detected": cover is not None,` 改为：
```python
        "cover_detected": cover_master is not None or cover is not None,
```

(e) 改 `validate_docx_upload`（约第 610 行）把文件名透传：找到其内部调用 `extract_layout_from_docx(data)` 处，改为 `extract_layout_from_docx(data, source_file=filename or "")`。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -k "extract" -v
```
Expected: PASS（3 个合成测试通过；真实样例 skipif 在 CI 跳过，本机若 SAMPLE 存在则跑——若 `test_extract_real_sample_cover_master` 在本机失败，先看断言：`boundary` 是否命中、`<w:tbl` 数量、`title` 槽位。常见原因：样例目录页是 TOC 字段而非普通"目录"段落，或标题文字跨多个单元格——据此微调 `_TOC_TEXT_RE` 或标题规则，**但不要放宽到误吃正文**）。

- [ ] **Step 5: 跑既有 layout_import 全量回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py -v
```
Expected: PASS（确认未破坏既有提取，尤其 `test_cover_not_detected_when_pre_region_is_toc`、`test_no_cover_detected_for_plain_document`、`test_cover_detected_for_first_page_cover`）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/extensions/output/layout_import.py backend/tests/test_cover_master.py
git commit -m "feat(output): cover_master 提取 (OOXML 片段+槽位预填+图片 base64)"
```

---

## Task 3: 封面母版生成（`_render_cover_master` + 槽位替换 + 图片重嵌入 + 分支优先级）

**Files:**
- Modify: `backend/app/extensions/output/generator.py`
- Test: `backend/tests/test_cover_master.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `test_cover_master.py` 末尾追加：

```python
# ── Task 3: generation ────────────────────────────────────────────────────

def test_render_cover_master_round_trip_replaces_variable():
    """Extract a master from a synthetic table-cover doc, render it into a fresh
    doc with a different client value → client slot replaced, tables present."""
    from app.extensions.output.generator import _render_cover_master

    master = extract_layout_from_docx(_make_table_cover_docx())["cover_master"]
    doc = Document()
    _render_cover_master(doc, master, {"client": "乙公司"}, {})

    assert len(doc.tables) == 2  # banner + 会签 both carried over
    all_text = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
        c.text for t in doc.tables for r in t.rows for c in r.cells
    )
    assert "乙公司" in all_text  # replaced
    assert "甲公司" not in all_text  # old value gone
    assert "消防设计专篇" in all_text  # banner title (literal) preserved


def test_render_cover_master_literal_slot_not_replaced():
    from app.extensions.output.generator import _render_cover_master

    master = {
        "mode": "master", "images": [], "sourceFile": "x", "boundary": "before_toc",
        "xml": '<w:p xmlns:w="%s"><w:r><w:t>建设单位：甲公司</w:t></w:r></w:p>' % "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "slots": [{"id": "client", "label": "建设单位", "kind": "literal", "sampleValue": "甲公司", "defaultFrom": "frontmatter:client"}],
    }
    doc = Document()
    _render_cover_master(doc, master, {"client": "乙公司"}, {})
    assert "甲公司" in "\n".join(p.text for p in doc.paragraphs)  # literal kept
    assert "乙公司" not in "\n".join(p.text for p in doc.paragraphs)


def test_render_cover_master_rewrites_image_embed():
    """A master carrying one base64 image: render re-embeds it and rewrites r:embed."""
    from app.extensions.output.generator import _render_cover_master

    # 1x1 transparent PNG
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    master = {
        "mode": "master", "slots": [], "sourceFile": "x", "boundary": "before_toc",
        "xml": (
            f'<w:p xmlns:w="{w}" xmlns:a="{a}" xmlns:r="{r}"><w:r><w:drawing>'
            f'<a:blip r:embed="rIdOld"/></w:drawing></w:r></w:p>'
        ),
        "images": [{"origRid": "rIdOld", "ext": "png", "b64": png_b64}],
    }
    doc = Document()
    _render_cover_master(doc, master, {}, {})
    # a new image relationship now exists on the document part
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    image_rids = [rid for rid, rel in doc.part.rels.items() if rel.reltype == RT.IMAGE]
    assert image_rids, "image should be re-embedded"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -k "render" -v
```
Expected: FAIL — `ImportError: cannot import name '_render_cover_master'`。

- [ ] **Step 3: 实现 `_render_cover_master` 与槽位替换**

编辑 `backend/app/extensions/output/generator.py`：

(a) 顶部 import 区（第 5-13 行附近）加：
```python
import base64
from io import BytesIO

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree
```

(b) 在 `_render_cover` 之后（约第 157 行后）插入两个函数：

```python
_W_GEN = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DRAWML_GEN = "http://schemas.openxmlformats.org/drawingml/2006/main"
_REL_GEN = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _replace_target_in_para(p_el, target: str, replacement: str) -> bool:
    """Replace `target` with `replacement` across all <w:r>/<w:t> of a <w:p>,
    keeping the first run's <w:rPr> and collapsing text into the first run.
    ponytail: 段落级替换，段落内混合格式（多字体）会丢失——封面槽位通常是
    整行/整格，影响可忽略；升级路径=按 run 边界细粒度替换。"""
    t_els = p_el.findall(f"{{{_W_GEN}}}t")
    full = "".join((t.text or "") for t in t_els)
    if not target or target not in full:
        return False
    runs = p_el.findall(f"{{{_W_GEN}}}r")
    if not runs:
        return False
    first = runs[0]
    for run in runs:  # clear all w:t (keeps rPr/other children)
        for t in run.findall(f"{{{_W_GEN}}}t"):
            run.remove(t)
    new_text = full.replace(target, replacement)
    new_t = etree.SubElement(first, f"{{{_W_GEN}}}t")
    new_t.text = new_text
    new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return True


def _render_cover_master(doc, master: dict, resolved: dict, frontmatter: dict) -> None:
    """Inject the cover-master OOXML fragment at the body start, replacing variable
    slots with resolved project values and re-embedding base64 images."""
    root = etree.fromstring(
        f'<root xmlns:w="{_W_GEN}" xmlns:a="{_DRAWML_GEN}" xmlns:r="{_REL_GEN}">'
        f'{master.get("xml", "")}</root>'
    )

    slot_value = {
        "title": resolved.get("title"),
        "client": resolved.get("client"),
        "project_number": resolved.get("project_number"),
        "date": resolved.get("date"),
        "project_name": frontmatter.get("project_name"),
        "stage": frontmatter.get("stage"),
    }
    for slot in master.get("slots", []):
        if slot.get("kind") != "variable":
            continue
        repl = slot_value.get(slot.get("id"))
        target = slot.get("sampleValue")
        if not repl or not target or str(repl) == target:
            continue
        for p_el in root.iter(f"{{{_W_GEN}}}p"):
            _replace_target_in_para(p_el, target, str(repl))

    for img in master.get("images", []):
        try:
            blob = base64.b64decode(img["b64"])
            result = doc.part.get_or_add_image_part(BytesIO(blob))  # version-stable: part or (part, _)
            image_part = result[0] if isinstance(result, tuple) else result
            new_rid = doc.part.relate_to(image_part, RT.IMAGE)
            for blip in root.iter(f"{{{_DRAWML_GEN}}}blip"):
                if blip.get(f"{{{_REL_GEN}}}embed") == img.get("origRid"):
                    blip.set(f"{{{_REL_GEN}}}embed", new_rid)
        except Exception:  # image must never abort cover generation
            pass

    body = doc.element.body
    for child in reversed(list(root)):  # insert at 0 in reverse → original order
        body.insert(0, deepcopy(child))


# deepcopy is module-level for the import above
from copy import deepcopy  # noqa: E402
```

> 注：`from copy import deepcopy` 放在函数后是为避免与顶部 import 分组规则冲突；若 linter 报 E402，可改成移到文件顶部 import 区（更优）。**推荐**：把 `from copy import deepcopy` 放进第 (a) 步的顶部 import 区，删除函数后的那行 `noqa`。

- [ ] **Step 4: 接分支优先级**

编辑 `generator.py` 的 `has_cover` 分支（第 818-829 行）。把：
```python
    has_cover = bool(template_data.get("cover_template"))
    has_toc = bool(template_data.get("toc_settings"))
    resolved_cover = _resolve_cover_fields(cover_fields or {}, frontmatter, blocks) if has_cover else {}
    numbers = _compute_heading_numbers(blocks, template_data.get("heading_styles", []))

    # === Section 0: COVER ===
    if has_cover:
        try:
            _render_cover(doc, template_data.get("cover_template"), resolved_cover)
        except Exception:  # cover must never abort generation
            pass
        doc.add_section(WD_SECTION.NEW_PAGE)
```
改为：
```python
    cover_master = template_data.get("cover_master")
    has_cover = bool(cover_master or template_data.get("cover_template"))
    has_toc = bool(template_data.get("toc_settings"))
    resolved_cover = _resolve_cover_fields(cover_fields or {}, frontmatter, blocks) if has_cover else {}
    numbers = _compute_heading_numbers(blocks, template_data.get("heading_styles", []))

    # === Section 0: COVER ===
    if has_cover:
        try:
            if cover_master and cover_master.get("mode") == "master":
                _render_cover_master(doc, cover_master, resolved_cover, frontmatter)
            else:
                _render_cover(doc, template_data.get("cover_template"), resolved_cover)
        except Exception:  # cover must never abort generation
            pass
        doc.add_section(WD_SECTION.NEW_PAGE)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py -v
```
Expected: PASS（全部 Task 1-3 测试）。

- [ ] **Step 6: 跑既有 cover 回归 + lint**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cover.py tests/test_output_sections.py -v
cd backend && uv run ruff check app/extensions/output/ tests/test_cover_master.py && uv run ruff format app/extensions/output/ tests/test_cover_master.py
```
Expected: PASS（既有 cover/sections 测试不破坏；ruff 无错）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/extensions/output/generator.py backend/tests/test_cover_master.py
git commit -m "feat(output): cover_master 生成 (OOXML 注入+槽位替换+图片重嵌入+分支优先级)"
```

---

## Task 4: 前端类型 + 转换 + API 接线

**Files:**
- Modify: `frontend/src/extensions/output/types.ts`
- Modify: `frontend/src/extensions/output/transforms.ts`
- Modify: `frontend/src/extensions/output/api.ts`
- Test: `frontend/tests/unit/extensions/output/transforms.test.ts`（新建）

- [ ] **Step 1: 写失败测试**

新建 `frontend/tests/unit/extensions/output/transforms.test.ts`：

```typescript
import { describe, expect, it } from "rstest";

import { transformTemplate } from "@/extensions/output/transforms";

describe("transformTemplate cover_master", () => {
  it("maps top-level cover_master → coverMaster (nested stays camelCase)", () => {
    const data = {
      id: "1",
      name: "T",
      report_type: "general",
      is_builtin: false,
      page_settings: { paperSize: "A4", orientation: "portrait", marginTop: 2.54, marginBottom: 2.54, marginLeft: 3.17, marginRight: 3.17 },
      body_styles: { fontFamily: "宋体", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 6, firstLineIndent: 2 },
      heading_styles: [],
      reference_style: "gb7714",
      created_at: "2026-08-07T00:00:00Z",
      updated_at: "2026-08-07T00:00:00Z",
      cover_master: {
        mode: "master",
        xml: "<w:p/>",
        images: [],
        slots: [{ id: "client", label: "建设单位", kind: "variable", sampleValue: "甲公司", defaultFrom: "frontmatter:client" }],
        sourceFile: "x.docx",
        boundary: "before_toc",
      },
    };
    const tpl = transformTemplate(data as never);
    expect(tpl.coverMaster).not.toBeNull();
    expect(tpl.coverMaster?.sourceFile).toBe("x.docx");
    expect(tpl.coverMaster?.slots[0].sampleValue).toBe("甲公司");
  });

  it("defaults coverMaster to null when absent", () => {
    const tpl = transformTemplate({ id: "1", name: "T", report_type: "g", is_builtin: false, page_settings: {}, body_styles: {}, heading_styles: [], reference_style: "gb7714", created_at: "", updated_at: "" } as never);
    expect(tpl.coverMaster).toBeNull();
  });
});
```

> 前端单测用 **Rstest**（`frontend/AGENTS.md` 明确：`pnpm test` 跑 Rstest；`*.test.ts` 跑在 node 环境，纯逻辑测试用普通 `.test.ts`，不进 happy-dom）。import 从 `rstest` 取，源模块用 `@/` 别名。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd frontend && pnpm test tests/unit/extensions/output/transforms.test.ts
```
Expected: FAIL — `tpl.coverMaster` 为 `undefined`（类型未加 / 转换未加）。

- [ ] **Step 3: 加类型**

编辑 `frontend/src/extensions/output/types.ts`。在 `CoverTemplate` interface（第 33-40 行）之后加：

```typescript
export interface CoverSlot {
  id: string;
  label: string;
  kind: "variable" | "literal";
  sampleValue: string;
  defaultFrom?: string | null;
}

export interface CoverMasterImage {
  origRid: string;
  ext: string;
  b64: string;
}

export interface CoverMaster {
  mode: "master";
  xml: string;
  images: CoverMasterImage[];
  slots: CoverSlot[];
  sourceFile: string;
  boundary: string;
}
```

在 `LayoutTemplate` interface（第 11 行 `coverTemplate` 下）加：
```typescript
  coverMaster: CoverMaster | null;
```

- [ ] **Step 4: 加转换映射**

编辑 `frontend/src/extensions/output/transforms.ts`，在 `coverTemplate: ...` 行（第 10 行）下加：
```typescript
    coverMaster: (data.cover_master as LayoutTemplate["coverMaster"]) ?? null,
```

- [ ] **Step 5: API 载荷透传**

编辑 `frontend/src/extensions/output/api.ts`：
- `createTemplate`：在 `if (tpl.coverTemplate) payload.cover_template = tpl.coverTemplate;`（第 34 行）下加：
  ```typescript
    if (tpl.coverMaster) payload.cover_master = tpl.coverMaster;
  ```
- `updateTemplate`：在 `if (tpl.coverTemplate !== undefined) payload.cover_template = tpl.coverTemplate;`（第 55 行）下加：
  ```typescript
    if (tpl.coverMaster !== undefined) payload.cover_master = tpl.coverMaster;
  ```

- [ ] **Step 6: 运行测试 + typecheck**

```bash
cd frontend && pnpm test tests/unit/extensions/output/transforms.test.ts
cd frontend && pnpm typecheck
```
Expected: 测试 PASS；typecheck 无新增错误。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/extensions/output/types.ts frontend/src/extensions/output/transforms.ts frontend/src/extensions/output/api.ts frontend/tests/unit/extensions/output/transforms.test.ts
git commit -m "feat(output-fe): coverMaster 类型 + 转换 + API 接线"
```

---

## Task 5: 编辑器「封面配置」UX（母版来源 + 槽位列表 + 导入）

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`
- 无前端组件单测（该组件无既有测试惯例）；验证靠 `pnpm typecheck` + 容器重启后手动核对。

- [ ] **Step 1: 加 state + patch 辅助**

编辑 `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`。

(a) 在 `coverTemplate` state（第 314 行）下加：
```typescript
  const [coverMaster, setCoverMaster] = useState<CoverMaster | null>(template?.coverMaster ?? null);
```

(b) 在 `patchCover`（第 329 行）下加槽位 patch 辅助：
```typescript
  const patchSlot = useCallback((index: number, p: Partial<CoverSlot>) => setCoverMaster((m) => (m ? { ...m, slots: m.slots.map((s, i) => (i === index ? { ...s, ...p } : s)) } : m)), []);
```

(c) 在顶部类型 import 区，把 `CoverTemplate` 所在 import 补上 `CoverMaster`、`CoverSlot`（即 `import type { ..., CoverMaster, CoverSlot, CoverTemplate, ... } from "./types";`，按字母序插入）。

- [ ] **Step 2: handleSave 载荷 + applyImported 拾取**

(a) `handleSave`（第 340-353 行的 `await onSave({...})`）在 `coverTemplate,` 行下加 `coverMaster,`；并把它加入依赖数组（第 357 行 `}, [name, ..., coverTemplate, ...]`）。

(b) `applyImported`（第 359-377 行）在末尾 `}` 前加（拾取 cover_master，且不再用旧 toggle 兜底覆盖已有母版）：
```typescript
    const cm = data.cover_master as CoverMaster | null | undefined;
    if (cm && cm.mode === "master") {
      setCoverMaster(cm);
    } else {
      // 无母版时才走旧 toggle 兜底（保留既有行为）
      const ct = data.cover_template as CoverTemplate | null | undefined;
      if (data.cover_detected === true && ct && (ct.showLogo || ct.showTitle || ct.showClient || ct.showDate || ct.showProjectNumber)) {
        setCoverTemplate(ct);
      }
    }
```
并删除上面原有的旧 `const ct = ...; if (data.cover_detected ...) setCoverTemplate(ct);` 那段（被新逻辑取代）。把 `coverMaster` 加入 `applyImported`/`handleImportedFile` 依赖（`useCallback` 依赖数组加 `setCoverMaster` 无需，因 setState 稳定；`applyImported` 依赖数组保持 `[]` 即可，因为它只用 setter）。

- [ ] **Step 3: 重写「封面配置」Section**

把第 598-623 行整段 `{/* 封面配置 */}` Section 替换为：

```tsx
          {/* 封面配置 */}
          <Section icon={ImageIcon} title="封面配置">
            {coverMaster ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate text-muted-foreground">来自样例：<span className="font-medium text-foreground">{coverMaster.sourceFile || "（未命名）"}</span></span>
                  <span className="ml-auto shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{coverMaster.boundary === "before_toc" ? "目录前" : "首标题前"}</span>
                </div>
                <div className="space-y-1.5">
                  <p className="text-[11px] font-medium text-muted-foreground">槽位（生成时替换"变量"，保留"字面"）</p>
                  {coverMaster.slots.map((slot, i) => (
                    <div key={slot.id} className="flex items-center gap-2 rounded-lg border border-border px-2 py-1.5">
                      <span className="w-16 shrink-0 text-[11px] font-medium text-muted-foreground">{slot.label}</span>
                      <input
                        className="h-7 flex-1 rounded-md border border-border bg-background px-2 text-xs disabled:opacity-50"
                        value={slot.sampleValue}
                        onChange={(e) => patchSlot(i, { sampleValue: e.target.value })}
                        disabled={slot.kind === "literal"}
                      />
                      <button
                        type="button"
                        onClick={() => patchSlot(i, { kind: slot.kind === "variable" ? "literal" : "variable" })}
                        className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-medium ring-1 ring-inset ring-border transition-colors hover:bg-muted ${slot.kind === "variable" ? "text-primary" : "text-muted-foreground"}`}
                        title={slot.kind === "variable" ? "点击切为字面（原样保留不替换）" : "点击切为变量（生成时替换）"}
                      >
                        {slot.kind === "variable" ? "变量" : "字面"}
                      </button>
                    </div>
                  ))}
                </div>
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={importing} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50">
                  <Upload className="h-3.5 w-3.5" />
                  {importing ? "提取中…" : "重新从样例导入封面"}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <Toggle checked={coverTemplate?.showLogo ?? false} onChange={(v) => patchCover({ showLogo: v })} label="显示 Logo" icon={ImageIcon} />
                  <Toggle checked={coverTemplate?.showTitle ?? false} onChange={(v) => patchCover({ showTitle: v })} label="显示标题" icon={Type} />
                  <Toggle checked={coverTemplate?.showClient ?? false} onChange={(v) => patchCover({ showClient: v })} label="显示建设单位" />
                  <Toggle checked={coverTemplate?.showDate ?? false} onChange={(v) => patchCover({ showDate: v })} label="显示日期" />
                  <Toggle checked={coverTemplate?.showProjectNumber ?? false} onChange={(v) => patchCover({ showProjectNumber: v })} label="显示项目编号" />
                </div>
                {((coverTemplate?.showLogo ?? false) || (coverTemplate?.showTitle ?? false) || (coverTemplate?.showClient ?? false) || (coverTemplate?.showDate ?? false) || (coverTemplate?.showProjectNumber ?? false)) && (
                  <div className="rounded-lg bg-muted/30 p-5">
                    <p className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">预览</p>
                    <div className="mx-auto max-w-[240px] space-y-2.5 text-center">
                      {coverTemplate?.showLogo && (
                        <div className="mx-auto flex h-12 w-20 items-center justify-center rounded-md bg-primary/10 text-[10px] font-medium text-primary ring-1 ring-inset ring-primary/15">LOGO</div>
                      )}
                      {coverTemplate?.showTitle && <div className="text-lg font-bold text-foreground">报告标题</div>}
                      <div className="space-y-1.5 pt-1 text-xs text-muted-foreground">
                        {coverTemplate?.showClient && <div>建设单位：XXXX</div>}
                        {coverTemplate?.showDate && <div>日期：2026-08</div>}
                        {coverTemplate?.showProjectNumber && <div>项目编号：XXXX</div>}
                      </div>
                    </div>
                  </div>
                )}
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={importing} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/5 disabled:opacity-50">
                  <Upload className="h-3.5 w-3.5" />
                  {importing ? "提取中…" : "从样例 .docx 导入真实封面"}
                </button>
              </div>
            )}
          </Section>
```

> 确认 `Upload` 图标已 import（顶部 lucide-react import）。若未 import，在图标 import 行加 `Upload`。`Type`、`ImageIcon`、`FileText` 已在用。

- [ ] **Step 4: typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 无新增错误（`CoverMaster`/`CoverSlot` 已在 Task 4 的 types.ts 定义并被 import）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output-fe): 封面配置母版UX (来源+槽位列表+导入按钮)"
```

---

## Task 6: 容器重启 + 真实样例端到端验证

**Files:** 无（运行验证）。

- [ ] **Step 1: 重启 gateway（触发 migrate_db 加列）+ frontend**

```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker restart frontend
```
等待就绪：
```bash
until curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/api/health | grep -q 200; do sleep 2; done; echo READY
```

- [ ] **Step 2: 确认列已加**

```bash
docker exec $(docker compose -p eai-docker ps -q postgres-ext 2>/dev/null || docker compose -p eai-docker ps -q postgres 2>/dev/null) psql -U agentflow -d agentflow -c "\d layout_templates" | grep cover_master
```
Expected: 输出含 `cover_master | jsonb`。若 postgres 容器名不同，用 `docker compose -p eai-docker ps` 找出 postgres 容器名替换。

- [ ] **Step 3: 本机跑真实样例提取单测**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_cover_master.py::test_extract_real_sample_cover_master -v
```
Expected: PASS（SAMPLE 本机存在，跑金标准测试）。**若失败**：按 Task 2 Step 4 的排查指引微调边界/标题启发式，修后重跑直至通过——这是"对照真实样例"铁律的硬门。

- [ ] **Step 4: 手动 UI 验证（对照真实样例）**

浏览器开 `http://localhost:2026`（admin / Admin@2026），进报告输出扩展 → 新建/编辑排版模板：
1. 「封面配置」点「从样例 .docx 导入真实封面」，选 `backend/data/users/.../基地项目-消防设计专篇.docx`。
2. 确认切到母版视图：来源行显示文件名 + "目录前"徽章；槽位列表含「报告标题」等（靶文本可编辑、变量⇄字面切换）；底部「重新从样例导入封面」按钮。
3. 保存模板 → 重新打开编辑 → 确认母版与槽位持久化。
4. 用该模板生成一份报告（Markdown 源即可），下载 .docx，用 Word 打开：封面应含**两张原样表**（标题横幅 + 编制会签表），报告标题/建设单位等变量按生成参数替换，会签表原样保留。

- [ ] **Step 5: OpenWolf 收尾**

更新 `.wolf/anatomy.md`（新增 `test_cover_master.py`；改动文件描述）、`.wolf/memory.md`（追加本次实施一行）、若遇 bug 追加 `.wolf/buglog.json`、若发现约定追加 `.wolf/cerebrum.md`。

- [ ] **Step 6: 推送（main-dev-fork）**

```bash
git push origin main-dev-fork
```
若 push flaky（curl 55），按 [[origin-push-postbuffer-fix]]：`git config http.postBuffer 524288000` 后重试，用 `git rev-list --left-right --count origin/main-dev-fork...HEAD` 确认同步。

---

## Self-Review（写计划后自查）

**1. Spec 覆盖**
- §4 数据模型 → Task 1（schema/列）+ Task 4（前端类型）。✓
- §4.2 生成优先级（cover_master > cover_template > 无）→ Task 3 Step 4。✓
- §5 提取（边界/序列化/图片/槽位预填/组装）→ Task 2。✓（含 TOC-style 边界 + 退化启发式，比 spec 更稳）
- §5.4 六槽位规则 → Task 2 `_prefill_cover_slots`。✓
- §6 生成（解析/槽位替换/注入/图片重嵌入/分节）→ Task 3。✓（分节复用既有 `doc.add_section`）
- §6.2 project_name/stage 从 frontmatter → Task 3 `_render_cover_master` 签名带 frontmatter。✓
- §7 编辑器 UX → Task 5。✓
- §8 受影响文件 → 全覆盖（含 spec 漏掉的 `_build_template_data`、service create/duplicate、database migrate）。✓
- §9 测试 → Task 1-3 的 `test_cover_master.py`（提取/生成/边界/替换/图片 + 真实样例 skipif）。✓
- §10 风险（边界误判→退化启发式；跨 run 丢格式→ponytail 注释；rId 重写→单测）→ 均落地。✓

**2. 占位符扫描**：无 TBD/TODO；每个改代码步骤都给了完整代码或精确 Edit 指令；测试代码完整。✓

**3. 类型一致性**：
- 槽位字段全链路 camelCase：`CoverSlotSchema.sampleValue` ↔ `CoverSlot.sampleValue` ↔ 提取 dict `"sampleValue"` ↔ 生成 `slot["sampleValue"]`。✓
- `CoverMaster.origRid`（camelCase）↔ 提取 `images:[{origRid}]` ↔ 生成 `img["origRid"]`。✓
- `_render_cover_master(doc, master, resolved, frontmatter)` 签名与 Task 3 调用一致。✓
- `_extract_cover_master(doc, source_file)` 与 `extract_layout_from_docx(data, source_file)` 一致。✓
- 前端 `coverMaster` state / `patchSlot` / `applyImported` / `handleSave` 字段名一致。✓

**已知风险/降级**：真实样例若目录页是 TOC 字段（非普通"目录"段落），`test_extract_real_sample_cover_master` 在 Task 2 Step 4 / Task 6 Step 3 会暴露，届时微调 `_TOC_TEXT_RE` 或加 TOC 字段识别——已在相应步骤标注排查路径，不放宽到误吃正文。
