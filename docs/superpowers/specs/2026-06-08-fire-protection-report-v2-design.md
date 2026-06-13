# 消防设计报告 Skill v2 — 知识工厂模板融合设计

**日期**: 2026-06-08
**状态**: 已确认
**作者**: 头脑风暴设计

## 目标

实现新版消防设计报告 Skill (`fire-protection-report-v2`)，优先从知识工厂获取报告模板元数据驱动生成，模板不可用时回退到内置 markdown 参考文档。旧版 Skill (`fire-protection-report`) 保持不变，两者并行便于结果对比。

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│  fire-protection-report-v2 SKILL.md                             │
│                                                                  │
│  metadata:                                                       │
│    template_query:            ← 声明式：我要什么模板              │
│      domain_keywords: ["消防设计专篇"]                           │
│      industry: "化工"                                            │
│      min_completeness_score: 60                                  │
│    fallback: "references/"    ← 声明：找不到时去哪回退           │
│                                                                  │
│  workflow 步骤:                                                  │
│    1. 了解项目需求                                               │
│    2. 调用 kf_resolve_template(...) 解析模板                     │
│    3. 加载补充知识（terminology.md + content_guidelines.md）     │
│    4. 按模板/fallback 结构起草报告                                │
│    5. 生成 Word 文档                                             │
│    6. 合规检查                                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ MCP 协议 (stdio)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  knowledge-factory MCP Server  (新增)                            │
│                                                                  │
│  kf_resolve_template(domain_keywords, industry, min_score)       │
│    │                                                             │
│    ├─ 1. 查询 ExtractionDomain (按 industry/关键词匹配)          │
│    ├─ 2. 查询 ExtractionTemplate (按 domain + name 关键词)       │
│    ├─ 3. 过滤: status='published', completeness_score >= min     │
│    ├─ 4. 排序: match_level DESC, completeness_score DESC         │
│    ├─ 5. 返回最佳匹配 TemplateData                               │
│    └─ 6. 无匹配 → 返回 {found: false}                            │
│                                                                  │
│  kf_get_template(template_id)  ← 按 ID 获取完整模板              │
│  kf_list_domains(industry?)    ← 列出可用领域                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ SQLAlchemy async session
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL: extraction_domains + extraction_templates           │
└─────────────────────────────────────────────────────────────────┘
```

## 两级数据源策略

| 优先级 | 数据源 | 获取方式 | 用途 |
|--------|--------|----------|------|
| **1 (优先)** | 知识工厂模板元数据 | MCP `kf_resolve_template(...)` | 章节结构 + generation_hint + compliance_rules + content_contract |
| **2 (回退)** | 内置 markdown 文档 | 读取 `references/*.md` | 章节结构 + 术语 + 编写指南（旧版逻辑） |
| **补充** | 术语词典 | **始终加载** `references/terminology.md` | 专业术语定义 |
| **补充** | 编写规范 | **始终加载** `references/content_guidelines.md` | 消防报告通用编写背景 |

### 补充知识始终加载

terminology.md 和 content_guidelines.md 是领域背景知识，模板的 generation_hint 不包含完整术语定义和编写规范背景，因此无论模板是否可用都必须加载。

## 新 Skill 文件布局

```
skills/custom/fire-protection-report-v2/
├── SKILL.md                         # 技能定义（声明式模板查询 + 工作流）
├── references/                      # fallback 参考文件
│   ├── report_structure.md          # 8章结构（模板不可用时 fallback）
│   ├── terminology.md               # 术语词典（补充知识，始终加载）
│   ├── content_guidelines.md        # 编写规范（补充知识，始终加载）
│   └── chapter_examples/
│       └── sample_fire_design.md    # 样例（fallback）
└── README.md
```

旧 Skill 保持不动：`skills/custom/fire-protection-report/`。

## SKILL.md 工作流

### 步骤 1：了解需求（不变）

- 项目名称和编号
- 项目类型：新建/改建/扩建
- 建筑规模和功能区
- 火灾危险性分类
- 用户的具体要求或重点领域

### 步骤 2：解析报告模板 ← NEW

**第一步**：调用 MCP 工具获取模板：

```
kf_resolve_template(
    domain_keywords=["消防设计专篇", "消防设计报告", "消防设计篇章"],
    industry="化工",
    min_completeness_score=60
)
```

**判断逻辑**：

- 如果 `found == true`：
  - 使用 `sections` 作为报告结构
  - 每章获得独立的 `generation_hint`、`compliance_rules`、`content_contract`、`example_snippet`
  - **跳过**读取 report_structure.md

- 如果 `found == false` 或调用失败（超时/报错/MCP 不可用）：
  - 通知用户："未找到可用的知识工厂模板（原因: {reason}），将使用内置参考文档生成"
  - 读取 `references/report_structure.md` 作为报告结构
  - 后续步骤使用全局 GB 标准列表

### 步骤 3：加载补充知识 ← 始终执行

```
读取 references/terminology.md        # 术语背景
读取 references/content_guidelines.md  # 编写规范
```

### 步骤 4：按模板驱动起草报告

**有模板时**：每章使用独立元数据：

| 元数据字段 | 作用 |
|-----------|------|
| `generation_hint` | LLM 精准生成提示，从样本报告中抽取提炼 |
| `content_contract.key_elements` | 该章必须覆盖的要素清单 |
| `content_contract.min_word_count` | 字数下限，防止内容过于简略 |
| `content_contract.forbidden_phrases` | 禁止出现的用语（如"大约""可能""暂定"） |
| `content_contract.structure_type` | 输出格式：narrative_text / table / mixed |
| `compliance_rules` | 该章须遵循的具体 GB 规范条款 |
| `example_snippet` | 样例内容，供 LLM 参考风格 |

**无模板时**：按旧版 markdown 结构生成（兼容旧逻辑）。

### 步骤 5：生成 Word 文档（同旧版）

使用 `word-document-server` MCP 工具生成 .docx 文件。

### 步骤 6：合规检查

- 有模板：汇总所有章节的 `compliance_rules` 逐项检查
- 无模板：使用 markdown 中的全局 GB 标准列表

## 统一 TemplateContext

无论数据来自知识工厂还是 markdown fallback，下游步骤读取统一结构：

```python
TemplateContext = {
    "source": "knowledge_factory" | "markdown_fallback",
    "sections": [
        {
            "title": "设计依据及采用的标准",
            "level": 1,
            "generation_hint": "..." | null,        # null = markdown fallback 无此字段
            "compliance_rules": [...] | null,
            "content_contract": {...} | null,
            "example_snippet": "..." | null
        },
        ...
    ],
    "global_standards": ["GB50160-2008", ...]
}
```

属性为 null 时该约束不生效，下游代码不做条件分支。

## kf_resolve_template 工具设计

### 输入参数

```python
domain_keywords: list[str]        # ["消防设计专篇", "消防设计报告"]
industry: str | None = None       # "化工"
report_type: str | None = None    # "消防设计"
min_completeness_score: int = 0   # 最低完整度评分
```

### 匹配逻辑（三层优先级递减）

1. **精确匹配**: domain.report_type == report_type AND domain.industry == industry AND template.name 包含任一 domain_keywords
2. **关键词匹配**: template.name 包含任一 domain_keywords AND (domain.industry == industry OR domain.report_type 匹配)
3. **宽松匹配**: template.name 或 domain.name 包含任一 domain_keywords

每层内按 `completeness_score DESC`、`version DESC` 排序，取第一名。

### 返回结构

成功：
```json
{
    "found": true,
    "template_id": "uuid-xxx",
    "template_name": "公用工程_消防设计专篇_模板",
    "version": "v1.0",
    "completeness_score": 72,
    "match_level": "exact",
    "sections": [...]
}
```

失败：
```json
{
    "found": false,
    "reason": "no_template_found" | "low_quality" | "service_error",
    "suggestion": "请先通过知识工厂抽取该领域的报告模板"
}
```

## 回退策略

| 触发条件 | 行为 | 用户通知 |
|----------|------|----------|
| `found=false, reason="no_template_found"` | 回退 markdown | ⚠️ 未找到匹配模板 |
| `found=false, reason="low_quality"` | 回退 markdown | ⚠️ 模板完整度低于阈值 |
| MCP 超时/进程崩溃 | 回退 markdown | ❌ 知识工厂服务不可达 |
| MCP 返回异常 | 回退 markdown | ❌ 服务异常 |
| MCP Server 未注册 | 回退 markdown | ❌ 配置缺失 |

## 回退时的用户通知示例

成功：
```
✅ 已从知识工厂获取模板：公用工程_消防设计专篇_模板 v1.0（完整度: 72/100, 匹配级别: exact）
```

失败：
```
⚠️ 知识工厂模板不可用（未找到匹配模板），使用内置参考文档继续生成
```

## MCP Server 实现方案

### 文件结构

```
backend/app/extensions/knowledge_factory/mcp_server/   # 新增目录
├── __init__.py
├── server.py                  # MCP Server 入口
└── tools/
    ├── __init__.py
    ├── template_tools.py      # kf_resolve_template, kf_get_template
    └── domain_tools.py        # kf_list_domains
```

### 需要增强的现有代码

**1. `routers.py` — `list_templates` 增加 `name` 过滤参数**

**2. `service.py` — `TemplateService.list_templates` 增加 `name` 参数（ILIKE 模糊匹配）**

### MVP 工具清单

| 工具 | 优先级 | 说明 |
|------|--------|------|
| `kf_resolve_template` | **P0** | 智能模板匹配 + 返回完整元数据 |
| `kf_list_domains` | P1 | 列出可用领域（辅助发现） |
| `kf_get_template` | P1 | 按模板 ID 获取指定模板 |
| `kf_query_templates` | P2 | 通用模板搜索（后续） |
| `kf_search_laws` | P3 | 法规搜索（后续） |
| `kf_check_compliance` | P3 | 合规检查（后续） |

### MCP 配置注册

```json
{
  "mcpServers": {
    "knowledge-factory": {
      "enabled": true,
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "app.extensions.knowledge_factory.mcp_server"],
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://agentflow:agentflow@postgres-ext:5432/agentflow"
      }
    }
  }
}
```

## 与旧 Skill 的对比

| 维度 | 旧 skill (v1) | 新 skill (v2) |
|------|--------------|---------------|
| 数据源 | 纯 markdown 静态文件 | 模板优先 + markdown fallback |
| 章节生成提示 | 通用段落描述 | 每章独立 `generation_hint` |
| 内容约束 | 隐式（人工阅读后遵守） | 显式 `content_contract`（字数/结构/禁用词/要素） |
| 合规规则 | 全局 GB 标准列表 | 每章独立 `compliance_rules` |
| 模板演进 | 改 markdown = 改行为 | 知识工厂编辑模板 → 即时生效 |
| 补充知识 | 合并加载 | 始终单独加载 terminology + content_guidelines |

## 实施路径

1. **Phase 1 — 基础数据增强**: `list_templates` API + service 增加 `name` 过滤
2. **Phase 2 — MCP Server**: 创建 MCP Server，实现 `kf_resolve_template` + `kf_list_domains` + `kf_get_template`
3. **Phase 3 — 新 Skill**: 创建 `fire-protection-report-v2` SKILL.md + references
4. **Phase 4 — 验证**: 两版 Skill 并行运行，对比生成结果
