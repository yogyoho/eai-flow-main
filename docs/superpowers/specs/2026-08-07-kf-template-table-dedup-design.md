# Design: 知识工厂模板抽取 — table_schemas 结果层去重 (P1)

**Date**: 2026-08-07
**Status**: Approved
**Source**: /superpowers:brainstorming (P1 重复抽取膨胀)
**Related**: bug-1120 (docx 表格进 LLM), bug-1122 (input_vars str→list), bug-1123 (内容查找降级诱导幻觉)

## Problem Statement

模板抽取流水线中，`table_schemas` 存在**重复抽取膨胀**：同一逻辑表被多次生成，导致模板体积虚高、章节归属混乱。

实测数据（真实文档端到端抽取）：
- 给排水：7 源表 → **26 个 table_schemas**（3.7x），`tbl_03_01` 复用 5 次、`tbl_05_01` 复用 4 次
- 环评：192 源表 → 40（去重后仅 ~30）
- 消防：8

## 根因（三机制）

1. **父子层级切片重叠（主因）**：`_enrich` 递归处理每个节点（父节和子节各自独立调一次 LLM），而 `section_text_by_title` 对父节返回整棵子树（含所有子节内容）。实证：`设计规模`(lvl1) 和 `工艺装置循环水量`(lvl2) 的切片都含表3.1-1。
2. **跨章节引用放大**：正文里一个表被多处引用（"见表3.1-1~2"），引用它的章节切片也含该表 → LLM 认为该章节也需要它。
3. **LLM 无全局视野 + 结果层零去重**：每节独立调用，LLM 不知道"这张表别处已抽过"；单文档路径 `_step_merge` 直接用 enriched 结果，富元数据零去重。

核心矛盾：**逐节抽取保证每节独立，但牺牲全局唯一性**。

## 方案：结果层去重（融合前）

### 决策

- **层**：结果层去重（不碰 LLM prompt、不改切片语义）
- **时机**：`_step_extract_metadata` 返回前（行 ~1500 `enriched` 后）对 enriched 全局去重；`_step_merge` 单文档路径直接用去重后结果，多文档路径先去重再喂 LLM 融合
- **判定键**：`(caption, columns)` 完全相同的 schema 视为重复
- **保留策略**：保留**叶子最深且文档序早**的副本（叶子优先 → depth 大者优先 → order 小者优先）

### 判定键安全性验证

按 `(caption, columns)` 精确分组，给排水 26 个 schema 中**只有 1 个真正的重复组**（循环水水量统计表 ×5）。其余 21 个组合全部唯一——包括吸水管/出水管两张同结构表（caption 不同，不会被误删）。模拟去重：26 → 22。

### 保留策略边界（已知，不修）

去重只解决数量膨胀，不解决**归属错误**（表挂错章节，如循环水水量统计表误挂在"标准及规范"子节下）。这是 bug-1123 那类幻觉的残留，超出本方案范围，单列后续项。

### 实现要点

- 新增 `_dedupe_table_schemas(sections: list[dict]) -> int`：遍历章节树收集所有 (caption, columns, meta)，用 dict 以 (caption, cols) 为键去重，返回被移除的 schema 数（可观测性）
- 保留副本的 `table_id` 沿用；被移除副本直接删除（不保留标记）
- 去重**不**处理 `figure_requirements`/`formula_references`（当前无明确重复证据，YAGNI）
- 去重计入 Step 2 完成 detail：`已抽取 N 节模板元数据，去重合并 M 个重复表`（与 `grounding 丢弃` 并列）

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/extensions/knowledge_factory/pipeline.py` | 新增 `_dedupe_table_schemas`；`_step_extract_metadata` 返回前调用；step detail 加去重计数 |
| `backend/tests/test_kf_pipeline_content_lookup.py`（或新文件） | 新增去重单元测试：同 (caption,cols) 去重、不同 caption 同列不误删、叶子最深优先 |

**不改**：`llm.py`（prompt）、`doc_parser.py`（切片）、`schemas.py`、`service.py`、前端。

## 测试

1. 单元：`_dedupe_table_schemas` 输入含 2 个同 (caption,cols) schema → 保留 1 个，返回移除 1
2. 单元：不同 caption 同列（吸水管/出水管）→ 都不删
3. 单元：同 caption+cols 但一个父节一个叶子 → 保留叶子
4. 回归：现有 64 测试全绿
5. 端到端：重跑给排水抽取，table_schemas 26 → ~22，无 tbl_03_01 复用 5 次

## 后续项（不在本次范围）

- P2 归属错误（表挂错章节）— bug-1123 残留，需切片/章节推断层修复
- P3 覆盖不完整（环评漏"环境管理监测计划"整章 4 表）
- P5 input_vars 键名不统一
