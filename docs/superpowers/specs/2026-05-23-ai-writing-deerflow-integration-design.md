# AI 撰写与 DeerFlow 对话页集成设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目管理模块的 AI 撰写和协作编辑阶段与 DeerFlow 原生对话页集成，通过 MCP 工具和 Skill 实现 Agent 自主读写章节内容。

**Architecture:** 跳转对话页模式——用户从 ProjectWorkspace 跳转到 DeerFlow 对话页，Agent 通过 Project MCP Server 提供的章节读写工具完成撰写和回写。Thread metadata 作为项目模块与对话系统的桥梁。

**Tech Stack:** DeerFlow MCP Server 标准、Thread metadata、FastAPI、React (对话页零改动)、单一撰写 Skill

---

## 1. 六阶段流程与分工机制

### 1.1 完整流程

| Stage | 名称 | 执行者 | 线程模型 | 说明 |
|-------|------|--------|---------|------|
| 1 | 项目设定 | 用户 | 无 | 创建项目、选择报告类型和模板 |
| 2 | 大纲确认 | 用户 | 无 | 编辑和确认章节大纲 |
| 3 | AI 撰写 | AI Agent | 一个项目级 thread | AI 遍历所有章节生成初稿，自动回写 |
| 4 | 协作编辑 | 人类成员 + AI 辅助 | 每章节一个 thread | 项目经理分配章节，成员各自编辑 |
| 5 | 审批 | 审核人 | 复用章节 thread | 审核人审批章节内容 |
| 6 | 定稿输出 | 项目经理 | 无 | 汇总导出完整报告 |

### 1.2 Stage 3：AI 撰写

- 项目经理点击「开始 AI 撰写」，系统创建一个项目级 thread
- 所有章节由 AI 在同一个 thread 中按顺序遍历生成初稿
- 项目经理可在对话页中实时指导（如 "第3章要侧重生态影响"），也可让 AI 全自动完成
- AI 通过 MCP 工具 `write_chapter()` 自动回写内容，章节状态从 `pending` → `draft`

### 1.3 Stage 4：协作编辑

- 项目经理在章节列表中将章节分配给不同成员（设置 `chapter.assigned_to`）
- 被分配人看到自己的待办章节，点击进入章节级 thread
- 章节级 thread 带有 AI 辅助——成员可用自然语言要求 AI "帮我润色这段"、"补充数据分析"
- AI 通过同一套 MCP 工具读写章节内容，回写时状态设为 `editing`

### 1.4 分配 UI 交互

Stage 4 的章节列表界面：

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
│  [开始编辑] → 跳转到对话页            │
└─────────────────────────────────────┘
```

---

## 2. Project MCP Server 设计

### 2.1 概述

MCP Server 是连接项目模块和 DeerFlow Agent 的核心桥梁。作为 DeerFlow 标准的 MCP server 注册到 `extensions_config.json`，Agent 在处理项目相关 thread 时自动加载。

### 2.2 工具列表

| 工具名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `read_chapter` | `chapter_id: UUID` | 标题、内容、状态、要求（purpose/generation_hint）、字数 | 读取单个章节的完整信息 |
| `write_chapter` | `chapter_id: UUID`, `content: str`, `status?: str` | 更新后的章节信息 | 回写内容到 `ProjectChapter.content`，更新 `word_count_current`，可选更新 `status` |
| `list_chapters` | `project_id: UUID` | 章节树（标题、状态、字数、编写人） | 返回项目的完整章节结构 |
| `get_project` | `project_id: UUID` | 项目信息（名称、类型、模板、当前阶段） | 获取项目元数据 |
| `get_chapter_neighbors` | `chapter_id: UUID` | 前一章和后一章的标题+摘要 | 获取相邻章节信息以保持上下文连贯 |

### 2.3 实现位置

```
backend/app/extensions/project/mcp.py     # MCP Server 定义
backend/app/extensions/project/service.py # 复用已有的 service 函数
```

MCP 工具内部调用 `project/service.py` 已有的函数（`update_chapter`、`get_project`、`get_outline_tree` 等），不绕过业务层。

### 2.4 认证与权限

- MCP server 通过 thread metadata 中的 `project_id` 确定作用域
- 复用已有的 auth 系统（`CurrentUser` + `require_permission`）验证权限
- Stage 4 中，`write_chapter` 检查当前用户是否为章节的 `assigned_to` 成员或项目经理

### 2.5 注册配置

在 `extensions_config.json` 中注册：

```json
{
  "mcpServers": {
    "project": {
      "command": "python",
      "args": ["-m", "app.extensions.project.mcp"],
      "env": {}
    }
  }
}
```

仅在有项目 thread 时由 Agent 按需加载。

---

## 3. report-write Skill 设计

### 3.1 概述

单一 Skill，定义报告撰写的策略指导。Agent 加载后遵循这些规则进行章节撰写。

### 3.2 Skill 内容

**触发条件：** thread metadata 包含 `project_id`

**撰写规则：**
- 严格遵循大纲结构，不增删章节
- 每章开头有概述段落，结尾有小结
- 字数遵循 `chapter.word_count_target`
- 引用数据时标注来源
- 技术术语首次出现时给出解释
- 保持前后章节的术语和表述一致

**工具使用流程（Stage 3 全自动）：**

1. `get_project(project_id)` → 了解整体背景（名称、报告类型）
2. `list_chapters(project_id)` → 了解全部章节和当前进度
3. `read_chapter(chapter_id)` → 读取目标章节的详细要求（purpose、generation_hint）
4. `get_chapter_neighbors(chapter_id)` → 读取前后章节摘要，保持连贯
5. 生成章节内容
6. `write_chapter(chapter_id, content, "draft")` → 回写并标记为草稿
7. 对下一个 `pending` 状态章节重复步骤 3-6

**协作编辑模式（Stage 4）：**
- 用户提出的修改要求优先于 Skill 默认策略
- 回写时 status 设为 `"editing"`
- Agent 只响应用户指令，不主动遍历章节

### 3.3 Skill 文件位置

```
skills/report-write/skill.md    # Skill 策略定义（Markdown 格式）
```

注册到 `extensions_config.json` 的 skills 列表中。

---

## 4. Thread 管理与跳转逻辑

### 4.1 Thread 结构

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

### 4.2 Stage 3 跳转流程

```
ProjectWorkspace Stage 3:
  用户点击「开始 AI 撰写」
    │
    ├─ 1. 检查 ReportProject.thread_id
    │     不存在 → POST /api/threads
    │       metadata: { project_id, type: "report_project" }
    │     更新 project.thread_id
    │
    └─ 2. 跳转 /workspace/chats/{thread_id}
           对话页自动开始逐章撰写
```

### 4.3 Stage 4 跳转流程

查询章节 thread 的方式：通过 DeerFlow Thread API 的 metadata 过滤功能，调用 `GET /api/threads?metadata.chapter_id={chapter_id}` 查找已有关联 thread。后端 Thread 存储支持 metadata JSON 字段的查询。

```
ProjectWorkspace Stage 4:
  张三 点击「第2章: 生态环境现状」→ [开始编辑]
    │
    ├─ 1. 检查 chapter 是否有 thread
    │     GET /api/threads?metadata.chapter_id=ch2.id
    │     不存在 → POST /api/threads
    │       metadata: {
    │         project_id,
    │         chapter_id: ch2.id,
    │         parent_thread_id: project.thread_id,
    │         type: "chapter_edit",
    │         assigned_to: zhangsan.id
    │       }
    │
    └─ 2. 跳转 /workspace/chats/{chapter_thread_id}
           系统提示注入: "你是报告编辑助手，
           当前章节: 第2章 生态环境现状，
           该章节已有 AI 初稿，请协助用户修改润色"
```

### 4.4 返回项目页

- 对话页顶部面包屑增加「← 返回项目」链接
- 跳转 URL 中带 `?from=project` 参数，对话页识别后显示返回按钮
- 点击返回按钮跳转回 `/projects/{project_id}?stage=4`

---

## 5. 整体数据流

```
┌─────────────────────┐
│ ProjectWorkspace    │
│ (Stage 3/4)         │
│                     │
│ 点击章节 → 创建线程  │
│ 跳转到对话页         │
└─────────┬───────────┘
          │  /workspace/chats/{thread_id}
          ▼
┌─────────────────────┐     ┌──────────────────┐
│ DeerFlow 对话页     │     │ report-write     │
│ (零改动)            │◄────│ Skill (策略指导)  │
│                     │     └──────────────────┘
│ Agent 加载:         │
│ ├─ 读 thread meta   │     ┌──────────────────┐
│ ├─ 加载 Skill       │◄────│ Project MCP      │
│ └─ 调用 MCP 工具    │     │ Server (章节读写) │
│                     │     └────────┬─────────┘
│ 工具调用:           │               │
│ read_chapter()      │               │
│ write_chapter()     │               ▼
│ list_chapters()     │     ┌──────────────────┐
└─────────┬───────────┘     │ project/service  │
          │                 │ (已有业务逻辑)    │
          │                 └────────┬─────────┘
          │                          │
          │                          ▼
          │                 ┌──────────────────┐
          │                 │ PostgreSQL        │
          │                 │ ProjectChapter    │
          │                 │ ReportProject     │
          │                 └──────────────────┘
          │
          ▼
┌─────────────────────┐
│ 用户返回项目页面     │
│ 刷新章节状态         │
│ chapter.content 已填充│
│ chapter.status 已更新 │
└─────────────────────┘
```

---

## 6. 需要新增的文件和修改

### 6.1 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/extensions/project/mcp.py` | Project MCP Server（4-5 个工具） |
| `skills/report-write/skill.md` | 撰写策略 Skill 文件 |
| `frontend/src/extensions/project/ChapterWritingPanel.tsx` | Stage 3 章节撰写面板（显示进度+跳转按钮） |
| `frontend/src/extensions/project/ChapterEditingPanel.tsx` | Stage 4 协作编辑面板（章节列表+分配+跳转） |

### 6.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/app/extensions/project/service.py` | 新增 `find_chapter_thread`、`create_project_thread`、`create_chapter_thread` 函数 |
| `backend/app/extensions/project/routers.py` | 新增 `POST /projects/{id}/start-writing`、`POST /projects/{id}/chapters/{ch_id}/start-editing` 端点 |
| `backend/app/extensions/project/schemas.py` | 新增 thread 创建相关的 request/response schemas |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | 添加 Stage 3 和 Stage 4 的界面渲染逻辑 |
| `frontend/src/extensions/project/api.ts` | 新增 `startWriting`、`startChapterEditing` API 方法 |
| `frontend/src/extensions/project/types.ts` | 新增 thread 相关类型定义 |
| 对话页面包屑组件 | 识别 `from=project` 参数，显示返回按钮 |

### 6.3 不修改的文件

- DeerFlow 对话页核心代码（零改动）
- DeerFlow Agent 系统（通过标准 MCP + Skill 扩展，不侵入核心）
- 已有的 `project/service.py` 函数签名（MCP 工具调用已有函数）

---

## 7. 分阶段实施建议

本设计涉及多个独立子系统，建议分阶段实施：

1. **Phase 1 — MCP Server**：实现 `project/mcp.py`，提供章节读写工具
2. **Phase 2 — Skill**：创建 `report-write` skill 策略文件
3. **Phase 3 — Stage 3 UI**：ProjectWorkspace 的 AI 撰写面板（创建项目线程+跳转）
4. **Phase 4 — Stage 4 UI**：协作编辑面板（章节分配+章节线程+跳转）
5. **Phase 5 — 返回导航**：对话页的返回按钮
