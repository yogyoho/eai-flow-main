# 写作项目管理模块 · 合并收敛设计（ADR）

- **日期**: 2026-08-09
- **状态**: 设计定稿（待评审 → 待实施）
- **分支**: `main-dev-fork`
- **继承**: 扩展 [2026-08-02 单一状态 ADR](./2026-08-02-writing-project-single-state.md)（其状态值已落地，本文接管其遗留的"流转权威未统一"）
- **取代**: [2026-08-01 collab-workspace-refactor](./2026-08-01-collab-workspace-refactor.md) 中"构建并行零耦合 `extensions/workspace`"的决策 → 改为"把 workspace 的好点子吸收进 `extensions/project`，退役并行模块"
- **范围**: `extensions/project` ⊕ `extensions/workspace` 合并 + 审批轨道收敛 + 角色词表统一 + 前端操作面收敛
- **依据**: 6-agent 审计（`wf_bc8c9162-2fd`，523k tokens，133 tool calls），证据 file:line 散见各 §
- **门禁**: 本文档为设计，不含实现代码。状态值收敛已在 2026-08-02 ADR 落地，**本设计不重写状态机**

---

## 1. 现状（grounding 结论）

用户三问："操作是否太复杂、多人协同是否合理、工作流转是否合理"。审计结论：**三问直觉全对，但根因已不是状态词表（已收敛干净），而是环绕它的并行系统**。

### 1.1 状态轴已干净（2026-08-02 ADR 实际已落地，文档"待实施"标记是 stale）

- `current_stage` 已物理 DROP（`database.py:1437`）
- DB CHECK 强制 `draft/in_review/approved`（项目）+ `pending/draft/reviewing/approved`（章节）（`database.py:816,843`）
- 双 fail-closed 校验器：`validate_status_transition`（`schemas.py:18`）、章节状态机（`writing/state_machine.py:20`）
- `_refresh_project_stats` 不再 clobber status（`service.py:786`）；AI 生成正确写 `draft` 不自动完成（`writing_activities.py:250`）
- **结论：状态值层面 3 套机制 / 4 套词表的乱象已解决。这部分不是问题。**

### 1.2 真正的复杂度来源 = 并行系统（add-instead-of-refactor 病理）

| 维度 | 现状（审计证据） | 用户的痛 |
|---|---|---|
| **操作面** | 前端 6 个断连顶层 surface；**3 个并行"项目详情"实现**：`ProjectWorkspace`(`/projects/[id]`)、`SciFiProjectDetail`(`/projects/[id]/scifi`，1182 行**从未被链接**，孤儿)、`agentspace/ProjectDetail`(`/agentspace/[id]`)。AI 写作对话 `window.open` **开在新浏览器标签**（`ProjectWorkspace.tsx:312`），核心写作行为游离于项目之外。`GanttChart/` 死代码（从未 import）。审批 UI 三连（`ApprovalPanel`/`ApprovalWorkflow`/`ApprovalsQueue`） | 太复杂 |
| **多人协同** | **2 个并行项目模块**：`extensions/project`(ReportProject) 与 `extensions/workspace`(CollabProject，7 表 ~2300 行，`gateway/app.py:594` 注册，`/agentspace` UI)，**零耦合** → 协作模型重复。**6+ 角色词表 / 11 处定义点**：ProjectRole 枚举、系统 RBAC Role+yaml、Department 组织树、ProjectMember.role 自由 String、phase_duties JSONB、workflow DAG required_roles、CollabMember.role(`owner/editor/reviewer/coordinator`，**故意与 ProjectRole 不同**)、CollabTask.assignee、CollabGate.participants、ReviewAssignment.reviewer_role、ApprovalWorkflow.role_required。仅靠 `unified_permissions.py:23,38` 的 **2 个 ad-hoc 映射字典** 桥接，从未真正统一。ProjectMember **无 agent 概念**，AI 写作无法归属/指派/审阅 | 协同不合理 |
| **工作流转** | 双校验器**仅 advisory**。约 **7 个项目 status writer + 5 个章节 status writer 绕过校验**用裸 ORM/SQL：legacy ApprovalWorkflow(`service.py:1109`)、Temporal `CompleteProjectNode`(`system_nodes.py:134`)、`notify_workflow_complete`(`notification_activities.py:265`)、docmgr `execute_finalize`(`finalize.py:158`)、`finalize_document`(`routers.py:1312`)、review rollback、workflow start、project create。**Temporal 本身是 status writer** → 引擎与校验器可独立漂移。**无单一 chokepoint**。**4 套审批轨道**：DB ApprovalWorkflow/Record（半弃用）、内存审批（`routers.py:19` 路由活但**零 UI 消费者**，死）、PhaseReview（活，主）、ReviewAssignment（docstring 自称"统一替代"但**从未接 HTTP，仅 Temporal**）。`ReviewTab.tsx:58` 在一个 tab 里渲染**两条并行审批时间线** | 流转不可验证 |

### 1.3 病理模式：加并行系统，而非重构既有

每一代都选"加"而非"替"：状态机→加 `current_phase_node`→加 `current_stage`；审批→加 ApprovalWorkflow→加内存版→加 ReviewAssignment；项目→加 `extensions/workspace`；详情页→加 SciFi→加 agentspace。

**唯一一次"合并而非新增"是 2026-08-02 单一状态 ADR。它成功了。** 状态乱象消失。这是 repo 内的可证论据：**在本模块，collapse 优于 parallelize。** 本设计把同一招用到其余每一行。

---

## 2. 核心决定

**ONE 项目抽象。** 把 `extensions/workspace` 的 3 个好点子吸收进 `extensions/project`，退役并行模块：

1. **协作的单位是闸门(gate)，不是项目** —— 把散在 4 套审批轨道的"门"收敛为**单一 gate 原语 = 唯一 transition 权威**。
2. **脚手架只在超过一个人/超过一章时才出现**（Tier 分层）—— 项目从 Tier 1（零脚手架：一个文档 + AI）起，sections/gates/roles/workflow **按信号派生**而非配置。
3. **agent 是一等成员** —— ProjectMember 增加 agent 能力，AI 写作可归属/指派/审阅。

**退役清单**：`extensions/workspace` 并行数据模型；2 套死审批（内存版、legacy ApprovalWorkflow 接线）；孤儿 UI（SciFi、GanttChart）；重复详情页。

**不重做**：状态值词表（已收敛）。本设计接管的是 ADR 留下的"流转权威未统一"。

---

## 3. 目标架构

```
                         ┌─────────────────────────────────────┐
                         │   extensions/project （唯一项目模块） │
                         ├─────────────────────────────────────┤
  ONE 详情屏 ◀──────────│  ProjectWorkspace（含嵌入式 AI 写作） │
  (3→1)                 │   ┌─ Tier 1: 零脚手架（单文档+AI）    │
                         │   ├─ Tier 2: 信号触发→出现 section+gate │
                         │   └─ Tier 3: 正式评审/发布          │
  ONE 角色词表 ◀────────│  ProjectMember = ProjectRole + agent  │
  (6+→1)                │                                       │
  ONE 流转权威 ◀────────│  gate() = 唯一 transition writer      │
  (4 轨道→1 gate)        │     ↳ DB CHECK backstop（已就位）     │
                         └─────────────────────────────────────┘
```

### 3.1 Tier = 脚手架从信号派生（核心洞察落地）

Tier **不是字段、不是配置**，是**纯函数**，输入项目信号：

| Tier | 信号 | 可见脚手架 |
|---|---|---|
| 1 | 单成员 且 单章 且 无 review 请求 | 无（= 一个文档 + AI）。**这正是今天走 docmgr-only 的简单报告路径（消防专篇/给排水），但它在项目模块内、脚手架不可见** |
| 2 | >1 成员 或 >1 章 或 首个 review 请求 | 出现 sections/gate 队列/角色分配/看板 |
| 3 | 正式发布/盖章/归档触发 | 出现正式评审流 + 审批记录 + 导出闸 |

- **关键**：Tier 1 项目"看起来"就是一个文档；项目壳对用户不可见。这统一了"简单报告走 docmgr、正式报告走 project"两条路径，**消解"项目模块太重所以简单报告绕开它"的根因**（= workspace Tier 模型的正确应用）。
- **quickdoc→report 提升** = 同一项目内 Tier 1→2→3，而非跨模块迁移。

### 3.2 gate = 唯一 transition 权威

- 一个 `transition(target_status, *, actor, gate_kind)` 函数 = 项目/章节状态变更的**唯一 writer**。
- 现有 12 个绕过 writer 全部改走它，或被 DB CHECK 拒绝（CHECK 已就位，是兜底）。
- PhaseReview（活）+ ReviewAssignment（Temporal-only，自称"统一替代"未落地）**合并为同一 gate 原语**：完成 ReviewAssignment 那次未完成的统一。
- 4 轨道 → 1。`ReviewTab` 双时间线消失。

### 3.3 agent-as-member

- ProjectMember 增加 `agent_id`（nullable，人/agent 二选一标识）。
- AI 写作经 MCP 写章节时，ActivityLog 归属到该 agent 成员；agent 可被指派到章节、可被请求 review。
- **不**把 agent 塞进 RBAC Role（agent 不持有系统权限），只在项目成员层建模。

### 3.4 嵌入式 AI 写作

- `window.open` 新标签 → **项目详情页内嵌 chat 面板**（host `useStream`）。
- 这是最大 UX 修正：核心写作行为回到项目所在处。架构含义：详情页 owns run 生命周期（设计层标注，非代码）。

---

## 4. 五阶段迁移（每阶段独立可发、独立降复杂度）

照搬 2026-08-02 ADR 的纪律：原子窗口、DB CHECK 兜底、迁移前后审计、重启验证。**顺序刻意：先把目标(project)清干净，最后才把 workspace 迁进去。**

### Phase 0 —— 止血（最低成本、零运行时风险、立竿见影）

删死代码/孤儿，不归档：
- 删 `SciFiProjectDetail.tsx`（1182 行孤儿，无链接）
- 删 `components/GanttChart/`（死，从未 import）
- 拆内存审批 live 接线（`routers.py:19`，零 UI 消费者）。DB 表暂留（数据），仅去 live wiring
- legacy ApprovalWorkflow UI 路径降级（保留 DB 表与 `service.py:1109` 绕过者的迁移用，去 UI 入口）

**产出**：~1400 行死/重复前端 + 1 死路由消失。用户感知：零（本来就没人在用）。

### Phase 1 —— 收敛操作面（用户最直观的"不再复杂"）

- **3 详情屏 → 1**：`ProjectWorkspace` 为唯一详情。把 agentspace `ProjectDetail` 的 2 个好 tab（agent-runs、gate 队列）port 进来。删 SciFi（Phase 0 已删）。
- **嵌入式 AI 写作**：`window.open` → 详情页内 chat 面板。
- **审批 UI 三连 → 一**：一个 gate 队列视图。

**产出**：用户在**一处**完成全部写作项目管理。复杂度直接下降。

### Phase 2 —— 统一流转权威（workflow 可验证）

- 引入唯一 `transition()`（§3.2）。
- 12 个绕过 writer 逐一改走它，或确认被 DB CHECK 兜底（审计每个）。
- 完成 ReviewAssignment 统一（PhaseReview + ReviewAssignment = 同一 gate）。删双时间线。

**产出**：状态值干净 + 流转权威单一 → 工作流转**可验证**。`ReviewTab` 不再分裂。

### Phase 3 —— 统一角色 + agent-as-member（协同可建模）

- ProjectRole `{owner, phase_lead, writer, reviewer, approver}` 为唯一词表；`unified_permissions.py` 两映射字典 = 迁移映射，迁完即删。
- CollabMember 的 `editor→writer`、`coordinator→phase_lead` 归并。
- 删 `phase_duties` 9 key（duty 由 role 按阶段派生）。
- ProjectMember 增 `agent_id`。

**产出**：协作模型**唯一**，AI 是一等成员。

### Phase 4 —— 吸收 workspace Tier/gate、退役并行模块（封顶，gated on 0–3）

前置：Phase 0–3 完成，`extensions/project` 已是干净单一宿主。

- 把 Tier 派生（§3.1）落到 project：项目从 Tier 1 起，脚手架按信号出现。
- workspace 7 表数据迁入 project 表（映射见 §5）。
- **退役 `extensions/workspace`**：见 §6 开放决策 A（全迁并删）vs B（降为 project 之上的 Tier-1 薄视图层，零数据模型）。推荐 B 更省、更 ponytail。

**产出**：ONE 项目抽象。第二项目模块消失。

---

## 5. 数据模型合并（workspace → project）

| workspace 表 | → project 归宿 | 说明 |
|---|---|---|
| `collab_projects` | 折入 `report_projects`（+ 可选 collab 字段） | 单一项目实体 |
| `collab_sections` | → `project_chapters` | 1:1 映射 |
| `collab_members` | → `project_members`（+ `agent_id`） | 吸收 agent 能力 |
| `collab_tasks` | → 章节级 todo 或 `activity_logs`（按 Tier 派生） | 不另立 task 表 |
| `collab_gates` | → 统一 gate 原语（§3.2） | 协作单位 = gate |
| `collab_agent_runs` | → `activity_logs` | AI 运行即活动 |
| `collab_activity` | → `activity_logs` | 单一活动流 |

**迁移纪律**（照搬 2026-08-02 ADR §6）：原子窗口、CASE 穷尽回填、DB CHECK 兜底、迁移前后 `SELECT status,count(*)` 审计、重启后跑一次真实 agent 写入 + 一次 Tier-1 同步验证。

**保留不动**：`approval_workflows/records`、`ai_documents`、`activity_logs`（各自独立域；workspace 迁完才清理孤儿 approval 数据）。

---

## 6. 风险与开放决策

| # | 决策 | 选项 | 建议 |
|---|---|---|---|
| A | Phase 4 退役方式 | (a) 全量迁数据 + 删 workspace；(b) workspace 降为 project 的 Tier-1 薄视图层（不再有独立数据模型） | **(b)**：更省、无数据迁移风险，且尊重"脚手架默认不可见"。仅当确认 agentspace 无深度定制用户时才上 (a) |
| B | agentspace 现状用户 | 真有用户在用 `/agentspace`？ | **先查 ActivityLog/访问日志**。无 → 直接 (a)；有 → (b) + 迁移 |
| C | 嵌入式 chat run 生命周期 | 详情页 owns run vs 沿用独立 thread + 内嵌展示 | 详情页 owns（设计层标注，实施时定） |
| D | Phase 4 触面大 | 全量一次 vs 按 Tier 渐进 | **渐进**：先 Tier 派生（纯函数、零数据改），再迁移 |
| E | 4 套审批的 DB 数据 | 删 vs 归档 | 归档（`approval_workflows/records` 保留只读），仅去 live wiring |

**最大风险**：Phase 4 触面大。缓解 = gated on 0–3，且 Tier 派生先以纯函数落地（零数据改、可独立验证）后再迁移。

---

## 7. 不做什么（scope guard）

- **不重写状态机** —— 2026-08-02 ADR 已收敛落地。本设计只统一"流转权威"。
- **不引入新模块 / 新依赖** —— 合并的本质是减少。
- **不动 harness 核心**（`deerflow.*`）—— 遵守 harness/app 边界。
- **不改 contract_price 等其它扩展** —— 聚焦写作项目模块。
- **本文件为设计，不含实现代码。**

---

## 8. 与既有 ADR 的关系

- **2026-08-02 单一状态**：状态值收敛（已落地）。本设计**继承**，接管其遗留的"流转权威未统一"。
- **2026-08-01 collab-workspace-refactor**：决策为"建并行零耦合模块"。本设计**取代**该决策 → 吸收其洞察（Tier/gate/agent-member/脚手架按需），但落点从"新模块"改为"既有模块"。
- **2026-06-01 workflow-project-collaboration-system-refinement**：管理面（org_units/system_roles/Gantt 等）大部分**降级**（org 角色已并入 §3 统一词表；Gantt 为死代码已删）。仅保留仍服务 Tier 3 正式流程的部分。
