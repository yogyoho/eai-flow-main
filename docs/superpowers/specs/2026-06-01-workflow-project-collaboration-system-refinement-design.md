# 项目协作体系细化设计：组织 · 角色 · 任务控制台 · 项目跟踪

**日期**: 2026-06-01
**状态**: Draft
**前置**: 2026-05-29-workflow-engine-traceability-review-design.md（工作流引擎+溯源+审核 主体设计）

## 1. 概述

在 `2026-05-29-workflow-engine-traceability-review-design.md` 的技术架构基础上，本设计文档细化四个组织协作层面的设计，解决以下核心问题：

1. **项目 Card 创建与流程配置**（领域 A）— 谁创建项目？流程如何配置？多部门多阶段人员不固定的项目如何组建？
2. **角色化页面和视图**（领域 B）— 不同角色（负责人/执行者/审核人/审批人）的项目页面各自什么样？
3. **个性化任务控制台**（领域 C）— 每个用户登录后的核心工作入口如何设计？
4. **项目跟踪工具**（领域 D）— 甘特图、阶段看板、个人日历、提醒通知系统。

**核心设计原则：双层配置机制** — 组织层预配置提供默认和标准化，项目层按需覆盖提供灵活性。这一原则贯穿全部四个领域。

**场景假设：混合组织** — 内部项目偏标准化（预定义岗位），外部协作项目偏灵活（发起人灵活组队）。同一用户在不同项目中可能承担不同角色，同一项目内可能有多重身份。

## 2. 领域 A：项目 Card 创建与流程配置

### 2.1 三层流程配置体系

```
组织层（Organization Level）
  ├── 部门注册 & 角色岗位定义
  │    └── 例如：技术分析部 → {部长, 高级工程师, 工程师, 审核员}
  │
  ├── 流程模板库（Workflow Template Library）
  │    ├── 模板定义：节点 + 每条边的组织单元 + 默认角色槽位
  │    ├── 模板分类：按报告类型（环评/验收/应急预案...）
  │    └── 模板权限：哪些部门/角色可以使用此模板
  │
  └── 自动流转规则（可选）
       └── 当阶段推进到"合规审查"节点时 → 自动通知合规部负责人

────────────────────────────────────────────────

项目层（Project Level）
  ├── 发起人选择模板 → 生成可编辑副本
  ├── 覆盖组织单元（"合规审查不由合规部做，外包给外部专家"）
  ├── 指定具体人员（从组织单元默认岗位 → 具体到人）
  └── 保存为"此项目的流程配置" → 启动工作流

────────────────────────────────────────────────

运行时（Runtime）
  ├── 阶段到达 → 检查槽位是否已填充
  │    ├── 已填充：直接通知具体人
  │    └── 未填充：通知组织单元负责人 → 由他分配
  └── 人员变更 → 阶段负责人可重新分配（不修改模板）
```

### 2.2 谁创建项目 Card — 场景矩阵

| 场景 | 创建者 | 流程配置方式 |
|------|--------|-------------|
| 内部标准项目 | 部门负责人/PM | 选模板 → 组织单元自动匹配 → 微调人员 |
| 内部临时项目 | 任何有权限的人 | 选模板 → 手动覆盖组织单元和人员 |
| 跨部门项目 | 牵头部门负责人 | 选模板 → 各阶段组织单元分别确认 |
| 外部协作项目 | PM/商务 | 选模板 → 外部人员槽位填邮箱 → 邀请加入 |
| 个人自由编写 | 任何用户 | 无需流程，直接对话 → 文档保存到个人区 |

### 2.3 项目创建对比：现有 vs 新设计

| | 当前系统 | 新设计 |
|---|---|---|
| **创建者** | 任何有 `project:create` 的人 | 同，但增加"部门管理员可为部门创建" |
| **流程来源** | 固定6阶段 | 从模板库选择 → 可编辑副本 |
| **团队组建** | 手动添加成员 | 模板预填组织单元 → 自动通知 → 负责人确认 |
| **外部协作** | 不支持 | 允许在槽位中指定外部用户（邮箱邀请） |
| **Card 归属** | 创建者即 owner | 创建者默认 owner，可转让给部门 |

### 2.4 DAG 节点组织绑定扩展

在 `workflow_definitions.graph_json` 的节点 data 中标准化组织绑定字段：

```json
{
  "id": "phase-a",
  "type": "phase",
  "data": {
    "label": "现状调查",
    "org_unit_id": "uuid-of-技术分析部",
    "required_roles": [
      {"role_key": "phase_lead", "count": 1, "label": "阶段负责人"},
      {"role_key": "writer", "count": 3, "label": "撰写人"},
      {"role_key": "data_reviewer", "count": 1, "label": "数据审核"}
    ],
    "chapter_range": [1, 3],
    "ai_assist": true,
    "input_from": []
  }
}
```

## 3. 领域 B：角色化页面和视图 + 角色与组织管理

### 3.1 身份模型

```
系统层（System Identity）
  ├── 所属部门（可多个）
  ├── 部门内岗位（如"技术分析部-高级工程师"）
  └── 系统级权限（project:create, template:manage...）

项目层（Project Identity）
  ├── 项目角色（owner / manager / editor / reviewer / approver）
  ├── 阶段职责（Phase A 负责人 / Phase B 审核人 / Phase C 写手）
  └── 章节分配（第1章撰写 / 第3章审核）

运行时层（Runtime Identity）
  ├── 当前待办（3个审核待处理 / 2个章节待写）
  └── 通知偏好（邮件/站内/企业微信...）
```

### 3.2 项目详情页 — 标签页可见性矩阵

标签页可见性由"用户是否在此项目中有相关职责"驱动，非简单的角色枚举。

| 标签页 | Owner | Manager | Editor | Reviewer | Approver |
|--------|-------|---------|--------|----------|----------|
| **项目概览** | ✓ 可编辑 | ✓ 可编辑 | ✓ 只读 | ✓ 只读 | ✓ 只读 |
| **流程看板** | ✓ 可操作 | ✓ 可操作 | - | - | - |
| **文档编辑** | ✓ 全部章节 | ✓ 全部章节 | ✓ 仅我的章节 | ✓ 只读+评论 | ✓ 只读 |
| **审核工作台** | ✓ 配置+查看 | ✓ 配置+查看 | - | ✓ 我的审核 | ✓ 我的审批 |
| **溯源面板** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **版本历史** | ✓ 含回滚 | ✓ 含回滚 | ✓ 只读 | ✓ 只读 | ✓ 只读 |
| **项目设置** | ✓ | - | - | - | - |

同一个标签页内部，组件根据职责做细粒度过滤（如文档编辑页，Editor 只看到分配给自己的章节）。

### 3.3 标签页注册机制

```typescript
interface TabDefinition {
  id: string;
  label: string;
  icon: LucideIcon;
  component: React.ComponentType<{ projectId: string }>;
  visibleWhen: (ctx: ProjectIdentity) => boolean;
  order: number;
}
```

7 个注册标签页：`overview`(1)、`workflow`(2)、`editor`(3)、`review`(4)、`traceability`(5)、`history`(6)、`settings`(99)。

### 3.4 数据模型 — 新增表

#### `organization_units`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `name` | VARCHAR(100) | 如"技术分析部" |
| `parent_id` | UUID FK→self | 支持层级 |
| `unit_type` | VARCHAR(20) | `internal` / `external` / `virtual` |
| `description` | TEXT | |
| `manager_id` | UUID FK→users | 部门负责人（默认通知人） |
| `metadata` | JSONB | 扩展信息 |
| `created_at` / `updated_at` | TIMESTAMP | |

#### `system_roles`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `name` | VARCHAR(50) | 如"部门管理员" |
| `key` | VARCHAR(50) | 唯一标识 |
| `description` | TEXT | |
| `is_system` | BOOLEAN | 内置角色不可删除 |
| `permissions` | JSONB | 权限列表 |
| `created_at` / `updated_at` | TIMESTAMP | |

`permissions` JSONB 结构：

```json
{
  "system": [
    "user:manage", "org:manage", "template:manage",
    "template:publish", "role:manage", "audit:view"
  ],
  "project": [
    "project:create", "project:delete",
    "member:add", "member:remove",
    "approval:submit", "approval:review", "approval:approve", "approval:view",
    "outline:edit", "chapter:write_any", "chapter:write_own", "chapter:review",
    "ai:start_writing", "source:view", "version:rollback",
    "export:generate", "settings:edit"
  ]
}
```

#### `organization_memberships`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `user_id` | UUID FK→users | |
| `org_unit_id` | UUID FK→organization_units | |
| `system_role_id` | UUID FK→system_roles | |
| `position_title` | VARCHAR(100) | 如"高级工程师" |
| `is_primary` | BOOLEAN | 是否为主要所属部门 |
| `joined_at` / `left_at` | TIMESTAMP | |

#### `project_members` 扩展字段

| 新增字段 | 类型 | 说明 |
|----------|------|------|
| `source_org_unit_id` | UUID FK→organization_units | 从哪个组织单元关联 |
| `phase_duties` | JSONB | 项目内阶段职责明细 |

`phase_duties` JSONB：

```json
{
  "phase-a": {"duty": "lead", "role": "阶段负责人"},
  "phase-b": {"duty": "reviewer", "dimension": "technical"},
  "chapter-1": {"duty": "writer", "status": "in_progress"}
}
```

### 3.5 管理功能矩阵

| 功能 | 超级管理员 | 部门管理员 | 普通用户 |
|------|-----------|-----------|---------|
| 创建/编辑/删除部门 | ✓ | - | - |
| 邀请用户加入系统 | ✓ | - | - |
| 将用户分配至部门 | ✓ | ✓(本部门) | - |
| 定义/编辑角色 | ✓ | - | - |
| 配置角色权限矩阵 | ✓ | - | - |
| 创建/编辑流程模板 | ✓ | ✓(本部门) | - |
| 发布模板到模板库 | ✓ | ✓(需审批) | - |
| 查看所有项目 | ✓ | ✓(本部门) | - |
| 强制转让项目Owner | ✓ | - | - |

### 3.6 管理页面结构

新增 `frontend/src/extensions/admin/`：

```
admin/
├── AdminLayout.tsx              // 管理后台布局（侧边栏导航）
├── OrgStructure/
│   ├── OrgTreePanel.tsx         // 组织树
│   ├── OrgDetailPanel.tsx       // 部门详情（含岗位、成员、模板、项目）
│   └── OrgMemberList.tsx        // 部门成员列表
├── RoleManagement/
│   ├── RoleList.tsx             // 角色列表
│   ├── RoleEditor.tsx           // 角色编辑器（含权限矩阵编辑器）
│   └── PermissionMatrix.tsx     // 权限矩阵可视化编辑器
├── UserManagement/
│   ├── UserList.tsx             // 用户列表
│   ├── UserDetail.tsx           // 用户详情（部门+角色+项目参与）
│   └── UserInviteDialog.tsx     // 邀请对话框
├── TemplateManagement/
│   ├── TemplateLibrary.tsx      // 模板库
│   ├── TemplateEditor.tsx       // 复用 WorkflowEditor + 组织绑定
│   └── TemplatePublishDialog.tsx // 发布审批
└── api/
    ├── adminApi.ts
    └── adminTypes.ts
```

**路由规划：**

```
/admin                          → 重定向到 /admin/org
/admin/org                      → 组织架构管理
/admin/org/[orgId]              → 部门详情
/admin/roles                    → 角色管理
/admin/roles/[roleId]           → 角色编辑
/admin/users                    → 用户管理
/admin/templates                → 模板管理
/admin/templates/[templateId]   → 模板编辑
```

### 3.7 管理 API

```
GET    /api/extensions/admin/org-units
POST   /api/extensions/admin/org-units
PATCH  /api/extensions/admin/org-units/{id}
DELETE /api/extensions/admin/org-units/{id}
GET    /api/extensions/admin/org-units/{id}/members
POST   /api/extensions/admin/org-units/{id}/members

GET    /api/extensions/admin/roles
POST   /api/extensions/admin/roles
PATCH  /api/extensions/admin/roles/{id}
DELETE /api/extensions/admin/roles/{id}

GET    /api/extensions/admin/users
GET    /api/extensions/admin/users/{id}
POST   /api/extensions/admin/users/invite

GET    /api/extensions/admin/templates
POST   /api/extensions/admin/templates
PATCH  /api/extensions/admin/templates/{id}
POST   /api/extensions/admin/templates/{id}/publish

GET    /api/extensions/admin/dashboard
```

### 3.8 后端目录结构

```
backend/app/extensions/admin/
├── __init__.py
├── routers.py
├── schemas.py
├── service.py
├── permissions.py
├── models.py
└── migration.py
```

### 3.9 向后兼容策略

- 初始化自动创建默认角色（映射现有的 owner/member）
- 现有 `project_members.role` 保持不变，新增字段有默认值
- 未配置组织架构的部署等同于当前系统
- 组织功能可选启用

## 4. 领域 C：个性化任务控制台

### 4.1 设计理念

从"项目驱动"转为"任务驱动"：

- **当前**："这里有50个项目" → 用户自己找该做什么
- **目标**："你有3个审核待处理、2个章节待写、1个阶段需要推进"

### 4.2 页面结构

```
┌──────────────────────────────────────────────────────┐
│ 导航栏: [Logo] 工作台 | 文档 | 项目 | 管理  [🔔][👤] │
├──────────────────────────────────────────────────────┤
│                                                      │
│ ┌─ 左侧: 任务区 (70%) ────┐ ┌─ 右侧: 面板 (30%) ──┐ │
│ │                          │ │                     │ │
│ │ 今日待办 (优先级排序)     │ │ 📊 我的统计         │ │
│ │ - 🔴 紧急任务            │ │ 📅 迷你日历         │ │
│ │ - 🟡 本周任务            │ │ 🔔 最近通知         │ │
│ │ - ⚪ 已完成(可折叠)      │ │                     │ │
│ │                          │ │                     │ │
│ │ 我的项目 (按角色分组)     │ │                     │ │
│ │ - 作为阶段负责人         │ │                     │ │
│ │ - 作为审核人             │ │                     │ │
│ │ - 作为撰写人             │ │                     │ │
│ │                          │ │                     │ │
│ └──────────────────────────┘ └─────────────────────┘ │
│                                                      │
│ 快捷入口: [个人写作] [从模板创建] [项目看板] [文档]   │
└──────────────────────────────────────────────────────┘
```

### 4.3 任务优先级算法

```
优先级 = 基础分 + 紧急度 + 阻塞度 + 角色权重

基础分: 审批 40 > 审核 30 > 编写 20 > 阶段推进 15
紧急度: 已逾期 +30 | 今天截止 +25 | 明天 +20 | 本周 +10 | 无 0
阻塞度: 阻塞下游 +25 | 无阻塞 0
角色权重: 唯一审核人 +10 | 多人之一 0
```

### 4.4 任务类型 → 操作映射

| 任务类型 | 触发条件 | 操作按钮 | 目标页面 |
|---------|---------|---------|---------|
| 审核待处理 | phase_review status=pending | `[开始审核→]` | 审核工作台，定位章节 |
| 编写待完成 | chapter status=writing/draft | `[继续编写→]` | BlockNote编辑器，定位章节 |
| 阶段待推进 | 用户是阶段负责人，上游已完成 | `[进入项目→]` | 流程看板 |
| AI写作进行中 | AI正在生成 | `[查看进度→]` | AI写作状态页 |
| 审核被退回 | rejection rollback | `[修改后重审→]` | 被退回章节编辑器 |

### 4.5 我的项目 — 分组逻辑

对于每个项目，确定用户的"首要身份"：
1. owner → "我负责的项目"
2. 任一阶段的 phase_lead → "作为阶段负责人"
3. 有待审核任务 → "作为审核人"
4. 有待编写章节 → "作为撰写人"
5. 以上都不是 → "仅查看"

### 4.6 项目迷你卡片

```
┌──────────────────────────────────────┐
│ 📁 2026年度XX项目环评                 │
│ 阶段 3/6 · 技术分析 · 进行中          │
│ ████████████░░░░░░░░ 48%             │
│ 我的待办: 📝 第5章 | 🔍 2项审核       │
│ 上次更新: 2小时前          [进入 →]  │
└──────────────────────────────────────┘
```

### 4.7 Dashboard API

```
GET    /api/extensions/dashboard/my-tasks
GET    /api/extensions/dashboard/my-stats
GET    /api/extensions/dashboard/my-projects
GET    /api/extensions/dashboard/my-calendar
GET    /api/extensions/dashboard/my-notifications
PATCH  /api/extensions/dashboard/notification/{id}/read
```

### 4.8 路由变更

```
现有:
  /                          → 不明确
  /projects                  → ProjectList (当前事实上的"首页")

新设计:
  /dashboard                 → 任务控制台 (新首页)
  /projects                  → ProjectList (保留，辅助导航)
  /admin/*                   → 管理后台 (新增，管理员权限)
  /projects/[id]             → 项目详情页 (保留，增强)
```

### 4.9 前端目录结构

```
frontend/src/extensions/dashboard/
├── DashboardPage.tsx
├── components/
│   ├── TodayTasks.tsx
│   ├── TaskItem.tsx
│   ├── MyProjects.tsx
│   ├── ProjectMiniCard.tsx
│   ├── StatsPanel.tsx
│   ├── MiniCalendar.tsx
│   ├── NotificationFeed.tsx
│   └── QuickActions.tsx
├── hooks/
│   ├── useMyTasks.ts
│   ├── useMyStats.ts
│   ├── useMyProjects.ts
│   ├── useMyCalendar.ts
│   └── useNotifications.ts
├── api.ts
├── types.ts
└── transforms.ts
```

## 5. 领域 D：项目跟踪工具

### 5.1 三层时间视图

```
第一层: 甘特图 (项目全景)
  面向: Owner / Manager / 阶段负责人
  维度: 全部阶段 + 依赖关系 + 里程碑
  数据: 工作流定义 + Temporal 执行状态 + project_timeline 表

第二层: 阶段看板 (单阶段)
  面向: 阶段负责人 / 执行者
  维度: 该阶段内章节任务 + 状态 + 指派人 + 审核状态
  数据: project_chapters + phase_reviews + 截止日期

第三层: 个人日历 (个人)
  面向: 所有项目参与者
  维度: 跨项目截止日期 + 里程碑 + 个人事项
  数据: 聚合所有任务的截止日期
```

### 5.2 数据模型 — 新增表

#### `project_timeline`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK→report_projects | |
| `phase_node` | VARCHAR(50) | DAG 节点 ID |
| `planned_start` | DATE | 计划开始 |
| `planned_end` | DATE | 计划结束 |
| `actual_start` | DATE | 实际开始（运行时填写） |
| `actual_end` | DATE | 实际结束（运行时填写） |
| `depends_on` | JSONB | 前置依赖阶段列表 |
| `milestones` | JSONB | 阶段内里程碑 |
| `progress_pct` | INTEGER | 进度 0-100 |
| `owner_id` | UUID FK→users | 阶段负责人 |

`milestones` JSONB：

```json
[
  {"label": "数据收集完成", "target_date": "2026-06-15", "status": "completed"},
  {"label": "初稿提交审核", "target_date": "2026-06-30", "status": "in_progress"},
  {"label": "审核通过", "target_date": "2026-07-10", "status": "pending"}
]
```

### 5.3 甘特图交互设计

| 交互 | 行为 |
|------|------|
| 拖拽阶段条 | 调整计划开始/结束日期 |
| 拉伸阶段条 | 调整计划时长 |
| 点击阶段条 | 展开里程碑 + 详情 |
| 点击里程碑 | 跳转到对应章节 |
| 双击空白 | 快速创建里程碑 |
| 鼠标悬停 | tooltip: 负责人、完成度、阻塞信息 |
| 时间轴缩放 | 月/周/日 三档 |
| 导出 | 图片或 PDF |

**延期预警可视化规则：**
- 当 时间消耗% > 完成% 超过15%：阶段条变橙色 ⚠，显示预警标签
- 当上游延期导致下游阻塞：下游阶段条变红色 🔴，依赖线变红色虚线

### 5.4 阶段看板设计

看板列 → 章节状态映射：

```
📝 待编写 (pending)  →  ✍️ 编写中 (writing)  →  🔍 审核中 (in_review)
    ↓                        ↓                       ↓
   (可拖拽)               (可拖拽)               (可拖拽)

✅ 已完成 (completed)  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←

❌ 已退回 (rejected) → 回到 ✍️ 编写中
```

| 交互 | 行为 |
|------|------|
| 章节卡片拖拽跨列 | 更新 `project_chapters.status` |
| 点击卡片 | 进入编辑器定位章节 |
| 点击指派人 | 重新分配 |
| 右键卡片 | 菜单：编辑详情/设置截止/AI生成/溯源/版本 |
| 阶段负责人操作栏 | 批量分配、批量AI写作 |

### 5.5 个人日历

从三个数据源聚合日历事件：

1. **项目任务截止日期**（系统自动）— 章节编写截止、审核截止、审批截止
2. **阶段/项目里程碑**（从 `project_timeline.milestones` 读取）
3. **用户个人事项**（用户自己添加，仅自己可见，可选关联项目/章节）

### 5.6 提醒触发规则

| 触发条件 | 提醒方式 | 频率 |
|---------|---------|------|
| 截止前 3 天 | 站内通知 + 可选邮件 | 每天一次 |
| 截止前 1 天 | 站内 + 邮件 + 标记紧急 | 当天一次 |
| 截止当天 | 站内 + 邮件 + 紧急标记 | 当天一次 |
| 逾期 1 天 | 站内 + 邮件 + 升级通知阶段负责人 | 每天一次 |
| 上游完成 2 天未启动 | 站内通知阶段负责人 | 每 2 天 |
| 审核积压 > 3 天 | 站内通知审核人 + 经理 | 每天一次 |

### 5.7 通知偏好配置项

```
通知渠道: 站内(默认不可关闭) / 邮件 / 企微(后续)
通知类型: 任务分配 / 截止提醒 / 审核结果 / 阶段流转 / 项目摘要 / @评论
提醒时间: 截止前N天(默认3) / 每日提醒时间(默认09:00)
免打扰: 开始时间(默认22:00) / 结束时间(默认08:00)
```

### 5.8 甘特图/看板/日历 API

```
# 甘特图
GET    /api/extensions/projects/{id}/timeline
PUT    /api/extensions/projects/{id}/timeline
POST   /api/extensions/projects/{id}/timeline/milestones
PATCH  /api/extensions/projects/{id}/timeline/milestones/{mid}
DELETE /api/extensions/projects/{id}/timeline/milestones/{mid}

# 阶段看板
PATCH  /api/extensions/projects/{id}/chapters/{ch_id}/status
GET    /api/extensions/projects/{id}/phases/{phase}/board
POST   /api/extensions/projects/{id}/phases/{phase}/batch-assign

# 日历 (复用 Dashboard API)
GET    /api/extensions/dashboard/my-calendar
GET    /api/extensions/dashboard/my-calendar?start=X&end=Y

# 提醒
GET    /api/extensions/users/me/notification-preferences
PUT    /api/extensions/users/me/notification-preferences
```

### 5.9 前端目录结构扩展

```
frontend/src/extensions/project/components/
├── (existing: ApprovalTab, ProjectCard, StatusBadge, FilterPills)
│
├── GanttChart/
│   ├── GanttChart.tsx
│   ├── GanttBar.tsx
│   ├── GanttMilestone.tsx
│   ├── GanttTimelineHeader.tsx
│   └── useGanttDrag.ts
│
├── KanbanBoard/
│   ├── KanbanBoard.tsx
│   ├── KanbanColumn.tsx
│   ├── KanbanCard.tsx
│   └── KanbanHeader.tsx
│
└── Dashboard/
    ├── ProjectDashboard.tsx
    ├── ProgressRing.tsx
    ├── ChapterStatusChart.tsx
    ├── MemberWorkload.tsx
    └── RecentActivity.tsx

frontend/src/extensions/dashboard/components/
├── (Dashboard 组件已在领域C定义)
├── FullCalendar.tsx
├── CalendarEvent.tsx
└── NotificationPreferences.tsx
```

## 6. 与现有系统的关系

### 6.1 依赖关系

```
本设计 (2026-06-01)
  ├── 依赖: 2026-05-29-workflow-engine-traceability-review-design.md
  │    └── 复用: Temporal 工作流引擎、DAG 编辑器、溯源系统、审核系统
  ├── 依赖: 2026-05-25-project-rbac-workspace-approval-design.md
  │    └── 扩展: 角色体系从 2 种→可配置多角色、权限矩阵
  ├── 依赖: 2026-05-26-project-document-collaboration-design.md
  │    └── 复用: BlockNote 编辑器、版本管理、评论系统
  └── 依赖: 2026-05-24-project-management-redesign.md
       └── 扩展: 项目仪表盘、阶段看板、甘特图
```

### 6.2 向后兼容

- 所有现有 API 保持不变
- 无 `workflow_id` 的项目继续走固定6阶段逻辑
- 无组织单元的用户行为等同当前系统
- 项目列表页保留为辅助导航，不再是默认首页

## 7. 交付建议

### 优先级排序（与用户确认）

| 优先级 | 领域 | 说明 |
|--------|------|------|
| P0 | A: 项目Card创建与流程配置 | 三层流程配置体系、模板库、组织绑定 |
| P1 | B: 角色化页面 + 角色管理 | 标签页矩阵、管理后台（组织/角色/用户/模板管理） |
| P2 | C: 个性化任务控制台 | 任务驱动首页、今日待办、角色分组项目 |
| P2 | D: 项目跟踪工具 | 甘特图、阶段看板、个人日历、提醒通知 |

**C+D 可后续再做**，优先完成 A+B。

### 建议子阶段

1. **A1**: 组织单元 + 系统角色 + 权限矩阵数据模型及管理 API
2. **A2**: 流程模板库（模板 CRUD、发布、组织绑定、复制为项目流程）
3. **A3**: 项目创建流程改造（选模板 → 覆盖组织/人员 → 启动）
4. **B1**: 管理后台页面（组织架构、角色管理、用户管理、模板管理）
5. **B2**: 项目详情页标签化改造（标签注册、可见性矩阵、细粒度权限过滤）
6. **C+D**: 任务控制台 + 项目跟踪（后续阶段）
