# 四模块业务流程重构设计

> 日期: 2026-06-13
> 分支: merge-2.0-rc
> 状态: 待实施
> 范围: 项目管理 · 流程编排 · AI 写作 · 文档空间

## 1. 动机

当前四模块存在 15 个业务逻辑缺口，根因是**同一概念在多个系统中重复定义**：

- 两套审核系统（PhaseReview + ApprovalWorkflow）各自演进，互不感知
- 三套权限体系（permissions.py / project_permissions.py / schemas.py）角色命名互不兼容
- 项目状态和工作流状态各自跟踪，无协调机制
- 审核门控只等待第一个审核员，其余意见丢失
- AI 写作仅支持单章触发，无法适配不同报告类型的粒度需求

本次重构采用**领域驱动设计**，将四模块拆分为四个限界上下文，通过 Temporal 编排层松耦合通信，从根本上消除并行系统。

## 2. 总体架构

### 2.1 四个限界上下文

```
                    ┌──────────────────────────────────────────────────┐
                    │           Temporal Orchestration Layer           │
                    │          (拓扑推进 · 超时 · 补偿 · 信号)          │
                    └─────┬──────────────┬──────────────┬──────────────┘
                          │              │              │
                    ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼─────┐
                    │  Writing  │ │   Review    │ │ DocSpace  │
                    │  Context  │ │   Context   │ │  Context  │
                    ├───────────┤ ├─────────────┤ ├───────────┤
                    │ 章节管理   │ │ 审核分配     │ │ 文档存储   │
                    │ AI 生成    │ │ 审核判定     │ │ 协作编辑   │
                    │ 溯源追踪   │ │ 驳回回滚     │ │ 版本管理   │
                    │ 成员确认   │ │ 审核聚合     │ │ 输出导出   │
                    └─────┬─────┘ └──────┬──────┘ └─────┬─────┘
                          │              │              │
                          └──────────────┼──────────────┘
                                         │
                         ┌───────────────▼────────────────┐
                         │       Shared Kernel            │
                         │  ProjectRole · Chapter ·       │
                         │  Project · 统一权限模型         │
                         └────────────────────────────────┘
```

### 2.2 上下文职责边界

| 上下文 | 拥有的聚合根 | 不负责的事 |
|--------|------------|-----------|
| **Writing Context** | `Chapter`, `ContentSource`, `WriteSession` | 不负责审核、不负责文档导出 |
| **Review Context** | `ReviewAssignment`, `ReviewJudgment` | 不负责章节编辑、不负责审批流 |
| **DocSpace Context** | `AIDocument`, `CollabSession`, `DocumentVersion` | 不负责章节状态、不负责审核 |
| **Orchestration（Temporal）** | DAG 拓扑、信号路由、超时/补偿 | 不持有业务数据，只转发事件 |

### 2.3 通信：事件 + 信号

```
Writing ──"PhaseCompleted"──▶ Orchestration ──"AdvancePhase"──▶ Review
Review  ──"ReviewRejected"──▶ Orchestration ──"RollbackPhase"──▶ Writing
Review  ──"ReviewApproved"──▶ Orchestration ──"CompletePhase"──▶ DocSpace
DocSpace──"DocumentFinalized"─▶ Orchestration ──"MarkCompleted"──▶ Project
```

- **Temporal 只做编排**：接收事件 → 查 DAG 拓扑 → 发信号给下一个上下文
- **上下文之间不直接调用**：必须通过 Temporal 路由，确保每次状态推进都经过 DAG 规则校验
- **共享内核**：`ProjectRole`、`Chapter`、`Project` 基础模型所有上下文可见，但只有拥有者上下文可以修改

### 2.4 与现状的核心差异

| 现状 | 新设计 |
|------|--------|
| `PhaseReview` 和 `ApprovalWorkflow` 两套审核 | 只有 `ReviewAssignment` + `ReviewJudgment`，挂在 review 节点下 |
| 权限三处定义，角色名互不兼容 | 统一 `ProjectRole` 枚举，权限映射存 DB |
| 项目状态和工作流状态各自演进 | 项目状态是工作流节点推进的投影 |
| AI 写作只支持单章 | 支持按阶段批量 + 按章节单独，依赖从模板树自动推导 |
| 审核门控只等第一个 | 四种门控策略（全员/任一/多数/加权），等全员提交才推进 |

## 3. Orchestration 层（可扩展注册表）

### 3.1 核心抽象：IWorkflowNodeExecutor

```python
class IWorkflowNodeExecutor(Protocol):
    """任何业务模块挂载到 Workflow 的契约"""

    node_type: str                   # 全局唯一的类型标识
    display_name: str                # 中文显示名
    display_category: str            # 分组
    config_schema: dict              # JSON Schema — 前端动态渲染配置面板
    signals: list[SignalDef]         # 声明的监听信号

    async def on_enter(self, node: DAGNode, ctx: WorkflowContext) -> NodeResult:
        """节点被激活时调用"""
        ...

    async def on_signal(self, node: DAGNode, signal: Signal, ctx: WorkflowContext) -> SignalResult:
        """收到信号时调用"""
        ...

    async def validate(self, config: dict) -> list[str]:
        """校验节点配置，返回错误列表"""
        ...
```

### 3.2 注册与发现

```python
# 报告模块内置注册
@register_node
class AIWritingExecutor:
    node_type = "report:ai_generate"
    display_name = "AI 初稿生成"
    ...

@register_node
class ReviewExecutor:
    node_type = "report:review"
    display_name = "阶段审核"
    ...

# 未来模块挂载
@register_node
class BiddingReviewExecutor:
    node_type = "purchase:bidding_review"
    display_name = "招标评审"
    ...
```

### 3.3 START 节点（显式，必须且只能 1 个）

```json
{
  "id": "start",
  "type": "system:start",
  "data": {
    "label": "项目启动",
    "entry_conditions": {
      "template_bound": true,
      "team_size_min": 2,
      "required_roles": ["owner", "writer"]
    },
    "trigger": "manual",
    "initial_context": {
      "inherit_from": "project"
    }
  }
}
```

- 每个 DAG 必须且只能有 1 个 START 节点
- 入度 = 0，出度 ≥ 1
- `entry_conditions` 不满足时返回明确错误

### 3.4 END 节点（可选，出度 = 0 的节点为隐式终点）

```json
{
  "id": "finalize",
  "type": "system:end",
  "data": {
    "label": "项目完成",
    "completion_actions": {
      "set_project_status": "completed",
      "merge_documents": true,
      "notify_roles": ["owner", "manager"],
      "archive_to_docspace": true
    }
  }
}
```

- 出度 = 0 的节点自动视为终点
- 显式 END 可附加 `completion_actions`
- workflow 在所有活动路径到达终点后结束

### 3.5 节点状态机

```
             ┌──────────┐
      ┌─────►│  WAITING │◄──────────┐
      │      └────┬─────┘           │
      │           │ on_enter()      │ signal received
      │           ▼                 │
      │      ┌──────────┐           │
      │      │  RUNNING │───────────┘
      │      └────┬─────┘
      │           │ on_enter() returns
      │      ┌────▼─────┐
      │      │ COMPLETED│
      │      └──────────┘
      │
      │      ┌──────────┐
      └──────│  FAILED  │  (超时/异常，支持重试)
             └──────────┘
```

### 3.6 信号系统

每个节点通过 `signals` 属性声明可接收的信号：

- `PhaseCompleted` — Writing → Orchestration
- `ReviewRejected` — Orchestration → Writing（回滚）
- `ReviewApproved` — Orchestration → DocSpace
- `workflow:cancel` — 系统信号，取消当前节点
- `workflow:timeout` — 系统信号，节点超时
- `workflow:retry` — 系统信号，重试失败节点

## 4. Writing Context（章节 + AI 写作）

### 4.1 章节状态机

```
                        ┌──────────┐
                  ┌────►│  PENDING │◄────────────── 驳回回滚
                  │     └────┬─────┘
                  │          │ AI 生成触发
                  │          ▼
                  │     ┌──────────┐
                  │     │  DRAFT   │  AI 初稿完成，等待人工
                  │     └────┬─────┘
                  │          │ 组员确认 (mark_complete)
                  │          ▼
                  │     ┌──────────┐
                  │     │COMPLETED │
                  │     └────┬─────┘
                  │          │ 审核通过
                  │          ▼
                  │     ┌──────────┐
                  │     │ APPROVED │
                  │     └──────────┘
                  │
                  │     ┌──────────┐
                  └─────│  ERROR   │  AI 生成失败
                        └──────────┘
                               │ 重试 → PENDING
```

### 4.2 智能 AI 生成策略

由报告类型决定生成粒度，章节依赖关系统一从模板树自动推导。

**依赖推导规则**：
1. 父 → 子：父章节必须在子章节之前生成
2. 同级：按 sort_order 顺序，第 N 章依赖第 N-1 章
3. 不同父下的同级：无依赖，可并行

**策略选择**：

| 报告类型 | 策略 | 行为 |
|---------|------|------|
| 简单报告（模板 `word_count_target` 累计 < 10 万字） | 阶段批量 | phase 内所有无依赖章节并行生成 |
| 复杂报告（模板 `word_count_target` 累计 ≥ 10 万字） | 按章节 | 按依赖图拓扑顺序逐个生成 |
| 用户手动指定 | 覆盖自动 | DAG 节点上设 `generation_mode: "batch" \| "sequential"` |

### 4.3 Writer 分配

三优先级分配，按当前工作量最少选择：

1. `phase_duties` 中 `role="writer"` 的成员
2. 全局角色为 `writer` 的成员
3. 全局角色为 `owner` 的成员（兜底）

工作量 = 该成员在项目中 `assigned_to` 的章节数。

### 4.4 溯源追踪

三层溯源：

1. **Prompt**：要求 JSON 格式溯源块
2. **解析**：优先 JSON，兜底正则
3. **校验**：AI 写完后的 on_generated hook，低置信度（< 0.7）标记"需人工核实"

## 5. Review Context（审核上下文）

### 5.1 废弃旧系统

```
废弃:
❌ ApprovalWorkflow（项目级审批链）
❌ ApprovalRecord（审批记录）
❌ submit_approval / approval_action 端点

保留并重构:
✅ ReviewAssignment（审核分配）
✅ ReviewJudgment（审核判定）

新增:
✅ ReviewPolicy（审核策略）
✅ ReviewGate（审核门控）
```

### 5.2 审核分配

节点配置：

```json
{
  "type": "report:review",
  "data": {
    "label": "部门审核",
    "reviewers": [
      {"role": "reviewer", "count": 2},
      {"role": "approver", "count": 1}
    ],
    "review_policy": {
      "mode": "all_must_approve",
      "dimensions": ["legal", "accuracy", "completeness"],
      "allow_delegation": true,
      "deadline_hours": 48
    }
  }
}
```

### 5.3 审核门控（ReviewGate）

| 门控模式 | 行为 |
|---------|------|
| `all_must_approve` | 等待全部 N 个审核员提交；全部 approved → 通过；任一 rejected → 驳回 |
| `any_can_approve` | 任一 approved → 通过；全部 rejected → 驳回 |
| `majority` | >50% approved → 通过 |
| `weighted` | 每个审核员有权重，加权计算 |

### 5.4 驳回回滚

```
审核驳回
  │
  ▼
1. ReviewJudgment {status: "rejected", reason: "..."}
  │
  ▼
2. Orchestration 查 DAG 边: review → label="rejected" → rollback_target
  │
  ▼
3. RollbackPhase(rollback_target):
   ├─ current_phase_node ← rollback_target
   ├─ 该 phase 下所有 COMPLETED/APPROVED 章节 → PENDING
   ├─ 被驳回的 ReviewAssignment → PENDING（可重新分配审核员）
   └─ 通知被驳回章节的 assigned writer
```

驳回时保留审核意见：`previous_judgments` 字段存储上一轮审核记录，供下一轮参考。

### 5.5 审核超时与提醒

```
 0h          24h              48h              72h
 │            │                │                │
 分配审核员    发送预警         超时通知          自动升级
             "24h后将超时"     "审核已超时"       → 通知 phase_lead
                                               → 若仍有 24h 未处理
                                               → 通知 owner
```

## 6. 统一权限模型

### 6.1 废弃旧体系

```
废弃:
❌ permissions.py 旧角色矩阵
❌ project_permissions.py slot 权限
❌ schemas.py VALID_MEMBER_ROLES（manager/editor/approver...）

统一为:
✅ 单一 ProjectRole 枚举
✅ 角色 → 权限映射存 DB（可配置）
```

### 6.2 统一角色

```python
class ProjectRole(str, Enum):
    OWNER = "owner"
    PHASE_LEAD = "phase_lead"
    WRITER = "writer"
    REVIEWER = "reviewer"
    APPROVER = "approver"
```

### 6.3 权限映射（DB 驱动，内置默认值）

| 角色 | 默认权限 |
|------|---------|
| **OWNER** | `project:edit`, `project:delete`, `member:add`, `member:remove`, `chapter:write_any`, `chapter:review_any`, `ai:start_writing`, `approval:review`, `workflow:start`, `workflow:cancel`, `settings:edit`, `export:generate` |
| **PHASE_LEAD** | `chapter:write_any`, `chapter:review_any`, `ai:start_writing`, `approval:submit` |
| **WRITER** | `chapter:write_own`, `chapter:confirm` |
| **REVIEWER** | `chapter:review`, `approval:review` |
| **APPROVER** | `approval:approve`, `approval:view` |

首次部署写入默认值（`ON CONFLICT DO NOTHING`），Admin 可在 UI 修改。

### 6.4 Phase Duties 精简

```json
// ProjectMember.phase_duties 统一格式
{
  "node_001": {"role": "writer"},
  "node_002": {"role": "reviewer"},
  "node_003": {"role": "phase_lead"}
}
```

只用一个 `role` 字段，值必须是 `ProjectRole` 枚举值。Pydantic validator 写入时校验。

### 6.5 权限检查统一入口

```python
def require_project_role(
    project_id: UUID,
    action: str,
    phase_node: str | None = None,
):
    """统一的权限检查入口"""
    # 1. 查 ProjectRole
    # 2. 有 phase_node 时查 phase_duties 覆盖
    # 3. 查 DB 权限映射
    # 4. Admin 始终放行
```

## 7. DocSpace Context（文档空间）

### 7.1 文档-章节关联

废弃标题字符串约定匹配，改为显式 FK：

```python
# 旧: 靠 AI 生成的标题恰好匹配模板标题
# 新: 显式关联
AIDocument.chapter_id → FK to ProjectChapter.id
```

### 7.2 文档生命周期

```
┌────────┐     ┌────────┐     ┌──────────┐     ┌────────┐
│ DRAFT  │────►│ REVIEW │────►│ APPROVED │────►│ FINAL   │
└───┬────┘     └────────┘     └──────────┘     └────────┘
    │                                               ▲
    └───────────────────────────────────────────────┘
                 可直接从草稿定稿（简单报告）
```

### 7.3 文档合并与输出

```
章节 A (COMPLETED) ──┐
章节 B (COMPLETED) ──┤
章节 C (APPROVED)  ──┼──► merge_documents() ──► 最终文档 (FINAL)
章节 D (COMPLETED) ──┘        │
                               ├─ 按 sort_order 拼接
                               ├─ 保留溯源标记
                               └─ 生成统一目录
                                         │
                                         ▼
                               ┌─────────────────┐
                               │  Output Engine   │
                               │  ├─ PDF          │
                               │  ├─ Word          │
                               │  └─ HTML          │
                               └─────────────────┘
```

### 7.4 Yjs 存储

Yjs 二进制 blob 从 PostgreSQL 迁出，改为文件存储：

```
/users/{user_id}/collab/{doc_id}.yjs
```

数据库只存路径引用。版本快照用 markdown 文本存 DB（`snapshot_text` 列），diff 用 `difflib.SequenceMatcher`。

### 7.5 文档空间角色权限

| 操作 | Writer | Phase Lead | Reviewer | Owner |
|------|--------|------------|----------|-------|
| 查看项目文档 | 自己的章节 | 阶段内章节 | 全部 | 全部 |
| 编辑协作文档 | 自己的章节 | 阶段内章节 | ❌ | 全部 |
| 查看版本历史 | ✅ | ✅ | ✅ | ✅ |
| 回滚版本 | ❌ | ✅ | ❌ | ✅ |
| 添加评论 | ✅ | ✅ | ✅ | ✅ |
| 定稿文档 | ❌ | ❌ | ❌ | ✅ |
| 导出文档 | ✅ | ✅ | ✅ | ✅ |

## 8. 定稿流程

### 8.1 前置条件

```
✅ 所有章节 status ∈ {COMPLETED, APPROVED}
✅ 所有审核节点全部通过
✅ 无未解决的评论（可配置跳过）
✅ 溯源覆盖率 ≥ 阈值（默认 80%）
✅ 交叉引用全部可解析
```

任一条件不满足 → 返回不满足清单（不阻塞，但需组长确认）。

### 8.2 定稿步骤

```
1. 组装文档
   ├─ 按 sort_order 排列所有章节
   ├─ 插入: 标题 + content + 溯源脚注
   └─ 生成统一目录

2. 合规校验
   ├─ 字数检查
   ├─ 法规引用检查
   ├─ 数据完整性
   └─ 交叉引用检查

3. 生成校验报告
   { "综合评分": 87/100, "警告": [...], "错误": [...] }

4. 组长确认
   ├─ 修复问题 → 重新校验
   ├─ 标记豁免 → "字数不足已确认，原因: 数据源有限"
   └─ 确认定稿

5. 执行定稿
   ├─ 创建 FINAL 文档
   ├─ 锁定所有章节 → APPROVED
   ├─ 生成最终版本快照
   └─ 触发通知
```

### 8.3 定稿后不可变性

- ❌ 不可编辑
- ❌ 不可回滚章节
- ✅ 可以导出
- ✅ 可以查看版本历史
- ✅ 可以创建副本（新项目从定稿复制）

如需修改 → 创建修订版本（`Revision 1.0 → 1.1`），走简化审核流（仅审批人签字）。

### 8.4 API

```
POST /projects/{id}/finalize          → 返回校验报告
POST /projects/{id}/finalize/confirm  → 确认定稿（含豁免项）
```

### 8.5 与工作流的关系

```
Workflow DAG:
  [writing] → [review] → [finalize]
                             │
                             ▼
                    Finalize 是独立节点，非审核节点

Finalize 节点行为:
  - 自动跑合规校验（不需要人工）
  - 通过 → 自动完成
  - 警告 → 通知组长，等待确认
  - 错误 → BLOCKED，阻止推进

Finalize 成功后:
  - END 节点触发 completion_actions
```

## 9. 个人仪表盘待办

### 9.1 设计原则

不建新表——待办是跨上下文的**查询视图**，从已有数据实时聚合。

### 9.2 聚合源

| 来源 | 查询内容 |
|------|---------|
| Writing Context | `assigned_to = my_user_id AND status IN ('pending', 'error')` |
| Review Context | `reviewer_id = my_user_id AND status = 'pending'` |
| Approval Context | `reviewer_id = my_user_id AND status = 'pending' AND role = 'approver'` |

### 9.3 按角色聚合

| 角色 | 看什么 |
|------|--------|
| Writer | 分配给自己的 PENDING/ERROR 章节 |
| Reviewer | 分配给自己的 PENDING 审核 |
| Phase Lead | 阶段内所有章节状态 + 审核状态 |
| Approver | 待最终签字的审批 |
| Owner | 全部（项目概览） |

### 9.4 API

```
GET /api/extensions/dashboard/my-todos?project_id=<optional>
  → 聚合三源数据，按优先级排序

GET /api/extensions/dashboard/my-todos/summary
  → 只返回计数 {total, writing, review, approval, overdue}
```

### 9.5 与通知系统的关系

通知和待办互补：
- 通知告诉你"有新任务了"（推送，可标记已读）
- 待办让你看到"我现在要做什么"（实时查询，完成即消失）

## 10. 领域不变量 vs 可配置项

| 硬编码（领域不变量） | 配置化（DB/JSONB） |
|---------------------|-------------------|
| `ProjectRole` 枚举值 | 角色 → 权限映射 |
| 章节状态机 | 审核策略参数（超时、门控模式） |
| 节点状态机 | AI 生成策略配置 |
| 信号类型 | 通知模板 |
| 章节依赖推导规则 | 重试策略 |
| IWorkflowNodeExecutor 接口 | 合规校验规则 |

## 11. 迁移路径

### 11.1 数据库变更

| 变更 | 类型 |
|------|------|
| 新增 `role_permissions` 表 | CREATE TABLE |
| 废弃 `approval_workflows` / `approval_records` 表 | 保留但不再写入 |
| `ProjectMember.phase_duties` 格式统一 | 数据迁移脚本 |
| `AIDocument.chapter_id` FK | ALTER TABLE ADD COLUMN |
| Yjs 数据从 DB 迁出 | 后台迁移脚本 |

### 11.2 废弃端点

以下端点保留但返回 410 Gone（过渡期）或直接移除：

- `POST /projects/{id}/submit-approval`
- `POST /projects/{id}/approval-action`
- `GET /projects/{id}/approval-status`

替代端点在 Review Context 下重建。

### 11.3 兼容策略

1. 旧 `phase_duties` 格式自动迁移：`{"duty": "lead"}` → `{"role": "phase_lead"}`
2. 旧 `ApprovalWorkflow` 数据只读保留 6 个月
3. 权限迁移：从旧矩阵提取当前有效权限 → 写入 `role_permissions` 表

## 12. 错误处理

| 场景 | 行为 |
|------|------|
| DAG 无 START 节点 | 校验阶段拒绝，返回明确错误 |
| entry_conditions 不满足 | 返回不满足的条件清单 |
| AI 生成超时 | 章节 → ERROR，记录 error_code，支持重试 |
| AI 生成认证失败 | 章节 → ERROR（auth_error），通知 admin |
| AI 生成配额耗尽 | 章节 → ERROR（quota_error），阻塞后续生成 |
| 审核超时 | 自动通知 phase_lead，可配置自动升级 |
| 审核员无可用 | 节点 → BLOCKED，通知 owner |
| 定稿合规校验失败 | 返回校验报告，允许组长豁免后继续 |
| 并行定稿冲突 | 乐观锁阻止，返回 400 |

## 13. 测试策略

### 13.1 单元测试

- 章节依赖推导（各种模板树结构）
- 章节状态机转换（合法/非法）
- 审核门控策略（all/any/majority/weighted）
- 权限检查（各角色 × 各操作）
- 待办聚合查询

### 13.2 集成测试

- 完整端到端流程：Admin 建模板 → 组长建项目 → AI 初稿 → 组员确认 → 审核 → 驳回 → 重写 → 审核通过 → 定稿
- 并发审核门控
- 审核驳回回滚章节状态
- 定稿合规校验

### 13.3 性能测试

- 待办聚合查询（100 个项目，每项目 50 章节）
- 章节依赖推导（700 章报告模板）
- 阶段批量 AI 生成（20 章节并行）

---

> 本文档是领域驱动重构的完整设计规范。实施时，每个限界上下文应独立演进，通过 Temporal 事件契约保持松耦合。
