# Word 样例自动提取排版 + 两对话框补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供共享的「上传 .docx 样例 → 提取排版参数」后端能力，接入报告输出模板编辑器（含目录设置 UI + 封面预览），并修好 docmgr 导出对话框的「导入排版」坏按钮与「保存为模板丢参」。

**Architecture:** 后端新增确定性 python-docx 提取函数 `output/layout_import.py`（页面/正文/标题/表格/页眉页脚 + 封面结构检测 A+C 兜底），由两个端点各自权限调用：`POST /api/extensions/output/import-layout`（`system:access`，报告输出编辑器用）、`POST /api/extensions/docmgr/import-layout`（`doc:upload` 薄封装，修好 docmgr 坏按钮）。前端报告输出编辑器加导入按钮/目录设置区/封面预览；docmgr 对话框修保存模板持久化 toc/cover。

**Tech Stack:** Python 3.12 / FastAPI / python-docx（已有依赖 ≥1.2.0）/ TypeScript / React 19 / Next.js 16。

**分支:** `main-dev-fork`（本项目所有代码提交到该分支，不提交到 main）。

---

### Task 1: 后端提取模块 `layout_import.py` + 单元测试

**Files:**
- Create: `backend/app/extensions/output/layout_import.py`
- Test: `backend/tests/test_output_layout_import.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_output_layout_import.py`:

```python
"""Tests for deterministic .docx → layout-template extraction."""

from io import BytesIO

import pytest
from docx import Document
from docx.shared import Cm, Pt

from app.extensions.output.layout_import import extract_layout_from_docx


def _docx_bytes(doc: Document) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_docx(*, body_font: str | None = None, heading_font: str | None = None, with_table: bool = False) -> bytes:
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    s.top_margin = Cm(2.0)
    s.bottom_margin = Cm(2.0)
    s.left_margin = Cm(3.0)
    s.right_margin = Cm(3.0)
    if body_font:
        normal = doc.styles["Normal"]
        normal.font.name = body_font
        normal.font.size = Pt(12)
    if heading_font:
        h1 = doc.styles["Heading 1"]
        h1.font.name = heading_font
        h1.font.size = Pt(16)
    if with_table:
        doc.add_table(rows=2, cols=2)
    doc.add_heading("第一章 概述", level=1)
    doc.add_paragraph("这是正文内容，用于测试提取。")
    return _docx_bytes(doc)


def data_for(**kw):
    return extract_layout_from_docx(_make_docx(**kw))


def test_extracts_page_settings():
    data = extract_layout_from_docx(_make_docx())
    ps = data["page_settings"]
    assert ps["paperSize"] == "A4"
    assert ps["orientation"] == "portrait"
    assert ps["marginTop"] == 2.0
    assert ps["marginBottom"] == 2.0
    assert ps["marginLeft"] == 3.0
    assert ps["marginRight"] == 3.0


def test_extracts_body_and_heading_fonts():
    data = extract_layout_from_docx(_make_docx(body_font="SimSun", heading_font="SimHei"))
    assert data["body_styles"]["fontSize"] == 12
    assert data["body_styles"]["fontFamily"] == "SimSun"
    h1 = data["heading_styles"][0]
    assert h1["level"] == 1
    assert h1["fontFamily"] == "SimHei"
    assert h1["fontSize"] == 16
    assert h1["numbering"] == "decimal"


def test_table_style_present_only_when_table_exists():
    assert data_for(with_table=True)["table_styles"] is not None
    assert data_for(with_table=True)["table_styles"]["stripeRows"] is True
    assert data_for()["table_styles"] is None


def test_figure_styles_null():
    assert data_for()["figure_styles"] is None


def test_no_cover_detected_for_plain_document():
    assert data_for()["cover_detected"] is False


def test_cover_detected_for_first_page_cover():
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    title = doc.add_paragraph("某化工项目消防设计专篇")
    title.runs[0].font.size = Pt(22)
    doc.add_paragraph("建设单位：某某公司")
    doc.add_paragraph("项目编号：P001")
    doc.add_paragraph("2026-08-01")
    doc.add_heading("第一章 概述", level=1)
    data = extract_layout_from_docx(_docx_bytes(doc))
    assert data["cover_detected"] is True
    ct = data["cover_template"]
    assert ct["showTitle"] is True
    assert ct["showClient"] is True
    assert ct["showProjectNumber"] is True
    assert ct["showDate"] is True


def test_rejects_non_docx_bytes():
    with pytest.raises(ValueError):
        extract_layout_from_docx(b"this is definitely not a docx file")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.extensions.output.layout_import'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/extensions/output/layout_import.py`:

```python
"""Deterministic .docx → layout-template extraction.

Reads page settings, body/heading styles, table style, header/footer, and
best-effort cover structure from a sample .docx and returns a
LayoutTemplate-shaped dict (snake_case) consumed by the output/docmgr
``import-layout`` endpoints. Pure python-docx, no new dependencies.
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

_PAPER_DIMS = {
    "A4": (21.0, 29.7),
    "A3": (29.7, 42.0),
    "B5": (17.6, 25.0),
    "letter": (21.59, 27.94),
}
_DRAWML = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _to_cm(length) -> float:
    """python-docx Length (EMU) → cm, rounded to 2 decimals."""
    return round(length.cm, 2) if length is not None else 0.0


def _paper_from_dimensions(width_cm: float, height_cm: float) -> tuple[str, str]:
    """Map page width/height (cm) → (paperSize, orientation)."""
    orientation = "landscape" if width_cm > height_cm else "portrait"
    w, h = (height_cm, width_cm) if width_cm > height_cm else (width_cm, height_cm)
    best, best_err = "A4", float("inf")
    for name, (pw, ph) in _PAPER_DIMS.items():
        err = abs(w - pw) + abs(h - ph)
        if err < best_err:
            best, best_err = name, err
    return best, orientation


def _style_font(style) -> str:
    """eastAsia-first font name for a docx style (CJK samples set w:eastAsia)."""
    try:
        m = re.search(r'w:eastAsia="([^"]+)"', style.element.xml)
        if m:
            return m.group(1)
    except Exception:
        pass
    return style.font.name or "宋体"


def _style_color(style, default: str) -> str:
    try:
        rgb = style.font.color.rgb
        if rgb is not None:
            return str(rgb)
    except Exception:
        pass
    return default


def _extract_body_styles(doc) -> dict:
    style = doc.styles["Normal"]
    pf = style.paragraph_format
    size = style.font.size.pt if style.font.size else None
    ls = pf.line_spacing
    line_spacing = round(float(ls), 2) if isinstance(ls, float) and ls else 1.5
    sa = pf.space_after.pt if pf.space_after else None
    return {
        "fontFamily": _style_font(style),
        "fontSize": int(size) if size else 12,
        "lineHeight": line_spacing,
        "paragraphSpacing": int(sa) if sa else 6,
        "firstLineIndent": 2,  # ponytail: char indent not reliably derivable → default
    }


def _extract_heading_styles(doc) -> list[dict]:
    defaults = {1: 16, 2: 14, 3: 12, 4: 12}
    out = []
    for level in range(1, 5):
        try:
            style = doc.styles[f"Heading {level}"]
        except KeyError:
            continue
        size = style.font.size.pt if style.font.size else None
        out.append(
            {
                "level": level,
                "fontFamily": _style_font(style),
                "fontSize": int(size) if size else defaults[level],
                "fontWeight": 700 if style.font.bold else 400,
                "color": _style_color(style, "#333333"),
                "numbering": "decimal",
            }
        )
    return out


def _extract_table_styles(doc) -> dict | None:
    if not doc.tables:
        return None
    try:
        cell = doc.tables[0].rows[0].cells[0]
        tc_pr = cell._tc.tcPr
        shd = tc_pr.find(qn("w:shd")) if tc_pr is not None else None
        header_bg = shd.get(qn("w:fill")) if shd is not None else None
    except Exception:
        header_bg = None
    return {
        "headerBg": f"#{header_bg}" if header_bg else "#2B579A",
        "headerColor": "#FFFFFF",
        "borderColor": "#CCCCCC",
        "stripeRows": True,  # ponytail: zebra striping not derivable from docx → default
    }


def _extract_header_footer(doc) -> dict:
    section = doc.sections[0]

    def _text(part) -> str:
        if part is None:
            return ""
        return " ".join(p.text.strip() for p in part.paragraphs if p.text.strip())

    def _has_page_field(part) -> bool:
        if part is None:
            return False
        try:
            return "PAGE" in part._element.xml
        except Exception:
            return False

    return {
        "headerText": _text(section.header),
        "footerText": _text(section.footer),
        "showPageNumber": _has_page_field(section.footer) or _has_page_field(section.header),
        "showLogo": False,  # ponytail: header logo detection omitted
    }


def _para_has_image(para) -> bool:
    return bool(para._p.findall(f".//{{{_DRAWML}}}blip"))


def _para_align(para) -> str:
    if para.alignment == WD_ALIGN_PARAGRAPH.LEFT:
        return "left"
    if para.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
        return "right"
    return "center"


def _detect_cover(doc) -> dict | None:
    """Best-effort cover detection from the first page.

    Returns None (fallback C) when no cover-like structure is found — the
    caller then leaves the cover section untouched rather than guessing.
    """
    section = doc.sections[0]
    try:
        different_first = bool(section.different_first_page_header_footer)
    except Exception:
        different_first = False

    pre: list = []
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            break
        if p.text.strip():
            pre.append(p)

    if not different_first and len(pre) < 3:
        return None

    cover: dict = {
        "showLogo": False,
        "logoPosition": "center",
        "showTitle": False,
        "showClient": False,
        "showDate": False,
        "showProjectNumber": False,
    }
    if not pre:
        return cover

    first = pre[0]
    cover["showLogo"] = _para_has_image(first)
    cover["logoPosition"] = _para_align(first)

    title_para = max(pre, key=lambda p: (p.runs[0].font.size.pt if p.runs and p.runs[0].font.size else 0))
    if title_para.runs and title_para.runs[0].font.size and title_para.runs[0].font.size.pt >= 14:
        cover["showTitle"] = True

    for p in pre:
        text = p.text
        if re.search(r"(建设单位|单位|公司|业主|client)", text, re.I):
            cover["showClient"] = True
        if re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{0,2}日?|日期)", text):
            cover["showDate"] = True
        if re.search(r"(项目编号|编号|项目号|工程号|number)", text, re.I):
            cover["showProjectNumber"] = True
    return cover


def extract_layout_from_docx(data: bytes) -> dict:
    """Parse a .docx byte stream → LayoutTemplate data subset (snake_case).

    Raises ValueError for non-.docx / unparseable input.
    """
    try:
        doc = Document(BytesIO(data))
    except Exception as exc:
        raise ValueError("无法解析该文件，请确保为 .docx 格式") from exc

    section = doc.sections[0]
    paper, orientation = _paper_from_dimensions(_to_cm(section.page_width), _to_cm(section.page_height))
    cover = _detect_cover(doc)

    return {
        "page_settings": {
            "paperSize": paper,
            "orientation": orientation,
            "marginTop": _to_cm(section.top_margin),
            "marginBottom": _to_cm(section.bottom_margin),
            "marginLeft": _to_cm(section.left_margin),
            "marginRight": _to_cm(section.right_margin),
        },
        "body_styles": _extract_body_styles(doc),
        "heading_styles": _extract_heading_styles(doc),
        "table_styles": _extract_table_styles(doc),
        "figure_styles": None,
        "header_footer": _extract_header_footer(doc),
        "cover_template": cover,
        "cover_detected": cover is not None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/layout_import.py backend/tests/test_output_layout_import.py
git commit -m "feat(output): 确定性 docx→排版参数提取 (layout_import) + 单测"
```

---

### Task 2: 报告输出 `POST /import-layout` 端点

**Files:**
- Modify: `backend/app/extensions/output/routers.py`
- Test: `backend/tests/test_output_layout_import.py`（追加路由注册测试）

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_output_layout_import.py`:

```python
def test_output_router_registers_import_layout():
    from app.extensions.output.routers import router

    paths = set()
    for route in router.routes:
        for method in getattr(route, "methods", None) or set():
            paths.add((route.path, method))
    assert ("/api/extensions/output/import-layout", "POST") in paths, "output import-layout route missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py::test_output_router_registers_import_layout -v`
Expected: FAIL (route not registered yet)

- [ ] **Step 3: Add the endpoint**

In `backend/app/extensions/output/routers.py`:

1. Add the import at the top (alphabetical, with the other `app.extensions.output` imports):
```python
from app.extensions.output.layout_import import extract_layout_from_docx
```

2. Add this route after `duplicate_template` (before the `# --- Report Generation ---` block):

```python
@router.post("/import-layout")
async def import_layout(
    file: UploadFile = File(...),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Upload a .docx sample → deterministic layout-template extraction (5 groups + cover detection)."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 10MB")
    try:
        return extract_layout_from_docx(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

注：`File` / `UploadFile` / `HTTPException` / `require_permission` / `CurrentUser` 已在该文件 import（第 11、16、20、26 行）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/output/routers.py backend/tests/test_output_layout_import.py
git commit -m "feat(output): POST /api/extensions/output/import-layout 端点"
```

---

### Task 3: docmgr `POST /import-layout` 薄封装（修坏按钮）

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`
- Test: `backend/tests/test_docmgr_export.py`（追加路由注册测试）

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_docmgr_export.py`:

```python
def test_docmgr_router_registers_import_layout():
    """POST /import-layout must be registered — the ExportDocxDialog 导入排版 button depends on it."""
    from app.extensions.docmgr.routers import router

    paths = set()
    for route in router.routes:
        for method in getattr(route, "methods", None) or set():
            paths.add((route.path, method))
    assert (
        "/api/extensions/docmgr/import-layout",
        "POST",
    ) in paths, "docmgr import-layout route is missing — 导入排版 button 404s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py::test_docmgr_router_registers_import_layout -v`
Expected: FAIL (route missing — this is the dead button)

- [ ] **Step 3: Add the endpoint**

In `backend/app/extensions/docmgr/routers.py`:

1. Extend the fastapi import on line 9:
```python
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
```

2. Add this route after the `list_cover_presets` endpoint (line ~301) and before the `ExportRequest` class:

```python
@router.post("/import-layout")
async def import_layout_docmgr(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Thin pass-through to the shared output layout extractor.

    Fixes the ExportDocxDialog「导入排版」dead button — this route was specified
    in 2026-06-09-docmgr-word-export-layout-design.md but never implemented.
    """
    from app.extensions.output.layout_import import extract_layout_from_docx

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 10MB")
    try:
        return extract_layout_from_docx(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

注：`require_permission` / `CurrentUser` 已 import（第 15、21 行）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py -v`
Expected: PASS (原有测试 + 新增 1 条)

- [ ] **Step 5: Run backend lint + full test sweep**

Run:
```bash
cd backend && make lint
cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py tests/test_docmgr_export.py tests/test_output_routers.py -v
```
Expected: lint clean + all pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/docmgr/routers.py backend/tests/test_docmgr_export.py
git commit -m "fix(docmgr): 实现 POST /import-layout 薄封装 — 修好导入排版坏按钮"
```

---

### Task 4: 前端 `output/api.ts` — `importLayout` 方法

**Files:**
- Modify: `frontend/src/extensions/output/api.ts`

- [ ] **Step 1: Add the method**

In `frontend/src/extensions/output/api.ts`, inside the `outputApi` object, after `getTemplate`:

```ts
  importLayout: async (file: File): Promise<Record<string, unknown>> => {
    const form = new FormData();
    form.append("file", file);
    return authFormFetch<Record<string, unknown>>(`${API_BASE}/import-layout`, form);
  },
```

`authFormFetch` 已 import（第 1 行 `import { authFetch, authFormFetch } from "@/extensions/api/client";`）。

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/output/api.ts
git commit -m "feat(output): api.importLayout 方法"
```

---

### Task 5: LayoutTemplateEditor — 导入按钮 + 应用提取结果

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`

- [ ] **Step 1: Update imports + add state/callbacks**

`frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`:

1. lucide import（第 3 行）加 `FileUp`:
```tsx
import { ChevronDown, ChevronRight, FileUp, Loader2 } from "lucide-react";
```

2. react import（第 4 行）加 `useRef`:
```tsx
import React, { useCallback, useRef, useState } from "react";
```

3. 新增 sonner import（在 `import { cn } from "@/lib/utils";` 之前）:
```tsx
import { toast } from "sonner";
```

4. 在 `const [saving, setSaving] = useState(false);`（第 135 行）后加 state:
```tsx
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
```

5. 在 `handleSave` 回调后（第 158 行 `}, [...onSave]);` 之后）加两个回调:
```tsx
  const applyImported = useCallback((data: Record<string, unknown>) => {
    const ps = data.page_settings as PageSettings | undefined;
    if (ps) setPageSettings(ps);
    const bs = data.body_styles as BodyStyles | undefined;
    if (bs) setBodyStyles(bs);
    const hs = data.heading_styles as HeadingStyle[] | undefined;
    if (hs?.length) setHeadingStyles(hs.map((h) => ({ ...h })));
    const ts = data.table_styles as TableStyles | null | undefined;
    if (ts) setTableStyles(ts);
    const ff = data.figure_styles as FigureStyles | null | undefined;
    if (ff) setFigureStyles(ff);
    const hf = data.header_footer as HeaderFooter | null | undefined;
    if (hf) setHeaderFooter(hf);
    // 封面方案 A+C 兜底：cover_detected=false 时不动封面区
    if (data.cover_detected === true) {
      const ct = data.cover_template as CoverTemplate | null | undefined;
      if (ct) setCoverTemplate(ct);
    }
  }, []);

  const handleImportedFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setImporting(true);
      try {
        const { outputApi } = await import("@/extensions/output/api");
        const data = await outputApi.importLayout(file);
        applyImported(data);
        toast.success("已从样例文档提取排版");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "无法从该文件提取排版信息");
      } finally {
        setImporting(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [applyImported],
  );
```

- [ ] **Step 2: Add button + hidden input in 基本信息 section**

在「基本信息」Section 的 `reportType` 那个 `<div>`（第 193-196 行）之后、该 Section 的 `</div>`（第 197 行）之前插入:

```tsx
              <div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={importing}
                    className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                    {importing ? "提取中..." : "从样例导入排版"}
                  </button>
                  <span className="text-xs text-muted-foreground">上传 .docx 样例自动提取排版参数</span>
                </div>
                <input ref={fileInputRef} type="file" accept=".docx" onChange={handleImportedFile} className="hidden" />
              </div>
```

- [ ] **Step 3: Verify typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: no new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output): 模板编辑器「从样例导入排版」按钮 + 应用提取结果"
```

---

### Task 6: LayoutTemplateEditor — 目录设置 UI

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`

- [ ] **Step 1: Add 目录设置 Section**

在「页眉页脚」Section（第 294 行 `</Section>`）之后、「参考文献与附录」Section（第 296 行）之前插入:

```tsx
          {/* 目录设置 */}
          <Section title="目录设置">
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={tocSettings !== null}
                  onChange={(e) => setTocSettings(e.target.checked ? { maxDepth: 3, showPageNumbers: true, leaderDots: true } : null)}
                  className="rounded"
                />
                包含目录
              </label>
              {tocSettings && (
                <>
                  <div>
                    <FieldLabel>收录级别</FieldLabel>
                    <AdminSelect
                      value={String(tocSettings.maxDepth)}
                      onChange={(v) => setTocSettings({ ...tocSettings, maxDepth: Number(v) })}
                      options={[1, 2, 3, 4].map((n) => ({ value: String(n), label: `${n} 级` }))}
                      className="w-full"
                    />
                  </div>
                  <div className="flex gap-6">
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={tocSettings.showPageNumbers} onChange={(e) => setTocSettings({ ...tocSettings, showPageNumbers: e.target.checked })} className="rounded" />
                      显示页码
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={tocSettings.leaderDots} onChange={(e) => setTocSettings({ ...tocSettings, leaderDots: e.target.checked })} className="rounded" />
                      目录点线
                    </label>
                  </div>
                </>
              )}
            </div>
          </Section>
```

- [ ] **Step 2: Verify typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output): 模板编辑器补「目录设置」区块 (tocSettings UI)"
```

---

### Task 7: LayoutTemplateEditor — 极简封面预览

**Files:**
- Modify: `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`

- [ ] **Step 1: Add cover preview inside 封面配置**

在「封面配置」Section 的 checkbox grid `</div>`（第 231 行）之后、该 Section 的 `</Section>` 之前插入:

```tsx
            {/* 极简封面预览 */}
            {(coverTemplate?.showLogo || coverTemplate?.showTitle || coverTemplate?.showClient || coverTemplate?.showDate || coverTemplate?.showProjectNumber) && (
              <div className="mt-3 rounded-lg border border-dashed border-border bg-muted/30 p-4">
                <p className="mb-2 text-xs font-medium text-muted-foreground">预览</p>
                <div className="mx-auto max-w-[220px] space-y-2 text-center">
                  {coverTemplate?.showLogo && (
                    <div className="mx-auto flex h-10 w-16 items-center justify-center rounded bg-primary/10 text-[10px] text-muted-foreground">LOGO</div>
                  )}
                  {coverTemplate?.showTitle && <div className="text-base font-bold text-foreground">报告标题</div>}
                  <div className="space-y-1 text-xs text-muted-foreground">
                    {coverTemplate?.showClient && <div>建设单位：XXXX</div>}
                    {coverTemplate?.showDate && <div>日期：2026-08</div>}
                    {coverTemplate?.showProjectNumber && <div>项目编号：XXXX</div>}
                  </div>
                </div>
              </div>
            )}
```

- [ ] **Step 2: Verify typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/output/components/LayoutTemplateEditor.tsx
git commit -m "feat(output): 模板编辑器封面极简预览"
```

---

### Task 8: ExportDocxDialog — 保存为模板持久化 toc/cover

**Files:**
- Modify: `frontend/src/extensions/docmgr/ExportDocxDialog.tsx`

- [ ] **Step 1: Rewrite the save-as-template block**

替换 `handleExport` 里的 `if (saveAsTemplate && templateName.trim()) { ... }` 块（第 445-461 行）：

```tsx
      if (saveAsTemplate && templateName.trim()) {
        const { outputApi } = await import("@/extensions/output/api");
        // 封面：活动预设字段 → CoverTemplate 5 开关（尽力映射；预设值仍在导出时按 default_from 填）
        const coverTpl =
          coverPresetId && activeCoverPreset
            ? {
                showLogo: false,
                logoPosition: "center" as const,
                showTitle: activeCoverPreset.fields.some((f) => /title/i.test(f.name)),
                showClient: activeCoverPreset.fields.some((f) => /client|unit|业主|单位/i.test(f.name)),
                showDate: activeCoverPreset.fields.some((f) => /date/i.test(f.name)),
                showProjectNumber: activeCoverPreset.fields.some((f) => /number|编号/i.test(f.name)),
              }
            : null;
        await outputApi.createTemplate({
          name: templateName.trim(),
          reportType: "general",
          pageSettings,
          bodyStyles,
          headingStyles,
          tableStyles,
          figureStyles,
          headerFooter,
          referenceStyle: "gb7714",
          coverTemplate: coverTpl,
          tocSettings: withToc ? { maxDepth: tocDepth, showPageNumbers: true, leaderDots: true } : null,
          appendixRules: null,
        });
      }
```

`activeCoverPreset` / `coverPresetId` / `withToc` / `tocDepth` 均已在组件内定义。

- [ ] **Step 2: Verify typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/ExportDocxDialog.tsx
git commit -m "fix(docmgr): 保存为模板持久化 tocSettings + coverTemplate（不再丢参）"
```

---

### Task 9: 全量验证

**Files:** 无代码改动

- [ ] **Step 1: 后端 lint + 全量相关测试**

Run:
```bash
cd backend && make lint
cd backend && PYTHONPATH=. uv run pytest tests/test_output_layout_import.py tests/test_output_routers.py tests/test_output_cover.py tests/test_docmgr_export.py tests/test_output_generate_integration.py -v
```
Expected: lint clean + all pass

- [ ] **Step 2: 前端 typecheck + lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: no new errors

- [ ] **Step 3: Docker 重启生效**

Run:
```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker restart frontend
```

- [ ] **Step 4: 冒烟验证（可选，人工）**

1. 打开 `http://localhost:2026/output?tab=templates` → 新建模板 → 点「从样例导入排版」上传一个 .docx → 表单被填充，封面区按样例开关变化
2. 打开文档空间 → 任一文档 → 导出 Word → 点「导入排版」上传 .docx → toast「已从文档导入排版设置」（不再 404）
3. 文档空间导出对话框：选目录 + 封面预设 → 勾「保存为排版模板」→ 到报告输出模板列表验证 tocSettings/封面已保存

- [ ] **Step 5: 更新 .wolf 记录**

```bash
# 按 OpenWolf 协议追加 memory.md 一行 + 更新 anatomy.md（新增 layout_import.py）
```

- [ ] **Step 6: 收尾提交（如 .wolf 变更）**

```bash
git add .wolf/memory.md .wolf/anatomy.md
git commit -m "chore(wolf): 记录 word-export-layout-import 实施"
```
