# 项目管理模块：RBAC 权限控制 + 成员工作台 + 审核流程设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目管理模块实现全链路权限控制（RBAC）、角色驱动的成员工作台、以及灵活的审核流程，覆盖 Stage 1-5 的角色体验差异。同时设计统一的权限架构，使其他模块（知识工厂、法规库、文档管理等）未来可复用。

**Architecture:** 在现有系统 RBAC 基础上扩展两层权限模型（系统级 + 资源级）。新建 `PermissionService` 统一权限检查入口。前端通过 `useProjectPermissions()` Hook 消费权限列表，驱动 Tab 可见性和操作按钮显隐。

**Tech Stack:** FastAPI Depends + SQLAlchemy async（后端），React Hook + TanStack Query（前端）

**Scope:** 本次实现覆盖项目管理的 5 种角色权限、成员工作台视图、审核流程全链路。其他模块的权限升级作为后续 Phase。

---

## 1. 角色定义（5 种）

| 角色 | 代码 | 定位 |
|------|------|------|
| 经理 | `manager` | 项目管理者 — 全局视角，管理成员、推进阶段、配置审核 |
| 编辑 | `editor` | 内容执行者 — 编辑章节、使用 AI 工具、参与大纲编辑 |
| 撰写人 | `writer` | 内容生产者 — 撰写被分配的章节、使用 AI 工具 |
| 审核人 | `reviewer` | 质量把控者 — 查看章节、执行技术审核 |
| 批准人 | `approver` | 最终审批者 — 审阅并做出通过/退回决定 |

**规则：**
- 项目创建者自动成为 `manager`（在 `service.py:create_project()` 中创建 ProjectMember 记录）
- 一个用户在一个项目中只能有一个角色（由 `ProjectMember` 表的唯一约束 `(project_id, user_id)` 保证）
- 系统管理员（superadmin）自动拥有 `manager` 级权限（在 `get_user_permissions()` 中判断 `is_admin`）

---

## 2. 两层权限模型

### 2.1 系统级权限（已有，不变）

存储在 `Role.permissions[]` 数组中，使用 `require_permission("kb:read")` 检查。

已有权限：`kb:read/create/update/delete/upload`、`user:read/create/update/delete`、`role:read/create/update/delete`、`threads:read/write`、`runs:create/read` 等。

新增系统级权限（控制用户能否访问项目管理功能）：

| 权限 | 说明 |
|------|------|
| `project:create` | 创建项目 |
| `project:list` | 查看项目列表 |
| `project:read` | 查看项目详情 |

### 2.2 资源级权限（新增）

由项目成员角色 + `PERMISSION_MATRIX` 推导，使用 `require_resource_permission(project_id, action)` 检查。

**权限矩阵：**

```python
PERMISSION_MATRIX: dict[str, list[bool]] = {
    #                     manager  editor  writer  reviewer  approver
    #                     ------   ------  ------  --------  --------
    "project:edit":       [True,   False,  False,  False,    False],
    "project:delete":     [True,   False,  False,  False,    False],
    "project:advance":    [True,   False,  False,  False,    False],

    "member:add":         [True,   False,  False,  False,    False],
    "member:remove":      [True,   False,  False,  False,    False],
    "member:list":        [True,   True,   True,   False,    False],

    "outline:edit":       [True,   True,   False,  False,    False],
    "outline:view":       [True,   True,   True,   True,     True],

    "chapter:write_own":  [True,   True,   True,   False,    False],
    "chapter:write_any":  [True,   False,  False,  False,    False],
    "chapter:view_all":   [True,   True,   True,   True,     True],
    "chapter:assign":     [True,   False,  False,  False,    False],
    "chapter:status":     [True,   False,  False,  False,    False],

    "ai:start_writing":   [True,   False,  False,  False,    False],
    "ai:start_editing":   [True,   True,   True,   False,    False],
    "ai:toolbox":         [True,   True,   True,   False,    False],

    "approval:submit":    [True,   False,  False,  False,    False],
    "approval:review":    [True,   False,  False,  True,     False],
    "approval:approve":   [True,   False,  False,  False,    True],
    "approval:view":      [True,   True,   True,   True,     True],

    "export:generate":    [True,   False,  False,  False,    False],
    "export:view":        [True,   True,   True,   True,     True],
}

ROLE_ORDER = ["manager", "editor", "writer", "reviewer", "approver"]
```

---

## 3. 后端实现

### 3.1 新建 `permissions.py`

```python
# backend/app/extensions/project/permissions.py

from uuid import UUID
from fastapi import HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import CurrentUser, require_permission
from app.extensions.models import ProjectMember, User

ROLE_ORDER = ["manager", "editor", "writer", "reviewer", "approver"]

PERMISSION_MATRIX: dict[str, list[bool]] = { ... }  # 如上


def check_permission(role: str, action: str) -> bool:
    allowed = PERMISSION_MATRIX.get(action)
    if not allowed:
        return False
    idx = ROLE_ORDER.index(role) if role in ROLE_ORDER else -1
    return idx >= 0 and allowed[idx]


async def get_project_role(
    db: AsyncSession, project_id: UUID, user_id: UUID
) -> str | None:
    result = await db.execute(
        select(ProjectMember.role)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_user_permissions(
    db: AsyncSession, project_id: UUID, user_id: UUID, is_admin: bool = False
) -> tuple[str | None, list[str]]:
    role = "manager" if is_admin else await get_project_role(db, project_id, user_id)
    if not role:
        return None, []
    permissions = [action for action in PERMISSION_MATRIX if check_permission(role, action)]
    return role, permissions


def require_resource_permission(resource_type: str, action: str):
    """FastAPI 依赖：检查当前用户在指定资源中的权限"""
    async def _check(
        resource_id: UUID,
        user: CurrentUser = Depends(require_permission("system:access")),
        db: AsyncSession = Depends(get_db),
    ):
        role = "manager" if user.is_admin else await get_project_role(db, resource_id, user.id)
        if not role:
            raise HTTPException(403, "不是项目成员")
        if not check_permission(role, action):
            raise HTTPException(403, f"角色 '{role}' 无权执行 '{action}'")
        return role
    return _check
```

### 3.2 新增 API 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| `GET` | `/projects/{id}/my-permissions` | `system:access` | 返回当前用户在项目中的角色和权限列表 |
| `POST` | `/projects/{id}/submit-approval` | `approval:submit` | 经理提交审核，配置审核链 |
| `POST` | `/projects/{id}/approval-action` | `approval:review` 或 `approval:approve` + 指定人验证 | 审核人/批准人执行审批 |
| `GET` | `/projects/{id}/approval-status` | `approval:view` | 获取审核流程状态 |
| `GET` | `/projects/{id}/approval-records` | `approval:view` | 获取审批记录列表 |

**`my-permissions` 响应格式：**

```python
class MyPermissionsResponse(BaseModel):
    role: str | None
    permissions: list[str]
    default_tab: str  # 根据 role 推导
```

### 3.3 现有端点权限升级

每个现有端点添加 `require_resource_permission` 依赖：

| 端点 | 所需权限 |
|------|---------|
| `PATCH /projects/{id}` | `project:edit` |
| `DELETE /projects/{id}` | `project:delete` |
| `PUT /projects/{id}/outline` | `outline:edit` |
| `POST /projects/{id}/confirm-outline` | `project:advance` |
| `POST /projects/{id}/members` | `member:add` |
| `DELETE /projects/{id}/members/{uid}` | `member:remove` |
| `PATCH /projects/{id}/chapters/{ch_id}` | `chapter:write_own` + 所有权验证 |
| `POST /projects/{id}/start-writing` | `ai:start_writing` |
| `POST /projects/{id}/chapters/{ch_id}/start-editing` | `ai:start_editing` + 章节分配验证 |

### 3.4 审核流程 Service

```python
# service.py 新增

async def submit_approval(
    db: AsyncSession, project_id: UUID, manager_id: UUID,
    workflow_steps: list[dict],  # [{"step_order": 1, "step_name": "...", "reviewer_id": "uuid"}]
):
    """经理提交审核，创建审核步骤链"""
    project = await _get_project_or_404(db, project_id)
    project.stage = 5
    for step in workflow_steps:
        workflow = ApprovalWorkflow(
            project_id=project_id,
            step_order=step["step_order"],
            step_name=step["step_name"],
            reviewer_id=step["reviewer_id"],
            status="pending",
        )
        db.add(workflow)
    await db.flush()


async def approval_action(
    db: AsyncSession, project_id: UUID, workflow_id: UUID,
    reviewer_id: UUID, action: str, comment: str | None,
):
    """审核人/批准人执行审批动作"""
    workflow = await db.get(ApprovalWorkflow, workflow_id)
    # 验证：当前步骤的指定人 === reviewer_id
    if workflow.reviewer_id != reviewer_id:
        raise HTTPException(403, "您不是此步骤的指定审核人")
    if workflow.status != "pending":
        raise HTTPException(400, "此步骤已处理")

    # 记录审批动作
    record = ApprovalRecord(
        workflow_id=workflow_id, project_id=project_id,
        reviewer_id=reviewer_id, action=action, comment=comment,
    )
    db.add(record)

    if action == "approved":
        workflow.status = "approved"
        # 检查是否有下一步
        next_step = await _get_next_pending_step(db, project_id, workflow.step_order)
        if next_step:
            pass  # 下一步自动变为 pending
        else:
            # 全部通过 → Stage 6
            project = await _get_project_or_404(db, project_id)
            project.stage = 6
    elif action == "rejected":
        workflow.status = "rejected"
        # 退回 → Stage 4
        project = await _get_project_or_404(db, project_id)
        project.stage = 4

    await db.flush()
```

---

## 4. 前端实现

### 4.1 `useProjectPermissions` Hook

```typescript
// frontend/src/extensions/project/hooks/useProjectPermissions.ts

interface ProjectMembership {
  role: string | null;
  permissions: string[];
  defaultTab: string;
}

function useProjectPermissions(projectId: string) {
  const { data, isLoading } = useQuery({
    queryKey: ["project-permissions", projectId],
    queryFn: () => projectApi.getMyPermissions(projectId),
    staleTime: 5 * 60 * 1000,
  });

  const can = (action: string) => data?.permissions.includes(action) ?? false;
  const role = data?.role ?? null;
  const defaultTab = data?.defaultTab ?? "dashboard";

  return { role, permissions: data?.permissions ?? [], can, defaultTab, isLoading };
}
```

### 4.2 Tab 注册表

```typescript
// frontend/src/extensions/project/tabRegistry.ts

interface TabConfig {
  id: string;
  label: string;
  icon: string;
  stages: number[];           // 在哪些 Stage 可见
  minPermission: string | null; // 最低权限要求
  defaultForRoles: string[];  // 哪些角色默认进入此 Tab
}

const TAB_REGISTRY: TabConfig[] = [
  { id: "my-workspace", label: "我的工作台", icon: "Target",   stages: [3, 4, 5], minPermission: null,            defaultForRoles: ["editor", "writer"] },
  { id: "dashboard",    label: "仪表盘",     icon: "BarChart3", stages: [2,3,4,5,6], minPermission: null,            defaultForRoles: ["manager"] },
  { id: "kanban",       label: "看板",       icon: "Kanban",    stages: [3, 4],     minPermission: "chapter:view_all", defaultForRoles: ["reviewer", "approver"] },
  { id: "outline",      label: "大纲",       icon: "FileText",  stages: [2, 3, 4],  minPermission: "outline:view",  defaultForRoles: [] },
  { id: "members",      label: "成员",       icon: "Users",     stages: [2,3,4,5,6], minPermission: "member:list",   defaultForRoles: [] },
  { id: "approval",     label: "审核",       icon: "CheckCircle",stages: [5],        minPermission: "approval:view", defaultForRoles: [] },
  { id: "ai-tools",     label: "AI工具",     icon: "Bot",       stages: [3, 4],     minPermission: "ai:toolbox",    defaultForRoles: [] },
];
```

### 4.3 ProjectWorkspace 重构

```typescript
// ProjectWorkspace.tsx — 核心重构逻辑

function ProjectWorkspace({ projectId, stage }: Props) {
  const { role, can, defaultTab, permissions } = useProjectPermissions(projectId);

  // 根据权限和 Stage 过滤可见 Tab
  const visibleTabs = TAB_REGISTRY.filter(tab => {
    if (!tab.stages.includes(stage)) return false;
    if (tab.minPermission && !can(tab.minPermission)) return false;
    return true;
  });

  // 确定默认激活 Tab
  const [activeTab, setActiveTab] = useState(() => {
    return defaultTab && visibleTabs.find(t => t.id === defaultTab)
      ? defaultTab
      : visibleTabs[0]?.id;
  });

  return (
    <div>
      <TabBar tabs={visibleTabs} active={activeTab} onChange={setActiveTab} />
      {activeTab === "my-workspace" && <MemberWorkspace can={can} role={role} />}
      {activeTab === "dashboard"    && <DashboardTab can={can} />}
      {activeTab === "kanban"       && <KanbanBoard can={can} />}
      {activeTab === "outline"      && <OutlineTab readOnly={!can("outline:edit")} />}
      {activeTab === "members"      && <MembersTab canManage={can("member:add")} />}
      {activeTab === "approval"     && <ApprovalTab can={can} role={role} />}
      {activeTab === "ai-tools"     && <AiToolsTab can={can} />}
    </div>
  );
}
```

### 4.4 成员工作台组件

```typescript
// MemberWorkspace.tsx — 个人视角

function MemberWorkspace({ can, role }: { can: (a: string) => boolean; role: string }) {
  const { data: tasks } = useQuery({
    queryKey: ["my-tasks", projectId],
    queryFn: () => projectApi.getMyTasks(projectId),
  });

  return (
    <div>
      {/* 个人统计卡片 */}
      <StatsCards tasks={tasks} />

      {/* 按状态分组的章节列表 */}
      <TaskGroup title="待处理" status="pending" tasks={tasks?.pending}>
        {(chapter) => (
          <TaskCard chapter={chapter}>
            {can("ai:start_editing") && <Button>编辑</Button>}
            {can("ai:toolbox") && <Button>AI辅助</Button>}
          </TaskCard>
        )}
      </TaskGroup>
      <TaskGroup title="进行中" status="in_progress" tasks={tasks?.in_progress} />
      <TaskGroup title="已完成" status="completed" tasks={tasks?.completed} />
    </div>
  );
}
```

---

## 5. 审核流程 UI

### 5.1 经理提交审核

经理点击「提交审核」后弹出对话框：
1. 从项目成员中选择审核人和批准人
2. 拖拽排列审核步骤顺序
3. 确认后创建审核步骤链，项目进入 Stage 5

### 5.2 审核人/批准人操作

审核人在「审核」Tab 中看到：
- 当前审核步骤（Step N/Total）
- 待审核章节列表
- 每个章节的「通过」和「退回」按钮（仅被指定的审核人可见操作按钮）
- 审核意见输入框

### 5.3 审核状态可视化

所有成员可看到审核进度条（Step 1 ✅ → Step 2 🔄 → Step 3 ⏳），但不能操作。

---

## 6. 数据库变更

### 6.1 现有模型（无变更）

- `ProjectMember` — 已有 `role` 字段
- `ApprovalWorkflow` — 已有 `step_order`, `step_name`, `reviewer_id`, `status`
- `ApprovalRecord` — 已有 `workflow_id`, `action`, `reviewer_id`, `comment`

### 6.2 现有模型字段扩展

**ApprovalWorkflow** — 需新增 `reviewer_id` 字段：

```python
# 现有字段：role_required（角色要求，保留但不再作为主要匹配条件）
# 新增字段：
reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
)
```

**原因：** 审核流程由经理灵活指定具体审核人（不只是角色），需要记录具体哪个用户负责哪个步骤。`role_required` 保留作为参考标签。

### 6.3 Alembic 迁移

```python
def upgrade():
    op.add_column("approval_workflows",
        sa.Column("reviewer_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True))
```

---

## 7. 权限统一入口 — 未来扩展

```python
# backend/app/extensions/auth/permissions.py — 统一权限服务（未来 Phase）

class PermissionService:
    @staticmethod
    async def can(
        user_id: UUID,
        action: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        db: AsyncSession = ...,
    ) -> bool:
        # 1. 查系统级权限
        user = await db.get(User, user_id)
        role = await db.get(Role, user.role_id)
        if "*" in role.permissions or action in role.permissions:
            return True

        # 2. 查资源级权限（项目、知识库等）
        if resource_type and resource_id:
            resource_role = await _get_resource_member_role(db, resource_type, resource_id, user_id)
            if resource_role:
                return check_resource_permission(resource_role, action)

        return False
```

**扩展路径：**
- Phase 1（本次）：项目管理模块接入资源级权限
- Phase 2：知识工厂、法规库、文档管理升级为细粒度系统级权限
- Phase 3：知识库、文件夹增加资源级权限

---

## 8. 分阶段交付

### Phase 1A：权限基础设施（~2 天）

- [ ] 新建 `backend/app/extensions/project/permissions.py` — 权限矩阵 + 检查函数
- [ ] 新增 `GET /projects/{id}/my-permissions` 端点
- [ ] 现有端点逐个添加 `require_resource_permission` 依赖
- [ ] 前端 `useProjectPermissions` Hook
- [ ] 前端 `tabRegistry.ts` — Tab 配置注册表

### Phase 1B：成员工作台（~2 天）

- [ ] `MemberWorkspace.tsx` — 个人工作台视图
- [ ] `GET /projects/{id}/my-tasks` API
- [ ] `ProjectWorkspace.tsx` 重构 — 角色默认页 + Tab 权限过滤
- [ ] 各 Tab 组件添加 `can()` 权限控制（按钮显隐）

### Phase 2：审核流程（~2-3 天）

- [ ] `submit_approval` / `approval_action` service 函数
- [ ] 审核 API 端点
- [ ] 经理审核配置对话框
- [ ] 审核人操作界面
- [ ] 审核状态可视化（进度条）
- [ ] 退回/通过逻辑 + Stage 联动

---

## 9. 设计决策

1. **集中权限矩阵而非装饰器分散控制** — `PERMISSION_MATRIX` 一目了然，新增角色/操作只改矩阵
2. **两层权限而非一层** — 系统级控制"能否用项目管理"，资源级控制"在这个项目里能做什么"
3. **API 返回权限列表而非前端硬编码** — 前端通过 `can()` 函数消费，与后端保持一致
4. **经理灵活指定审核链** — 审核步骤由经理从成员中选择，不硬编码角色审核顺序
5. **双重验证** — 审核操作不只验证角色（reviewer/approver），还验证是否为该步骤的指定人
6. **去委托方角色** — 简化为 5 种角色，减少角色混淆
7. **最小数据库变更** — 仅新增 `ApprovalWorkflow.reviewer_id` 字段，权限基于 `ProjectMember.role` + 内存矩阵推导
8. **渐进式实现** — Phase 1A/1B/2 可独立上线，每步都有独立价值
