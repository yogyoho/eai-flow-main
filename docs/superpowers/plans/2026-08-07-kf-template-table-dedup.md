# P1 table_schemas 结果层去重 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在模板抽取流水线中，对 `table_schemas` 按 `(caption, columns)` 全局去重，消除同一逻辑表被多次抽取的膨胀（给排水 7 源表 → 26 schema，`tbl_03_01` 复用 5 次）。

**Architecture:** 在 `_step_extract_metadata` 返回前对 enriched 章节树调用新的模块级纯函数 `_dedupe_table_schemas`。该函数遍历章节树，以 `(caption, columns)` 为键收集所有 schema，保留叶子最深且文档序早的副本，返回被移除的 schema 数。单文档/多文档路径都受益（`_step_merge` 直接用去重后的 enriched）。去重计数并入 Step 2 的完成 detail。

**Tech Stack:** Python 3.12, asyncio, pytest。改动仅 `backend/app/extensions/knowledge_factory/pipeline.py` + 测试。

**Spec:** `docs/superpowers/specs/2026-08-07-kf-template-table-dedup-design.md`

**文件结构:**
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py` — 新增 `_dedupe_table_schemas` 模块级函数；`_step_extract_metadata` 返回前调用；Step 2 detail 加去重计数
- Create: `backend/tests/test_kf_pipeline_dedupe.py` — 去重单元测试

---

### Task 1: 实现 `_dedupe_table_schemas` 纯函数（TDD）

**Files:**
- Create: `backend/tests/test_kf_pipeline_dedupe.py`
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_kf_pipeline_dedupe.py`：

```python
"""Unit tests for table_schemas result-layer dedup (P1, bug 膨胀).

Regression: 给排水 7 源表 → 26 schema, tbl_03_01 复用 5 次。
_dedupe_table_schemas 按 (caption, columns) 全局去重，保留叶子最深且文档序早的。
"""

import pytest

from app.extensions.knowledge_factory.pipeline import _dedupe_table_schemas


def _table(table_id, caption, headers):
    return {
        "table_id": table_id,
        "caption": caption,
        "columns": [{"header": h} for h in headers],
    }


def _sec(id, tables, children=None):
    sec = {"id": id, "title": id, "table_schemas": tables}
    if children is not None:
        sec["children"] = children
    return sec


def test_dedupe_removes_same_caption_columns():
    """同 (caption, columns) 的 schema 只保留一份。"""
    t1 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位", "进界区压力"])
    t2 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位", "进界区压力"])
    sections = [
        _sec("sec_03", [t1]),
        _sec("sec_03_02", [t2]),
    ]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    # 保留叶子最深（sec_03_02 depth 2 > sec_03 depth 1）
    remaining = [t["table_id"] for s in sections for t in (s.get("table_schemas") or [])]
    assert len(remaining) == 1
    assert remaining == ["tbl_03_01"]


def test_dedupe_keeps_different_caption_same_columns():
    """不同 caption 同列（如吸水管/出水管）不误删。"""
    t1 = _table("tbl_08_01", "循环水泵吸水管水力计算表", ["输送水量", "管径", "流速", "i"])
    t2 = _table("tbl_08_02", "循环水泵出水管水力计算表", ["输送水量", "管径", "流速", "i"])
    sections = [_sec("sec_08", [t1, t2])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 0
    assert len(sections[0]["table_schemas"]) == 2


def test_dedupe_keeps_deepest_leaf():
    """同 (caption, cols)：父节(depth 1) 与叶子(depth 2) 并存 → 保留叶子。"""
    t_parent = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    t_leaf = _table("tbl_03_02_01", "循环水水量统计表", ["序号", "用水单位"])
    sections = [_sec("sec_03", [t_parent], children=[_sec("sec_03_02", [t_leaf])])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    # 叶子 sec_03_02 保留，父节 sec_03 的移除
    assert sections[0]["table_schemas"] == []
    assert sections[0]["children"][0]["table_schemas"] == [t_leaf]


def test_dedupe_keeps_earliest_when_same_depth():
    """同 (caption, cols) 同深度：保留文档序早的。"""
    t1 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    t2 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    sections = [_sec("sec_02_01", [t1]), _sec("sec_03_01", [t2])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    assert sections[0]["table_schemas"] == [t1]  # 文档序早的保留
    assert sections[1]["table_schemas"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_pipeline_dedupe.py -v`
Expected: FAIL — `ImportError: cannot import name '_dedupe_table_schemas' from 'app.extensions.knowledge_factory.pipeline'`

- [ ] **Step 3: 实现 `_dedupe_table_schemas`**

在 `pipeline.py` 中 `_count_sections` 函数之后（行 ~78）添加：

```python
def _dedupe_table_schemas(sections: list[dict]) -> int:
    """结果层去重：按 (caption, columns) 全局合并 table_schemas。

    同一逻辑表在父子切片重叠 + 跨章节引用下会被 LLM 重复生成
    （给排水 7 源表 → 26 schema，tbl_03_01 复用 5 次）。两遍算法：
    1. scan：确定每个 (caption, columns) 键保留哪个副本 ——
       叶子优先 → depth 大者优先 → order(文档序) 早者优先
    2. prune：移除所有非胜者副本，返回移除数。

    P1 设计：只解决数量膨胀，不解决归属错误（后者见 bug-1123）。
    """
    keep: dict[tuple, dict] = {}   # key → 保留的 table dict（对象引用）
    best: dict[tuple, tuple] = {}  # key → (is_leaf, depth, -order) 比较元组
    order = [0]

    def _scan(nodes: list[dict], depth: int) -> None:
        for sec in nodes:
            for t in sec.get("table_schemas") or []:
                key = (t.get("caption", ""), tuple(c.get("header", "") for c in (t.get("columns") or [])))
                cand = (not (sec.get("children") or []), depth, -order[0])
                order[0] += 1
                if key not in best or cand > best[key]:
                    best[key] = cand
                    keep[key] = t
            if sec.get("children"):
                _scan(sec["children"], depth + 1)

    def _prune(nodes: list[dict]) -> int:
        n = 0
        for sec in nodes:
            tables = sec.get("table_schemas") or []
            if tables:
                kept = [
                    t for t in tables
                    if keep.get(
                        (t.get("caption", ""), tuple(c.get("header", "") for c in (t.get("columns") or [])))
                    ) is t
                ]
                n += len(tables) - len(kept)
                if len(kept) < len(tables):
                    sec["table_schemas"] = kept
            if sec.get("children"):
                n += _prune(sec["children"])
        return n

    _scan(sections, 1)
    return _prune(sections)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_pipeline_dedupe.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge_factory/pipeline.py backend/tests/test_kf_pipeline_dedupe.py
git commit -m "feat(kf): table_schemas 结果层去重 (P1, (caption,columns) 键)"
```

---

### Task 2: 接入 `_step_extract_metadata` 并计入 Step 2 detail

**Files:**
- Modify: `backend/app/extensions/knowledge_factory/pipeline.py`（`_step_extract_metadata` 返回前，行 ~1500-1515）

- [ ] **Step 1: 在 `enriched` 后调用去重**

定位 `_step_extract_metadata` 中（行 ~1500）：

```python
        # 顶层章节并发抽取（semaphore 全局限流），耗时从 N×5s 降到 N/5×5s
        enriched = await asyncio.gather(*[_safe_enrich(s) for s in sections])
```

在 `enriched = await asyncio.gather(...)` 之后、`flat = _flatten_sections(enriched)` 之前插入：

```python
        # P1 结果层去重：合并 (caption, columns) 相同的 table_schemas
        deduped_count = _dedupe_table_schemas(enriched)
        if deduped_count:
            logger.info(f"[Task {task_id_meta}] 结果层去重合并 {deduped_count} 个重复 table_schemas")
```

- [ ] **Step 2: 去重计数计入 `_meta_stats`**

在同一函数中，`ctx["_meta_stats"]` 的 dict（行 ~1504-1508）增加 `deduped` 键：

```python
        ctx["_meta_stats"] = {
            "total": len(flat),
            "failed": failed["n"],
            "grounded_dropped": grounded_dropped["n"],
            "deduped": deduped_count,
        }
```

- [ ] **Step 3: Step 2 detail 加去重计数**

在 `pipeline.py` 的 `run()` 方法中，Step 2 完成的 detail 构造处（行 ~456-466，`detail = f"已抽取 {len(flat)} 节模板元数据"` 附近），`dropped_n` 之后加：

```python
        deduped_n = stats.get("deduped", 0)
        if deduped_n:
            detail += f"，去重合并 {deduped_n} 个重复表"
```

- [ ] **Step 4: 跑全套件确认无回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kf_doc_parser.py tests/test_knowledge_factory_mcp.py tests/test_kf_schemas.py tests/test_kf_pipeline_content_lookup.py tests/test_kf_pipeline_dedupe.py`
Expected: 68 PASS (64 现有 + 4 新增)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge_factory/pipeline.py
git commit -m "feat(kf): _step_extract_metadata 接入去重 + Step2 detail 计数 (P1)"
```

---

### Task 3: 端到端验证（可选，需 gateway 环境）

**Files:**
- 无代码改动，仅验证

- [ ] **Step 1: 重启 gateway 部署**

Run: `docker compose -p eai-docker restart gateway`

- [ ] **Step 2: 重跑给排水抽取任务**

用已有 Document `0e86844d-8090-4bfa-88ae-41dfb6a11108`（给排水单体计算书）创建抽取任务，domain=default，等待完成。

- [ ] **Step 3: 断言去重生效**

抓取新模板 JSON，检查：
- `table_schemas` 总数从 26 降到 ~22
- `tbl_03_01`（循环水水量统计表）不再复用 5 次
- Step 2 detail 含 "去重合并 N 个重复表"
