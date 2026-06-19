# Design: 知识工厂报告模板 — 结构化富元数据增强

**Date**: 2026-06-19
**Status**: Approved (pending spec review)
**Source**: `/plan-ceo-review` + `/superpowers:brainstorming` session

## Context

分析真实环评报告样例（横城矿区，406 页）发现：报告 ~50% 的篇幅是表格（190 个）和图片（187 个），并大量引用公式（63 个标准引用）。当前知识工厂的 `TemplateSection` 模型只提取文本级元数据（`key_elements`、`structure_type`、`min_word_count` 等），完全缺少表结构、图片需求、公式引用、计算脚本绑定等富内容元数据。

结果：agent 生成报告时只能凭 `generation_hint` 自行脑补表格表头、图片位置、公式编号——跨轮次产出不一致，且无法精准驱动 `scripts/calc/` 计算脚本。

**目标**：在知识工厂的「模板抽取」（LLM 自动）和「模板编辑」（人工修正）两条路径中，统一引入 5 个新的结构化元数据字段，使 `kf_resolve_template` 返回的模板能完整描述一章报告需要的表格/图片/公式/计算/章节深度，agent 据此生成格式一致、内容完整的报告。

## 设计模式：混合（LLM 抽取 + 人工修正）

- **LLM 自动抽取**（模板抽取 tab）：增强 `_METADATA_EXTRACTION_*` prompt，让 LLM 从样例报告中识别 5 类新字段，自动填充。
- **人工修正**（模板编辑 tab）：在每个章节的编辑表单中新增 5 个可折叠区域，用户校准 LLM 抽错的、补充 LLM 漏掉的字段。
- **MCP 透传**：`kf_resolve_template` 已返回完整 `root_sections` JSON，新字段无需改 MCP 协议即透明透传给 agent。

## 数据模型：5 个新字段

所有字段挂在 `TemplateSection` 上，全部 optional（老模板和样例中无对应内容的章节不报错）。

### 1. `table_schemas: TableSchema[]` — 按章节的表结构定义

```python
class TableColumn(BaseModel):
    header: str          # "编号"
    width: str = ""      # "5%"
    type: str = "string" # string|number|coordinate|unit
    unit: str = ""       # "μg/m³"

class TableSchema(BaseModel):
    table_id: str        # "tbl_03_01"
    caption: str         # "表 3-1  监测点位布设一览表"
    columns: list[TableColumn] = []
    data_source: str = "template"  # template|user|calc|monitoring
    required: bool = True
```

### 2. `figure_requirements: FigureRequirement[]` — 按章节的图片/图表需求

```python
class FigureRequirement(BaseModel):
    figure_id: str       # "fig_03_01"
    caption: str         # "图 3-1  区域监测点位分布图"
    suggested_type: str = "image"  # mermaid|ascii|image|text_fallback
    placement_section: str = ""    # "3.2.1"
    required: bool = False
    fallback: str = ""   # 无图时的文字替代
```

### 3. `formula_references: FormulaReference[]` — 按章节的公式引用

```python
class FormulaReference(BaseModel):
    formula_id: str      # "HJT2.3-2018_§6.2.1"
    name: str            # "完全混合河流水质预测模型"
    applicable_section: str = ""  # "6.3.2"
    expression: str = ""          # "C_mix = (Q_up·C_up + Q_d·C_d) / ..."
    input_vars: list[str] = []    # ["Q_up", "C_up", "Q_d", "C_d"]
```

### 4. `calc_script_bindings: CalcScriptBinding[]` — 计算脚本绑定

```python
class CalcScriptParam(BaseModel):
    name: str            # "H"
    unit: str = ""       # "m"
    source: str = "user" # user|default|calc_params_guide

class CalcScriptBinding(BaseModel):
    script: str          # "scripts/calc/calc_subsidence.py"
    section: str = ""    # "6.2.4"
    input_params: list[CalcScriptParam] = []
    output_table: str = ""  # 引用 table_schemas.table_id
    trigger: str = "auto"   # auto|manual
```

### 5. `sub_section_profile: SubSectionProfile | None` — 子章节深度指导

```python
class SubSectionProfile(BaseModel):
    expected_h2_count: int = 0
    expected_h3_count: int = 0
    volume_estimate: str = "medium"  # short|medium|long
    notes: str = ""
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/extensions/knowledge_factory/schemas.py` | 新增 5 组 Pydantic 模型；`TemplateSection`/`ContentContract` 增 5 个 optional 字段 |
| `backend/app/extensions/knowledge_factory/llm.py` | 增强 `_METADATA_EXTRACTION_SYSTEM_PROMPT` + `_USER_PROMPT_TEMPLATE`，JSON schema 中新增 5 个 optional block |
| `frontend/src/extensions/knowledge-factory/types.ts` | 新增对应 TS interface；`TemplateSection`/`EditorSection` 增 5 个 optional 字段 |
| `frontend/src/extensions/knowledge-factory/TemplateEditor.tsx` | 每章节编辑表单新增 5 个可折叠输入区域 |

**不改**：`models.py`（`root_sections_json` 是 JSONB，自动容纳）、`mcp_server/server.py`（透明透传）、`pipeline.py`（提取流程不变）。

**前置依赖**：`coal-eia-report/SKILL.md` 需要另行增加"读取并使用新字段"的指令（按 `table_schemas` 生成表格、按 `figure_requirements` 嵌图、按 `calc_script_bindings` 调脚本）。本期只让数据流通（抽取→编辑→MCP 返回）；技能消费侧作为紧随其后的 skill-layer 改动，不并入本期 spec。

## LLM 提取 prompt 增强

`_METADATA_EXTRACTION_SYSTEM_PROMPT` 新增字段说明（告诉 LLM 输出什么）；`_METADATA_EXTRACTION_USER_PROMPT_TEMPLATE` 的 JSON schema 模板新增 5 个 optional block。所有新字段标注「样例中无对应内容则返回空数组/null」。

## 模板编辑器 UI

每章节编辑表单在现有 `content_contract` 区域下方新增 5 个可折叠 section（默认折叠，有内容显示计数 badge）：

- 📊 表格定义（Table Schemas）— 表格列表，每行编辑 id/caption/columns（动态增删列）/data_source/required
- 📷 图片需求（Figure Requirements）— 图片列表，每行编辑 id/caption/type/fallback
- 📐 公式引用（Formula References）— 公式列表，每行编辑 id/name/expression/section/input_vars
- ⚙️ 计算脚本（Calc Script Bindings）— 脚本列表，每行编辑 script/section/trigger/input_params/output_table
- 📏 章节剖面（Sub-Section Profile）— H2/H3 预期数 + 篇幅估计

## 边界与兼容性

- 所有新字段 optional → 老 API/老模板/无对应内容的章节不报错。
- LLM 抽不准的字段返回空 → 用户在编辑器中补充。
- `kf_resolve_template` 返回的 JSON 体积会增大（含表格列定义等），但 skill 端已用 `tool_output_budget_middleware` 自动外化大输出（fire-protection 测试时已见 97KB→166KB 外化到 .tool-results）。
- 环评报告样例 166KB 模板 + 新字段后预计 ~250-400KB，仍在 MCP 工具输出预算内。

## 验证

1. **后端**：直接调 `kf_resolve_template` 返回的 JSON 中包含新字段（先用 DB 手工塞一条测试数据验证透传）。
2. **LLM 抽取**：对横城矿区样例跑一次模板抽取任务，检查返回的 `root_sections` 中是否自动出现 `table_schemas`/`figure_requirements`（样例有 190 表 + 187 图，应抽到相当数量）。
3. **编辑器**：打开模板编辑 tab → 选章节 → 5 个新区域可编辑、可保存、刷新后持久化。
4. **端到端**（依赖前置的 skill-layer 改动）：coal-eia-report skill 生成第 3 章 → agent 按 `table_schemas` 生成表格（表头一致）、按 `figure_requirements` 嵌入图片、按 `calc_script_bindings` 调用计算脚本。本期 spec 只验证数据流通（1-3 项）；第 4 项在 skill 消费侧改动完成后验证。

## F0（前置基础设施）：合规规则 tab 下拉框动态化 + 字典对齐

### 问题

`ComplianceRules.tsx:390,447` 的行业/报告类型/地区下拉框直接 import `types.ts` 的硬编码常量（`INDUSTRIES` / `REPORT_TYPES` / `REGIONS`，`as const`，5+5+N 项英文 enum）。而：

- **业务字典 tab**（`BusinessDictionary.tsx:91`）已通过 `kfApi.listDictItems("industry")` 动态加载同一批数据。
- **后端** `GET /rule-dictionaries`（`routers.py:1295`）已从业务字典 DB 读取（`load_rule_dictionaries_from_db` → `DictionaryService.load_all_as_dict`），DB 空时回退内存种子。
- **规则 DB** 的 `industry`/`report_types` 字段值必须与字典 value 对齐才能匹配。

三套数据源（types.ts 常量 / 业务字典 DB / 规则 DB）各存各的，合规规则 tab 绕过了 DB 直读写死常量。这导致：`kf_check_compliance` 传中文 `industry="煤炭"` 时 0 匹配（规则 DB 存英文 `environmental`）；且字典维护者改了 DB，合规规则 tab 的下拉框不会更新。

### 设计

**单一数据源**：业务字典 DB 是唯一真相。合规规则 tab 通过 `GET /rule-dictionaries` 动态加载下拉选项（该 API 已从业务字典 DB 读取 + 内存回退）。`types.ts` 常量降级为 API 失败时的 fallback。

```
业务字典 DB (single source of truth)
    │
    ├── /dictionaries/{category}  ← 业务字典 tab 已用
    ├── /rule-dictionaries        ← 合规规则 tab 改为使用（本 F0）
    │     └── load_all_as_dict() 读同一张表
    └── 规则 DB industry/report_types 字段值
          └── 必须与字典 value 对齐（数据治理，非代码）
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/.../knowledge-factory/hooks.ts`（或新建） | 新增 `useRuleDictionaries()` hook，调 `GET /rule-dictionaries`，TanStack Query 缓存 |
| `frontend/.../knowledge-factory/ComplianceRules.tsx` | 行业/报告类型/地区下拉框改为从 `useRuleDictionaries()` 加载；API 失败时 fallback 到 `types.ts` 常量 |

**不改**：后端（`/rule-dictionaries` API 已就绪）、`types.ts`（保留为 fallback）。

### 边界

- API 失败/超时 → fallback 到 `types.ts` 常量，下拉框仍可用（不白屏）。
- DB 字典为空 → `/rule-dictionaries` 回退内存种子（`load_rule_dictionaries()`），返回与 `types.ts` 一致的英文 enum。
- 字典 value 与规则 DB 不一致 → 这是**数据治理**问题，不在代码范围内。建议在业务字典 tab 维护时确保 `industry`/`report_type` 字典项的 value 字段使用与规则 DB 一致的英文 enum（如 `environmental`），label 用中文显示。

### 对富元数据增强的影响

本期 spec 的模板编辑器富元数据 UI（表格/图片/公式编辑器）如果也需要行业/报告类型下拉，应复用同一个 `useRuleDictionaries()` hook，不要重新硬编码。F0 是富元数据增强的前置依赖。

### 验证

1. 业务字典 tab 新增一个 industry 字典项 → 合规规则 tab 的行业下拉框自动出现该项。
2. `/rule-dictionaries` 返回的 value 与规则 DB 的 `industry` 字段值一致（如都是 `environmental`）→ 按行业筛选规则能正确命中。
3. 断网/API 500 → 合规规则 tab 下拉框 fallback 到 `types.ts` 常量，不报错。

---

## 不在本次范围

- 模板编辑器的拖拽排序、批量编辑等 UX 增强。
- 跨章节依赖追踪（cross-section reference map）。
- 图片自动识别（OCR/视觉模型从样例中提取图片内容）——本期仅抽标题和位置，不识别图片本身。
- 合规校验 MCP 工具（`kf_check_compliance`）——已实现（commits `438f0d9b` + `c26e3d33`）。
