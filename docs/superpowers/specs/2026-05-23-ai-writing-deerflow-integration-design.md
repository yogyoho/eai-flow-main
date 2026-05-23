# AI 撰写与 DeerFlow 对话页集成设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让项目模块的 AI 撰写和协作编辑复用 DeerFlow 已有的 lead_agent 对话能力，通过 MCP 工具和 Skill 扩展 Agent 的章节读写能力，不单独开发任何 agent 对话功能。

**核心原则：** 充分利用 DeerFlow 已有的任务执行 agent（lead_agent + subagent + tools + streaming + artifacts + memory），项目模块只做"跳转 + 上下文注入 + MCP 工具提供"。对话页、Agent 编排、流式响应、文件上传等全部复用，零重复开发。

**Architecture:** 跳转对话页模式——ProjectWorkspace 创建 thread 并注入项目上下文（metadata + system prompt），然后跳转到 DeerFlow 原生对话页。Agent 加载时自动识别项目 thread，通过 Project MCP Server 提供的章节读写工具完成任务。

**Tech Stack:** DeerFlow lead_agent（完全复用）、MCP Server（标准扩展点）、Skill（策略文件）、Thread metadata（桥梁）

---

## 1. 设计原则：最大化复用 DeerFlow Agent

本设计的每一步都遵循一个原则：**不造轮子**。

| 需要 | DeerFlow 已有 | 项目模块做什么 |
|------|--------------|---------------|
| 对话界面 | `/workspace/chats/[thread_id]` 完整页面 | 跳转过去，零 UI 开发 |
| Agent 编排 | lead_agent + subagent + tool 选择 | 不碰 agent 代码 |
| 流式响应 | SSE + `useStream()` hook | 直接复用 |
| 文件上传 | InputBox upload → sandbox | 直接复用 |
| Artifacts | 生成文件展示和下载 | 直接复用 |
| Memory | 跨对话记忆系统 | 直接复用 |
| 章节读写 | 无 | **新增 MCP Server 提供** |
| 撰写策略 | 无 | **新增 Skill 定义** |
| 项目上下文 | 无 | **Thread metadata 注入** |

项目模块的**全部新增工作**仅三件事：
1. **MCP Server**（让 Agent 能读写章节）
2. **Skill**（告诉 Agent 怎么写报告）
3. **Thread 创建 + 跳转**（从项目页进入对话页）

---

## 2. 六阶段流程与分工机制

### 2.1 完整流程

| Stage | 名称 | 执行者 | 线程模型 | 说明 |
|-------|------|--------|---------|------|
| 1 | 项目设定 | 用户 | 无 | 创建项目、选择报告类型和模板（已实现） |
| 2 | 大纲确认 | 用户 | 无 | 编辑和确认章节大纲（已实现） |
| 3 | AI 撰写 | DeerFlow lead_agent | 一个项目级 thread | Agent 遍历所有章节生成初稿，自动回写 |
| 4 | 协作编辑 | 人类成员 + lead_agent 辅助 | 每章节一个 thread | 分配章节给成员，成员借助 Agent 润色 |
| 5 | 审批 | 审核人 | 复用章节 thread | 审核人审批章节内容 |
| 6 | 定稿输出 | 项目经理 | 无 | 汇总导出完整报告 |

### 2.2 Stage 3：AI 撰写

- 项目经理点击「开始 AI 撰写」→ 创建项目级 thread → 跳转到 DeerFlow 对话页
- DeerFlow lead_agent 加载后，自动识别 thread metadata 中的项目信息
- Agent 根据 Skill 策略，通过 MCP 工具遍历章节生成初稿
- 项目经理可在对话页中实时指导（如 "第3章要侧重生态影响"），也可让 Agent 全自动
- 每个章节完成后 Agent 调用 `write_chapter()` 回写，章节状态 `pending` → `draft`
- Agent 在生成过程中可利用已有的 subagent、文件上传、artifacts 等全部能力

### 2.3 Stage 4：协作编辑

- 项目经理在章节列表中将章节分配给不同成员（`chapter.assigned_to`）
- 被分配人点击章节 → 创建章节级 thread → 跳转到 DeerFlow 对话页
- 同样是 DeerFlow lead_agent 接待，通过同一套 MCP 工具读写章节
- 成员用自然语言与 Agent 协作："帮我润色这段"、"补充数据分析"、"对比前后章节一致性"
- Agent 还可以调用已有的搜索工具、文件分析工具等 DeerFlow 原生能力

### 2.4 分配 UI

```
┌─────────────────────────────────────┐
│  协作编辑 (Stage 4)                  │
│                                     │
│  章节              编写人    状态     │
│  ─────────────────────────────────  │
│  第1章 概述        👤 张三   ✅ 完成  │
│  第2章 生态现状    👤 李四   ● 编辑中 │
│  第3章 影响分析    [分配▼]   ○ 草稿   │
│  第4章 措施建议    [分配▼]   ○ 草稿   │
│  第5章 结论        👤 AI     ○ 草稿   │
│                                     │
│  [开始编辑] → 跳转到 DeerFlow 对话页 │
└─────────────────────────────────────┘
```

---

## 3. Project MCP Server 设计

### 3.1 定位

MCP Server 是**唯一新增的后端代码**。它的职责是让 DeerFlow lead_agent 能读写项目章节数据。Agent 的编排、工具选择、LLM 调用全部由 DeerFlow 已有系统处理。

### 3.2 工具列表

| 工具名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `read_chapter` | `chapter_id: UUID` | 标题、内容、状态、字数、编写人 | 读取章节当前状态和内容 |
| `write_chapter` | `chapter_id: UUID`, `content: str`, `status?: str` | 更新后的章节信息 | 回写内容，更新 `word_count_current`，可选更新 `status` |
| `list_chapters` | `project_id: UUID` | 章节树（标题、状态、字数、编写人） | 返回项目完整章节结构 |
| `get_project` | `project_id: UUID` | 项目信息（名称、类型、模板、当前阶段） | 获取项目元数据 |
| `get_chapter_neighbors` | `chapter_id: UUID` | 前一章和后一章的标题+摘要 | 获取相邻章节，保持上下文连贯 |
| `get_chapter_spec` | `chapter_id: UUID` | 完整编写规格（见下方） | 获取模板中该章节的编写要求 |

### 3.3 `get_chapter_spec` 返回的编写规格数据

这个工具是 Agent 撰写的**核心上下文来源**。它从模板的 `root_sections_json` 中提取对应章节的编写规格，与项目章节数据合并返回：

```
get_chapter_spec(chapter_id) 返回:
{
  // 来自 ProjectChapter（项目数据）
  "chapter_id": "uuid",
  "title": "第3章 生态环境影响分析",
  "level": 1,
  "sort_order": 2,
  "current_content": "...",        // 当前已有内容（编辑阶段有值）
  "word_count_target": 5000,
  "word_count_current": 0,

  // 来自 ExtractionTemplate.root_sections_json（模板数据）
  "purpose": "分析项目建设和运营对生态环境的潜在影响...",
  "generation_hint": "需覆盖水环境、大气环境、声环境、生态环境四个维度...",
  "content_contract": {
    "key_elements": ["现状调查", "影响预测", "保护措施"],
    "structure_type": "narrative_text",
    "style_rules": "使用科学严谨的表述，数据需标注来源",
    "min_word_count": 5000,
    "forbidden_phrases": ["我认为", "感觉"]
  },
  "compliance_rules": [
    "环境影响评价技术导则 总纲 HJ 2.1-2016",
    "环境影响评价技术导则 生态影响 HJ 19-2022"
  ],
  "rag_sources": [
    {
      "kb_id": "uuid",
      "kb_name": "环评法规库",
      "retrieval_strategy": "hybrid",
      "top_k": 5,
      "similarity_threshold": 0.7
    }
  ],
  "example_snippet": "## 3.1 水环境影响分析\n\n根据现场监测数据...",

  // 来自上下文计算
  "neighbors": {
    "previous": { "title": "第2章 环境现状", "summary": "..." },
    "next": { "title": "第4章 环保措施", "summary": "..." }
  }
}
```

**关键设计点：**
- 模板数据（purpose、content_contract、rag_sources 等）存储在 `ExtractionTemplate.root_sections_json` 中，通过章节标题匹配关联到 `ProjectChapter`
- Agent 拿到完整规格后，知道"写什么、怎么写、参考什么、不能写什么"
- `rag_sources` 告诉 Agent 应该查询哪些知识库，Agent 可调用 DeerFlow 已有的 RAG 搜索工具获取参考资料

### 3.3 实现方式

- **位置**：`backend/app/extensions/project/mcp.py`
- **内部调用**：复用 `project/service.py` 已有函数（`update_chapter`、`get_project`、`get_outline_tree`），不绕过业务层
- **认证**：复用 DeerFlow 已有的 MCP 认证机制
- **注册**：在 `extensions_config.json` 中注册为标准 MCP server

```json
{
  "mcpServers": {
    "project": {
      "command": "python",
      "args": ["-m", "app.extensions.project.mcp"]
    }
  }
}
```

---

## 4. report-write Skill 设计

### 4.1 定位

Skill 是给 DeerFlow lead_agent 的**策略指导文件**，告诉 Agent "怎么写报告"。Agent 的执行能力（LLM、subagent、工具调用）完全复用已有系统。

### 4.2 Skill 内容

**触发条件：** thread metadata 包含 `project_id`

**撰写规则：**
- 严格遵循大纲结构，不增删章节
- 以 `get_chapter_spec()` 返回的编写规格为准——`purpose` 决定写什么方向，`content_contract` 决定结构和约束，`generation_hint` 提供额外指导
- `content_contract.min_word_count` 为最低字数，`word_count_target` 为目标字数
- `content_contract.key_elements` 中的要素必须全部覆盖
- `content_contract.forbidden_phrases` 中的表述严禁使用
- `content_contract.style_rules` 定义写作风格，必须遵循
- 如有 `rag_sources`，先查询对应知识库获取参考资料，引用数据标注来源
- 如有 `example_snippet`，参考其结构和风格但不可照搬
- 如有 `compliance_rules`，内容必须符合引用的法规/标准要求
- 保持前后章节术语和表述一致

**Stage 3 工具使用流程（Agent 自主执行）：**

1. `get_project(project_id)` → 了解整体背景（名称、报告类型、模板）
2. `list_chapters(project_id)` → 了解全部章节和当前进度
3. `get_chapter_spec(chapter_id)` → 获取该章节的**完整编写规格**（目的、契约、RAG来源、提示词、样例）
4. 如有 `rag_sources`，调用 DeerFlow 已有的知识库搜索工具获取参考资料
5. 参照 `example_snippet` 风格，遵循 `content_contract` 约束，生成章节内容
6. `write_chapter(chapter_id, content, "draft")` → 回写并标记为草稿
7. 对下一个 `pending` 章节重复 3-6

**Stage 4 协作编辑模式：**
- 用户指令优先于 Skill 默认策略
- 回写时 status 设为 `"editing"`
- Agent 只响应用户指令，不主动遍历章节

### 4.3 Skill 文件

```
skills/report-write/skill.md
```

标准 DeerFlow Skill 格式，注册到 `extensions_config.json` 的 skills 列表。

---

## 5. Thread 管理与跳转逻辑

### 5.1 Thread Metadata 结构

```
项目级 thread (Stage 3)
  metadata: {
    "project_id": "uuid",
    "type": "report_project",
    "report_type": "environmental_impact"
  }

章节级 thread (Stage 4)
  metadata: {
    "project_id": "uuid",
    "chapter_id": "uuid",
    "parent_thread_id": "uuid",
    "type": "chapter_edit",
    "assigned_to": "uuid"
  }
```

Metadata 的作用：让 DeerFlow lead_agent 在加载时识别项目上下文，自动激活 `report-write` skill 和 `project` MCP server。这是项目模块和 DeerFlow 之间**唯一的集成点**。

### 5.2 Stage 3：跳转到对话页

```
ProjectWorkspace Stage 3:
  用户点击「开始 AI 撰写」
    │
    ├─ 1. 检查 ReportProject.thread_id
    │     不存在 → POST /api/threads（DeerFlow 已有 API）
    │       metadata: { project_id, type: "report_project" }
    │     更新 project.thread_id = new_thread_id
    │
    └─ 2. 跳转 /workspace/chats/{thread_id}?from=project
           → DeerFlow 对话页，lead_agent 接管
           → Agent 识别 metadata，加载 skill + MCP 工具
           → 自主开始逐章撰写
```

### 5.3 Stage 4：跳转到章节对话页

```
ProjectWorkspace Stage 4:
  张三 点击「第2章: 生态环境现状」→ [开始编辑]
    │
    ├─ 1. 查找章节 thread
    │     GET /api/threads?metadata.chapter_id=ch2.id
    │     不存在 → POST /api/threads
    │       metadata: {
    │         project_id, chapter_id: ch2.id,
    │         parent_thread_id: project.thread_id,
    │         type: "chapter_edit",
    │         assigned_to: zhangsan.id
    │       }
    │
    └─ 2. 跳转 /workspace/chats/{chapter_thread_id}?from=project
           → DeerFlow 对话页，同样由 lead_agent 接管
           → Agent 识别 chapter_edit 类型，进入辅助编辑模式
```

### 5.4 返回项目页

- 对话页 URL 中的 `from=project` 参数触发「← 返回项目」按钮
- 点击返回 `/projects/{project_id}?stage=4`
- 面包屑导航：对话页 → 项目名称 → 返回项目页

---

## 6. 整体数据流

```
┌───────────────────────┐
│ ProjectWorkspace      │
│                       │
│ 创建 thread (metadata) │
│ 跳转对话页             │
└──────────┬────────────┘
           │  /workspace/chats/{thread_id}?from=project
           ▼
┌───────────────────────────────────────────────┐
│ DeerFlow 对话页 (完全复用，零改动)              │
│                                               │
│ ┌─────────┐  ┌────────────┐  ┌─────────────┐ │
│ │lead_agent│  │report-write│  │Project MCP  │ │
│ │(已有)    │←─│Skill (新增) │  │Server (新增)│ │
│ │         │  └────────────┘  └──────┬──────┘ │
│ │自动加载: │                         │        │
│ │├读meta  │                         │        │
│ │├加载skill│                         │        │
│ │└调用MCP │                         │        │
│ │         │                         │        │
│ │可复用:    │                         │        │
│ │├subagent │                         │        │
│ │├文件上传  │                         │        │
│ │├artifacts │                        │        │
│ │├memory   │                         │        │
│ │├RAG搜索  │← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│        │
│ │└搜索工具  │  (rag_sources 指定查询)  │        │
│ └────┬─────┘                         │        │
│      │ read/write_chapter            │        │
│      │ get_chapter_spec              │        │
└──────┼──────────────────────────────┼────────┘
       │                              │
       ▼                              ▼
┌──────────────┐            ┌─────────────────┐
│ 用户返回      │            │ project/service │
│ 项目页面      │            │ (已有业务逻辑)   │
│ 刷新章节状态  │            └────────┬────────┘
└──────────────┘                     │
                                     ▼
                           ┌─────────────────┐
                           │ PostgreSQL       │
                           │ ProjectChapter   │
                           │ ReportProject    │
                           │ ExtractionTemplate│ ← get_chapter_spec 读取模板规格
                           └─────────────────┘
```

---

## 7. 新增文件清单

本设计的**全部新增代码**：

### 7.1 新增文件

| 文件 | 说明 | 代码量估计 |
|------|------|-----------|
| `backend/app/extensions/project/mcp.py` | Project MCP Server（5 个工具） | ~150 行 |
| `skills/report-write/skill.md` | 撰写策略 Skill 文件 | ~50 行 |
| `frontend/src/extensions/project/ChapterWritingPanel.tsx` | Stage 3 撰写面板（进度+跳转按钮） | ~120 行 |
| `frontend/src/extensions/project/ChapterEditingPanel.tsx` | Stage 4 编辑面板（章节列表+分配+跳转） | ~200 行 |

### 7.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/app/extensions/project/routers.py` | 新增 `POST /projects/{id}/start-writing`、`POST /projects/{id}/chapters/{ch_id}/start-editing` |
| `backend/app/extensions/project/service.py` | 新增 thread 创建和查询辅助函数 |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | Stage 3/4 渲染新面板 |
| `frontend/src/extensions/project/api.ts` | 新增 `startWriting`、`startChapterEditing` API |
| `frontend/src/extensions/project/types.ts` | 新增 thread 相关类型 |
| 对话页面包屑组件 | 识别 `from=project` 显示返回按钮（~10 行） |

### 7.3 不修改的文件

- DeerFlow 对话页核心代码（零改动）
- DeerFlow Agent 系统（lead_agent、subagent、middleware 不碰）
- DeerFlow 流式系统（SSE、useStream 不碰）
- DeerFlow 工具系统（已有工具全部保留，新增的走 MCP 标准扩展）
- 已有的 `project/service.py` 函数签名（MCP 工具调用已有函数）

---

## 8. 分阶段实施建议

按依赖关系分 5 个阶段，每个阶段独立可验证：

1. **Phase 1 — MCP Server**：实现 `project/mcp.py`，可在 DeerFlow 对话页中手动测试工具调用
2. **Phase 2 — Skill**：创建 `report-write` skill，验证 Agent 能自动遵循策略
3. **Phase 3 — Stage 3 跳转**：ProjectWorkspace 创建项目 thread + 跳转对话页 + 返回按钮
4. **Phase 4 — Stage 4 协作**：章节分配 UI + 章节 thread 创建 + 跳转
5. **Phase 5 — 端到端验证**：完整流程测试（创建→大纲→AI撰写→协作编辑）
