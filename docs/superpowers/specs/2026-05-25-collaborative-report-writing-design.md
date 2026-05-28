# 协作智能写作功能设计

> 日期: 2026-05-25
> 状态: Draft
> 范围: 项目管理模块精简 + DeerFlow 对话集成

## 1. 核心思路

**松耦合、零侵入**：项目管理模块只做元数据粘合层，报告编写完全复用 DeerFlow 现有对话能力。

- 项目 = 元数据（团队、领域、模板）+ 审批流程设置
- 报告编写 = DeerFlow 对话（通过 Prompt 注入模板上下文）
- 文件共享 = 虚拟聚合视图（不改变底层 per-user per-thread 目录结构）
- 不修改 harness 层代码

## 2. 用户流程

```
1. 创建项目
   选择领域 → 选择报告类型 → 选择模板 → 添加成员 → 生成项目 Card

2. 配置审批流程
   项目详情页 → 审批流程设置 → 定义步骤/审批人/流转规则

3. 进入项目对话
   成员在项目列表看到自己的 Card → 点击"进入对话"
   → 自动创建/绑定线程 → Prompt 注入模板上下文
   → 进入 DeerFlow 对话页，Agent 已知道"你在写 XX 类型的报告"

4. AI 生成报告
   成员在对话中要求 AI 生成报告内容
   → Agent 根据注入的模板上下文按章节结构生成
   → 文件输出到线程目录（现有机制，零改动）

5. 查看项目文件
   项目文件视图 → 聚合查询所有成员线程的文件
   → 虚拟展示，底层文件仍在各线程目录

6. 合规校验
   复用现有 ComplianceEngine，在项目页面可触发校验
```

## 3. 协作模型

- **线程模型**: 每人独立线程 + 共享项目文件视图
- **并发模型**: 章节锁定由对话中的 Agent 管理（非实时 CRDT）
- **AI 介入**: 双模式 — 内联编辑（对话中）+ 全自动编排（Agent 按模板自动生成）

## 4. 前端精简

### 4.1 页面路由（3个，原5个）

| 路由 | 用途 | 变化 |
|------|------|------|
| `/projects` | 项目列表页 | 保留 |
| `/projects/new` | 创建项目页 | 保留 |
| `/projects/[id]` | 项目详情+审批流程设置 | 简化（删除其他 Tab） |

删除的路由：
- `/projects/[id]/chapter/[chapterId]` — 章节编辑在对话中完成
- `/projects/workspace` — 不需要独立工作台

### 4.2 保留的组件

**核心组件（6个）：**
- `ProjectList.tsx` — 项目列表
- `ProjectCreateWizard.tsx` — 创建向导
- `components/ProjectCard.tsx` — 项目卡片（增加"进入对话"按钮）
- `components/StatusBadge.tsx` — 状态徽章
- `components/FilterPills.tsx` — 筛选器

**审批流程设置（3个）：**
- `ApprovalFlowEditor.tsx` — 审批流编辑器
- `ApprovalWorkflow.tsx` — 审批工作流管理
- `ApprovalTab.tsx` — 审批 Tab

**工作台（1个，大幅简化）：**
- `ProjectWorkspace.tsx` — 从 7 Tab 简化为：项目信息 + 审批流程设置

**基础设施（3个）：**
- `api.ts` — API 调用（精简接口）
- `types.ts` — 类型定义（精简）
- `transforms.ts` — 数据转换

### 4.3 删除的组件（~20个）

| 类别 | 删除文件 |
|------|----------|
| 成员管理 | `MembersTab.tsx`、`MemberList.tsx` |
| 大纲管理 | `OutlineTab.tsx`、`OutlineEditor.tsx`、`OutlinePreview.tsx`、`OutlineTree.tsx` |
| 章节编辑 | `ChapterEditor.tsx`、`ChapterWritingPanel.tsx`、`ChapterEditingPanel.tsx`、`ChapterAssignDropdown.tsx`、`ChapterStatusBadge.tsx` |
| 仪表盘/看板 | `DashboardTab.tsx`、`KanbanBoard.tsx`、`MilestoneTimeline.tsx` |
| AI 工具 | `AiToolbox.tsx`、`AiToolsTab.tsx` |
| 布局/导航 | `WorkspaceTabs.tsx`、`SplitScreenLayout.tsx`、`ProjectBreadcrumbBar.tsx`、`tabRegistry.ts`、`navigateToChat.ts` |
| 成员工作台 | `MemberWorkspace.tsx` |
| 权限 | `useProjectPermissions.ts`（替换为简单的 owner/member 判断） |

## 5. 后端精简

### 5.1 保留的 API 端点（10个）

**项目 CRUD（6个）：**
- `GET /api/extensions/project/projects` — 列表
- `GET /api/extensions/project/projects/{id}` — 详情
- `POST /api/extensions/project/projects` — 创建
- `PATCH /api/extensions/project/projects/{id}` — 更新
- `DELETE /api/extensions/project/projects/{id}` — 删除
- `POST /api/extensions/project/projects/{id}/members` — 添加成员

**审批流程设置（4个）：**
- `GET /api/extensions/project/projects/{id}/approval-status` — 获取审批流程配置
- `POST /api/extensions/project/projects/{id}/submit-approval` — 保存审批流程
- `POST /api/extensions/project/projects/{id}/approval-action` — 审批操作
- `GET /api/extensions/project/projects/{id}/approval-records` — 审批记录

### 5.2 新增 API 端点（2个）

**进入项目对话：**
```
POST /api/extensions/project/projects/{id}/enter
Response: { thread_id: string }
```
逻辑：
1. 查询当前用户在该项目中的成员记录
2. 如无绑定线程 → 调用 LangGraph API 创建线程，写入模板上下文到 metadata
3. 返回 thread_id，前端跳转到 `/workspace/chats/{thread_id}`

**项目文件聚合：**
```
GET /api/extensions/project/projects/{id}/files
Response: { files: [{ name, path, thread_id, owner, size, updated_at }] }
```
逻辑：
1. 查询项目所有成员的 thread_id
2. 遍历每个线程的输出目录，收集文件列表
3. 返回聚合结果（虚拟视图，不移动文件）

### 5.3 删除的 API 端点（~13个）

- 大纲 CRUD（`GET/PUT/PATCH /outline`、`POST /confirm-outline`）
- 章节编辑（`POST /start-writing`、`POST /start-editing`）
- AI 操作（`POST /ai-action`）
- 权限查询（`GET /my-permissions`）
- 成员删除（`DELETE /members/{uid}`）— 简化，成员在项目创建时确定

### 5.4 数据模型精简

**保留的表/字段：**
- `report_projects`: id, name, domain_id, report_type, template_id, status, created_by
- `project_members`: project_id, user_id, role (owner/member), thread_id

**简化的状态：** 3 种（active / completed / archived），不再有 7 阶段状态机

**保留审批相关：** 审批流程配置表和审批记录表保持不变

### 5.5 权限精简

- 2 种角色：`owner`（创建者，可管理项目和审批流程）、`member`（成员，可进入对话和查看文件）
- 删除 5 角色 / 15 动作的复杂权限矩阵
- `permissions.py` 简化为简单的角色判断函数

## 6. Prompt 注入方案

**方式：通过线程 metadata 注入模板上下文**

创建线程时，`POST /enter` API 在线程 metadata 中写入：
```json
{
  "project_id": "uuid",
  "domain": "environmental_impact",
  "report_type": "环评报告",
  "template_id": "uuid",
  "template_context": {
    "name": "XX项目环评报告模板",
    "chapters": [
      { "id": "1", "title": "概述", "required": true },
      { "id": "2", "title": "工程分析", "required": true },
      ...
    ]
  }
}
```

`ThreadDataMiddleware` 已读取 thread_data，只需在 App 层创建线程时写入 metadata。harness 层的改动仅限于：在 Agent system prompt 模板中添加一个 `{template_context}` 占位符，当 thread_data 中存在 `template_context` 时自动注入。

如果希望完全不动 harness 层，备选方案是通过 Skill 注入：为项目创建一个 `SKILL.md`，内容为模板上下文，启用在线程的 Skill 列表中。

## 7. ProjectCard 增强

在现有 `ProjectCard.tsx` 基础上增加操作按钮：

- **"进入对话"** — 调用 `POST /enter` 获取 thread_id → 跳转 `/workspace/chats/{thread_id}`
- **"项目文件"** — 跳转项目文件聚合视图
- **"审批设置"** — 跳转项目详情页的审批流程设置

## 8. 项目文件聚合视图

在项目详情页或文档空间中新增一个视图：

- 调用 `GET /files` 获取所有成员线程的文件列表
- 按成员分组展示，支持查看和编辑（复用现有 TiptapEditor）
- 底层文件仍在各线程目录，不移动

## 9. 不改动的部分

以下系统不做任何修改：
- **harness 层**：Lead Agent、SubagentExecutor、Middlewares（或仅添加一行 prompt 占位符）
- **Knowledge Factory**：模板引擎、合规引擎、质量评估（直接复用）
- **TiptapEditor**：文档编辑器（复用现有能力）
- **StreamBridge**：SSE 流式传输
- **文件上传/输出**：线程目录机制

## 10. 实施优先级

1. **P0 - 精简项目管理模块**：删除冗余组件和 API，简化数据模型
2. **P0 - ProjectCard 增强**：添加"进入对话"按钮 + `POST /enter` API
3. **P1 - Prompt 注入**：线程 metadata 写入模板上下文 + system prompt 占位符
4. **P1 - 项目文件聚合视图**：`GET /files` API + 前端聚合展示
5. **P2 - 合规校验集成**：项目页面一键触发 ComplianceEngine
