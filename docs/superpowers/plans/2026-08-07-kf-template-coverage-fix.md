# P3 覆盖不完整修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 `build_structure_hint` 输出完整子节树 + 短摘要，解决 Step 1 章节推断看不到长章节子节标题导致 Step 2 成体系漏表的问题。

**Architecture:** `build_structure_hint`（doc_parser.py:568）当前给 Step 1 LLM 每章仅 450 字摘要，长章节（环评 406 页）的子节标题被截断 → 子节树建不全 → Step 2 漏抽被漏子节的表。改为：输出 H1 目录 → 每 H1 下完整子节树（H2/H3/H4，过滤表 caption）→ 每章 200 字短摘要。子节树来自已解析的 `parsed.headings`（零额外成本）。

**Tech Stack:** Python 3.12, pytest。改动仅 `backend/app/extensions/knowledge_factory/doc_parser.py` + 测试。

**Spec:** `docs/superpowers/specs/2026-08-07-kf-template-coverage-fix-design.md`

**文件结构:**
- Modify: `backend/app/extensions/knowledge_factory/doc_parser.py` — 新增 `_is_table_caption` helper + 重写 `build_structure_hint`
- Modify: `backend/tests/test_kf_doc_parser.py` — 新增子节树/表caption过滤/短摘要测试

**实证基线**（供验证）:
- 横城环评：level 分布 {1:14, 2:70, 3:179, 4:64, 5:65}
- level 5 全部（65/65）是"表N.M-x"格式；level 4 全部（64/64）是真章节
- 子节树提示实测 ~5650 chars < max_chars 5000（需在实现中确认截断行为）

---

### Task 1: 新增 `_is_table_caption` 判定 + 子节树构建 helper（TDD）

**Files:**
- Modify: `backend/tests/test_kf_doc_parser.py`
- Modify: `backend/app/extensions/knowledge_factory/doc_parser.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_kf_doc_parser.py` 末尾追加：

```python
# ── P3 覆盖修复: 表 caption 过滤 + 子节树构建 ──

def test_is_table_caption_matches():
    """'表N.M-x' 标题是表格 caption，不是章节。"""
    from app.extensions.knowledge_factory.doc_parser import _is_table_caption
    assert _is_table_caption("表1.4-1") is True
    assert _is_table_caption("表 10.1-1") is True
    assert _is_table_caption("表2.3-10") is True
    # level 5 的（expat 样式路径产出）也识别
    assert _is_table_caption("表3.4-20") is True


def test_is_table_caption_rejects_real_sections():
    """真实章节标题（含数字编号）不是表格 caption。"""
    from app.extensions.knowledge_factory.doc_parser import _is_table_caption
    assert _is_table_caption("2.2.1.1 原总体规划批复情况") is False
    assert _is_table_caption("10 环境管理、监测计划与跟踪评价") is False
    assert _is_table_caption("1.1 规划背景与任务由来") is False


def test_build_structure_hint_includes_subsection_tree():
    """结构提示必须包含 H1 下的 H2/H3 子节标题（P3 根因）。"""
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint
    # 手工构造带子节的 ParsedDocument
    doc = ParsedDocument(file_path="x", file_type="docx")
    paragraphs = [
        "1 总则", "内容A", "1.1 规划背景", "内容B", "1.2 评价依据", "内容C",
        "2 规划方案", "内容D",
    ]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 规划背景", level=2, para_idx=2),
        Heading(title="1.2 评价依据", level=2, para_idx=4),
        Heading(title="2 规划方案", level=1, para_idx=6),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 5000)
    # 子节树包含 H2 标题
    assert "1.1 规划背景" in hint
    assert "1.2 评价依据" in hint
    # H1 目录仍存在
    assert "2 规划方案" in hint


def test_build_structure_hint_filters_table_captions():
    """表 caption（表N.M-x）不进入子节树。"""
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint
    doc = ParsedDocument(file_path="x", file_type="docx")
    paragraphs = ["1 总则", "见下表", "表1.4-1", "数据行", "2 结论", "结束"]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="表1.4-1", level=5, para_idx=2),  # 表格 caption 误标 Heading5
        Heading(title="2 结论", level=1, para_idx=4),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 5000)
    assert "表1.4-1" not in hint  # 过滤
    assert "1 总则" in hint


def test_build_structure_hint_truncates_summary_not_tree():
    """max_chars 截断时子节树优先保留，摘要后砍。"""
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint
    doc = ParsedDocument(file_path="x", file_type="docx")
    long_text = "内容" * 3000  # 超 max_chars
    paragraphs = ["1 总则", "1.1 子节", long_text]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 子节", level=2, para_idx=1),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 1000)  # 小预算
    # 子节树（短）必须保留
    assert "1.1 子节" in hint
    assert "1 总则" in hint
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_doc_parser.py -k "is_table_caption or structure_hint" -v`
Expected: FAIL — `ImportError: cannot import name '_is_table_caption'`

- [ ] **Step 3: 实现 `_is_table_caption`**

在 `doc_parser.py` 中 `_heading_level_from_number` 函数之后（行 ~151）添加：

```python
_TABLE_CAPTION_RE = re.compile(r"^表\s*\d+[\.\-]\d+")


def _is_table_caption(title: str) -> bool:
    """判断标题是否为表格 caption（'表N.M-x' 格式）。

    环评样例中，表格标题被作者套了 Heading 5 样式（level=5，65/65 全是
    '表N.M-x'），而 level 4 是真章节（2.2.1.1）。用格式而非 level 判定，
    兼容 regex 兜底（_heading_level_from_number 上限 3，无 level 5）。
    """
    return bool(_TABLE_CAPTION_RE.match(title.strip()))
```

- [ ] **Step 4: 运行测试确认失败（只剩 structure_hint 测试）**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_doc_parser.py -k "structure_hint" -v`
Expected: FAIL — 断言 `1.1 规划背景 in hint` 失败（旧实现只输出 450 字摘要，H2 标题可能不在或仅在内容里）

- [ ] **Step 5: 重写 `build_structure_hint`**

替换 `doc_parser.py` 的 `build_structure_hint` 函数（当前 568-579 行）为：

```python
def build_structure_hint(parsed: ParsedDocument, max_chars: int = 5000) -> str:
    """构建结构提示：完整章节树 + 每章短摘要。

    P3 修复（覆盖不完整）：旧实现每章仅前 450 字摘要，长章节（环评 406 页
    13 章全部）子节标题被截断 → Step 1 章节推断建不全子节树 → Step 2
    漏抽被漏子节的表。改为：
    1. H1 目录 + 每 H1 下完整子节树（H2/H3/H4，过滤表 caption）
    2. 每章 200 字短摘要（结构已由子节树提供，内容仅作 purpose 信号）
    子节树优先保留，max_chars 超限时摘要后砍。
    """
    headings = parsed.headings
    if not headings:
        return parsed.full_text[:max_chars]

    # H1 起始 index 列表（无 H1 时退化到 level<=2）
    h1_positions = [i for i, h in enumerate(headings) if h.level == 1]
    if not h1_positions:
        h1_positions = [i for i, h in enumerate(headings) if h.level <= 2]
    if not h1_positions:
        h1_positions = list(range(len(headings)))

    parts = [f"## 文档章节目录（自动识别，共 {len(h1_positions)} 章）\n"]

    # 子节树：H1 → H2/H3/H4，过滤表 caption（表N.M-x 是 Heading5 噪声）
    for pi, start in enumerate(h1_positions):
        end = h1_positions[pi + 1] if pi + 1 < len(h1_positions) else len(headings)
        h1 = headings[start]
        parts.append(f"### {h1.title}")
        for k in range(start + 1, end):
            hk = headings[k]
            if hk.level > 4 or _is_table_caption(hk.title):
                continue
            indent = "  " * (hk.level - 2)
            parts.append(f"{indent}- {hk.title}")

    parts.append("\n## 各章节内容摘要（每章节前200字）\n")
    for start in h1_positions:
        h = headings[start]
        idx = h.text_offset if h.text_offset >= 0 else parsed.full_text.find(h.title)
        snippet = parsed.full_text[idx:idx + 200] if idx >= 0 else "（内容未找到）"
        parts.append(f"### {h.title}\n{snippet}\n")

    # 子节树优先：max_chars 超限时保留树 + 预算内摘要，树本身超限则截断树
    result = "\n".join(parts)
    if len(result) > max_chars:
        tree_lines = []
        for line in parts:
            if line.startswith("## 各章节内容摘要"):
                break
            tree_lines.append(line)
        tree = "\n".join(tree_lines)
        if len(tree) <= max_chars:
            budget = max_chars - len(tree)
            summary_lines = []
            for line in parts:
                if not line.startswith("### ") or line in tree_lines:
                    continue
                if sum(len(s) for s in summary_lines) + len(line) > budget:
                    break
                summary_lines.append(line)
            result = tree + "\n" + "\n".join(summary_lines)
        else:
            result = tree[:max_chars]
    return result
```

注意：`hk.level > 4` 过滤 level 5（表 caption）；`_is_table_caption` 双保险匹配"表N.M-x"格式（兼容 regex 兜底路径无 level 5 的情况）。`line in tree_lines` 用逐行相等判断避免摘要里同标题误判。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_doc_parser.py -k "is_table_caption or structure_hint" -v`
Expected: 5 PASS

- [ ] **Step 7: 跑全套件确认无回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_doc_parser.py`
Expected: 全部 PASS（现有用例 + 5 新）

- [ ] **Step 8: Commit**

```bash
git add backend/app/extensions/knowledge_factory/doc_parser.py backend/tests/test_kf_doc_parser.py
git commit -m "feat(kf): build_structure_hint 输出子节树+短摘要 (P3 覆盖修复)"
```

---

### Task 2: 端到端验证（需 gateway 环境）

**Files:**
- 无代码改动，仅验证

- [ ] **Step 1: 重启 gateway 部署**

Run: `docker compose -p eai-docker restart gateway`

- [ ] **Step 2: 重跑环评抽取任务**

用已有 Document `61c14fc7-9328-4e62-ae54-6a409bf723f6`（横城环评报批版）创建抽取任务，domain=environmental_impact_assessment，等待完成。

- [ ] **Step 3: 断言覆盖修复生效**

抓取新模板 JSON，检查：
- 第 10 章（环境管理、监测计划与跟踪评价）出现 table_schemas（至少含表10.1-1/10.2-1/10.3-1 之一）
- 总则出现评价标准表/保护目标表
- table_schemas 总数比修复前（40）显著增加
- Step 1 章节推断 detail 的子节数增加（第 10 章应有 >4 个子节）
