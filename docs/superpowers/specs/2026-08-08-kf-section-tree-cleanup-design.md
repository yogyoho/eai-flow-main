# Design: 知识工厂模板抽取 — 章节树畸形标题清理 + 去重 (P3 副作用)

**Date**: 2026-08-08
**Status**: Approved
**Source**: /superpowers:brainstorming (P3 副作用)
**Related**: bug-1125 (P3 覆盖), bug-404 (目录劫持), bug-1124 (P1 表格去重)

## Problem Statement

P3 覆盖修复后，809 节大树产生**畸形标题 + 重复章节**：

- **90 个章节标题带数字后缀**（如 `1.3 评价目的与原则11`、`10 环境管理、监测计划与跟踪评价365`、`1 总则3`）
- **84/90 剥离后缀后与树中已存在的干净孪生标题撞车** → 两代树被拼接
- 2 个孤儿章节（sec_29 `4.6 矿区生态恢复措施、效果及经验214`、sec_79 `12.5 调查结论390`）无孪生、对不上源文档

## 根因（Workflow 4 维分析确认）

**页码后缀不是 LLM 幻觉，是"目录劫持"——bug-404 只修了一半。**

`build_structure_hint`（doc_parser.py:619）的摘要切片：
```python
idx = h.text_offset if h.text_offset >= 0 else parsed.full_text.find(h.title)
```
- **text_offset >= 0**（样式化 docx）：取正文章节位置 → 干净 ✓（P3 修的路径）
- **text_offset == -1**（正则兜底：PDF / 无样式 docx）：回退 `full_text.find(h.title)` → **命中文档开头目录条目（带页码）** → LLM 拿到"标题……页码"行 → 把页码复制进标题

环评正是这种文档（正则扫出 809 标题，全 text_offset=-1）。809 节超大树是放大器：截断后 LLM 拿到 ~809 行扁平标题 + 极少摘要，注意力稀释下就近抓取唯一带页码的目录区。

**注意**：根因修复（改 find 兜底）在本次范围外——用户选择仅结果层。根因留作后续（见"后续项"）。

## 方案：结果层清理 + 章节树去重

### 决策

- **层**：结果层（`_step_validate` 内，纯函数、无 LLM、可单测）
- **范围**：仅结果层兜底，不修 doc_parser 根因（后续项）
- **核心**：`_clean_section_title`（grounding-strip）+ `_dedupe_sections`（兄弟级字段合并）+ 接线 `_step_validate`

### 1. `_clean_section_title(title: str) -> str` — 标题卫生

剥离标题尾部数字后缀（页码噪声），**grounding 约束**：剥离后剩余部分必须命中 doc_parser 源 headings 才采用，否则保留原值（防误伤合法数字结尾如"2021 年度报告"）。

```python
def _clean_section_title(title: str) -> str:
    """剥离标题尾部页码/位置噪声（P3 副作用）。

    正则兜底路径的标题可能带目录页码后缀（'1.3 评价目的与原则11'）。
    grounding 约束：剥离后剩余部分须命中源 headings，否则保留原值，
    防误伤合法数字结尾（如年份/编号）。只清理、不改变章节身份。
    """
    if not title:
        return title
    stripped = re.sub(r"[\s.…、·]{0,4}\d{1,4}\s*$", "", title).rstrip()
    # grounding: 剥离后须命中源标题（normalize 比较）
    if stripped and normalize_text(stripped) in _SOURCE_TITLE_SET:
        return stripped
    return title
```

`_SOURCE_TITLE_SET` 来自 `_parsed.headings` 的 normalize 集合，在调用处构建注入。

### 2. `_dedupe_sections(sections) -> tuple[list[dict], int]` — 章节树去重

递归、**兄弟级作用域**（同 parent 下按规范化标题分组），字段级合并（非删一留一）：
- 判定键：`(normalize(title), level)`，兄弟作用域
- 胜者决胜（确定性，仿 P1 比较元组）：无页码后缀 > rag_sources 更多 > table_schemas 更多 > completeness_score 高 > id 小
- 合并：title 取干净副本；rag_sources/generation_hint 等列表字段 union；被删节点的 children/table_schemas 吸收进胜者
- 返回 `(去重后树, 移除节数)`

### 3. 接线 `_step_validate`（纯函数、无 LLM）

在 `sections = merged.get("sections", [])` 之后、计算 score 之前：

```python
sections, removed_sections = _dedupe_sections(sections)
for s in _flatten_sections(sections):
    s["title"] = _clean_section_title(s.get("title", ""))
re_table = _dedupe_table_schemas(sections)  # 补 P1 缺口（merge 后重引入）
merged["sections"] = sections
```

即：清理标题 → 章节去重 → P1 表去重兜底 → 重算完整度。单文档路径 `_dedupe_table_schemas` 幂等返回 0。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/extensions/knowledge_factory/pipeline.py` | 新增 `_clean_section_title` + `_dedupe_sections`；`_step_validate` 接线；`_meta_stats` 加 sections 去重计数 |
| `backend/tests/test_kf_pipeline_section_dedupe.py`（新） | `_clean_section_title` / `_dedupe_sections` / `_step_validate` 集成单测 |

**不改**：`doc_parser.py`（根因修复留后续）、`llm.py`、`schemas.py`、前端。

### 孤儿章节处理（sec_29/sec_79）

无孪生且对不上源标题 → `_clean_section_title` grounding 失败会保留原值，日志告警。不静默删除（避免误删真实内容），上抛给后续人工复核。

## 测试

1. `_clean_section_title`：剥尾部页码（"1.3 评价目的与原则11"→"1.3 评价目的与原则"）、grounding 守卫（"2021 年度报告"原样保留）、空守卫（纯数字标题非空）
2. `_dedupe_sections`：同父同级同标题去重且保留胜者、不同父同名子节不去重、副本 children/table_schemas 吸收、removed 计数正确
3. `_step_validate` 集成：含重复章节+重复表的 merged dict → 去重后树、表收敛、score 重算
4. 回归：现有 73 KF 测试全绿
5. 端到端：重跑环评抽取，确认 90 个畸形标题清理、84 组孪生合并、无重复 (level, title) 键

## 后续项（不在本次范围）

- **根因修复（P1 级）**：`build_structure_hint` 的 text_offset==-1 分支改用正文章节定位（修 bug-404 另一半），让页码不进 LLM 上下文
- **prompt 硬化（P2 级）**：`_SCHEMA_INFERENCE_SYSTEM_PROMPT` 要求 title 逐字复制源标题，禁附加页码
- **规模治理（P3 级）**：>300 节点时目录压缩或分批推断，降低退化
- **孤儿章节人工复核**：sec_29/sec_79 上抛人工确认
