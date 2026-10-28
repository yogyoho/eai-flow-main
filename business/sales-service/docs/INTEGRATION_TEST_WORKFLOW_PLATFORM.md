# 营销平台 × Workflow 平台 × Temporal 集成测试用例

## 1. 测试范围

验证营销平台（sales-service）通过 workflow 平台发起和办理审批，workflow 平台底层由 Temporal 编排：

```text
营销前端 / sales API
  → sales-service
  → workflow-backend（预置 R4/R6/撞单流程与表单）
  → Temporal FlowInstanceWorkflow
  → workflow-worker
  → sales 审批投影同步
```

## 2. 测试身份

| 用户 | sales 角色 | 营销平台职责 |
|---|---|---|
| `demo-rep` | sales_rep | 发起 R4/R6/撞单审批 |
| `demo-manager` | regional_manager | 第一步审批 |
| `demo-director` | sales_director | 第二步审批 |
| `demo-compliance` | compliance_officer | R6 第三步合规审批 |

Workflow 平台使用 `X-Workflow-Internal-Token` + `X-User-*` 作为受信任 BFF 调用。

## 3. 预置流程

| sales 闸门 | workflow flow_code | 审批节点 | 表单 |
|---|---|---|---|
| R4 | `sales_r4_exception` | regional_manager → sales_director | `sales_approval_form:1` |
| R6 | `sales_r6_related_party` | regional_manager → sales_director → compliance_officer | `sales_approval_form:1` |
| DUPLICATE/R10 | `sales_duplicate_merge` | regional_manager | `sales_approval_form:1` |

## 4. 用户测试用例

### TC-01 R4 两级审批通过

**前置条件**
- R4 流程和表单已发布。
- 存在新客户集团、无示范面、归属 `demo-rep` 的商机。

**步骤**
1. `demo-rep` 在营销平台发起 R4 审批，填写原因。
2. `demo-manager` 在“待我审批”中看到该申请，状态为运行中、当前第 1 步。
3. `demo-manager` 填写意见并通过。
4. `demo-director` 在“待我审批”中看到该申请，当前第 2 步。
5. `demo-director` 通过。
6. 查询 sales 审批详情与 workflow 平台实例。

**预期**
- sales 审批状态依次为 `running → running → approved`。
- 第 1、2 步依次 `active → approved`。
- sales `approval_actions` 有两条审批意见。
- workflow 平台实例 `flow_status=8`，命令 `APPROVE` 均为 `APPLIED`。
- workflow Outbox 产生 started/updated/completed 事件。

### TC-02 R6 三级合规审批

**步骤**
1. `demo-rep` 对关联方商机发起 R6。
2. 依次由 `demo-manager`、`demo-director`、`demo-compliance` 通过。

**预期**
- 当前步骤依次推进 1 → 2 → 3。
- 最终 sales 状态 `approved`，workflow 实例 `flow_status=8`。
- 合规官只能看到第 3 步，前两步用户不能越权审批。

### TC-03 R4 第一步驳回（终态）

**步骤**
1. `demo-rep` 发起 R4。
2. `demo-manager` 选择“驳回”并填写意见。

**预期**
- sales 状态 `rejected`，后续步骤为 `skipped`。
- workflow 实例终态（`flow_status=8`，`node_code=end`）；第 2 步不产生待办。
- `/tasks/{id}/reject` 显式指向 `end`，不会误走“退回申请人”边。
- 审批历史保留驳回意见。

### TC-04 越权审批

**步骤**
1. R4 第 1 步激活后，`demo-director` 尝试审批。

**预期**
- 返回 `403`，sales 状态仍 `running`，第 1 步仍 `active`。
- workflow 平台不产生成功命令。

### TC-05 幂等重复提交

**步骤**
1. `demo-manager` 用同一 `idempotency_key` 提交两次审批。
2. 第二次请求重复相同动作。

**预期**
- 只产生一条 sales 审批动作。
- 只产生一条 workflow 命令。
- 第二次请求返回成功或幂等结果，不重复推进。

### TC-06 待办可见性

**步骤**
1. R4 第 1 步时查询 `demo-manager`、`demo-director`、`demo-compliance` 的待办列表。
2. 第 1 步通过后再次查询。

**预期**
- 第 1 步只有 `demo-manager` 有待办。
- 第 2 步只有 `demo-director` 有待办。
- 无关角色和申请人不会把待办误显示给自己。

### TC-07 申请人查询与状态同步

**步骤**
1. `demo-rep` 查询自己发起的审批列表和详情。
2. 每次审批后刷新详情。

**预期**
- 申请人可见状态、当前步骤、步骤意见。
- workflow 平台状态变化后，sales 详情在同步调用后更新。
- 终态带 `completed_at`。

### TC-08 申请人撤销

**步骤**
1. R4 第 1 步运行中，`demo-rep` 撤销。

**预期**
- sales 状态 `cancelled`。
- workflow 实例终态为取消/终止。
- 待办从审批人列表消失。

### TC-09 资料不完整退回申请人并重新提交

**步骤**
1. `demo-rep` 发起 R4。
2. `demo-manager` 选择“退回申请人”，填写“资料不完整，请补充客户资质和例外依据”。
3. 用管理员身份调用 `POST /approvals/{id}/resubmit`，应返回 403（只有申请人本人可以重提）。
4. `demo-rep` 打开同一审批单，点击“修改并重新提交”，更新原因和证据 JSON。
5. 查看 workflow 历史和流程图。
6. `demo-manager`、`demo-director` 再次审批通过。

**预期**
- sales 状态为 `returned`，不是 `rejected`/`approved`；`completed_at` 为空。
- 第 1 步状态 `returned`，后续步骤保持 `pending`；原审批单号和 `platform_instance_id` 不变。
- workflow 实例 `flow_status=9`、`node_code=start`；开始节点生成 `assignee=demo-rep` 的申请人任务。
- 流程图 `step_1 → start` 退回边为红色虚线；`step_1 → end` 驳回边仍为灰色。
- 管理员重提返回 `SALES-403-RESUBMIT`，审批单保持 `returned`。
- 重新提交后状态回到 `running`，第 1 步重新激活；202 响应后的详情立刻可见新的原因/证据；不创建新审批单、不创建新 workflow 实例。
- workflow 命令序列为 `START, RETURN, APPROVE, APPROVE, APPROVE`，最终实例 `flow_status=8`。

## 5. 自动化验证点

- sales `approval_requests.engine=workflow_platform`、`platform_instance_id` 非空。
- sales `approval_steps.platform_task_id` 非空且随步骤推进变化。
- workflow `flow_command`：START/APPROVE/RETURN 状态为 `APPLIED`。
- workflow `flow_instance_runtime.status=COMPLETED`。
- workflow `flow_outbox`：事件已生成；未配置 Webhook 时为 `SKIPPED`。
- Temporal 工作流 ID：`flow-instance-{platform_instance_id}`。

## 6. 执行方式

本地联调可用 `AUTH_MODE=local` 启动 sales API（workflow 平台保持 `eai` + 内部令牌）：

```powershell
$env:DATABASE_URL="postgresql+asyncpg://business:business123@127.0.0.1:5433/sales"
$env:AUTH_MODE="local"
$env:TEMPORAL_ENABLED="false"
$env:WORKFLOW_PLATFORM_ENABLED="true"
$env:WORKFLOW_PLATFORM_BASE_URL="http://127.0.0.1:8020/api/workflow"
$env:WORKFLOW_PLATFORM_INTERNAL_TOKEN="<WORKFLOW_INTERNAL_TOKEN>"
python -m uvicorn app.main:app --host 127.0.0.1 --port 3104
```

另开终端执行：

```powershell
$env:SALES_BASE="http://127.0.0.1:3104/api/v1"
$env:WORKFLOW_BASE="http://127.0.0.1:8020/api/workflow"
$env:WORKFLOW_DB_URL="postgresql+asyncpg://business:business123@127.0.0.1:5433/workflow"
python business/sales-service/tests/integration_workflow_platform.py
```

## 7. 本次执行结果（2026-10-24）

- TC-01 R4 两级审批：通过
- TC-02 R6 三级合规审批：通过
- TC-03 R4 驳回：通过
- TC-04 越权审批拦截：通过
- TC-05 幂等重复提交：通过
- TC-06 待办可见性：通过
- TC-08 申请人撤销：通过
- workflow 命令均为 `APPLIED`，runtime 均为 `COMPLETED`，Outbox 事件已生成。
- 测试使用真实 Temporal + PostgreSQL，workflow 平台预置流程为
  `sales_r4_exception`、`sales_r6_related_party`、`sales_duplicate_merge`。

## 8. 页面层与实时刷新验证

- 营销审批详情已嵌入 `WorkflowApprovalPanel`：
  - 面板实现位于共享包 `packages/workflow-embed`（`@eai/workflow-embed`）
  - sales 前端只保留一个注入 BFF client 的适配器
  - 表单快照：字段来自实例启动时冻结的 `formSnapshot`
  - 流程图：使用实例 `def_json` 节点/边快照
  - 审批历史：来自 workflow 实例 history
  - 操作区：通过/驳回/退回由组件调用 sales BFF decision 接口
- BFF 聚合接口验证：
  - `GET /api/v1/approvals/{id}/workflow`
  - 返回 7 个表单字段、4 个流程节点、3 条历史记录
- SSE 验证：
  - `GET /api/v1/approvals/{id}/stream`
  - 返回 `event: approval`，内容包含当前 status/current_step
  - SSE 失败时前端自动降级为 8 秒轮询
- 管理员侧边栏已增加“流程管理”入口，跳转 `/workflow`，与 sales 共用 EAI SSO。
