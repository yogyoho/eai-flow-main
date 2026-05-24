# 项目管理模块全面重设计方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目管理模块从基础的 CRUD + 大纲编辑器扩展为完整的报告项目管理平台，新增项目立项向导、章节任务看板、进度仪表盘、成员工作台、审核流程和 AI 辅助工具箱。

**Architecture:** 基于现有六阶段流程（Setup→Outline→AI Writing→Collab Editing→Approval→Export）的 stage-centric 架构。每个新功能模块作为独立的前端面板 + 后端 API 扩展，通过 `ReportProject` / `ProjectChapter` / `ProjectMember` 现有模型扩展字段实现。Phase 1 交付任务管理（看板+仪表盘），Phase 2 交付审批流程，Phase 3 交付向导，Phase 4 交付 AI 工具箱和分析。

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Shadcn UI, Lucide Icons, Recharts, FastAPI, SQLAlchemy async, PostgreSQL, DeerFlow Agent System（已集成）

**UI Prototype:** `docs/superpowers/specs/ai-writing-prototype.pen`（6 个新屏幕）

---

## 1. 已实现功能清单

以下功能已完成并通过测试，作为本设计的基线：

| 功能 | 状态 | 关键文件 |
|------|------|---------|
| 项目 CRUD（列表/创建/读取/更新/删除） | ✅ | `backend/app/extensions/project/routers.py`, `service.py` |
| 大纲树编辑器（增删改、拖拽排序、层级调整） | ✅ | `frontend/src/extensions/project/OutlineEditor.tsx` |
| 大纲预览 | ✅ | `frontend/src/extensions/project/OutlinePreview.tsx` |
| Stage 进度条 | ✅ | `frontend/src/extensions/project/StageProgressBar.tsx` |
| ProjectWorkspace（按 Stage 切换渲染） | ✅ | `frontend/src/extensions/project/ProjectWorkspace.tsx` |
| Stage 3 AI 撰写（创建 thread → 跳转对话页） | ✅ | `ChapterWritingPanel.tsx`, `service.py:start_writing()` |
| Stage 4 协作编辑（章节分配 → 跳转对话页） | ✅ | `ChapterEditingPanel.tsx`, `service.py:start_chapter_editing()` |
| Project MCP Server（6 个工具） | ✅ | `backend/app/extensions/project/mcp.py` |
| report-write Skill | ✅ | `skills/custom/report-write/SKILL.md` |
| 成员管理（增删） | ✅ | `routers.py`, `service.py` |
| 审批模型（ApprovalWorkflow, ApprovalRecord） | ✅ | `backend/app/extensions/models.py` |
| 前端 API 客户端（snake_case ↔ camelCase） | ✅ | `frontend/src/extensions/project/api.ts`, `transforms.ts` |
| 单元测试 | ✅ | `frontend/tests/unit/extensions/project/api.test.ts` |

---

## 2. 新增功能模块

### 2.1 项目立项向导（Project Wizard）

**目的：** 替代当前的简单创建对话框，引导用户完成项目初始化的每个步骤。

**向导步骤：**

1. **基本信息** — 项目名称、报告类型（必填）
2. **模板选择** — 可选，从 Knowledge Factory 已发布模板中选择，预览章节结构
3. **团队组建** — 添加项目成员，分配角色（经理/编辑/审核人/批准人）
4. **确认创建** — 汇总信息，一键创建项目

**UI 参考：** Prototype 屏幕帧 `HU3y6`（Enhanced Project Wizard）

```
┌──────────────────────────────────────────┐
│  创建新项目                    Step 2/4   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  ━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                          │
│  选择报告模板                             │
│                                          │
│  ┌─────────────┐  ┌─────────────┐        │
│  │ 环评标准模板  │  │ 地质勘查模板  │       │
│  │ 12章节      │  │ 8章节       │         │
│  │ [选择]      │  │ [选择]      │         │
│  └─────────────┘  └─────────────┘        │
│                                          │
│  [跳过] [下一步 →]                        │
└──────────────────────────────────────────┘
```

**数据流：**
- Step 1 → 调用 `projectApi.create()` 创建项目（status=`setup`）
- Step 2 → 可选调用 `GET /api/kf/templates` 获取模板列表
- Step 3 → 调用 `projectApi.addMember()` 添加成员
- Step 4 → 确认后跳转到 `/projects/{id}?stage=2`（大纲确认页）

**后端变更：**
- 无新增端点。复用已有 `POST /projects`、`POST /projects/{id}/members`
- 模板列表复用 Knowledge Factory 的 `GET /api/kf/templates` 端点

**前端新增文件：**
- `frontend/src/extensions/project/ProjectWizard.tsx` — 向导容器组件（~200 行）
- `frontend/src/extensions/project/WizardStepBasic.tsx` — Step 1 基本信息表单（~80 行）
- `frontend/src/extensions/project/WizardStepTemplate.tsx` — Step 2 模板选择（~100 行）
- `frontend/src/extensions/project/WizardStepTeam.tsx` — Step 3 团队组建（~120 行）
- `frontend/src/extensions/project/WizardStepConfirm.tsx` — Step 4 确认汇总（~80 行）

---

### 2.2 章节任务看板（Kanban Board）

**目的：** Stage 3/4 中以看板视图管理章节任务，按状态分列，支持拖拽排序和状态变更。

**看板列（对应 ChapterStatus）：**

| 列名 | 状态 | 颜色 |
|------|------|------|
| 待撰写 | `pending` | gray |
| AI 撰写中 | `writing` | blue |
| 初稿 | `draft` | blue-light |
| 编辑中 | `editing` | orange |
| 已完成 | `completed` | green |
| 退回修改 | `rejected` | red |

**看板卡片内容：**
- 章节标题
- 指派人头像 + 名称
- 字数进度（当前/目标）
- 优先级标记（如需）
- 最后更新时间

**交互：**
- 拖拽卡片跨列 → 自动更新章节状态
- 点击卡片 → 打开章节详情侧边栏（内容预览、编辑操作、跳转对话页）
- 列头部显示统计数字

**UI 参考：** Prototype 屏幕帧 `n7d0W`（Kanban Task Board）

**后端变更：**
- 新增 `PATCH /api/extensions/project/projects/{id}/chapters/{ch_id}/status` — 单独更新章节状态（已有 `update_chapter` 但需专用端点简化看板操作）

```python
# schemas.py 新增
class ChapterStatusUpdate(BaseModel):
    status: str

# routers.py 新增
@router.patch("/projects/{project_id}/chapters/{chapter_id}/status")
async def update_chapter_status(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterStatusUpdate,
    ...
):
    result = await service.update_chapter(db, chapter_id, status=body.status)
    ...
```

**前端新增文件：**
- `frontend/src/extensions/project/KanbanBoard.tsx` — 看板容器（~150 行）
- `frontend/src/extensions/project/KanbanColumn.tsx` — 看板列（~80 行）
- `frontend/src/extensions/project/KanbanCard.tsx` — 看板卡片（~100 行）
- `frontend/src/extensions/project/ChapterDetailDrawer.tsx` — 章节详情侧边栏（~200 行）

---

### 2.3 进度仪表盘（Project Dashboard）

**目的：** 项目首页（Stage 概览），展示项目整体进度、章节状态分布、成员工作量、时间线。

**仪表盘组件：**

1. **统计卡片** — 总章节数、已完成数、进行中数、完成率
2. **进度环形图** — 整体完成百分比
3. **章节状态分布** — 按状态的条形图
4. **成员工作量** — 每人分配的章节数和完成数
5. **最近活动** — 最近 10 条操作记录
6. **阶段时间线** — 各阶段的进入/完成时间

**UI 参考：** Prototype 屏幕帧 `xD4aB`（Project Dashboard）

**数据来源：**
- 统计数据从 `get_project()` 返回的章节树计算
- 前端遍历 `chapters` 树统计各状态数量
- 活动记录需要后端新增查询

**后端变更：**
- 新增 `GET /api/extensions/project/projects/{id}/stats` — 返回聚合统计数据

```python
# schemas.py 新增
class ProjectStats(BaseModel):
    total_chapters: int
    completed_chapters: int
    in_progress_chapters: int
    total_word_count: int
    total_word_target: int
    completion_rate: float  # 0.0 - 1.0
    status_distribution: dict[str, int]  # {"pending": 3, "draft": 2, ...}
    member_workload: list[dict]  # [{"user_id": ..., "username": ..., "assigned": 3, "completed": 1}]
    recent_activity: list[dict]  # [{"action": "chapter_updated", "chapter_title": ..., "user": ..., "time": ...}]
```

- 新增 `GET /api/extensions/project/projects/{id}/activity` — 操作记录查询
- 后端在关键操作（章节状态变更、成员分配、内容写入）时记录活动日志

**数据模型变更：**

```python
# models.py 新增
class ProjectActivity(Base):
    """Activity log for project operations."""
    __tablename__ = "project_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("report_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("project_chapters.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "status_change", "assign", "content_update", "member_add"
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON detail
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
```

**前端新增文件：**
- `frontend/src/extensions/project/ProjectDashboard.tsx` — 仪表盘容器（~200 行）
- `frontend/src/extensions/project/StatsCards.tsx` — 统计卡片区（~100 行）
- `frontend/src/extensions/project/ProgressChart.tsx` — 进度图表组件（~150 行，使用 Recharts）
- `frontend/src/extensions/project/MemberWorkload.tsx` — 成员工作量组件（~80 行）
- `frontend/src/extensions/project/ActivityFeed.tsx` — 最近活动列表（~100 行）

---

### 2.4 成员工作台（Member Workspace）

**目的：** 为每个项目成员提供个人视角，展示自己负责的章节、待办任务和协作信息。

**工作台内容：**
- 当前用户被分配的章节列表（按状态分组）
- 每个章节的快速操作按钮（开始编辑、查看内容、AI 辅助）
- 个人进度统计（我的完成率、待处理数）
- 通知/提醒区域

**UI 参考：** Prototype 屏幕帧 `Z5JafO`（Member Workspace）

**后端变更：**
- 新增 `GET /api/extensions/project/projects/{id}/my-tasks` — 返回当前用户的章节任务

```python
# schemas.py 新增
class MyTasksResponse(BaseModel):
    assigned_chapters: list[ChapterOut]
    pending_count: int
    in_progress_count: int
    completed_count: int
```

**前端新增文件：**
- `frontend/src/extensions/project/MemberWorkspace.tsx` — 成员工作台容器（~200 行）
- `frontend/src/extensions/project/MyTaskList.tsx` — 个人任务列表（~120 行）
- `frontend/src/extensions/project/TaskCard.tsx` — 任务卡片（~80 行）

---

### 2.5 审核流程（Approval Workflow）

**目的：** Stage 5 中实现多步骤审核流程，支持按角色逐步审批、退回修改、审批记录追溯。

**审核流程设计：**

1. 项目经理提交审核 → 创建 `ApprovalWorkflow` 步骤链
2. 每个步骤指定所需角色（如：技术审核→部门负责人→质量总监）
3. 审核人在自己的待办中看到待审核章节
4. 审核人可以：通过（带评语）或退回（带修改意见）
5. 全部步骤通过 → 项目状态推进到 Stage 6
6. 任一步骤退回 → 返回 Stage 4 重新编辑

**审核步骤状态机：**

```
pending → approved → (next step pending → ...)
                  \→ all steps done → Stage 6
       → rejected → Stage 4 (re-edit)
```

**UI 参考：** Prototype 屏幕帧 `S4Ke4`（Approval Workflow）

**后端变更（大部分已实现）：**

已有模型：`ApprovalWorkflow`（步骤定义）、`ApprovalRecord`（审批记录）

已有 schemas：`ApprovalActionRequest`、`ApprovalWorkflowOut`、`ApprovalRecordOut`

需新增端点：
- `POST /api/extensions/project/projects/{id}/submit-approval` — 提交审核，创建审核步骤链
- `POST /api/extensions/project/projects/{id}/approval-action` — 审核人执行审批动作
- `GET /api/extensions/project/projects/{id}/approval-status` — 获取审核流程状态
- `GET /api/extensions/project/projects/{id}/approval-records` — 获取审批记录列表

```python
# service.py 新增
async def submit_approval(db: AsyncSession, project_id, workflow_config: list[dict]):
    """Create approval workflow steps and advance project to stage 5."""
    ...

async def approval_action(db: AsyncSession, project_id, workflow_id, action: str, comment: str, reviewer_id):
    """Execute approval action (approve/reject). If rejected, roll back to stage 4."""
    ...

async def get_approval_status(db: AsyncSession, project_id):
    """Get current approval status with all steps and records."""
    ...
```

**前端新增文件：**
- `frontend/src/extensions/project/ApprovalPanel.tsx` — 审核面板容器（~200 行）
- `frontend/src/extensions/project/ApprovalStepList.tsx` — 审核步骤列表（~120 行）
- `frontend/src/extensions/project/ApprovalActionDialog.tsx` — 审批操作对话框（~100 行）
- `frontend/src/extensions/project/ApprovalRecordList.tsx` — 审批记录列表（~80 行）

---

### 2.6 AI 辅助工具箱（AI Toolbox）

**目的：** 为编辑人员提供一键 AI 辅助操作，直接在项目页面调用 Agent 完成常见编辑任务。

**AI 工具列表：**

| 工具 | 功能 | 调用方式 |
|------|------|---------|
| 内容润色 | 优化语言表述，提升文字质量 | 选中章节 → 点击润色 |
| 扩写 | 根据目的和要求扩展内容 | 选中章节 → 设置目标字数 |
| 缩写 | 精简冗余内容 | 选中章节 → 设置目标字数 |
| 格式检查 | 检查标点、编号、格式一致性 | 选中章节 → 一键检查 |
| 合规检查 | 对照法规/标准验证内容 | 选中章节 → 一键检查 |
| 术语统一 | 检查全文术语使用一致性 | 全文扫描 |

**UI 参考：** Prototype 屏幕帧 `N47vs`（AI Toolbox Panel）

**交互流程：**

1. 用户在看板或章节详情中选择一个/多个章节
2. 点击 AI 工具箱中的某个工具
3. 系统创建临时对话 thread，注入章节上下文和工具指令
4. Agent 执行任务，结果回写到章节内容
5. 章节状态更新为 `editing`，用户可查看变更

**后端变更：**
- 新增 `POST /api/extensions/project/projects/{id}/ai-action` — 触发 AI 辅助操作

```python
# schemas.py 新增
class AiActionRequest(BaseModel):
    chapter_ids: list[UUID]
    action: str  # "polish", "expand", "condense", "format_check", "compliance_check", "terminology_check"
    params: dict | None = None  # {"target_word_count": 5000, "standard": "HJ 2.1-2016"}

class AiActionResponse(BaseModel):
    thread_id: str
    task_count: int
```

**实现策略：**
- 复用 DeerFlow thread + Agent 架构，创建临时 thread 注入 AI 工具 prompt
- MCP 工具 `write_chapter` 回写结果
- 前端轮询章节状态或通过 thread 查询进度

**前端新增文件：**
- `frontend/src/extensions/project/AiToolbox.tsx` — AI 工具箱面板（~150 行）
- `frontend/src/extensions/project/AiActionDialog.tsx` — AI 操作确认对话框（~100 行）

---

## 3. 导航结构重设计

### 3.1 项目列表页

保持现有列表视图，新增：
- 顶部搜索/筛选栏
- 项目卡片视图切换（列表/网格）
- 快速创建按钮 → 打开向导

### 3.2 项目工作区

现有 `ProjectWorkspace` 按.stage 切换的架构不变。新增 Tab 式子导航，在工作区内切换视图：

```
项目工作区顶部导航:
┌──────────────────────────────────────────────────┐
│ ← 返回  项目名称         [仪表盘][看板][大纲][成员] │
│                                    Stage 3/6 ▶▶▶ │
└──────────────────────────────────────────────────┘
```

**Tab 与 Stage 映射：**

| Tab | 可见 Stage | 说明 |
|-----|-----------|------|
| 仪表盘 | 2-6 | 任何阶段都可查看项目整体状况 |
| 看板 | 3-4 | Stage 3/4 中管理章节任务 |
| 大纲 | 2 | Stage 2 大纲编辑（已有） |
| 成员 | 2-6 | 管理团队成员（已有） |
| 审核 | 5 | Stage 5 审核流程 |
| AI工具 | 3-4 | Stage 3/4 AI 辅助操作 |

**前端实现：**

`ProjectWorkspace.tsx` 重构：当前按 stage 渲染面板的逻辑改为 Tab + Stage 联合控制。Stage 决定哪些 Tab 可用，用户可在允许的 Tab 间自由切换。

---

## 4. 数据模型变更

### 4.1 新增模型

```python
class ProjectActivity(Base):
    """Activity log for project operations."""
    __tablename__ = "project_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_chapters.id"), nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
```

### 4.2 现有模型字段扩展

**ReportProject** — 无新增字段（现有字段足够支撑新功能）

**ProjectChapter** — 无新增字段（`assigned_to`, `status`, `word_count_*` 已足够）

**ApprovalWorkflow** — 已有足够字段（`step_order`, `step_name`, `role_required`, `status`）

**ApprovalRecord** — 已有足够字段（`workflow_id`, `chapter_id`, `action`, `reviewer_id`, `comment`）

### 4.3 Alembic 迁移

```python
# 新增 project_activities 表
def upgrade():
    op.create_table(
        'project_activities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), sa.ForeignKey('report_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chapter_id', sa.UUID(), sa.ForeignKey('project_chapters.id'), nullable=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_project_activities_project_id', 'project_activities', ['project_id'])
```

---

## 5. API 端点汇总

### 5.1 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects/{id}/stats` | 项目统计数据（仪表盘） |
| GET | `/projects/{id}/activity` | 操作记录（活动流） |
| GET | `/projects/{id}/my-tasks` | 当前用户的任务（成员工作台） |
| PATCH | `/projects/{id}/chapters/{ch_id}/status` | 快速状态变更（看板拖拽） |
| POST | `/projects/{id}/submit-approval` | 提交审核 |
| POST | `/projects/{id}/approval-action` | 执行审批动作 |
| GET | `/projects/{id}/approval-status` | 审核流程状态 |
| GET | `/projects/{id}/approval-records` | 审批记录列表 |
| POST | `/projects/{id}/ai-action` | 触发 AI 辅助操作 |

### 5.2 复用端点（已有，不修改）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects` | 项目列表 |
| GET | `/projects/{id}` | 项目详情（含章节树、成员列表） |
| POST | `/projects` | 创建项目 |
| PATCH | `/projects/{id}` | 更新项目 |
| DELETE | `/projects/{id}` | 删除项目 |
| GET | `/projects/{id}/outline` | 获取大纲树 |
| PUT | `/projects/{id}/outline` | 替换大纲 |
| PATCH | `/projects/{id}/chapters/{ch_id}` | 更新章节 |
| POST | `/projects/{id}/confirm-outline` | 确认大纲 |
| POST | `/projects/{id}/members` | 添加成员 |
| DELETE | `/projects/{id}/members/{uid}` | 移除成员 |
| POST | `/projects/{id}/start-writing` | 开始 AI 撰写 |
| POST | `/projects/{id}/chapters/{ch_id}/start-editing` | 开始章节编辑 |

---

## 6. 前端文件结构

```
src/extensions/project/
├── api.ts                          # API 客户端（已有，扩展）
├── transforms.ts                   # snake_case/camelCase（已有）
├── types.ts                        # 类型定义（已有，扩展）
│
├── ProjectWorkspace.tsx            # 主工作区（已有，重构 Tab 导航）
├── ProjectWizard.tsx               # 🆕 项目立项向导
├── WizardStepBasic.tsx             # 🆕 向导 Step 1
├── WizardStepTemplate.tsx          # 🆕 向导 Step 2
├── WizardStepTeam.tsx              # 🆕 向导 Step 3
├── WizardStepConfirm.tsx           # 🆕 向导 Step 4
│
├── ProjectDashboard.tsx            # 🆕 进度仪表盘
├── StatsCards.tsx                  # 🆕 统计卡片
├── ProgressChart.tsx               # 🆕 进度图表
├── MemberWorkload.tsx              # 🆕 成员工作量
├── ActivityFeed.tsx                # 🆕 活动流
│
├── KanbanBoard.tsx                 # 🆕 看板容器
├── KanbanColumn.tsx                # 🆕 看板列
├── KanbanCard.tsx                  # 🆕 看板卡片
├── ChapterDetailDrawer.tsx         # 🆕 章节详情侧边栏
│
├── OutlineEditor.tsx               # 大纲编辑器（已有）
├── OutlinePreview.tsx              # 大纲预览（已有）
├── SplitScreenLayout.tsx           # 分屏布局（已有）
├── StageProgressBar.tsx            # 阶段进度条（已有）
│
├── ChapterWritingPanel.tsx         # AI 撰写面板（已有）
├── ChapterEditingPanel.tsx         # 协作编辑面板（已有）
├── MemberWorkspace.tsx             # 🆕 成员工作台
├── MyTaskList.tsx                  # 🆕 个人任务列表
├── TaskCard.tsx                    # 🆕 任务卡片
│
├── ApprovalPanel.tsx               # 🆕 审核面板
├── ApprovalStepList.tsx            # 🆕 审核步骤列表
├── ApprovalActionDialog.tsx        # 🆕 审批操作对话框
├── ApprovalRecordList.tsx          # 🆕 审批记录列表
│
├── AiToolbox.tsx                   # 🆕 AI 工具箱
└── AiActionDialog.tsx              # 🆕 AI 操作对话框
```

---

## 7. 与 DeerFlow Agent 系统的集成

### 7.1 核心设计：提示词预注入

调用 DeerFlow Agent 时，**项目模块负责将模板的编写契约内容作为提示词注入 thread**，而非让 Agent 自行通过 MCP 拉取。Agent 只通过 MCP 工具读写章节数据（内容、状态），不负责获取"怎么写"的指令。

**提示词构建流程：**

```
创建 thread 时:
  1. 从 ExtractionTemplate.root_sections_json 提取各章节的编写规格
  2. 从 ProjectChapter 获取当前章节状态和已有内容
  3. 组装完整提示词，包含：
     - 项目背景（名称、报告类型）
     - 各章节编写契约：
       · purpose（编写目的）
       · content_contract（结构约束、关键要素、风格规则、最低字数、禁用表述）
       · generation_hint（额外编写指导）
       · example_snippet（参考样例，仅参考结构和风格）
       · compliance_rules（需遵守的法规/标准）
     - RAG 资源引用（知识库ID、检索策略、top_k、相似度阈值）
     - 相邻章节标题和摘要（保持上下文连贯）
  4. 将组装的提示词写入 thread metadata 的 system_prompt 字段
```

**提示词结构示例：**

```json
{
  "project_id": "uuid",
  "type": "report_project",
  "report_type": "environmental_impact",
  "system_prompt": "你是专业的环评报告撰写专家。请按照以下章节规格撰写报告。\n\n## 项目信息\n项目名称：XX环境影响评价报告\n报告类型：环境影响评价\n\n## 章节规格\n\n### 第1章 概述\n- 编写目的：[purpose]\n- 关键要素：[content_contract.key_elements]\n- 结构类型：[content_contract.structure_type]\n- 风格规则：[content_contract.style_rules]\n- 最低字数：[content_contract.min_word_count]\n- 禁用表述：[content_contract.forbidden_phrases]\n- 编写提示：[generation_hint]\n- 参考样例：\n[example_snippet]\n\n### 第2章 环境现状\n...\n\n## RAG 资源\n- 知识库「环评法规库」(id: xxx)：检索策略 hybrid, top_k=5, 相似度阈值 0.7\n- 知识库「监测数据库」(id: yyy)：检索策略 vector, top_k=3, 相似度阈值 0.8\n\n## 合规要求\n- 环境影响评价技术导则 总纲 HJ 2.1-2016\n- 环境影响评价技术导则 生态影响 HJ 19-2022\n\n## 撰写规则\n1. 严格遵循大纲结构，不增删章节\n2. 内容必须覆盖所有关键要素\n3. 数据引用必须标注来源\n4. 保持前后章节术语和表述一致\n5. 禁用「我认为」「感觉」等主观表述"
}
```

### 7.2 各场景的提示词注入策略

**Stage 3 AI 撰写（项目级 thread）：**
- 提示词包含**所有章节**的编写契约（Agent 需要遍历全部章节）
- 包含完整 RAG 资源列表和合规要求
- Agent 通过 MCP `list_chapters` + `read_chapter` + `write_chapter` 执行实际读写
- 编写指令（写什么、怎么写）来自预注入的提示词，不来自 MCP

**Stage 4 协作编辑（章节级 thread）：**
- 提示词仅包含**当前章节**的编写契约 + 相邻章节摘要
- 包含当前章节已有内容（供 Agent 理解和修改）
- RAG 资源限定为与该章节相关的知识库
- Agent 以辅助编辑模式运作（响应用户指令，不主动遍历）

**AI 工具箱（临时 thread）：**
- 提示词注入工具特定的指令（如"润色以下内容"、"检查合规性"）
- 包含目标章节的当前内容
- 包含适用的编写契约和合规规则
- Agent 执行单项任务后通过 MCP `write_chapter` 回写

### 7.3 后端实现：提示词构建服务

```python
# service.py 新增
async def _build_chapter_spec_prompt(
    db: AsyncSession,
    project: ReportProject,
    chapters: list[ProjectChapter],
) -> str:
    """从模板构建完整的项目级编写提示词。"""

    if not project.template_id:
        return _build_generic_prompt(project, chapters)

    from app.extensions.knowledge_factory.models import ExtractionTemplate
    template = await db.get(ExtractionTemplate, project.template_id)
    if not template:
        return _build_generic_prompt(project, chapters)

    sections_data = template.root_sections_json or {}
    section_list = sections_data.get("sections", [])
    section_map = _match_sections_to_chapters(section_list, chapters)

    prompt_parts = [
        f"你是专业的{REPORT_TYPE_NAMES.get(project.report_type, '')}报告撰写专家。",
        f"\n## 项目信息\n项目名称：{project.name}\n",
    ]

    for chapter in chapters:
        spec = section_map.get(chapter.title, {})
        prompt_parts.append(f"\n### {chapter.title}")
        if spec.get("purpose"):
            prompt_parts.append(f"- 编写目的：{spec['purpose']}")
        contract = spec.get("content_contract", {})
        if contract.get("key_elements"):
            prompt_parts.append(f"- 关键要素：{', '.join(contract['key_elements'])}")
        if contract.get("min_word_count"):
            prompt_parts.append(f"- 最低字数：{contract['min_word_count']}")
        if contract.get("style_rules"):
            prompt_parts.append(f"- 风格规则：{contract['style_rules']}")
        if contract.get("forbidden_phrases"):
            prompt_parts.append(f"- 禁用表述：{', '.join(contract['forbidden_phrases'])}")
        if spec.get("generation_hint"):
            prompt_parts.append(f"- 编写提示：{spec['generation_hint']}")
        if spec.get("example_snippet"):
            prompt_parts.append(f"- 参考样例：\n{spec['example_snippet']}")

    # RAG 资源
    rag_sources = _extract_rag_sources(section_list)
    if rag_sources:
        prompt_parts.append("\n## RAG 资源")
        for src in rag_sources:
            prompt_parts.append(f"- 知识库「{src['kb_name']}」(id: {src['kb_id']})：检索策略 {src['retrieval_strategy']}, top_k={src['top_k']}")

    # 合规规则
    rules = _extract_compliance_rules(section_list)
    if rules:
        prompt_parts.append("\n## 合规要求")
        for rule in rules:
            prompt_parts.append(f"- {rule}")

    return "\n".join(prompt_parts)


async def _build_chapter_edit_prompt(
    db: AsyncSession,
    project: ReportProject,
    chapter: ProjectChapter,
) -> str:
    """为单个章节构建协作编辑提示词。"""
    # 与 _build_chapter_spec_prompt 类似，但只包含目标章节
    # 并附加当前章节内容和相邻章节摘要
    ...
```

**修改已有 `start_writing` 和 `start_chapter_editing`：**

```python
async def start_writing(db, project_id, *, user_id=None, cookies=None, csrf_token=None):
    project = await _get_project_or_404(db, project_id)
    if project.thread_id:
        return {"thread_id": project.thread_id, "project_id": project_id}

    # 构建包含模板编写契约的提示词
    chapters = await _get_all_chapters(db, project_id)
    system_prompt = await _build_chapter_spec_prompt(db, project, chapters)

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "type": "report_project",
        "report_type": project.report_type,
        "system_prompt": system_prompt,  # 注入完整编写提示词
    }, cookies=cookies, csrf_token=csrf_token)

    project.thread_id = thread_id
    await db.flush()
    return {"thread_id": thread_id, "project_id": project_id}


async def start_chapter_editing(db, project_id, chapter_id, *, user_id=None, cookies=None, csrf_token=None):
    project = await _get_project_or_404(db, project_id)
    chapter = await _get_chapter_or_404(db, chapter_id)

    # 构建单章节编辑提示词
    edit_prompt = await _build_chapter_edit_prompt(db, project, chapter)

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "parent_thread_id": project.thread_id or "",
        "type": "chapter_edit",
        "assigned_to": str(chapter.assigned_to) if chapter.assigned_to else "",
        "system_prompt": edit_prompt,  # 注入章节级编写提示词
    }, cookies=cookies, csrf_token=csrf_token)

    chapter.status = "editing"
    await db.flush()
    return {"thread_id": thread_id, "project_id": project_id, "chapter_id": chapter_id}
```

### 7.4 MCP 工具角色调整

提示词预注入后，MCP 工具职责简化为纯数据读写：

| 工具 | 职责 | 不再负责 |
|------|------|---------|
| `read_chapter` | 读取章节内容和状态 | ~~获取编写规格~~ |
| `write_chapter` | 回写内容和更新状态 | ~~获取编写规格~~ |
| `list_chapters` | 获取章节列表和进度 | ~~获取编写规格~~ |
| `get_project` | 获取项目元数据 | 无变化 |
| `get_chapter_neighbors` | 获取相邻章节信息 | 无变化 |
| `get_chapter_spec` | **可选保留**，供 Agent 运行时查看完整规格 | 从主要信息源降级为参考工具 |

`get_chapter_spec` 保留但定位从"Agent 的主要上下文来源"降级为"运行时参考工具"。Agent 主要依靠 thread 中预注入的提示词工作。

### 7.5 已集成（不变）

- **CSRF 认证** — `_create_deerflow_thread` 已转发 cookies 和 csrf_token
- **report-write Skill** — 策略指导文件，告诉 Agent 如何按提示词撰写报告

### 7.6 审核流程

不涉及 Agent。纯人工审核流程，通过 `ApprovalWorkflow` 和 `ApprovalRecord` 模型管理。

---

## 8. 分阶段交付计划

### Phase 1: 任务管理（看板 + 仪表盘）

**范围：** 看板面板、仪表盘面板、ProjectWorkspace Tab 导航重构、章节快速状态变更、项目统计 API

**价值：** Stage 3/4 的核心操作体验从简单的列表升级为看板视图，项目经理可以看到整体进度

**估计工作量：** ~3-4 天

### Phase 2: 审核流程

**范围：** 审核面板、审核 API、审核状态机、Activity 活动日志模型、审批记录展示

**价值：** 补全 Stage 5，实现从编辑到审批的闭环

**估计工作量：** ~2-3 天

### Phase 3: 项目立项向导

**范围：** 4 步向导组件、模板预览、团队组建

**价值：** 改善首次使用体验，引导用户正确初始化项目

**估计工作量：** ~2 天

### Phase 4: AI 工具箱 + 成员工作台

**范围：** AI 辅助工具面板、AI 操作 API、成员工作台视图

**价值：** 提升编辑效率，为编辑人员提供 AI 辅助能力

**估计工作量：** ~3-4 天

---

## 9. 设计约束与决策

1. **Stage-centric 架构不变** — Tab 导航是 Stage 内部的视图切换，不影响六阶段主线流程
2. **最大复用 DeerFlow** — AI 操作（工具箱、撰写、编辑）全部走 Agent thread，不自己实现任何 AI 调用
3. **数据模型最小变更** — 仅新增 `ProjectActivity` 表，其他模型已有足够字段
4. **前端组件独立性** — 每个功能模块（看板、仪表盘、审核等）都是独立面板，可独立开发和测试
5. **渐进式交付** — 4 个 Phase 可独立上线，每个 Phase 都有独立价值
6. **权限沿用现有体系** — 使用 `CurrentUserWithAccess` + `require_permission("system:access")`，不做新的权限系统
7. **Polling 而非 WebSocket** — 进度更新使用前端轮询（`useQuery` refetchInterval），不用 WebSocket
8. **导出格式** — Stage 6 定稿输出支持 Word (.docx) 和 PDF，使用 Python `python-docx` 库服务端渲染
