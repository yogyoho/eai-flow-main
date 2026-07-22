# 文档空间 Word 导出目录(TOC)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 文档空间「我的文档 → 文档编辑页 → 导出 Word」支持按 markdown 标题(`#`/`##`/`###`)可选生成 Word 目录,默认关闭。

**Architecture:** 复用 `generate_docx()` 已有的目录 helper(`_render_toc` + `_set_update_fields`),给 `generate_docx_simple()` 加 `toc_settings` 开关;docmgr 两个导出端点的请求模型加 `with_toc`/`toc_depth`,透传 `toc_settings`;导出弹窗 `ExportDocxDialog.tsx` 加「包含目录」勾选框 + 深度下拉。目录是 Word 域,Word/WPS 打开自动更新页码。

**Tech Stack:** Python 3.12 + python-docx(FastAPI 后端)、React 19 + TypeScript + Tailwind(Next.js 前端)、pytest / Rstest。

**关联设计:** `docs/superpowers/specs/2026-07-22-docmgr-export-toc-design.md`

**分支:** `main-dev-fork`(已在上面,所有提交到此分支)。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `backend/app/extensions/output/generator.py` | `generate_docx_simple` 增加 `toc_settings` 形参,条件渲染目录 + 分页 + `updateFields` | 修改 |
| `backend/app/extensions/docmgr/routers.py` | `ExportRequest` / `ExportContentRequest` 增加 `with_toc` / `toc_depth`;两处调用点透传 `toc_settings` | 修改 |
| `backend/tests/test_docmgr_export.py` | 目录生成 / 不生成 的回归断言 + 请求模型字段断言 | 修改(新增用例) |
| `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` | 「包含目录」勾选框 + 深度下拉;两 payload 分支带 `with_toc` / `toc_depth` | 修改 |

不做封面(后续独立任务)、不做标题自动编号。

---

## Task 1: `generate_docx_simple` 支持目录(后端,TDD)

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(签名 1003-1008;插入点 1054-1056;save 前 1199-1200)
- Test: `backend/tests/test_docmgr_export.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_docmgr_export.py` 末尾追加:

```python
def test_generate_docx_simple_with_toc_emits_field_and_update_flag():
    """with toc_settings(maxDepth=3) → document.xml 含 TOC \\o "1-3";settings.xml 含 updateFields."""
    import zipfile

    from app.extensions.output.generator import generate_docx_simple

    md = "# 一级标题\n\n正文。\n\n## 二级标题\n\n更多正文。\n"
    buf = BytesIO()
    generate_docx_simple(md, buf, toc_settings={"maxDepth": 3})
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        document_xml = z.read("word/document.xml").decode("utf-8")
        settings_xml = z.read("word/settings.xml").decode("utf-8")
    assert 'TOC \\o "1-3"' in document_xml, "TOC field not injected"
    assert "w:updateFields" in settings_xml, "updateFields flag not set"


def test_generate_docx_simple_without_toc_is_unchanged():
    """默认(无 toc_settings)→ 不含 TOC 域、不含 updateFields。"""
    import zipfile

    from app.extensions.output.generator import generate_docx_simple

    md = "# 一级标题\n\n正文。\n"
    buf = BytesIO()
    generate_docx_simple(md, buf)  # 不传 toc_settings
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        document_xml = z.read("word/document.xml").decode("utf-8")
        settings_xml = z.read("word/settings.xml").decode("utf-8")
    assert "TOC \\o" not in document_xml
    assert "updateFields" not in settings_xml
```

- [ ] **Step 2: 运行测试,确认失败** — `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py::test_generate_docx_simple_with_toc_emits_field_and_update_flag tests/test_docmgr_export.py::test_generate_docx_simple_without_toc_is_unchanged -v`

预期:第一条 FAIL(`TypeError: generate_docx_simple() got an unexpected keyword argument 'toc_settings'`);第二条 PASS(默认本就无目录)。

- [ ] **Step 3: 加形参** — 编辑 `backend/app/extensions/output/generator.py`,把签名(约 1003 行)改为:

```python
def generate_docx_simple(
    markdown_content: str,
    buf,
    template_data: dict | None = None,
    watermark: str | None = None,
    toc_settings: dict | None = None,
) -> None:
```

- [ ] **Step 4: 补 docstring** — 在同函数 docstring 的 `Args:` 段(约 1011-1017 行)末尾、`watermark` 那行之后加一行:

```
        toc_settings: Optional dict ``{"maxDepth": int}``. When present with
            maxDepth > 0, a native Word TOC field is rendered before the body
            (Word/WPS auto-updates page numbers on open).
```

- [ ] **Step 5: 在正文循环前渲染目录** — 找到(约 1054-1056 行):

```python
    ol_counters: dict[int, int] = {}

    for block in blocks:
```

替换为:

```python
    ol_counters: dict[int, int] = {}

    # --- Optional Table of Contents (built from markdown headings) ---
    has_toc = _render_toc(doc, toc_settings)
    if has_toc:
        doc.add_page_break()

    for block in blocks:
```

> 说明:`_render_toc`(generator.py:188)在 `toc_settings` 为 None 或 `maxDepth<=0` 时返回 False,因此 `has_toc` 始终有定义,无需额外判空。

- [ ] **Step 6: save 前写 updateFields** — 找到文件末尾(约 1199-1200 行,`generate_docx_simple` 的尾部):

```python
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.save(buf)
```

替换为:

```python
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # --- Auto-update the TOC field when the document opens in Word/WPS ---
    if has_toc:
        _set_update_fields(doc)

    doc.save(buf)
```

> 这个 `RGBColor(0x99, 0x99, 0x99)\n\n    doc.save(buf)` 锚点在全文唯一(只有 `generate_docx_simple` 末尾紧接 `doc.save(buf)`)。

- [ ] **Step 7: 运行测试,确认通过** — `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py -v`

预期:全部 PASS(含原有 4 条 + 新增 2 条)。

- [ ] **Step 8: Lint** — `cd backend && make lint`(ruff)。预期无错。

- [ ] **Step 9: 提交**

```bash
git add backend/app/extensions/output/generator.py backend/tests/test_docmgr_export.py
git commit -m "feat(output): generate_docx_simple 支持 toc_settings 渲染 Word 目录"
```

---

## Task 2: docmgr 导出端点暴露 `with_toc` / `toc_depth`(后端,TDD)

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`(模型 277-280、330-337;调用点 321-322、371-372)
- Test: `backend/tests/test_docmgr_export.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_docmgr_export.py` 末尾追加:

```python
def test_export_requests_carry_toc_fields():
    """ExportRequest / ExportContentRequest 必须接受 with_toc / toc_depth,且默认 关/3。"""
    from app.extensions.docmgr.routers import ExportContentRequest, ExportRequest

    er = ExportRequest(with_toc=True, toc_depth=2)
    assert er.with_toc is True
    assert er.toc_depth == 2

    er_default = ExportRequest()
    assert er_default.with_toc is False
    assert er_default.toc_depth == 3

    ec = ExportContentRequest(with_toc=True, toc_depth=4)
    assert ec.with_toc is True
    assert ec.toc_depth == 4

    ec_default = ExportContentRequest()
    assert ec_default.with_toc is False
    assert ec_default.toc_depth == 3
```

- [ ] **Step 2: 运行测试,确认失败** — `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py::test_export_requests_carry_toc_fields -v`

预期:FAIL(`ValidationError` / `with_toc` 字段不允许)。

- [ ] **Step 3: `ExportRequest` 加字段** — 编辑 `backend/app/extensions/docmgr/routers.py`(约 277 行):

```python
class ExportRequest(BaseModel):
    format: str = "docx"
    layout_template: dict | None = None
    watermark: str | None = None
    with_toc: bool = False
    toc_depth: int = 3
```

- [ ] **Step 4: `ExportContentRequest` 加字段** — 同文件(约 330 行):

```python
class ExportContentRequest(BaseModel):
    """Export raw markdown content (no AIDocument row) — used for personal/thread files."""

    content: str = ""
    format: str = "docx"
    layout_template: dict | None = None
    watermark: str | None = None
    filename: str | None = None
    with_toc: bool = False
    toc_depth: int = 3
```

- [ ] **Step 5: 两处调用点透传 toc_settings** — 同文件有两处完全相同的两行(约 321-322、371-372):

```python
    buf = BytesIO()
    generate_docx_simple(content, buf, template_data=request.layout_template, watermark=request.watermark)
```

用**替换全部**把它(两处)改为:

```python
    buf = BytesIO()
    toc_settings = {"maxDepth": max(1, min(4, request.toc_depth))} if request.with_toc else None
    generate_docx_simple(content, buf, template_data=request.layout_template, watermark=request.watermark, toc_settings=toc_settings)
```

> `max(1, min(4, ...))` 把深度钳制到 1-4(后端是信任边界,即使前端传非法值也安全)。两处文本完全一致,故 `replace_all` 一次覆盖。

- [ ] **Step 6: 运行测试,确认通过** — `cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_export.py -v`

预期:全部 PASS(含 Task 1 的 6 条 + 本任务新增 1 条 = 7 条)。

- [ ] **Step 7: Lint** — `cd backend && make lint`。预期无错。

- [ ] **Step 8: 提交**

```bash
git add backend/app/extensions/docmgr/routers.py backend/tests/test_docmgr_export.py
git commit -m "feat(docmgr): 导出端点暴露 with_toc / toc_depth 并透传 toc_settings"
```

---

## Task 3: 导出弹窗加「包含目录」勾选框 + 深度下拉(前端)

**Files:**
- Modify: `frontend/src/extensions/docmgr/ExportDocxDialog.tsx`(import 4-14;state 293;payload 457-469;deps 499;UI 847-864)

- [ ] **Step 1: 加 lucide 图标 import** — 编辑 `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` 顶部 import(4-14 行),加入 `List`(按字母序,在 `LayoutTemplate` 与 `Loader2` 之间):

```tsx
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileUp,
  LayoutTemplate,
  List,
  Loader2,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
```

- [ ] **Step 2: 加状态** — 找到 watermark 状态(约 293 行):

```tsx
  const [watermark, setWatermark] = useState<WatermarkType | "none">("none");
```

在其**下方**新增两行:

```tsx
  const [withToc, setWithToc] = useState(false);
  const [tocDepth, setTocDepth] = useState(3);
```

- [ ] **Step 3: 加 UI 区块** — 找到水印区块之后的「Bottom spacer」(约 863-864 行):

```tsx
              {/* Bottom spacer */}
              <div className="h-4" />
```

在 `{/* Bottom spacer */}` **之前**插入新目录区块(替换上面两行为下面整段):

```tsx
              {/* Section: Table of Contents */}
              <div data-section="toc" ref={(el) => { sectionRefs.current.toc = el; }}>
                <SectionTitle icon={<List className="w-4 h-4" />}>目录设置</SectionTitle>
                <div className="mt-3 flex items-center gap-4">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <StyledCheckbox checked={withToc} onChange={setWithToc} />
                    包含目录
                  </label>
                  <label
                    className={cn(
                      "flex items-center gap-1.5 text-sm transition-opacity",
                      !withToc && "opacity-40 pointer-events-none",
                    )}
                  >
                    收录到
                    <select
                      value={tocDepth}
                      disabled={!withToc}
                      onChange={(e) => setTocDepth(Number(e.target.value))}
                      className={cn(inputCls, "w-16 h-7 text-xs")}
                    >
                      {[1, 2, 3, 4].map((n) => (
                        <option key={n} value={n}>
                          {n} 级
                        </option>
                      ))}
                    </select>
                    级标题
                  </label>
                </div>
              </div>

              {/* Bottom spacer */}
              <div className="h-4" />
```

> 复用文件内既有组件:`StyledCheckbox`(155-200 行,与「保存为排版模板」同款)、`inputCls`(259 行)、`SectionTitle`(920 行)。`sectionRefs.current.toc` 与水印的 `sectionRefs.current.watermark` 同模式。

- [ ] **Step 4: payload 带字段** — 找到 `handleExport` 的两个 payload 分支(约 457-469 行):

```tsx
      const payload = useContent
        ? {
            content: content ?? "",
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
            filename: docTitle,
          }
        : {
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
          };
```

改为(两个分支各加 `with_toc` / `toc_depth`):

```tsx
      const payload = useContent
        ? {
            content: content ?? "",
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
            filename: docTitle,
            with_toc: withToc,
            toc_depth: tocDepth,
          }
        : {
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
            with_toc: withToc,
            toc_depth: tocDepth,
          };
```

- [ ] **Step 5: 补 useCallback 依赖** — `handleExport` 的依赖数组(约 499 行)末尾(在 `onOpenChange]` 之前)加入 `tocDepth, withToc`:

```tsx
  }, [docId, docTitle, content, saveAsTemplate, templateName, pageSettings, bodyStyles, headingStyles, tableStyles, figureStyles, headerFooter, watermark, withToc, tocDepth, onOpenChange]);
```

- [ ] **Step 6: Typecheck** — `cd frontend && pnpm typecheck`。预期无错。

- [ ] **Step 7: Lint** — `cd frontend && pnpm lint`。预期无错(本文件非自动生成,需过 lint)。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/extensions/docmgr/ExportDocxDialog.tsx
git commit -m "feat(docmgr): 导出弹窗加「包含目录」勾选框 + 深度下拉"
```

---

## Task 4: 端到端验证(Docker 环境)

**Files:** 无(仅运行验证)

- [ ] **Step 1: 重启 gateway(应用后端改动)**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 2: 重启 frontend(应用前端改动;未改依赖,无需 rebuild)**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 3: 手动验证** — 浏览器打开 `http://localhost:2026`,进入「文档空间 → 我的文档」,打开一篇含多级标题(`#`/`##`/`###`)的文档,点「导出 Word」:

  - 默认:「包含目录」未勾选 → 导出的 docx **无**目录。
  - 勾选「包含目录」,深度选 3 → 导出 docx,用 **Word/WPS 打开** → 首页出现「目录」+ 自动生成的标题树 + 正确页码(打开瞬间自动更新域)。
  - 勾选后深度下拉可选 1/2/3/4;未勾选时下拉置灰。
  - 个人文件(docId 为空,走 `/export-content`)同样验证一次。

- [ ] **Step 4: 回归** — 确认水印、排版模板、页眉页脚等既有导出功能未受影响。

---

## Self-Review(计划自检)

- **Spec 覆盖**:
  - §4.1 生成器 `toc_settings` → Task 1 ✓
  - §4.2 两个端点 `with_toc`/`toc_depth` + 透传 → Task 2 ✓
  - §4.3 弹窗勾选框 + 深度下拉 + payload + deps → Task 3 ✓
  - §7 测试(域 + updateFields、默认不含、模型字段)→ Task 1 Step 1、Task 2 Step 1 ✓
  - §9 Docker 验证 → Task 4 ✓
  - §2 非目标(封面 / 编号 / GET 端点)→ 均未触碰 ✓
- **占位符扫描**:无 TBD/TODO;每个改动步骤都给了精确 old/new 代码块与命令 ✓
- **类型/命名一致**:`toc_settings` / `with_toc` / `toc_depth` / `withToc` / `tocDepth` / `maxDepth` / `_render_toc` / `_set_update_fields` 在各任务间一致 ✓
