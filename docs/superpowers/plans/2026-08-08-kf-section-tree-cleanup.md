# P3 副作用修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在模板抽取结果层清理章节树畸形标题（剥离页码后缀）+ 章节树去重，消除 P3 修复引入的 90 个畸形标题和 84 组孪生重复章节。

**Architecture:** 在 `_step_validate`（纯函数、无 LLM）内依次执行：`_dedupe_sections`（兄弟级作用域字段合并）→ `_clean_section_title`（grounding-strip 剥离页码后缀）→ `_dedupe_table_schemas` 兜底 → 重算完整度。两函数均为模块级纯函数，可单测。

**Tech Stack:** Python 3.12, pytest。改动仅 `backend/app/extensions/knowledge_factory/pipeline.py` + 新测试文件。

**Spec:** `docs/superpowers/specs/2026-08-08-kf-section-tree-cleanup-design.md`

**文件结构:**
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py` — 新增 `_clean_section_title` + `_dedupe_sections`；接线 `_step_validate`
- Create: `backend/tests/test_kf_pipeline_section_dedupe.py` — 单元测试

**关键实现前提**：
- `_dedupe_table_schemas(sections) -> int` 已存在（P1，模块级，pipeline.py:80-129）
- `_flatten_sections(sections)` 已存在（pipeline.py:53-61）
- `normalize_text` 从 `app.extensions.knowledge_factory.doc_parser` 导入（文件内已有局部导入模式）
- grounding 集（源 headings normalize 集合）在 `_step_validate` 内从 `ctx["_documents"][*]["_parsed"].headings` 构建

---

### Task 1: 实现 `_clean_section_title` + `_dedupe_sections` 纯函数（TDD）

**Files:**
- Create: `backend/tests/test_kf_pipeline_section_dedupe.py`
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_kf_pipeline_section_dedupe.py`：

```python
"""Unit tests for section-tree cleanup (P3 副作用): _clean_section_title + _dedupe_sections.

Regression: P3 覆盖修复后 809 节大树产生 90 个带页码后缀的畸形标题
（'1.3 评价目的与原则11'）和 84 组孪生重复章节（两代树被拼接）。
"""

import pytest

from app.extensions.knowledge_factory.pipeline import (
    _clean_section_title,
    _dedupe_sections,
)


# ── _clean_section_title: grounding-strip 页码后缀 ──

def test_clean_strips_page_number_suffix():
    """剥离标题尾部页码后缀（目录劫持产物）。"""
    src = {"1.3 评价目的与原则", "1 总则", "10 环境管理、监测计划与跟踪评价"}
    assert _clean_section_title("1.3 评价目的与原则11", src) == "1.3 评价目的与原则"
    assert _clean_section_title("1 总则3", src) == "1 总则"
    assert _clean_section_title("10 环境管理、监测计划与跟踪评价365", src) == "10 环境管理、监测计划与跟踪评价"


def test_clean_keeps_title_when_strip_grounds_nowhere():
    """剥离后不命中源标题 → 保留原值（防误伤合法数字结尾）。"""
    src = {"2021 年度报告", "评价结果2"}
    assert _clean_section_title("2021 年度报告", src) == "2021 年度报告"
    assert _clean_section_title("评价结果2", src) == "评价结果2"


def test_clean_keeps_already_clean_title():
    """无后缀标题不变。"""
    src = {"1.3 评价目的与原则", "1 总则"}
    assert _clean_section_title("1.3 评价目的与原则", src) == "1.3 评价目的与原则"
    assert _clean_section_title("1 总则", src) == "1 总则"


def test_clean_empty_guard():
    """空标题原样返回。"""
    src = {"x"}
    assert _clean_section_title("", src) == ""
    assert _clean_section_title(None, src) is None


# ── _dedupe_sections: 兄弟级作用域字段合并 ──

def _sec(id, title, level=2, tables=None, children=None, rag=None):
    s = {"id": id, "title": title, "level": level}
    if tables: s["table_schemas"] = tables
    if rag: s["rag_sources"] = rag
    if children: s["children"] = children
    return s


def test_dedupe_same_parent_same_title():
    """同父同级同标题 → 保留胜者（rag_sources 更多者），副本移除。"""
    t1 = _sec("sec_03", "1.3 评价目的与原则", rag=[{"kb_id": "a"}])
    t2 = _sec("sec_91", "1.3 评价目的与原则", rag=[{"kb_id": "a"}, {"kb_id": "b"}])
    sections, removed = _dedupe_sections([t1, t2])
    assert removed == 1
    assert len(sections) == 1
    # 胜者 t2（rag_sources 更多）
    assert sections[0]["id"] == "sec_91"
    assert len(sections[0]["rag_sources"]) == 2


def test_dedupe_different_parent_same_title_not_merged():
    """不同父节点下的同名子节不合并（兄弟级作用域）。"""
    a = _sec("sec_01", "1 总则", children=[_sec("sec_01_01", "监测方法")])
    b = _sec("sec_02", "2 环境现状", children=[_sec("sec_02_01", "监测方法")])
    sections, removed = _dedupe_sections([a, b])
    assert removed == 0
    assert len(sections) == 2
    assert len(sections[0]["children"]) == 1
    assert len(sections[1]["children"]) == 1


def test_dedupe_absorbs_child_tables():
    """副本的 children 和 table_schemas 吸收进胜者。"""
    table = {"table_id": "tbl_01", "caption": "循环水水量统计表", "columns": [{"header": "序号"}]}
    t1 = _sec("sec_03", "1.3 评价目的与原则", tables=[table])
    t2 = _sec("sec_91", "1.3 评价目的与原则", rag=[{"kb_id": "a"}])
    sections, removed = _dedupe_sections([t1, t2])
    assert removed == 1
    assert len(sections) == 1
    winner = sections[0]
    # table_schemas 从副本吸收
    assert len(winner.get("table_schemas") or []) == 1
    # rag_sources 从胜者保留
    assert len(winner.get("rag_sources") or []) == 1


def test_dedupe_idempotent():
    """已去重树重跑 → no-op，removed=0。"""
    t1 = _sec("sec_03", "1.3 评价目的与原则", rag=[{"kb_id": "a"}])
    t2 = _sec("sec_91", "1.4 评价范围", rag=[{"kb_id": "b"}])
    sections, removed = _dedupe_sections([t1, t2])
    assert removed == 0
    # 重跑 no-op
    sections2, removed2 = _dedupe_sections(sections)
    assert removed2 == 0
    assert len(sections2) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_pipeline_section_dedupe.py -v`
Expected: FAIL — `ImportError: cannot import name '_clean_section_title'`

- [ ] **Step 3: 实现 `_clean_section_title`**

在 `pipeline.py` 中 `_table_schema_key` 函数之后（P1 helper 附近）添加：

```python
def _clean_section_title(title: str, source_titles: set[str]) -> str:
    """剥离标题尾部页码/位置噪声（P3 副作用，目录劫持产物）。

    正则兜底路径的标题可能带目录页码后缀（'1.3 评价目的与原则11'）。
    grounding 约束：剥离后剩余部分须命中源 headings（normalize 后），
    否则保留原值，防误伤合法数字结尾（如 '2021 年度报告'）。
    只清理、不改变章节身份。
    """
    if not title:
        return title
    stripped = re.sub(r"[\s.…、·]{0,4}\d{1,4}\s*$", "", title).rstrip()
    if stripped and normalize_text(stripped) in source_titles:
        return stripped
    return title
```

- [ ] **Step 4: 实现 `_dedupe_sections`**

在 `_clean_section_title` 之后添加：

```python
def _dedupe_sections(sections: list[dict]) -> tuple[list[dict], int]:
    """章节树去重：兄弟级作用域 + 字段级合并（P3 副作用）。

    809 节大树的孪生重复章节（两代树拼接，'1.3 评价目的与原则' vs
    '1.3 评价目的与原则11'）。递归按 (normalize(title), level) 在兄弟级
    分组，命中时把副本的 rag_sources/generation_hint/table_schemas/
    children 吸收进胜者，移除副本。胜者决胜：rag_sources 更多 >
    table_schemas 更多 > completeness_score 高 > id 小（文档序早）。
    返回 (去重后树, 移除节数)。
    """
    removed = [0]

    def _score(sec: dict) -> tuple:
        """胜者决胜：rag_sources 更多 > table_schemas 更多 > completeness 高。

        平局时 max() 取迭代先出现的（即文档序靠前的），确定性。
        """
        return (
            len(sec.get("rag_sources") or []),
            len(sec.get("table_schemas") or []),
            sec.get("completeness_score") or 0,
        )

    def _merge(winner: dict, loser: dict) -> None:
        """把 loser 的字段合并进 winner（字段级，非删一留一）。"""
        for key in ("rag_sources", "generation_hint", "compliance_rules"):
            lv = loser.get(key)
            wv = winner.get(key)
            if lv and not wv:
                winner[key] = lv
        # table_schemas union
        wt = winner.get("table_schemas") or []
        for t in loser.get("table_schemas") or []:
            key = (t.get("caption", ""), tuple(c.get("header", "") for c in (t.get("columns") or [])))
            if not any(
                (x.get("caption", ""), tuple(c.get("header", "") for c in (x.get("columns") or []))) == key
                for x in wt
            ):
                wt.append(t)
        if wt:
            winner["table_schemas"] = wt
        # children 吸收（递归去重）
        wc = winner.get("children") or []
        for child in loser.get("children") or []:
            wc.append(child)
        if wc:
            winner["children"] = wc

    def _walk(nodes: list[dict]) -> list[dict]:
        # 兄弟级分组：键 = (normalize(title), level)
        groups: dict[tuple, list[dict]] = {}
        for sec in nodes:
            key = (normalize_text(sec.get("title", "")), sec.get("level", 1))
            groups.setdefault(key, []).append(sec)
        out = []
        for key, members in groups.items():
            if len(members) <= 1:
                out.extend(members)
                continue
            # 胜者 = score 最大者
            winner = max(members, key=_score)
            for m in members:
                if m is not winner:
                    _merge(winner, m)
                    removed[0] += 1
            # 递归 children 去重
            if winner.get("children"):
                winner["children"] = _walk(winner["children"])
            out.append(winner)
        return out

    result = _walk(sections)
    return result, removed[0]
```

**注意**：`normalize_text` 需在模块顶部或函数内导入。此文件已用局部导入模式（如 `from .doc_parser import normalize_text`），在 `_clean_section_title`/`_dedupe_sections` 内局部导入即可。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_pipeline_section_dedupe.py -v`
Expected: 9 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/knowledge_factory/pipeline.py backend/tests/test_kf_pipeline_section_dedupe.py
git commit -m "feat(kf): 章节树畸形标题清理 + 兄弟级去重 (P3 副作用)"
```

---

### Task 2: 接线 `_step_validate` 并集成到流水线

**Files:**
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py`

- [ ] **Step 1: 改写 `_step_validate`**

替换当前 `_step_validate`（pipeline.py:1636-1656）为：

```python
    async def _step_validate(
        self, ctx: dict[str, Any], merged: dict
    ) -> dict:
        """检查章节完整性，计算完整度评分。结果层清理：章节去重 + 标题卫生。"""
        sections = merged.get("sections", [])
        cross_rules = merged.get("cross_section_rules", [])

        if not sections:
            merged["completeness_score"] = 0
            return merged

        # P3 副作用：章节树去重（兄弟级字段合并）+ 标题页码剥离
        source_titles: set[str] = set()
        for doc in ctx.get("_documents", []):
            parsed = doc.get("_parsed")
            if parsed is not None:
                source_titles.update(normalize_text(h.title) for h in parsed.headings)
        sections, removed_sections = _dedupe_sections(sections)
        for s in _flatten_sections(sections):
            s["title"] = _clean_section_title(s.get("title", ""), source_titles)
        re_table = _dedupe_table_schemas(sections)  # 补 P1 缺口（merge 后重引入）
        merged["sections"] = sections

        flat = _flatten_sections(sections)
        scored = [s for s in flat if s.get("completeness_score")]

        if scored:
            avg_score = sum(s.get("completeness_score", 0) for s in scored) // len(scored)
        else:
            avg_score = 50

        merged["completeness_score"] = avg_score
        # 可观测性：并入 ctx 供 run() 摘要
        ctx["_clean_stats"] = {
            "sections_deduped": removed_sections,
            "tables_deduped": re_table,
        }
        return merged
```

- [ ] **Step 2: run() 完成 detail 加清理计数**

在 `pipeline.py` 的 `run()` 方法最终 `_emit("完成", ...)` 前（行 ~524），读取清理统计并入 detail：

```python
        clean_stats = ctx.get("_clean_stats") or {}
        clean_parts = []
        if clean_stats.get("sections_deduped"):
            clean_parts.append(f"章节去重 {clean_stats['sections_deduped']} 节")
        if clean_stats.get("tables_deduped"):
            clean_parts.append(f"表格去重 {clean_stats['tables_deduped']} 个")
        final_detail = f"所有阶段完成，共 {chapters} 章 / {total} 节"
        if clean_parts:
            final_detail += f"（{'，'.join(clean_parts)}）"
```

找到 `await _emit("完成", StepStatus.COMPLETED, ...)` 的调用处（run() 末尾），用 `final_detail` 替换原 detail 字符串。

- [ ] **Step 3: 跑全套件确认无回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_pipeline_dedupe.py tests/test_kf_pipeline_section_dedupe.py tests/test_kf_pipeline_content_lookup.py tests/test_kf_doc_parser.py tests/test_kf_schemas.py tests/test_knowledge_factory_mcp.py`
Expected: 82 PASS (73 现有 + 9 新)

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/knowledge_factory/pipeline.py
git commit -m "feat(kf): _step_validate 接入章节去重+标题清理 (P3 副作用)"
```

---

### Task 3: 端到端验证（需 gateway 环境）

**Files:**
- 无代码改动，仅验证

- [ ] **Step 1: 重启 gateway 部署**

Run: `docker compose -p eai-docker restart gateway`

- [ ] **Step 2: 重跑环评抽取任务**

用已有 Document `61c14fc7-9328-4e62-ae54-6a409bf723f6`（横城环评）创建抽取任务，等待完成。

- [ ] **Step 3: 断言清理生效**

抓取新模板 JSON，检查：
- 无带数字后缀的畸形标题（`\d{2,4}$` 结尾且非表编号）
- 无重复 (level, normalize title) 键
- 第 10 章正常（无双第 10 章）
- Step 完成 detail 含章节去重计数
