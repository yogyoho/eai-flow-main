# 模板管理重构设计

**日期**: 2026-06-02
**状态**: Approved
**前置**: 2026-06-01-workflow-project-collaboration-system-refinement-design.md（§3.6 模板管理）
**问题**: 当前 `/admin/templates` 页面"新建模板"和"编辑模板"都指向 `/projects/new`（项目创建向导），管理员无法编辑工作流 DAG、组织绑定和角色槽位。

## 1. 方案选择

**选定方案 B：TemplateEditor 页面包装器**

- WorkflowEditor 做最小改动（接受 `initialGraphJson` + `onSave` 两个新 prop）
- 模板特有逻辑（审批、可见性、发布）隔离在 admin 页面
- 后端已有 CRUD 基础，在此基础上扩展审批和可见性字段

## 2. WorkflowEditor 最小重构

### 2.1 Props 扩展

```typescript
interface WorkflowEditorProps {
  // 初始化数据（新增）
  initialGraphJson?: WorkflowGraph;
  initialName?: string;
  // 保存回调（新增）——外部控制保存行为
  onSave?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  onSaveTemplate?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  // 组织绑定回调（新增）——模板编辑模式下透传到 PhaseConfigPanel
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
  orgBindings?: Record<string, { deptCode?: string }>;
  // 原有（保持向后兼容）
  projectId?: string;
}
```

### 2.2 行为变化

- 传入 `initialGraphJson` → `useWorkflowDAG` 用它初始化（而非空白）
- 传入 `onSave` → 工具栏"保存"按钮调用它（而非 `workflowApi.create`）
- 不传 `onSave` → 保持原有行为（向后兼容项目内使用）
- `onOrgBindingChange` 透传给 `PhaseConfigPanel`

### 2.3 useWorkflowDAG hook 改造

- 新增 `loadGraphJson(json: WorkflowGraph)` 方法
- `WorkflowEditor` 在 `useEffect` 中检测 `initialGraphJson` 变化并加载

### 2.4 向后兼容

- `projectId` 仍作为可选 prop 保留，项目内使用不受影响
- 不传新 props 时行为与现在完全一致

## 3. 模板编辑页面 TemplateEditorPage

### 3.1 路由

- `/admin/templates/new` — 新建模板
- `/admin/templates/[templateId]` — 编辑已有模板

### 3.2 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│ 顶部操作栏 (shrink-0)                                        │
│ [← 返回列表]  模板名称输入  报告类型选择  |  [校验] [保存] [发布/提交审批] │
├─────────────────────────────────────────────────────────────┤
│ WorkflowEditor (flex-1, 填满剩余空间)                         │
│ ┌────────┬──────────────────────┬────────────┐              │
│ │ 节点面板 │   DAG 画布             │ 配置面板     │              │
│ │        │                      │ + 组织绑定   │              │
│ │        │                      │ + 角色槽位    │              │
│ └────────┴──────────────────────┴────────────┘              │
├─────────────────────────────────────────────────────────────┤
│ 底部面板 (可折叠, shrink-0)                                    │
│ 描述: [____________]    可见部门: [多选下拉]   状态: 草稿        │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 数据流

```
加载阶段:
  路由参数 templateId → workflowApi.get(templateId)
    → 解析 name, reportType, graphJson, orgBindings
    → 传入 WorkflowEditor 的 initialGraphJson

编辑阶段:
  WorkflowEditor 内部操作 DAG
    → onSave 回调将最新 graphJson + name 传回 TemplateEditorPage
    → TemplateEditorPage 调用 workflowApi.update() 或 workflowApi.create()

发布阶段:
  超级管理员 → 直接调用 publishTemplate → 跳回列表
  部门管理员 → 创建审批请求 → 状态变更为 pending_approval
```

### 3.4 新建入口

- 管理员点"新建模板" → 导航到 `/admin/templates/new`
- 第一次保存时调用 `workflowApi.create()`，获得 ID 后更新 URL 为 `/admin/templates/[id]`

## 4. 后端改造

### 4.1 数据模型扩展

WorkflowDefinition 新增字段：

```python
description: Mapped[str | None] = mapped_column(Text, nullable=True)
template_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
# draft | pending_approval | published | rejected
visible_dept_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
# ["uuid1", "uuid2"] — 空/null 表示全部可见
version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
```

### 4.2 审批记录表

```python
class TemplateApproval(Base):
    __tablename__ = "template_approvals"

    id: Mapped[uuid.UUID] PK
    template_id: Mapped[uuid.UUID] FK → workflow_definitions.id (CASCADE)
    requester_id: Mapped[uuid.UUID] FK → users.id
    reviewer_id: Mapped[uuid.UUID | None] FK → users.id
    status: Mapped[str]  # pending | approved | rejected
    comment: Mapped[str | None]
    created_at: Mapped[datetime]
    reviewed_at: Mapped[datetime | None]
```

### 4.3 Schema 扩展

WorkflowDefinitionCreate/Update/Out 新增：`description`, `template_status`, `visible_dept_ids`, `version`。

新增 schemas：
- `TemplateApprovalOut` — 审批记录响应
- `TemplateApprovalAction` — 审批操作请求 `{action, comment}`
- `TemplateListItem` — 增强列表项（含 `template_status`, `has_pending_approval`）

### 4.4 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/definitions/{id}/submit-approval` | 提交审批（部门管理员） |
| POST | `/definitions/{id}/review-approval` | 审批操作（超管：通过/拒绝） |
| GET | `/definitions/{id}/approvals` | 获取审批记录列表 |
| POST | `/definitions/{id}/withdraw-approval` | 撤回审批 |

### 4.5 权限

- 创建/编辑模板：`template:manage`（超管 + 部门管理员）
- 提交审批：`template:manage` + 非超管
- 审批操作：`template:publish`（仅超管）
- 数据库迁移：所有新字段有默认值，现有记录自动为 `draft`

## 5. 模板列表页重写

### 5.1 导航修正

| 当前 | 改造后 |
|------|--------|
| "新建模板" → `/projects/new` | "新建模板" → `/admin/templates/new` |
| 卡片操作 → `/projects/new?workflowId=` | 卡片操作 → 编辑 `/admin/templates/[id]` |

### 5.2 状态增强

区分 `draft` / `pending_approval` / `published` / `rejected` 四种状态，每种状态显示不同操作按钮：

| 状态 | 操作 |
|------|------|
| draft | 编辑、发布（超管）/ 提交审批（部门管理员）、删除 |
| pending_approval | 编辑（只读 DAG）、撤回审批、查看审批记录 |
| published | 编辑、撤回发布、删除 |
| rejected | 编辑、重新提交审批、查看驳回原因、删除 |

### 5.3 模板卡片信息

显示：名称、报告类型、描述摘要、状态标签、可见部门标签、创建日期。

## 6. 审批 UI 组件

### 6.1 ApprovalDialog

超管审批对话框，显示模板信息 + 审批历史 + 意见输入 + 通过/拒绝按钮。

### 6.2 ApprovalHistoryPanel

审批记录时间线，显示每步操作：提交、通过、拒绝、撤回。

### 6.3 SubmitApprovalDialog

部门管理员提交审批确认框，含可选备注输入。

### 6.4 状态机

```
draft ──[超管]──→ published          draft ──[部门管理员]──→ pending_approval
  ↑                   ↑                                        │
  │                   │                               [撤回] ←─┘
  │                   │                                        │
  │                   │              [超管审批通过] ──────────────┘
  │                   │                                        │
  │                   │              [超管审批拒绝] → rejected
  │                   │                                │
  │                   │              [重新提交] → pending_approval
  │                   │
 published ──[撤回发布]──→ draft
```

## 7. 实施步骤

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 1 | 后端数据模型 + 迁移 | `models.py`, `schemas.py`, `migration.py` |
| 2 | 后端审批 API | `routers.py`, `service.py` |
| 3 | 后端测试 | `tests/test_workflow_template.py` |
| 4 | 前端类型 + API | `types.ts`, `api.ts` |
| 5 | WorkflowEditor 重构 | `WorkflowEditor.tsx`, `hooks/useWorkflowDAG.ts` |
| 6 | 模板列表页重写 | `admin/templates/page.tsx` |
| 7 | 模板编辑页 | `admin/templates/[templateId]/page.tsx`, `admin/templates/new/page.tsx` |
| 8 | 审批 UI | `admin/templates/components/` |
| 9 | 集成验证 | 手动测试完整流程 |

## 8. 文件清单

### 后端修改

- `backend/app/extensions/workflow/models.py` — 新增字段 + TemplateApproval 表
- `backend/app/extensions/workflow/schemas.py` — 新增/扩展 schemas
- `backend/app/extensions/workflow/routers.py` — 新增 4 个审批端点
- `backend/app/extensions/workflow/service.py` — 审批服务方法
- `backend/app/extensions/workflow/migration.py` — 数据库迁移（新增）
- `backend/tests/test_workflow_template.py` — 测试（新增）

### 前端修改

- `frontend/src/extensions/workflow/types.ts` — 新增类型
- `frontend/src/extensions/workflow/api.ts` — 新增 API 方法
- `frontend/src/extensions/workflow/WorkflowEditor.tsx` — Props 扩展
- `frontend/src/extensions/workflow/hooks/useWorkflowDAG.ts` — loadGraphJson 方法
- `frontend/src/app/admin/templates/page.tsx` — 列表页重写
- `frontend/src/app/admin/templates/[templateId]/page.tsx` — 编辑页（新增）
- `frontend/src/app/admin/templates/new/page.tsx` — 新建页（新增）
- `frontend/src/app/admin/templates/components/ApprovalDialog.tsx` — 审批对话框（新增）
- `frontend/src/app/admin/templates/components/ApprovalHistoryPanel.tsx` — 审批记录（新增）
- `frontend/src/app/admin/templates/components/SubmitApprovalDialog.tsx` — 提交确认（新增）
