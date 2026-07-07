# Output 模块:封面 + 目录 + 标题自动编号 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `output` 模块的 DOCX 生成器真正渲染封面页、目录页、标题自动编号(目前这三项在模板里配置了但生成器完全忽略)。

**Architecture:** 在 `generator.py` 增加 5 个纯函数 helper(front-matter 解析 / 标题编号计算 / 封面渲染 / 目录域渲染 / 分节页码),再把它们串进 `generate_docx` 的"封面节 → 目录节 → 正文节"三节流式;`routers.py` 补传 `cover_template`/`toc_settings` 和 4 个封面 Form 参数。全部 TDD,每个 helper 先写失败测试再实现。顺带修 `/generate` 路径中文 eastAsia 字体不生效的既有 bug。

**Tech Stack:** Python 3.12、python-docx、FastAPI、pytest(异步用 AsyncSession fake)。

**Spec:** `docs/superpowers/specs/2026-07-07-output-cover-toc-numbering-design.md`

---

## ⚠️ 提交规则(本分支 main-dev-fork 有并发 docmgr agent)

**每个 commit 必须用显式 pathspec,绝不 bare commit:**
```bash
git add <本次改动的确切路径>
git commit -m "<msg>" -- <本次改动的确切路径>
```
`git commit -- <paths>` 只提交这些路径(忽略 index 里其他已暂存文件),防止并发 agent 的改动被扫进我们的 commit / 我们的改动被扫进它的 commit。**不要** `git reset`/`rebase` 整理历史——会抢 HEAD。

**运行测试:** `cd backend && PYTHONPATH=. uv run pytest tests/test_output_<name>.py -v`
**Lint:** `cd backend && make lint`(ruff,line length 240)
**改后端代码后:** `docker compose -p eai-docker restart gateway`

---

## 文件结构

| 文件 | 职责 | 本计划动作 |
|---|---|---|
| `backend/app/extensions/output/generator.py` | Markdown→DOCX 生成 | 新增 5 个 helper + 重写 `generate_docx` 三节流 + 修 CJK 字体 |
| `backend/app/extensions/output/routers.py` | `/generate` API | 提取 `_build_template_data`/`_collect_cover_fields` + 加 4 个 cover Form 参数 |
| `backend/tests/test_output_frontmatter.py` | front-matter 解析测试 | 新建 |
| `backend/tests/test_output_numbering.py` | 标题编号测试 | 新建 |
| `backend/tests/test_output_cover.py` | 封面渲染 + cover_fields 解析测试 | 新建 |
| `backend/tests/test_output_toc.py` | 目录域 + updateFields 测试 | 新建 |
| `backend/tests/test_output_sections.py` | 分节页码 + 页脚 PAGE 域测试 | 新建 |
| `backend/tests/test_output_generate_integration.py` | generate_docx 端到端三节测试 | 新建 |
| `backend/tests/test_output_routers.py` | routers helpers 测试 | 新建 |
| `backend/tests/test_output_seed.py` | seed per-id upsert 回归测试 | 新建 |

无 DB schema 变更(`layout_templates.cover_template`/`toc_settings` JSONB 列早已存在)。无前端必改。

---

## Task 1: Front-matter 解析器 `_split_frontmatter`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(在 `parse_markdown` 函数之前新增)
- Test: `backend/tests/test_output_frontmatter.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_frontmatter.py`:
```python
"""Tests for markdown front-matter splitting."""
from app.extensions.output.generator import _split_frontmatter


def test_splits_simple_frontmatter():
    md = "---\ntitle: 消防专篇\nclient: 甲公司\n---\n# 总论\n正文\n"
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "消防专篇", "client": "甲公司"}
    assert body == "# 总论\n正文\n"


def test_no_frontmatter_returns_empty_and_original():
    md = "# 没有前置 front-matter\n正文\n"
    meta, body = _split_frontmatter(md)
    assert meta == {}
    assert body == md


def test_strips_quoted_values():
    md = '---\ntitle: "双 引 号 标 题"\n---\n# H\n'
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "双 引 号 标 题"}
    assert body == "# H\n"


def test_malformed_line_treats_whole_as_body():
    # 一行没有冒号 → 视为畸形,整段当正文
    md = "---\ntitle: X\n这行没有冒号\n---\n# H\n"
    meta, body = _split_frontmatter(md)
    assert meta == {}
    assert body == md


def test_ignores_comment_and_blank_lines_in_frontmatter():
    md = "---\n# 这是注释\ntitle: X\n\n---\n# H\n"
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "X"}
    assert body == "# H\n"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_frontmatter.py -v
```
Expected: FAIL — `ImportError: cannot import name '_split_frontmatter'`

- [ ] **Step 3: 实现 `_split_frontmatter`**

在 `generator.py` 的 `HEADING_RE = ...` 常量定义之后、`@dataclass class Block` 之前插入:
```python
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def _split_frontmatter(md: str) -> tuple[dict, str]:
    """Split leading ``---\\nkey: value\\n---\\n`` front-matter from markdown.

    Only flat ``key: value`` lines are supported (no nested YAML, no new dep).
    Returns ``(meta_dict, body_markdown)``. If there is no front-matter, or any
    non-blank/non-comment line lacks a colon (malformed), returns ``({}, md)``
    — i.e. treat the whole input as body so generation never crashes.
    """
    m = FRONTMATTER_RE.match(md)
    if not m:
        return {}, md
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            return {}, md  # malformed → degrade to whole-body
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, md[m.end():]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_frontmatter.py -v
```
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_frontmatter.py
git commit -m "feat(output): add markdown front-matter splitter for cover field extraction" -- app/extensions/output/generator.py tests/test_output_frontmatter.py
```

---

## Task 2: 标题编号计算 `_compute_heading_numbers`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(在 `_split_frontmatter` 之后新增)
- Test: `backend/tests/test_output_numbering.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_numbering.py`:
```python
"""Tests for decimal heading-number computation."""
from app.extensions.output.generator import Block, _compute_heading_numbers


def _blocks(*specs):
    # specs: ("h1","总论"), ("h2","子"), ...
    out = []
    for level, text in specs:
        out.append(Block(kind="heading", level=level, text=text))
    return out


def test_decimal_multilevel():
    blocks = _blocks((1, "总论"), (2, "a"), (2, "b"), (3, "b1"), (1, "二章"), (2, "c"))
    hs = [
        {"level": 1, "numbering": "decimal"},
        {"level": 2, "numbering": "decimal"},
        {"level": 3, "numbering": "decimal"},
    ]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {0: "1", 1: "1.1", 2: "1.2", 3: "1.2.1", 4: "2", 5: "2.1"}


def test_level_reset_when_parent_advances():
    blocks = _blocks((1, "一"), (2, "a"), (1, "二"), (2, "b"))
    hs = [{"level": 1, "numbering": "decimal"}, {"level": 2, "numbering": "decimal"}]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {0: "1", 1: "1.1", 2: "2", 3: "2.1"}


def test_numbering_none_skips_number():
    blocks = _blocks((1, "一"), (2, "a"))
    hs = [{"level": 1, "numbering": "none"}, {"level": 2, "numbering": "none"}]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {}


def test_non_heading_blocks_ignored():
    blocks = [Block(kind="paragraph", text="p"), Block(kind="heading", level=1, text="h")]
    nums = _compute_heading_numbers(blocks, [{"level": 1, "numbering": "decimal"}])
    assert nums == {1: "1"}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_numbering.py -v
```
Expected: FAIL — `ImportError: cannot import name '_compute_heading_numbers'`

- [ ] **Step 3: 实现**

在 `generator.py` 的 `_split_frontmatter` 之后插入:
```python
def _compute_heading_numbers(blocks: list[Block], heading_styles: list[dict]) -> dict[int, str]:
    """Compute decimal multilevel numbers for heading blocks.

    Returns ``{block_index: number_string}`` (e.g. ``{0: "1", 1: "1.1", 3: "1.2.1"}``)
    for heading blocks whose level has ``numbering == "decimal"``. Headings on
    levels with ``numbering != "decimal"`` (or unspecified) are omitted.

    Note: meaningful only when every relevant level is "decimal". Mixing
    "none" in the middle produces counter-intuitive numbers for deeper levels —
    acceptable since templates configure all-or-none per the spec.
    """
    numbering_by_level: dict[int, str] = {
        hs.get("level", 0): hs.get("numbering", "none") for hs in heading_styles
    }
    counters = [0, 0, 0, 0]  # levels 1..4
    result: dict[int, str] = {}
    for i, b in enumerate(blocks):
        if b.kind != "heading":
            continue
        level = max(1, min(b.level, 4))
        if numbering_by_level.get(level, "none") != "decimal":
            continue
        counters[level - 1] += 1
        for deeper in range(level, 4):
            counters[deeper] = 0
        result[i] = ".".join(str(counters[k]) for k in range(level))
    return result
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_numbering.py -v
```
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_numbering.py
git commit -m "feat(output): compute decimal multilevel heading numbers" -- app/extensions/output/generator.py tests/test_output_numbering.py
```

---

## Task 3: 修复 `/generate` 路径 CJK 字体(统一用 `_set_run_font`)

**背景:** `generate_docx`(模板路径)给标题/正文设字体时只调 `run.font.name`(设 `w:ascii`/`w:hAnsi`,**没设 `w:eastAsia`**),中文不会按黑体/宋体渲染。`generate_docx_simple` 里有正确的 `_set_run_font`。本任务把 `generate_docx` 内所有 `run.font.name = _resolve_font(...)` / `run.font.name = body_font` 换成 `_set_run_font(run, ...)`。

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(`generate_docx` 函数体内多处)
- Test: `backend/tests/test_output_cjk_font.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_cjk_font.py`:
```python
"""Regression: generate_docx must set w:eastAsia font so Chinese renders correctly."""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.extensions.output.generator import generate_docx


def _eastasia(run) -> str | None:
    rPr = run._element.find(qn("w:rPr"))
    if rPr is None:
        return None
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        return None
    return rFonts.get(qn("w:eastAsia"))


def test_heading_and_body_runs_have_eastasia(tmp_path: Path):
    md = "# 总论标题\n\n这是正文段落。\n"
    tpl = {
        "body_styles": {"fontFamily": "宋体", "fontSize": 12},
        "heading_styles": [{"level": 1, "fontFamily": "黑体", "numbering": "none"}],
    }
    out = tmp_path / "t.docx"
    generate_docx(md, tpl, out)

    doc = Document(str(out))
    # find heading run
    heading_run = next(
        (r for p in doc.paragraphs if "标题" in p.text for r in p.runs if r.text),
        None,
    )
    assert heading_run is not None, "heading run not found"
    assert _eastasia(heading_run) == "SimSun"  # 黑体→SimSun? see note below

    body_run = next(
        (r for p in doc.paragraphs if "正文" in p.text for r in p.runs if r.text),
        None,
    )
    assert body_run is not None, "body run not found"
    assert _eastasia(body_run) == "SimSun"
```

> **注:** `_resolve_font("黑体")` → `"SimHei"`,`_resolve_font("宋体")` → `"SimSun"`。修标题 run 的断言应是 `"SimHei"`。把上面 heading 断言改为:
```python
    assert _eastasia(heading_run) == "SimHei"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cjk_font.py -v
```
Expected: FAIL — `_eastasia(heading_run) is None`(当前 generate_docx 不设 eastAsia)

- [ ] **Step 3: 修改 `generate_docx`,把 `run.font.name = ...` 改为 `_set_run_font(run, ...)`**

在 `generator.py` 的 `generate_docx` 函数体内,**逐一替换**(共 5 处:heading / paragraph / ul_item / ol_item / table cell)。具体:

① heading 分支(原 `for run in heading.runs: run.font.name = _resolve_font(...)`):
```python
            for run in heading.runs:
                _set_run_font(run, _resolve_font(hs.get("fontFamily", body_font)))
                run.font.size = Pt(hs.get("fontSize", 16))
                if hs.get("fontWeight", 700) >= 700:
                    run.bold = True
                c = hs.get("color")
                if c:
                    run.font.color.rgb = RGBColor.from_string(c.replace("#", ""))
```

② paragraph 分支(原 `for run in para.runs: run.font.name = body_font`):
```python
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size
```

③ ul_item 分支(原 `for run in para.runs: run.font.name = body_font`):
```python
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size
```

④ ol_item 分支(原 `for run in para.runs: run.font.name = body_font`):
```python
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size
```

⑤ table cell 分支(原 `for run in para.runs: run.font.name = body_font`):
```python
                            for run in para.runs:
                                _set_run_font(run, body_font)
                                run.font.size = Pt(body_size.pt - 1)
```

(每处只把 `run.font.name = X` 一行换成 `_set_run_font(run, X)`,其余行不动。`_set_run_font` 是模块级函数,在 `generate_docx` 之后定义,Python 调用时解析,无前向引用问题。)

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cjk_font.py -v
```
Expected: PASS

- [ ] **Step 5: 回归全量 + 提交**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_frontmatter.py tests/test_output_numbering.py tests/test_output_cjk_font.py -v
```
Expected: 全 PASS。然后:
```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_cjk_font.py
git commit -m "fix(output): set w:eastAsia font in generate_docx so Chinese renders (CJK)" -- app/extensions/output/generator.py tests/test_output_cjk_font.py
```

---

## Task 4: 封面渲染 `_render_cover`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(新增 `_render_cover`,放在 `_compute_heading_numbers` 之后)
- Test: `backend/tests/test_output_cover.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_cover.py`:
```python
"""Tests for cover-page rendering."""
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.extensions.output.generator import _render_cover


def _texts(doc):
    return [p.text for p in doc.paragraphs]


def test_renders_all_fields_when_all_shown():
    ct = {"showLogo": False, "showTitle": True, "showClient": True,
          "showDate": True, "showProjectNumber": True}
    cf = {"title": "消防专篇", "client": "甲公司", "date": "2026-07", "project_number": "P001"}
    doc = Document()
    _render_cover(doc, ct, cf)
    txt = _texts(doc)
    assert "消防专篇" in txt
    assert any("建设单位" in t and "甲公司" in t for t in txt)
    assert any("项目编号" in t and "P001" in t for t in txt)
    assert any("日期" in t and "2026-07" in t for t in txt)


def test_skips_line_when_value_missing():
    ct = {"showTitle": True, "showClient": True, "showDate": False, "showProjectNumber": True, "showLogo": False}
    cf = {"title": "T"}  # client/date/project_number 全缺
    doc = Document()
    _render_cover(doc, ct, cf)
    txt = _texts(doc)
    assert "T" in txt
    assert not any("建设单位" in t for t in txt), "no client value → no 建设单位 line"
    assert not any("项目编号" in t for t in txt)


def test_skips_line_when_toggle_false():
    ct = {"showTitle": True, "showClient": False, "showDate": False, "showProjectNumber": False, "showLogo": False}
    cf = {"title": "T", "client": "C", "date": "D", "project_number": "P"}
    doc = Document()
    _render_cover(doc, ct, cf)
    txt = _texts(doc)
    assert not any("建设单位" in t for t in txt)


def test_title_centered_heiti():
    ct = {"showTitle": True, "showClient": False, "showDate": False, "showProjectNumber": False, "showLogo": False}
    cf = {"title": "标题X"}
    doc = Document()
    _render_cover(doc, ct, cf)
    title_para = next(p for p in doc.paragraphs if p.text == "标题X")
    assert title_para.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_no_cover_when_template_none():
    doc = Document()
    _render_cover(doc, None, {"title": "T"})
    # only spacer/empty paragraphs, no title rendered
    assert "T" not in _texts(doc)


def test_renders_logo_placeholder_when_shown():
    ct = {"showLogo": True, "showTitle": False, "showClient": False, "showDate": False, "showProjectNumber": False}
    doc = Document()
    _render_cover(doc, ct, {})
    assert any("LOGO" in t for t in _texts(doc))
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cover.py -v
```
Expected: FAIL — `ImportError: cannot import name '_render_cover'`

- [ ] **Step 3: 实现 `_render_cover`**

在 `generator.py` 的 `_compute_heading_numbers` 之后插入:
```python
def _render_cover(doc, cover_template: dict | None, cover_fields: dict) -> None:
    """Render the cover page at the start of the document body.

    ``cover_template`` toggles which fields appear (showLogo/showTitle/showClient/
    showDate/showProjectNumber). ``cover_fields`` carries resolved values
    (title/client/date/project_number); a line is rendered only if its toggle is
    on AND its value is present. No-op when ``cover_template`` is falsy.
    """
    ct = cover_template or {}

    if ct.get("showLogo"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[编制单位 LOGO]")
        _set_run_font(run, "宋体")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    for _ in range(3):  # vertical spacing before title
        doc.add_paragraph()

    if ct.get("showTitle") and cover_fields.get("title"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(cover_fields["title"]))
        _set_run_font(run, "黑体")
        run.font.size = Pt(22)
        run.bold = True

    for _ in range(4):  # spacing before info lines
        doc.add_paragraph()

    def _info_line(label: str, value) -> None:
        if not value:
            return
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"{label}:{value}")
        _set_run_font(run, "宋体")
        run.font.size = Pt(14)

    if ct.get("showClient"):
        _info_line("建设单位", cover_fields.get("client"))
    if ct.get("showProjectNumber"):
        _info_line("项目编号", cover_fields.get("project_number"))
    if ct.get("showDate"):
        _info_line("日期", cover_fields.get("date"))
```

> **注:** 测试里断言 `"建设单位" in t and "甲公司" in t`——上面 `_info_line` 用 `f"{label}:{value}"` 生成 `"建设单位:甲公司"`,两者都在,通过。冒号用 ASCII `:` 避免 Windows 编码琐事。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cover.py -v
```
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_cover.py
git commit -m "feat(output): render cover page from cover_template toggles + resolved fields" -- app/extensions/output/generator.py tests/test_output_cover.py
```

---

## Task 5: 目录域渲染 `_render_toc` + `_set_update_fields`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(新增 `_render_toc` / `_add_toc_field` / `_set_update_fields`,放在 `_render_cover` 之后)
- Test: `backend/tests/test_output_toc.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_toc.py`:
```python
"""Tests for TOC field rendering + updateFields setting."""
from docx import Document

from app.extensions.output.generator import _render_toc, _set_update_fields


def test_toc_field_present_with_maxdepth():
    doc = Document()
    _render_toc(doc, {"maxDepth": 2})
    xml = doc.element.body.xml
    assert 'TOC \\o "1-2"' in xml
    assert "目录" in doc.element.body.xml  # 目录 heading


def test_toc_uses_configured_maxdepth():
    doc = Document()
    _render_toc(doc, {"maxDepth": 3})
    assert 'TOC \\o "1-3"' in doc.element.body.xml


def test_toc_skipped_when_settings_none():
    doc = Document()
    _render_toc(doc, None)
    assert "TOC" not in doc.element.body.xml


def test_toc_skipped_when_maxdepth_zero():
    doc = Document()
    _render_toc(doc, {"maxDepth": 0})
    assert "TOC" not in doc.element.body.xml


def test_update_fields_written_to_settings():
    doc = Document()
    _set_update_fields(doc)
    assert 'w:updateFields' in doc.settings.element.xml
    assert 'w:val="true"' in doc.settings.element.xml


def test_update_fields_idempotent():
    doc = Document()
    _set_update_fields(doc)
    _set_update_fields(doc)
    assert doc.settings.element.xml.count("w:updateFields") == 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_toc.py -v
```
Expected: FAIL — `ImportError: cannot import name '_render_toc'`

- [ ] **Step 3: 实现**

在 `generator.py` 的 `_render_cover` 之后插入:
```python
def _add_toc_field(paragraph, max_depth: int) -> None:
    """Inject a native Word TOC field (TOC \\o "1-N" \\h \\z \\u) into paragraph XML."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def _fld(char_type: str) -> None:
        run = paragraph.add_run()
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), char_type)
        if char_type == "begin":
            el.set(qn("w:dirty"), "true")
        run._element.append(el)

    _fld("begin")
    run_instr = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f' TOC \\o "1-{max_depth}" \\h \\z \\u '
    run_instr._element.append(instr)
    _fld("separate")

    run_placeholder = paragraph.add_run("（打开文档后右键“更新域”生成目录）")
    _set_run_font(run_placeholder, "宋体")
    run_placeholder.font.size = Pt(10)
    run_placeholder.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    _fld("end")


def _render_toc(doc, toc_settings: dict | None) -> bool:
    """Add a 目录 heading + TOC field. Returns True if rendered, False if skipped."""
    if not toc_settings:
        return False
    max_depth = toc_settings.get("maxDepth") or 0
    if max_depth <= 0:
        return False
    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run("目录")
    _set_run_font(run, "黑体")
    run.font.size = Pt(16)
    run.bold = True
    _add_toc_field(doc.add_paragraph(), max_depth)
    return True


def _set_update_fields(doc) -> None:
    """Write <w:updateFields w:val="true"/> into settings.xml so Word/WPS auto-updates the TOC on open."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        el = OxmlElement("w:updateFields")
        el.set(qn("w:val"), "true")
        settings.append(el)
```

> **注:** 测试断言 `"目录" in body.xml`——heading 文本是 "目录"(不间夹空格),匹配。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_toc.py -v
```
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_toc.py
git commit -m "feat(output): render native Word TOC field + set updateFields on open" -- app/extensions/output/generator.py tests/test_output_toc.py
```

---

## Task 6: 分节页码 `_set_section_pagenum` + 页脚 PAGE 域 `_add_page_number_footer`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(新增两个 helper,放在 `_set_update_fields` 之后)
- Test: `backend/tests/test_output_sections.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_sections.py`:
```python
"""Tests for per-section page numbering + footer PAGE field."""
from docx import Document
from docx.oxml.ns import qn

from app.extensions.output.generator import _add_page_number_footer, _set_section_pagenum


def test_set_section_pagenum_upper_roman():
    doc = Document()
    _set_section_pagenum(doc.sections[0], fmt="upperRoman", start=1)
    xml = doc.sections[0]._sectPr.xml
    assert "w:pgNumType" in xml
    assert 'w:fmt="upperRoman"' in xml
    assert 'w:start="1"' in xml


def test_set_section_pagenum_decimal():
    doc = Document()
    _set_section_pagenum(doc.sections[0], fmt="decimal", start=1)
    xml = doc.sections[0]._sectPr.xml
    assert 'w:fmt="decimal"' in xml


def test_set_section_pagenum_idempotent():
    doc = Document()
    _set_section_pagenum(doc.sections[0], fmt="decimal", start=1)
    _set_section_pagenum(doc.sections[0], fmt="decimal", start=1)
    assert doc.sections[0]._sectPr.xml.count("w:pgNumType") == 1


def test_add_page_number_footer_inserts_page_field():
    doc = Document()
    section = doc.sections[0]
    section.footer.is_linked_to_previous = False
    _add_page_number_footer(section)
    xml = section.footer.paragraphs[0]._element.xml
    assert "PAGE" in xml
    assert 'w:fldCharType="begin"' in xml
    assert 'w:fldCharType="end"' in xml
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_sections.py -v
```
Expected: FAIL — `ImportError: cannot import name '_set_section_pagenum'`

- [ ] **Step 3: 实现**

在 `generator.py` 的 `_set_update_fields` 之后插入:
```python
def _set_section_pagenum(section, fmt: str | None = None, start: int | None = None) -> None:
    """Set pgNumType (page number format + restart) on a section's sectPr. Idempotent."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    sectPr = section._sectPr
    pgNum = sectPr.find(qn("w:pgNumType"))
    if pgNum is None:
        pgNum = OxmlElement("w:pgNumType")
        sectPr.append(pgNum)
    if fmt:
        pgNum.set(qn("w:fmt"), fmt)
    if start is not None:
        pgNum.set(qn("w:start"), str(start))


def _add_page_number_footer(section) -> None:
    """Add a centered PAGE field to the section's footer. Caller must unlink first."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    footer_para = section.footer.paragraphs[0]
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _fld(char_type: str) -> None:
        run = footer_para.add_run()
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), char_type)
        run._element.append(el)

    _fld("begin")
    run_instr = footer_para.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    run_instr._element.append(instr)
    _fld("end")

    for run in footer_para.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_sections.py -v
```
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_sections.py
git commit -m "feat(output): per-section page numbering (pgNumType) + footer PAGE field helpers" -- app/extensions/output/generator.py tests/test_output_sections.py
```

---

## Task 7: 封面字段解析 `_resolve_cover_fields`

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(新增 `_resolve_cover_fields`,放在 `_render_cover` 之前)
- Test: `backend/tests/test_output_cover.py`(追加用例)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_output_cover.py` 末尾追加:
```python
from app.extensions.output.generator import Block, _resolve_cover_fields


def test_resolve_prefers_api_over_frontmatter_over_fallback():
    api = {"title": "API标题", "client": "API客户"}
    fm = {"title": "FM标题", "date": "2026-01"}
    blocks = [Block(kind="heading", level=1, text="H1兜底")]
    resolved = _resolve_cover_fields(api, fm, blocks)
    assert resolved["title"] == "API标题"      # api wins
    assert resolved["client"] == "API客户"      # api
    assert resolved["date"] == "2026-01"         # frontmatter (no api)


def test_resolve_title_falls_back_to_first_h1():
    api = {}
    fm = {}
    blocks = [Block(kind="paragraph", text="p"), Block(kind="heading", level=1, text="首个H1")]
    resolved = _resolve_cover_fields(api, fm, blocks)
    assert resolved["title"] == "首个H1"


def test_resolve_date_falls_back_to_today():
    import datetime
    api = {}
    fm = {}
    blocks = []
    resolved = _resolve_cover_fields(api, fm, blocks)
    assert resolved["date"] == datetime.date.today().isoformat()


def test_resolve_omits_missing_optional_fields():
    resolved = _resolve_cover_fields({}, {}, [])
    assert "client" not in resolved
    assert "project_number" not in resolved
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cover.py -v
```
Expected: FAIL — `ImportError: cannot import name '_resolve_cover_fields'`

- [ ] **Step 3: 实现**

在 `generator.py` 的 `_render_cover` 之前插入:
```python
def _resolve_cover_fields(api_fields: dict, frontmatter: dict, blocks: list[Block]) -> dict:
    """Resolve cover field values by priority: API params > front-matter > fallback.

    - title: api > front-matter > first H1 block text
    - client/project_number: api > front-matter (omit if neither)
    - date: api > front-matter > today (ISO)
    """
    resolved: dict = {}
    title = api_fields.get("title") or frontmatter.get("title")
    if not title:
        for b in blocks:
            if b.kind == "heading" and b.level == 1:
                title = b.text
                break
    if title:
        resolved["title"] = title
    for key in ("client", "project_number"):
        val = api_fields.get(key) or frontmatter.get(key)
        if val:
            resolved[key] = val
    date_val = api_fields.get("date") or frontmatter.get("date")
    resolved["date"] = date_val or datetime.date.today().isoformat()
    return resolved
```

并在 `generator.py` 顶部 import 区(`import re` 附近)加:
```python
import datetime
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_cover.py -v
```
Expected: PASS(10 passed:6 cover + 4 resolve)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_cover.py
git commit -m "feat(output): resolve cover fields by priority (api > front-matter > fallback)" -- app/extensions/output/generator.py tests/test_output_cover.py
```

---

## Task 8: 串进 `generate_docx`(三节流式 + 编号前缀)端到端

**本任务是核心集成**:给 `generate_docx` 加 `cover_fields` 形参,改成"封面节 → 目录节 → 正文节"三节流,正文标题前缀编号,按节设页码/页脚。

**Files:**
- Modify: `backend/app/extensions/output/generator.py`(顶部加 `WD_SECTION` import + 重写 `generate_docx` 函数体)
- Test: `backend/tests/test_output_generate_integration.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_generate_integration.py`:
```python
"""End-to-end: generate_docx produces cover + TOC + body sections with numbering."""
from pathlib import Path

from docx import Document

from app.extensions.output.generator import generate_docx


TPL_WITH_COVER_TOC = {
    "page_settings": {"paperSize": "A4", "orientation": "portrait",
                      "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
    "body_styles": {"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5,
                    "paragraphSpacing": 6, "firstLineIndent": 2},
    "heading_styles": [
        {"level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
        {"level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#000000", "numbering": "decimal"},
    ],
    "cover_template": {"showLogo": False, "showTitle": True, "showClient": True,
                       "showDate": True, "showProjectNumber": True},
    "toc_settings": {"maxDepth": 2, "showPageNumbers": True, "leaderDots": True},
    "header_footer": {"headerText": "", "footerText": "", "showPageNumber": True, "showLogo": False},
}


def test_three_sections_cover_toc_body(tmp_path: Path):
    md = "# 总论\n\n正文段。\n## 子节\n\n更多正文。\n"
    out = tmp_path / "r.docx"
    generate_docx(md, TPL_WITH_COVER_TOC, out,
                  cover_fields={"title": "消防专篇", "client": "甲公司",
                                "date": "2026-07", "project_number": "P001"})
    doc = Document(str(out))
    assert len(doc.sections) == 3  # cover / toc / body


def test_cover_section_has_no_page_number(tmp_path: Path):
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n", TPL_WITH_COVER_TOC, out,
                  cover_fields={"title": "T", "date": "2026-07"})
    doc = Document(str(out))
    cover_sectpr = doc.sections[0]._sectPr.xml
    assert "pgNumType" not in cover_sectpr


def test_toc_section_is_upper_roman(tmp_path: Path):
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n", TPL_WITH_COVER_TOC, out, cover_fields={"title": "T", "date": "2026-07"})
    doc = Document(str(out))
    assert 'w:fmt="upperRoman"' in doc.sections[1]._sectPr.xml


def test_body_section_is_decimal_restart_1(tmp_path: Path):
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n", TPL_WITH_COVER_TOC, out, cover_fields={"title": "T", "date": "2026-07"})
    doc = Document(str(out))
    body_xml = doc.sections[2]._sectPr.xml
    assert 'w:fmt="decimal"' in body_xml
    assert 'w:start="1"' in body_xml


def test_toc_field_and_updatefields_present(tmp_path: Path):
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n", TPL_WITH_COVER_TOC, out, cover_fields={"title": "T", "date": "2026-07"})
    doc = Document(str(out))
    assert 'TOC \\o "1-2"' in doc.element.body.xml
    assert "updateFields" in doc.settings.element.xml


def test_body_headings_carry_decimal_numbers(tmp_path: Path):
    md = "# 总论\n## 子节\n# 二章\n"
    out = tmp_path / "r.docx"
    generate_docx(md, TPL_WITH_COVER_TOC, out, cover_fields={"title": "T", "date": "2026-07"})
    doc = Document(str(out))
    heading_texts = [p.text for p in doc.paragraphs if p.style and p.style.name and p.style.name.startswith("Heading")]
    assert "1 总论" in heading_texts
    assert "1.1 子节" in heading_texts
    assert "2 二章" in heading_texts


def test_cover_title_rendered(tmp_path: Path):
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n", TPL_WITH_COVER_TOC, out,
                  cover_fields={"title": "我的消防专篇", "date": "2026-07"})
    doc = Document(str(out))
    assert any("我的消防专篇" in p.text for p in doc.paragraphs)


def test_backward_compat_no_cover_no_toc(tmp_path: Path):
    """Template without cover_template/toc_settings → single section, no cover/TOC."""
    tpl = {
        "page_settings": {"paperSize": "A4"},
        "body_styles": {"fontFamily": "宋体", "fontSize": 12},
        "heading_styles": [{"level": 1, "fontFamily": "黑体", "numbering": "none"}],
    }
    out = tmp_path / "r.docx"
    generate_docx("# 总论\n正文\n", tpl, out)
    doc = Document(str(out))
    assert "TOC" not in doc.element.body.xml
    # no cover title rendered (no cover_template)
    assert not any("建设单位" in p.text for p in doc.paragraphs)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_generate_integration.py -v
```
Expected: 多数 FAIL(当前 `generate_docx` 无 `cover_fields` 形参、不渲染封面/目录、不分节)

- [ ] **Step 3: 重写 `generate_docx`**

在 `generator.py` 顶部 import 区(`from docx.enum.text import WD_ALIGN_PARAGRAPH` 那行附近)加:
```python
from docx.enum.section import WD_SECTION
```

把整个 `generate_docx` 函数(从 `def generate_docx(` 到它 `return str(output_path)` 结束)替换为:
```python
def generate_docx(
    markdown_content: str,
    template_data: dict,
    output_path: Path,
    watermark: str | None = None,
    cover_fields: dict | None = None,
) -> str:
    """Generate a DOCX from markdown using layout template styling.

    Renders up to three sections: cover (no page number) → TOC (roman) → body
    (arabic from 1). Cover/TOC are added only when the template declares
    ``cover_template`` / ``toc_settings``. Returns the output file path.
    """
    frontmatter, body_md = _split_frontmatter(markdown_content)
    blocks = parse_markdown(body_md)
    doc = Document()

    has_cover = bool(template_data.get("cover_template"))
    has_toc = bool(template_data.get("toc_settings"))

    # --- Resolve cover fields (api > front-matter > fallback) ---
    resolved_cover = _resolve_cover_fields(cover_fields or {}, frontmatter, blocks) if has_cover else {}

    # --- Page setup (applies to the first section; subsequent inherit) ---
    ps = template_data.get("page_settings", {})
    section = doc.sections[0]
    section.page_width = Cm(21.0) if ps.get("paperSize", "A4") == "A4" else Cm(29.7)
    section.page_height = Cm(29.7) if ps.get("paperSize", "A4") == "A4" else Cm(42.0)
    if ps.get("orientation") == "landscape":
        section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(ps.get("marginTop", 2.54))
    section.bottom_margin = Cm(ps.get("marginBottom", 2.54))
    section.left_margin = Cm(ps.get("marginLeft", 3.17))
    section.right_margin = Cm(ps.get("marginRight", 3.17))

    # --- Body style defaults ---
    bs = template_data.get("body_styles", {})
    body_font = _resolve_font(bs.get("fontFamily", "宋体"))
    body_size = Pt(bs.get("fontSize", 12))
    body_line_spacing = bs.get("lineHeight", 1.5)

    # --- Heading styles map ---
    heading_styles: dict[int, dict] = {}
    for hs in template_data.get("heading_styles", []):
        heading_styles[hs.get("level", 0)] = hs

    numbers = _compute_heading_numbers(blocks, template_data.get("heading_styles", []))

    def style_paragraph(para, font_name: str = body_font, font_size=body_size, bold: bool = False, color: str | None = None, alignment=None, first_indent: float | None = None, space_after: int | None = None):
        pf = para.paragraph_format
        pf.line_spacing = body_line_spacing
        if space_after is not None:
            pf.space_after = Pt(space_after)
        else:
            pf.space_after = Pt(bs.get("paragraphSpacing", 6))
        if first_indent is not None:
            pf.first_line_indent = Cm(first_indent)
        if alignment is not None:
            pf.alignment = alignment

    # === Section 0: COVER ===
    if has_cover:
        try:
            _render_cover(doc, template_data.get("cover_template"), resolved_cover)
        except Exception:  # cover must never abort generation
            pass
        doc.add_section(WD_SECTION.NEW_PAGE)

    # === Section 1: TOC ===
    if has_toc:
        toc_rendered = _render_toc(doc, template_data.get("toc_settings"))
        if toc_rendered:
            doc.add_section(WD_SECTION.NEW_PAGE)

    # === Section 2: BODY ===
    ol_counters: dict[int, int] = {}
    for i, block in enumerate(blocks):
        if block.kind == "heading":
            level = min(block.level, 4)
            hs = heading_styles.get(level, {})
            heading = doc.add_heading(level=level)
            text = f"{numbers[i]} {block.text}" if i in numbers else block.text
            _add_inline_text(heading, text)
            for run in heading.runs:
                _set_run_font(run, _resolve_font(hs.get("fontFamily", body_font)))
                run.font.size = Pt(hs.get("fontSize", 16))
                if hs.get("fontWeight", 700) >= 700:
                    run.bold = True
                c = hs.get("color")
                if c:
                    run.font.color.rgb = RGBColor.from_string(c.replace("#", ""))
            style_paragraph(heading, space_after=6)

        elif block.kind == "paragraph":
            para = doc.add_paragraph()
            indent = bs.get("firstLineIndent", 2)
            style_paragraph(para, first_indent=indent * body_size.pt / 28.35 * 0.5 if indent else None)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ul_item":
            para = doc.add_paragraph()
            indent_cm = block.level * 0.6
            para.paragraph_format.left_indent = Cm(indent_cm)
            para.paragraph_format.first_line_indent = Cm(-0.3)
            _set_run_font(para.add_run("• "), body_font)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ol_item":
            indent_level = block.level
            ol_counters[indent_level] = ol_counters.get(indent_level, 0) + 1
            counter = ol_counters[indent_level]
            para = doc.add_paragraph()
            indent_cm = indent_level * 0.6
            para.paragraph_format.left_indent = Cm(indent_cm)
            _set_run_font(para.add_run(f"{counter}. "), body_font)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "hr":
            para = doc.add_paragraph()
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(6)
            run = para.add_run("─" * 60)
            run.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
            run.font.size = Pt(8)

        elif block.kind == "code_block":
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Cm(1)
            para.paragraph_format.space_before = Pt(4)
            para.paragraph_format.space_after = Pt(4)
            run = para.add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        elif block.kind == "table":
            if block.rows:
                tstyles = template_data.get("table_styles")
                ncols = max(len(r) for r in block.rows)
                table = doc.add_table(rows=len(block.rows), cols=ncols)
                table.style = "Table Grid"
                for ri, row in enumerate(block.rows):
                    for ci, cell_text in enumerate(row):
                        if ci < ncols:
                            cell = table.rows[ri].cells[ci]
                            cell.text = ""
                            para = cell.paragraphs[0]
                            _add_inline_text(para, cell_text.strip())
                            for run in para.runs:
                                _set_run_font(run, body_font)
                                run.font.size = Pt(body_size.pt - 1)
                                if ri == 0 and tstyles:
                                    run.bold = True
                                    c = tstyles.get("headerColor", "#FFFFFF")
                                    run.font.color.rgb = RGBColor.from_string(c.replace("#", ""))
                if tstyles and block.rows:
                    from docx.oxml.ns import qn
                    bg = tstyles.get("headerBg", "#2B579A").replace("#", "")
                    for ci in range(ncols):
                        cell = table.rows[0].cells[ci]
                        shading = cell._element.get_or_add_tcPr()
                        shading_elem = shading.makeelement(qn("w:shd"), {
                            qn("w:fill"): bg,
                            qn("w:val"): "clear",
                        })
                        shading.append(shading_elem)

    # === Per-section footers + page numbering + header_footer + watermark ===
    _apply_section_chrome(doc, template_data, watermark, has_cover, has_toc)

    # === Auto-update TOC on open ===
    if has_toc:
        _set_update_fields(doc)

    doc.save(str(output_path))
    return str(output_path)
```

然后在 `generate_docx` 之后新增 `_apply_section_chrome` 辅助函数:
```python
def _apply_section_chrome(doc, template_data: dict, watermark: str | None, has_cover: bool, has_toc: bool) -> None:
    """Apply per-section footer page numbers, pgNumType, header_footer text, watermark.

    Sections layout: [cover?][toc?][body...]. Cover: no page number. TOC: roman.
    Body (last) section: decimal restart 1 + header_footer template config + watermark.
    """
    hf = template_data.get("header_footer") or {}
    sections = doc.sections
    last_idx = len(sections) - 1

    for idx, sec in enumerate(sections):
        is_cover = has_cover and idx == 0
        is_toc = has_toc and ((idx == 1) if has_cover else (idx == 0))

        if is_cover:
            continue  # cover: no footer page number, no chrome

        # unlink footer so we don't inherit cover's empty footer
        sec.footer.is_linked_to_previous = False
        sec.header.is_linked_to_previous = False

        if is_toc:
            _set_section_pagenum(sec, fmt="upperRoman", start=1)
            _add_page_number_footer(sec)
        else:
            # body section(s): decimal page numbers, restart at 1
            _set_section_pagenum(sec, fmt="decimal", start=1)
            _add_page_number_footer(sec)
            _apply_header_footer_text(sec, hf)

    # watermark on body (last) section header
    if watermark and last_idx >= 0:
        labels = {"draft": "初稿", "review": "送审稿", "final": "正式稿"}
        label = labels.get(watermark, watermark)
        body_sec = sections[last_idx]
        existing = body_sec.header.paragraphs[0].text if body_sec.header.paragraphs else ""
        body_sec.header.paragraphs[0].text = f"【{label}】{chr(10)}{existing}".strip()
        for run in body_sec.header.paragraphs[0].runs:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)


def _apply_header_footer_text(section, hf: dict) -> None:
    """Apply headerText/footerText from template header_footer config to a body section."""
    if hf.get("headerText"):
        section.header.paragraphs[0].text = hf["headerText"]
        for run in section.header.paragraphs[0].runs:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    if hf.get("footerText"):
        section.footer.paragraphs[0].text = hf["footerText"]
```

> **清理:** 上面 `_apply_section_chrome` 里 body 分支写了两行 `_set_section_pagenum`(第一行有乱的 `or True` 逻辑)——**删掉第一行,只保留** `_set_section_pagenum(sec, fmt="decimal", start=1)`。最终 body 分支应为:
> ```python
>         else:
>             # body section(s)
>             _set_section_pagenum(sec, fmt="decimal", start=1)
>             _add_page_number_footer(sec)
>             _apply_header_footer_text(sec, hf)
> ```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_generate_integration.py tests/test_output_cjk_font.py -v
```
Expected: PASS(8 integration + 1 cjk 回归)

- [ ] **Step 5: 全量回归 + 提交**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_*.py -v
```
Expected: 全 PASS。然后:
```bash
cd backend
git add app/extensions/output/generator.py tests/test_output_generate_integration.py
git commit -m "feat(output): wire cover+TOC+numbering into generate_docx 3-section flow" -- app/extensions/output/generator.py tests/test_output_generate_integration.py
```

---

## Task 9: `routers.py` — 提取 helper + 加 cover Form 参数

**Files:**
- Modify: `backend/app/extensions/output/routers.py`
- Test: `backend/tests/test_output_routers.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_output_routers.py`:
```python
"""Tests for routers template_data assembly + cover field collection."""
from types import SimpleNamespace

from app.extensions.output.routers import _build_template_data, _collect_cover_fields


def _fake_template():
    return SimpleNamespace(
        page_settings={"paperSize": "A4"},
        body_styles={"fontFamily": "宋体"},
        heading_styles=[{"level": 1, "numbering": "decimal"}],
        table_styles=None,
        figure_styles=None,
        header_footer={"showPageNumber": True},
        reference_style="gb7714",
        appendix_rules=None,
        cover_template={"showTitle": True},
        toc_settings={"maxDepth": 2},
    )


def test_build_template_data_includes_cover_and_toc():
    """Regression: cover_template + toc_settings must NOT be dropped (the original bug)."""
    td = _build_template_data(_fake_template())
    assert td["cover_template"] == {"showTitle": True}
    assert td["toc_settings"] == {"maxDepth": 2}
    assert td["page_settings"] == {"paperSize": "A4"}
    assert td["reference_style"] == "gb7714"


def test_build_template_data_cover_none_when_absent():
    tpl = _fake_template()
    tpl.cover_template = None
    tpl.toc_settings = None
    td = _build_template_data(tpl)
    assert td["cover_template"] is None
    assert td["toc_settings"] is None


def test_collect_cover_fields_drops_none():
    fields = _collect_cover_fields(
        cover_title="T", cover_client=None, cover_date="2026-07", cover_project_number=None
    )
    assert fields == {"title": "T", "date": "2026-07"}


def test_collect_cover_fields_all_none_returns_empty():
    assert _collect_cover_fields(None, None, None, None) == {}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_routers.py -v
```
Expected: FAIL — `ImportError: cannot import name '_build_template_data'`

- [ ] **Step 3: 改 `routers.py`**

在 `routers.py` 的 `router = APIRouter(...)` 之后、`_OUTPUT_DIR` 之前新增两个模块级 helper:
```python
def _build_template_data(template) -> dict:
    """Assemble the template_data dict passed to generate_docx.

    Includes cover_template + toc_settings (these were previously dropped —
    that was the bug that made cover/TOC configuration inert).
    """
    return {
        "page_settings": template.page_settings or {},
        "body_styles": template.body_styles or {},
        "heading_styles": template.heading_styles or [],
        "table_styles": template.table_styles,
        "figure_styles": template.figure_styles,
        "header_footer": template.header_footer,
        "reference_style": template.reference_style,
        "appendix_rules": template.appendix_rules,
        "cover_template": template.cover_template,
        "toc_settings": template.toc_settings,
    }


def _collect_cover_fields(
    cover_title: str | None,
    cover_client: str | None,
    cover_date: str | None,
    cover_project_number: str | None,
) -> dict:
    """Collect non-None cover Form params into a {title/client/date/project_number} dict."""
    fields = {}
    if cover_title:
        fields["title"] = cover_title
    if cover_client:
        fields["client"] = cover_client
    if cover_date:
        fields["date"] = cover_date
    if cover_project_number:
        fields["project_number"] = cover_project_number
    return fields
```

然后修改 `generate_report` 端点:

① 函数签名加 4 个 Form 参数。把:
```python
async def generate_report(
    source: str = Form(...),
    format: str = Form("docx"),
    layout_template_id: str = Form(...),
    watermark: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    chapter_ids: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
```
改为:
```python
async def generate_report(
    source: str = Form(...),
    format: str = Form("docx"),
    layout_template_id: str = Form(...),
    watermark: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    chapter_ids: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    cover_title: Optional[str] = Form(None),
    cover_client: Optional[str] = Form(None),
    cover_date: Optional[str] = Form(None),
    cover_project_number: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
```

② 把组装 `template_data` 的那段(原 150-159 行):
```python
    template_data = {
        "page_settings": template.page_settings or {},
        "body_styles": template.body_styles or {},
        "heading_styles": template.heading_styles or [],
        "table_styles": template.table_styles,
        "figure_styles": template.figure_styles,
        "header_footer": template.header_footer,
        "reference_style": template.reference_style,
        "appendix_rules": template.appendix_rules,
    }
```
改为:
```python
    template_data = _build_template_data(template)
    cover_fields = _collect_cover_fields(cover_title, cover_client, cover_date, cover_project_number)
```

③ 把 `generate_docx(...)` 调用(原 168-173 行):
```python
    generate_docx(
        markdown_content=markdown_content,
        template_data=template_data,
        output_path=output_path,
        watermark=watermark,
    )
```
改为:
```python
    generate_docx(
        markdown_content=markdown_content,
        template_data=template_data,
        output_path=output_path,
        watermark=watermark,
        cover_fields=cover_fields,
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_routers.py -v
```
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/output/routers.py tests/test_output_routers.py
git commit -m "feat(output): pass cover_template/toc_settings + cover_* form params to generator" -- app/extensions/output/routers.py tests/test_output_routers.py
```

---

## Task 10: `seed_builtin_templates` per-id upsert 回归测试

**背景:** Task 已在本次设计阶段预先实现(seed.py 已改 + 已 psql 验证)。补一个回归测试锁住"新增 builtin 只补缺的、不动已有"。

**Files:**
- Test: `backend/tests/test_output_seed.py`

- [ ] **Step 1: 写测试**

创建 `backend/tests/test_output_seed.py`:
```python
"""Regression: seed_builtin_templates is per-id idempotent (adds only missing builtins)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.extensions.output import seed
from app.extensions.output.models import LayoutTemplate


class _FakeResult:
    def __init__(self, ids):
        self._ids = ids

    def all(self):
        return [(i,) for i in self._ids]

    def scalars(self):
        return self

    def first(self):
        return self._ids[0] if self._ids else None


def _fake_db(existing_ids):
    """Minimal AsyncSession fake: returns existing builtin ids, records added."""
    db = AsyncMock()
    added = []

    async def _execute(stmt):
        return _FakeResult(existing_ids)

    async def _commit():
        return None

    db.execute = _execute
    db.commit = _commit
    db.add = lambda obj: added.append(obj)
    db._added = added
    return db


async def test_seeds_only_missing_builtins():
    # one builtin already present (the first); should add the rest
    existing = {uuid.UUID(seed.BUILTIN_TEMPLATES[0]["id"])}
    db = _fake_db(existing)
    await seed.seed_builtin_templates(db)
    added_ids = {t.id for t in db._added}
    expected_new = {
        uuid.UUID(t["id"]) for t in seed.BUILTIN_TEMPLATES[1:]
    }
    assert added_ids == expected_new
    assert uuid.UUID(seed.BUILTIN_TEMPLATES[0]["id"]) not in added_ids


async def test_seeds_nothing_when_all_present():
    existing = {uuid.UUID(t["id"]) for t in seed.BUILTIN_TEMPLATES}
    db = _fake_db(existing)
    await seed.seed_builtin_templates(db)
    assert db._added == []
    db.commit.assert_not_called()


async def test_seeds_all_when_empty():
    db = _fake_db(set())
    await seed.seed_builtin_templates(db)
    assert len(db._added) == len(seed.BUILTIN_TEMPLATES)
```

> **注:** `db.commit = _commit` 把真实 AsyncMock 的 commit 覆盖成 coroutine;`test_seeds_nothing` 用 `db.commit.assert_not_called()` —— 但我们用 `_commit` 覆盖后它不是 AsyncMock 了。改为:在 `_fake_db` 里保留 `db.commit = AsyncMock()` 并让被测函数 `await db.commit()`。修正 `_fake_db`:
> ```python
> def _fake_db(existing_ids):
>     db = AsyncMock()
>     added = []
>     async def _execute(stmt):
>         return _FakeResult(existing_ids)
>     db.execute = _execute
>     db.add = lambda obj: added.append(obj)
>     db._added = added
>     # db.commit stays an AsyncMock (awaitable, assertable)
>     return db
> ```
> 这样 `await db.commit()` 走 AsyncMock,`assert_not_called()` 可用。

- [ ] **Step 2: 跑测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_output_seed.py -v
```
Expected: PASS(3 passed)。若 `asyncio` 收集报错,在文件顶部加 `import pytest` 并给用例加 `@pytest.mark.asyncio`(项目已配 asyncio mode)。

- [ ] **Step 3: 提交**

```bash
cd backend
git add tests/test_output_seed.py
git commit -m "test(output): lock per-id upsert in seed_builtin_templates" -- tests/test_output_seed.py
```

---

## 收尾验证

- [ ] **全量测试 + lint**
```bash
cd backend && make lint && PYTHONPATH=. uv run pytest tests/test_output_*.py -v
```
Expected: ruff 0 errors,所有 output 测试 PASS。

- [ ] **容器内端到端冒烟**(用新加的「消防设计专篇」模板真跑一次 /generate)
```bash
docker compose -p eai-docker restart gateway
# 取 csrf + session cookie 后:
curl -b cookies.txt -H "X-CSRF-Token: <csrf>" -F "source=markdown" \
  -F "layout_template_id=00000000-0000-4000-8000-000000000005" \
  -F "content=# 总论\n## 子节\n正文。\n" \
  -F "cover_title=基地项目消防设计专篇" -F "cover_client=吉林院" \
  -F "cover_date=2026-07" -F "cover_project_number=JL-001" \
  http://localhost:2026/api/extensions/output/generate
```
下载生成的 docx,用 Word/WPS 打开 → 应见:封面(标题/建设单位/项目编号/日期)→ 目录(自动出页码)→ 正文(标题带 1 / 1.1 编号,页码从 1 起)。

- [ ] **回归:** 现有 4 个内置模板中无 `cover_template` 的(如"通用A4")生成行为不变(无封面无目录,单节)。

---

## Self-Review(plan 自检)

**Spec coverage:**
- §5.1 数据流 → Task 8(generate_docx 流式)+ Task 9(router 补传) ✓
- §5.2 封面 → Task 4 + Task 7(渲染 + 字段解析) ✓
- §5.3 目录 → Task 5 ✓
- §5.4 标题编号 → Task 2 + Task 8(前缀接入) ✓
- §5.5 多节页码 → Task 6 + Task 8(_apply_section_chrome) ✓
- §5.6 API/Schema → Task 9 ✓
- §5.7 CJK 字体修复 → Task 3 ✓
- §5.8 docmgr 导出默认不变 → Task 8 未改 `generate_docx_simple`,行为不变 ✓(显式不碰)
- §6 错误处理 → Task 4(缺值跳行)+ Task 5(None/0 跳目录)+ Task 8(cover try/except 降级) ✓
- §7 测试清单 → Tasks 1-10 全覆盖 ✓
- §10 已完成前置(seed) → Task 10 回归测试 ✓

**Placeholder scan:** 无 TBD/TODO 占位;Task 8 Step 3 有一处"清理"说明(删除冗余 `_set_section_pagenum` 行),已给出最终代码,非占位。

**Type consistency:** `_render_cover(doc, cover_template, cover_fields)` / `_resolve_cover_fields(api, fm, blocks)` / `_set_section_pagenum(section, fmt, start)` / `_add_page_number_footer(section)` / `_build_template_data(template)` / `_collect_cover_fields(...)` 在各 Task 与测试中签名一致。`generate_docx` 新增 `cover_fields: dict | None = None` 形参与 Task 9 调用一致。
