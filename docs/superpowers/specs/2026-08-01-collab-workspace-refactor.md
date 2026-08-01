# 协作工作台（Collab Workspace）设计 — 人+agent 通用协作 workspace

- **日期**: 2026-08-01
- **状态**: Draft rev 3 — 经三轮对抗性评审迭代（5.2 → 7.4 → 7.75，0 critical / 1 major + 8 minor 已全部修复），判定可实施
- **分支**: `main-dev-fork`
- **范围**: 大重构「泛化为 AgentSpace 式人+agent 协作 workspace」的 **子项目 #2（通用 Task+指派）+ #3（agent 执行桥）+ #4（通用 Project 抽象）+ 分层 Tier**
- **参照**: [HKUDS/AgentSpace](https://github.com/HKUDS/AgentSpace) — `apps/web/`（页面功能/操作/布局全面照抄）+ `apps/web/features/`（task-board / approvals / agents showcase / inbox / knowledge / settings）
- **样式**: 复用本系统 `frontend/src/extensions/dashboard/dashboard.css`（工作台风格）

---

## 1. 背景与目标

### 1.1 上层目标（本 spec 的母体）

借鉴 AgentSpace 的功能设计思路，把本系统的「项目管理 + 工作台」从**人驱动的报告生产工作流**演进为**人 + agent 协作的通用 workspace**。核心洞察（来自跨系统研究：OpenClaw / Hermes / AgentSpace / 2026 通用范式）：

> **协作的单位是"闸门"(gate)，不是"项目"。** 章节分配、RBAC、阶段看板、审批链都是脚手架——只有当工作集实际超过一个人时才应该出现。30 页备忘录和 700 页环评**不是两个产品**，是一个产品，区别只在闸门密度、扇出深度、参与者集合。

已拆为 6 个独立子项目（见 §12）。**本 spec 覆盖子项目 #2、#3、#4**：
- **#2**：通用 Task + 指派（人/agent）
- **#3**：agent 任务执行桥
- **#4**：通用 Project 抽象（`ReportProject → Project(kind)`）
- 外加贯穿三者的**分层 Tier 模型**（Tier 1 单人速写零脚手架 → Tier 3 团队正式管线）

### 1.2 关键决策（用户确认）

| 决策 | 选择 | 理由 |
|---|---|---|
| 模块形态 | **完全独立新模块** `extensions/workspace` | 用户明确："完全独立新做的模块，不要与现有写作项目模块耦合" |
| 与现有模块关系 | **零引用** `extensions/project`、`extensions/workflow`、`extensions/approval` | 不调 project MCP / enter_project / Temporal；多章节 report 用 workspace 自有 `collab_sections` |
| 复用基础设施 | docmgr+collab（**仅数据表 + 协编端点，不调 service 里 import ProjectMember 的函数**）/ review gate（纯函数）/ AgentStore / dashboard.css | 共享底座，非写作项目模块 |
| Agent 身份 | `agent_name` 字符串先行 | 与 project MCP 工具寻址一致；#1 注册表后续升级稳定 ID |
| Tier 1 默认 | 快速文档（零脚手架） | 研究结论：单人速写占 80% 真实使用 |
| Tier 触发 | 信号自动升高，绝不手动配置 | 避免重造配置负担 |
| UI | **页面功能/操作/布局尽可能照抄 AgentSpace**；样式用工作台（dashboard）风格 | 用户明确 |

### 1.3 现状（必须先理解的起点）

- **无统一任务实体**：任务性散落于 `ProjectChapter.assigned_to`、`ProjectMember.phase_duties`、`ApprovalRecord`、`ReviewAssignment`，且**没有任何 `agent_id` 字段**。
- **审批 4 轨并存**：DB `ApprovalWorkflow/Record`（已 410 弃用）、内存 `extensions/approval`（孤儿 UI）、HTTP `PhaseReview`（ReviewTab 在用）、Temporal `ReviewAssignment`（无 HTTP 布线）。`review/gate.py` 的 `evaluate_gate` 是唯一值得复用的纯函数（已验证无 app import、stateless）。
- **Temporal 脆弱**：`local_executor.py` 是死代码，Temporal 是现有模块唯一推进阶段的运行时，`phase-complete` 在 Temporal 挂时静默失效 → **workspace 完全绕开 Temporal**。
- **agent 绑定在 run 时，不在 thread 创建时**（已验证）：`POST /api/threads` 的 `ThreadCreateRequest` 只有 `thread_id/assistant_id/metadata`（threads.py:257-264），**无 `agent_name`**。agent 绑定发生在 run 时，经 `build_run_config`（services.py:626-631）读 `config.configurable.agent_name` 或 `config.context.agent_name`。owner 用户作用域经 **`X-DeerFlow-Owner-User-Id` 内部鉴权头**（internal_auth.py:14,28 `create_internal_auth_headers(owner_user_id=...)`）注入，否则 run 落 `default` 桶导致 agent 解析失败。
- **`docmgr/service.py::sync_thread_files` 内部 import `ProjectMember`**（service.py:14）→ 直接调用会**传递耦合**到写作项目模块。workspace 必须**自实现沙箱→文档同步**（模式复用契约，不 import docmgr service）。

---

## 2. 非目标（明确排除 / 留到后续子项目）

- ❌ 修改 `extensions/{project,approval,dashboard,workflow}` 任何业务代码（除 `shell/Sidebar.tsx` +1 导航行）。
- ❌ 修改 deer-flow harness 核心（`packages/harness/deerflow/`），只经其公开 API。
- ❌ 迁移现有 `report_projects` 数据进 workspace（并存；增量迁移留后续子项目）。
- ❌ Agent 注册表（#1）、3 套审批合并（#5）、工作台重做（#6）。
- ❌ 任何 Temporal/workflow 集成（workspace 用自有 Python 状态机）。
- ❌ Tier 3 的完整 UI/权限引擎/发布管线。**唯一例外**：`POST /projects/{id}/release` 最小占位（status→`submitted_for_release` + S2 信号 + 计算 T3）**在本轮范围内**；完整发布管线（多签 UI/审计）留后续。
- ❌ 通知（邮件/IM 指派）、WebSocket 任务板推送（TanStack Query 轮询即可）。
- ❌ 多租户 `org_id` 实际使用（字段预留恒 NULL）。

---

## 3. 设计护栏（硬约束）

1. **完全独立**：零引用 `extensions/project`、`extensions/workflow`、`extensions/approval` 业务代码。只 import 无状态纯函数（`review/gate.py::evaluate_gate`）与共享基础设施（docmgr **数据表** + 协编端点、AgentStore、dashboard.css）。**不得调用任何 import `ProjectMember` 的现有 service 函数**（如 `sync_thread_files`）。
2. **不动 harness 核心**；只经公开 API 调用。
3. **不改现有模块业务代码**（除 Sidebar +1 导航行）；跨扩展复用为 import/调用，不复制逻辑。
4. **EAI-CUSTOM 注释**所有对 deer-flow 上游行为的定制。
5. **提交 `main-dev-fork`**。
6. 保持 `tests/test_harness_boundary.py` 绿（app import deerflow，反向禁止）。

---

## 4. 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: extensions/workspace（新，AgentSpace 布局 + dashboard 风格）│
│    Sidebar 框架 · 任务板 · 审批 · 数字员工(只读) · 动态 · 文档库 · 设置 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ /api/extensions/workspace (cookie-JWT)
┌──────────────────────────┴──────────────────────────────────────┐
│  Backend: app/extensions/workspace（新，完全独立）                │
│    routers · service · schemas · models · tier · gate(复用)      │
│    agent_bridge（thread+run 编排，不经 project MCP）              │
│    sandbox_sync（workspace 本地沙箱→文档同步，不 import docmgr svc）│
│                                                                   │
│    collab_projects / collab_sections / collab_members             │
│    collab_tasks / collab_gates / collab_agent_runs / collab_activity│
│                                    ← PostgreSQL agentflow          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 复用（共享基础设施）
                           ▼
  docmgr 数据表（ai_documents/collab_documents/collab_versions）
  collab 协编端点（/api/collab + /api/extensions/docmgr/*）
  review/gate.py（纯函数） · AgentStore（agent_name 解析）
  Gateway /api/threads + /api/threads/{id}/runs（run 时绑 agent）
  X-DeerFlow-Owner-User-Id（内部鉴权，owner 作用域）
```

**核心思想**：workspace 是一个**自足的编排层**——项目/章节/成员/任务/闸门/执行桥全部自建，只复用文档数据表、协编端点、闸门纯函数、agent 运行时。与现有写作项目模块**零共享数据表、零函数调用**（`ai_documents` 是共享 docmgr 底座，其 `project_id`/`chapter_id` FK 列对 workspace 文档恒 NULL）。

---

## 5. 数据模型（agentflow DB，7 张新表）

### 5.1 `collab_projects`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | 稳定主键 |
| `name` | str | 项目名 |
| `kind` | str | **immutable** `quickdoc`（单文档）\| `report`（多章节） |
| `doc_id` | UUID FK→ai_documents.id, null | **quickdoc 用**：单文档（`ai_documents.project_id` 留 NULL） |
| `owner_id` | UUID FK→users.id | 创建者/管理者 |
| `tier_state` | str default `tier1` | **derived 缓存**，不手写；`tier1\|tier2\|tier3` |
| `tier_signals` | JSONB default `[]` | 已触发信号 `[{signal, at, to}]` |
| `escalated_at` | datetime, null | 上次升级时间 |
| `status` | str default `active` | `active\|submitted_for_release\|released\|archived` |
| `compliance_pin` | bool default false | 合规钉（S3 信号） |
| `org_id` | UUID null | 多租户预留，恒 NULL |
| `created_by` / `created_at` / `updated_at` | | — |

**约束**：`kind='quickdoc'` 必须有 `doc_id`；`kind='report'` 用 `collab_sections`。**kind 不可变，仅经 `promote-to-report`（含 S4 自动物化）变更**；quickdoc 永不持有 collab_sections 行。

### 5.2 `collab_sections`（report 章节模型，全新）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | |
| `project_id` | UUID FK→collab_projects.id CASCADE | |
| `parent_id` | UUID null | 层级 |
| `title` | str | |
| `level` | int default 1 | |
| `sort_order` | int default 0 | |
| `status` | str default `pending` | `pending\|draft\|in_review\|completed\|deleted` |
| `doc_id` | UUID FK→ai_documents.id, null | 每 section 可挂独立协编文档 |
| `content` | text null | section 内容快照 |
| `revision` | int default 0 | **内容乐观锁**（publish-doc / agent 写回 compare-and-set，冲突 409） |
| `word_count_target` / `word_count_current` | int | |
| 时间戳 | | — |

### 5.3 `collab_members`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | |
| `project_id` | UUID FK CASCADE | |
| `member_type` | str | `human\|agent` |
| `user_id` | UUID null | human 时 |
| `agent_name` | str null | agent 时 |
| `role` | str default `editor` | `owner\|editor\|reviewer\|coordinator` |
| `joined_at` | datetime | |

CHECK 判别字段正确；UNIQUE(project_id, member_type, resolved_id)。**S1 信号数据源**。

### 5.4 `collab_tasks`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | |
| `project_id` | UUID FK CASCADE | |
| `title` | str | |
| `kind` | str | `section_write\|doc_review\|research` |
| `assignee_type` | str | `human\|agent`（CHECK 判别） |
| `assignee_user_id` | UUID null | |
| `assignee_agent_name` | str null | |
| `status` | str default `pending` | `pending\|in_progress\|done\|blocked` |
| `section_ref` | UUID null →collab_sections.id | report 用 |
| `doc_id` | UUID null FK→ai_documents.id | quickdoc 用 |
| `context` | JSONB | 指令/合规/spec-merge |
| `handoff_state` | str null | `acked\|progress\|done\|blocked` |
| `handoff_payload` | JSONB null | `{state, progress_pct, content_delta, notes}`（与 §8.2 `.handoff.json` schema 完全一致） |
| `thread_id` / `run_id` | str null | agent 执行桥 |
| `attempt_count` | int default 0 | |
| `last_error` | str null | |
| `revision` | int default 0 | **任务记录**乐观锁（非内容锁；内容锁在 section） |
| `due_at` | datetime null | |
| `created_by` / 时间戳 | | — |

### 5.5 `collab_gates`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | 稳定 ID，fail-closed |
| `project_id` | UUID FK CASCADE | |
| `task_id` | UUID null FK→collab_tasks.id | task 级闸门 |
| `scope` | str | `task\|project_release` |
| `state` | str default `pending` | `pending\|approved\|rejected` |
| `mode` | str | `review/gate.py` GateMode 值（默认 `all_must_approve`） |
| `participants` | JSONB | `[{type, user_id\|agent_name, weight}]` |
| `deadline_at` | datetime null | 防 WAITING 死锁 |
| `escalation_rule` | JSONB null | `{after_days, action: escalate_admin\|auto_approve}` |
| `resolved_by` / `resolved_at` | | — |
| `audit` | JSONB default `[]` | 审计轨迹 |
| `revision` | int default 0 | reopen 用 |
| `propagated_to` | JSONB null | 传播给协调者/上级闸门 |
| 时间戳 | | — |

**闸门生命周期（评审修正）**：
- **创建**：task 指派时自动建 `scope=task` 闸门；**`scope=project_release` 闸门在 `POST /projects/{id}/release` 内、S2 触发 T3 后创建**（非按章节数；§6.2 "Tier 3 门出现在首次 release 之后"一致）。
- **零人类参与者防退化**：闸门默认参与者若无任何 human（如 task 仅派 agent 且无 owner/coordinator），**不自动通过**——escalate 给 owner 或保持 pending 直到加 human。
- **默认 mode**：`all_must_approve`（复用 `review/gate.py::GateMode`）；**默认参与者** = task 指派对象 + 项目 owner/coordinator。
- **agent 参与者语义**：agent 在任务完成时**自动批准**该闸门；agent 永不判定（不拉长 quorum）。`evaluate_gate(total_reviewers, judgments, weights)` 的 `total_reviewers` = **人类参与者数**。
- **deadline 执行**：**惰性**——每次 `GET /projects/{id}/gates` 和 `POST /projects/{id}/gates/{gid}/judge` 时检查 `deadline_at` 并应用 `escalation_rule`（无需调度器；与"不加调度器"一致）。纯函数 `evaluate_gate` 不含 deadline，wrapper 在 workspace gate service 里加；**桥在 run 完成自动触发闸门时同样先跑该 deadline 检查**。
- **结果耦合**：PASS → task 标 `done` / section 释放；REJECT / needs_changes → task 标 `blocked`（coordinator 可 `POST /projects/{id}/gates/{gid}/reopen`：gate.state→pending + task.status→in_progress，revision++）。

### 5.6 `collab_agent_runs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | |
| `task_id` | UUID FK→collab_tasks.id | |
| `project_id` | UUID FK CASCADE | |
| `thread_id` / `run_id` | str | 网关 thread/run |
| `agent_name` | str | |
| `prompt_snapshot` | text | 本次 prompt（审计） |
| `status` | str | `spawned\|running\|success\|failed\|timed_out` |
| `result` | JSONB null | 结构化 handoff 结果 |
| `max_duration` | int default 1800 | 超时秒数（默认 30min） |
| `started_at` / `finished_at` | datetime | |

### 5.7 `collab_activity`（评审修正：必建，属 #3 执行桥 provenance，非 Tier 3 审计）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | |
| `project_id` | UUID FK CASCADE | |
| `actor_type` / `actor_id` | str / str | `human\|agent` |
| `action` | str | `task_created\|task_assigned\|run_spawned\|handoff_received\|gate_judged\|gate_resolved\|doc_published\|section_status` |
| `target` | str null | 目标实体 id |
| `detail` | JSONB null | |
| `created_at` | datetime | |

---

## 6. 分层 Tier 模型

### 6.1 信号表（自动升高，粘性单向）

| # | 信号 | 触发 | 具体规则 | 升到 |
|---|---|---|---|---|
| S1 | 第二参与者 | 加成员 | `collab_members` ≥ 2（任意类型）OR 任一 agent 成员 | T2 |
| S2 | 外部发布 | `POST /projects/{id}/release` | status→`submitted_for_release`（本轮实现最小占位）+ 创建 `scope=project_release` 闸门 | T3 |
| S3 | 合规钉 | flag/任务 context | `compliance_pin=true` OR 任一任务 context 有非空 `compliance_rules` | T3 |
| S4 | 章节数 | 文档保存/章节创建 | quickdoc: 最新 `collab_versions.snapshot_text` 中 `##` 标题 ≥8 或字符 ≥5000（协编保存由 collab server 写 snapshot_text；未开编辑器则经 publish-doc/sandbox_sync 写）——实施前先验证此基建行为；report: `collab_sections` 行数（status≠deleted）≥6 | T2 |

**规则**：
- **粘性单向**：升了不降级（记 `escalated_at`）。
- **`recompute_tier(project)`** 从写端点幂等调用（成员增删、release、章节创建、文档保存），**不加调度器**。
- 每次触发追加 `tier_signals`（`{signal, at, to}`），UI 显示"为何升级"。
- **release 排序**：`POST /projects/{id}/release` 任意 tier 可调；动作设 `status→submitted_for_release` 并触发 S2 升 T3；"Tier 3 门"指 T3 之后新增发布审批闸门，**不是首个 release 的前置**。`status='released'` 为延期管线的桩（本轮无产出的端点，保留枚举供后续）。

### 6.2 Tier 形态

| | Tier 1 单人速写 | Tier 2 并行交接 | Tier 3 正式评审 |
|---|---|---|---|
| **场景** | 30 页备忘录 | 多章节、几个人 | 700 页环评 |
| **形态** | 版本化文档 + AI 起草 + 修订 | 协调者分解 section TaskPackage 扇出 + 每 section 闸门 + 变更请求 | 全管线 + 发布审批闸门 |
| **闸门** | 隐性（人读+就地改） | 每 section approve/needs_changes | 每阶段人审 + 多签 |
| **脚手架** | **零** | section 任务清单 + 闸门 | 权限 + 发布 |
| **本轮做** | ✅ 完整 | ✅ 数据+编排 | ⚠️ schema + release 最小占位 only |

**quickdoc→report 升级路径（评审修正）**：S4 触发 quickdoc 升 T2 时，**自动从文档 `##` 标题物化 `collab_sections` 行**（每行挂独立 doc_id），**同时把 `kind` 翻为 `report` 并将项目行 `doc_id` 置 NULL、原文档作为首个/根 section 的 `doc_id` 保留内容**（两路径等价，kind 翻转一致）——或用户显式调 `POST /projects/{id}/promote-to-report` 做同样的事。**quickdoc 永不持有 collab_sections 行**。

**同层不变**：section/文档模型、AI 起草原语、版本化 diff 历史、任务=自含单元+结构化交接、闸门原语。

---

## 7. API 清单（前缀 `/api/extensions/workspace`，cookie-JWT + `system:access` + 写操作成员校验）

| Method | Path | 说明 |
|---|---|---|
| GET/POST | `/projects` | 列表（默认 Tier 1 快速文档入口）/ 创建 |
| GET/PATCH/DELETE | `/projects/{id}` | 详情/更新/删除（**删除=归档**，设 status→`archived`） |
| GET | `/projects/{id}/tier` | tier 状态 + signals（为何升级） |
| POST | `/projects/{id}/release` | **最小占位**：status→`submitted_for_release` + S2 信号 + 计算 T3 + **创建 `scope=project_release` 闸门**（完整发布管线出范围） |
| POST | `/projects/{id}/promote-to-report` | quickdoc→report：从 `##` 标题物化 collab_sections + 翻 kind |
| POST/DELETE | `/projects/{id}/members` / `/members/{mid}` | 成员增删（触发 recompute_tier） |
| PATCH | `/projects/{id}/members/{mid}` | 角色变更 |
| GET/POST | `/projects/{id}/sections` | report 章节列表/创建（S4 计数源） |
| PATCH | `/projects/{id}/sections/{sid}` | section 更新（title/status） |
| GET/POST | `/projects/{id}/tasks` | 任务列表/创建 |
| GET/PATCH/DELETE | `/projects/{id}/tasks/{tid}` | 任务详情/更新/删除 |
| POST | `/projects/{id}/tasks/{tid}/assign` | 指派（human/agent） |
| POST | `/projects/{id}/tasks/{tid}/handoff` | 交接回写——**主要走 §8.2 `.handoff.json` 文件由桥解析**；本端点供协调者手动记录/覆盖（agent 不直接调 REST） |
| POST/GET | `/projects/{id}/tasks/{tid}/runs` | spawn agent run / 查询状态 |
| GET | `/projects/{id}/gates` | 闸门列表（含 deadline 惰性检查） |
| POST | `/projects/{id}/gates/{gid}/judge` | 判定（approve/reject/comment） |
| POST | `/projects/{id}/gates/{gid}/reopen` | 变更请求 reopen（revision++） |
| POST | `/projects/{id}/publish-doc` | **flush 契约（评审修正）**：遍历每个有 `doc_id` 的 section（quickdoc=项目 doc_id，report=各 section doc_id），取其 collab doc 的**最新** `collab_versions.snapshot_text` → 写该 section 的 `ai_documents.content`（report 再写 `collab_sections.content`）并重算 `word_count_current`。**快照为 NULL 时跳过不覆盖**（Python 不解码 Yjs 二进制），记 skip 日志。**覆盖写**，唯一冲突防护 = `collab_sections.revision` CAS（冲突 409）。触发：手动 POST 或 agent run 完成后由桥自动调。 |

**资源嵌套约定（评审修正）**：一律**嵌套在 project 下**（`/projects/{id}/tasks/{tid}`、`/projects/{id}/gates/{gid}`），id 视为 project 范围内唯一；杜绝顶层/嵌套混用。

**访问控制（服务端强约束）**：list 看 owner/成员项目；写操作需成员身份；owner 才可删项目/归档/改成员角色/promote-to-report；agent 指派需 `agent_name` 对项目 owner 的 `users/{user_id}/agents/{agent_name}` 可解析（不存在 4xx）。

---

## 8. Agent 执行桥（#3）

**完全独立**：不经 project MCP / enter_project / Temporal。

### 8.1 thread + run 编排（评审修正：agent 在 run 时绑定，不是 thread 创建时）

1. **建 thread**：`POST /api/threads`（`ThreadCreateRequest` 只有 `thread_id/assistant_id/metadata`，**无 agent_name**）——metadata 记 `workspace_project_id`。
2. **spawn run**：`POST /api/threads/{thread_id}/runs`，body **`{"input": {...}, "context": {"agent_name": name, "user_id": project.owner_id}, "config": {...}}`**——**`context` 在顶层**（thread_runs.py:124 的 RunCreateRequest 顶层字段），不是 `config.context`。`workspace_project_id` 不在 `_CONTEXT_CONFIGURABLE_KEYS` 白名单，靠 thread metadata 传递。
   - ⚠ **agent_name 必须放在顶层 `body.context`，不能放 `body.config.configurable`**（评审修正，已验证）：`build_run_config`（services.py:562-591）在请求同时含 `context` 和 `configurable` 时**丢弃调用方的 configurable**（重建为 `{thread_id}`）；而 `agent_name` 在 `_CONTEXT_CONFIGURABLE_KEYS` 白名单（services.py:195-208），放 `context` 会经 `merge_run_context_overrides` **转发进 configurable + context 两处**（services.py:257+）。放 configurable 会被静默丢弃 → run 回落默认 lead-agent。
   - **CSRF**：桥的 HTTP 调用非 CSRF 豁免（csrf_middleware 无 internal-token 旁路），必须镜像 `ChannelManager._get_client`（manager.py:735-740）：请求头加 `CSRF_HEADER_NAME` + `Cookie: {CSRF_COOKIE_NAME}={token}`，再叠加 `create_internal_auth_headers(owner_user_id=...)`（internal_auth.py:28）。否则每个状态变更请求 403 "CSRF token missing"。
   - **owner 作用域**：`X-DeerFlow-Owner-User-Id` 注入 owner_id，否则 run 落 `default` 桶 agent 解析失败。
3. **写 context 文件**：workspace 本地写 project-context 文件（模式复用 `_write_project_context` 契约：thread 沙箱路径 + JSON `{project_id, name, kind, sections_summary}`；实现在 workspace 内，不 import project）。
4. **prompt**：嵌入 section spec（从 `collab_sections` + context JSONB 拼装），指示 agent 用 `write_file`/`present_files` 产出 markdown + 写 **`.handoff.json`**（见 8.2）。

### 8.2 结构化 handoff 契约（评审修正：此前未定义）

- **载体**：agent 在 thread 沙箱 `outputs/` 下写 `.handoff.json`（与产出 md 同目录）。
- **Schema**（枚举对齐 `handoff_state` 4 值）：
  ```json
  { "state": "acked|progress|done|blocked",
    "progress_pct": 0.0,          // 0-1，progress 时必填
    "content_delta": "",          // 本次新增内容摘要
    "notes": "" }
  ```
- **映射**：`handoff_state` = `state`；`handoff_payload` = 整份 JSON。
- **无 `.handoff.json` 兜底**：run 结束但文件缺失 + **有产出 md** → 视 `done` 并记 `last_error` 提示；**无 handoff 且无任何 md 产出** → `blocked` + `last_error`；run 失败/超时 → `blocked`。

### 8.3 run 完成检测（评审修正：此前无机制）

- **workspace 内部 asyncio task 每 run 一个**：**轮询 `GET /api/threads/{thread_id}/runs/{run_id}`**（thread_runs.py:930，GET 无需 CSRF）直到 status 进入终态（`success/failed/error`），在 `collab_agent_runs.max_duration` 内。⚠ **不存在 `POST /runs/{run_id}/wait`**——网关的 `/runs/wait`（thread_runs.py:893）是 create+wait（会误建新 run），不得用于已存在的 run。完成后 `sandbox_sync` → 解析 `.handoff.json` → 更新 task → 触发闸门（含 deadline 检查）→ 写 `collab_agent_runs` + `collab_activity`。
- **生命周期**：task 记录 `thread_id/run_id` 到 `collab_agent_runs`；网关重启时从 `status='running'` 的 runs 行**rehydrate** 重等（幂等）。**rehydrate 遇 run 404/不存在** → 视为 spawn 失败：`attempt_count++`、`last_error`，走 §8.5 失败路径（不空转死 run_id）。
- **超时**：`collab_agent_runs.max_duration`（默认 1800s）→ `timed_out` → task `blocked`。

### 8.4 沙箱→文档同步（评审修正：不调 `sync_thread_files`，因其 import ProjectMember）

- workspace 本地 `sandbox_sync(db, project_id, thread_id, owner_id)`：
  - 定位 thread 沙箱 `outputs/` 目录（经 `Paths.sandbox_user_data_dir`，模式复用）
  - 读 `*.md` → 写 `ai_documents.content`（doc_type=`document`）→ 有 `doc_id`（quickdoc=项目 doc_id，report=各 section doc_id）则写 `collab_sections.content` 并重算 `word_count_current`
  - **不 import docmgr service**（其内部 import ProjectMember）；只经 SQLAlchemy 直接写共享数据表 + 调协编 REST 端点
  - **collab_versions 写入（评审修正）**：`collab_versions` 有 `UniqueConstraint(doc_id, version)`（collab_models.py:48-50）且版本号由 collab server 拥有（`SELECT MAX+1`）——workspace **不直接 INSERT 猜版本**，改调协编 REST `POST /api/extensions/docmgr/documents/{doc_id}/versions`（或同事务内 `MAX(version)+1`）。
- `revision` compare-and-set：写前比 section `revision`，冲突 409。

### 8.5 失败状态机（评审修正）

| 事件 | 处理 |
|---|---|
| thread 建失败 | `attempt_count++`、`last_error`，task 回 `pending`；连续 2 次如实报用户 |
| run spawn 失败 | 同上 |
| run 超时 | `collab_agent_runs.status='timed_out'`，task `blocked` |
| handoff 解析失败 | 保留原始输出，`last_error`，task `blocked`（coordinator reopen/reassign 解锁） |
| run 成功但 sandbox_sync 失败 | 记 `attempt_count++` + `last_error`，task 留 `in_progress`，可手动重试 |
| task `blocked` | 解锁 = coordinator reopen（`POST /projects/{id}/gates/{gid}/reopen`）或 reassign（`POST /projects/{id}/tasks/{tid}/assign`） |

---

## 9. 前端（照抄 AgentSpace 页面功能/操作/布局 + dashboard 样式）

### 9.1 页面映射

新模块 `src/extensions/workspace/`，路由 `/workspace/collab`。**页面功能操作与布局尽可能照抄 AgentSpace**（源为 AgentSpace `apps/web/app` + `features/`），样式套 `dashboard.css`（工作台风格）。

| AgentSpace 页面 | workspace 模块页面 | 照抄的布局/操作 |
|---|---|---|
| `task-board`（Kanban，按状态/负责人/优先级/群组分组 + 拖拽 + 统计行） | 任务板 `/workspace/collab/tasks` | 工具栏分组按钮、列 count 徽章、拖拽（仅状态模式）、紧凑模式状态 select |
| `approvals`（双栏审批队列，筛选 Tab + 状态徽章 + 内容预览 + 批准/驳回） | 审批 `/workspace/collab/approvals` | 筛选 Tab（全部/待审批/已批准/已驳回）、双栏 master-detail、审批意见 textarea |
| `agents?mode=showcase`（数字员工展板，卡片 + 搜索/筛选/排序 + 待我审批） | 数字员工（只读露出，#1 未实现则先展示 owner 自有 agent） | 卡片网格、就绪徽章、角色/摘要/skills 行 |
| `inbox`（双栏 feed + 执行时间线，任务状态按钮） | 任务动态 `/workspace/collab/inbox` | 筛选 pills、执行时间线、状态按钮（设为待开始/进行中/阻塞/完成） |
| `knowledge`（双栏 wiki 树 + 文档，master-detail） | 文档库 `/workspace/collab/docs` | 双栏、树/列表、筛选、打开协编 |
| `settings`（双栏设置，8 section） | 设置 `/workspace/collab/settings` | 左栏设置 rail + 右栏内容 |
| **Sidebar**（`workspace-frame.tsx`） | workspace 框架 | 分组可折叠 sidebar（含 count 徽章）、**signals 行**（打开任务/待审批/知识页）、底部账户入口 |

### 9.2 照抄的通用 UI 模式

- **双栏 master-detail** + `PaneResizeHandle`（默认 340px / min 300 / max 560；<860px 塌缩为列表/详情切换 + 返回按钮）
- **status-chip**（positive/warning/danger/neutral tone）— agent/任务/审批状态
- **GeneratedAvatar**（`variant: human|agent`）— 侧栏/列表/卡片
- **AppIcon** 图标系统 + **filter pill bars**（带 count）
- **EmptyState**（eyebrow + title + body + action，如"知识页为空"）
- **FeedbackToast + runAction** — 每次变更 toast + 刷新模块（React startTransition，"处理中…"）
- **Modal 模式**（overlay + wide/narrow + 主/ghost 按钮）
- **双语标签** zh/en + **auto-refresh 轮询**（任务/审批进行中时 2-3s）

### 9.3 具体实现要点（评审修正：零引用 extensions/project）

- 快速文档（Tier 1）= `CollabEditor`/`BlockNoteEditor` + 内联 AI menu（`aiMenuItems.tsx`）+ `useCollab`，样式套 dashboard token——**零新 AI 脚手架**。
- **任务板组件自维护**：不 import `extensions/project/components/KanbanBoard`（那会拖入写作项目模块的 types/props）。**vendor 独立副本**到 `src/extensions/workspace/components/KanbanBoard/`（EAI-CUSTOM 注释，workspace 自有），零 import 自 extensions/project。
- 导航：`extensions/shell/Sidebar.tsx` +1 行「协作工作台」；Tab 可见性用 workspace 自有 registry。
- **数字员工只读露出**：只读 `AgentStore` / agent `config.yaml`（`AgentStore.get_soul/list`），skills 索引/就绪状态/摘要富化**属于 #1**——边界写明。可选：威胁进度则砍掉。

---

## 10. 边界 / 错误 / 测试 / 上线

### 10.1 边界 & 错误

- **agent 桥**：见 §8.5 失败状态机。
- **并发写**：`collab_sections.revision` compare-and-set（publish-doc / agent 写回 / 手动编辑均比 version，冲突 409）；yjs 层负责协编文档自身的并发合并——`revision` 只保护 section 元数据/content 快照过渡。bridge 对同一 `doc_id` 只允许**一个 in-flight run**。
- **闸门死锁**：`deadline_at` + `escalation_rule`，惰性执行（GET gates / POST judge 时检查）；`evaluate_gate` wrapper 处理 agent 参与者语义（agent 完成自动批准，quorum=人类数）。
- **鉴权/参数/未找到**：401/403/422/404，沿用 gateway 既有中间件。
- **agent_name 不可解析**：4xx（owner 的 `users/{uid}/agents/{name}` 不存在）。
- **workspace 文档泄漏到个人文档空间**：workspace 文档 `ai_documents.project_id` 恒 NULL → 会出现在用户个人文档树。**缓解**：workspace 文档列表按 `collab_projects.doc_id` / folder 约定过滤展示，或保留专用 folder 前缀（实施时定）。

### 10.2 测试

- **后端 pytest**（`make test`）：tier 信号派生（S1/S3/S4）、任务指派（human/agent）、闸门 evaluate（gate 模式 + agent 参与者 + deadline 惰性）、agent 桥（thread spawn + run 时 agent 绑定 + handoff 解析 + 失败重试 + 超时）、sandbox_sync（不 import ProjectMember 的隔离验证）、publish-doc（per-section flush + revision 冲突 409）、访问控制（非成员 403）。
- **前端**：任务板/审批双栏渲染、tier 信号展示、owner vs 成员 UI 门控单测。
- **harness 边界测试** `tests/test_harness_boundary.py` 保持绿。

### 10.3 上线（全增量、零改既有模块）

1. 后端：7 表建表 + service + API（`system:access` 门）。
2. 前端：快速文档（Tier 1）先上线——doc 编辑器 + AI menu。
3. 开任务板 + 审批（Tier 2 数据 + 编排）+ agent 桥。
4. 数字员工只读露出、Sidebar +1 导航行。

### 10.4 文件清单

- **后端**：`app/extensions/workspace/{__init__,models,schemas,service,routers,tier,gate,agent_bridge,sandbox_sync}.py`；7 表建表走 `database.py::migrate_db`（`CREATE TABLE IF NOT EXISTS` 幂等，沿用 agent-registry 先例）；`gateway/app.py` 注册路由。
- **前端**：`src/extensions/workspace/{types,api,hooks,index}` + `components/`（WorkspaceFrame/Sidebar/TaskBoard(vendor)/ApprovalsQueue/QuickDocEditor/AgentShowcase/Inbox/DocsList/SettingsPane）+ `app/workspace/collab/**` 路由 + Sidebar +1 行 + import `dashboard.css`。
- 全程 `EAI-CUSTOM` 注释；提交 `main-dev-fork`。

---

## 11. 开放问题

1. **导航接入**：`shell/Sidebar.tsx` +1 行（最简） vs 模块自注册导航（完全隔离）。→ 倾向 +1 行（pragmatic）。
2. **quickdoc→report 物化**：S4 自动物化 `collab_sections` vs 显式 `promote-to-report` 操作。→ 倾向**自动物化**（sections 从 `##` 标题生成），`promote-to-report` 作为手动兜底。
3. **release 最小占位**：§2 已定"本轮实现最小占位"。完整发布管线（多签 UI/审计）留后续。
4. **workspace 文档隔离**：个人文档树泄漏缓解方案——专用 folder 前缀 vs 列表过滤。→ 实施时定，倾向专用 folder。

---

## 12. 后续子项目（母体重构全景，供上下文）

| # | 子项目 | 依赖 | 备注 |
|---|---|---|---|
| 1 | **Agent 注册表 / 数字员工看板** | 无 | 地基（已设计 2026-07-27，未实现） |
| **2** | **通用 Task + 指派**（本 spec） | 1 | 统一任务板 |
| **3** | **Agent 任务执行桥**（本 spec） | 1+2 | 派 agent 跑任务、产出回写 |
| **4** | **通用 Project 抽象**（本 spec） | 可与 2 并行 | 报告流变模块 |
| 5 | 治理整合（合并 3 套审批 + agent 行为门 + 审计） | 1 | 清技术债 |
| 6 | 工作台重做（AgentSpace 式总览） | 1,2 | 最后整合；**本 spec 的 workspace 页面即为 #6 的先行形态** |

> 每个子项目各自走 spec → plan → implement。本 spec 授权 #2/#3/#4 + 分层 Tier。

---

## 13. 决策日志

- **2026-08-01** 重构方向确认：参考 AgentSpace 做**完全独立** workspace 模块，不与现有写作项目模块耦合。（用户中途强调）
- **2026-08-01** 范围：全量 #2（Task+指派）+ #3（agent 执行桥）+ #4（Project 抽象）+ 分层 Tier；交付先 spec。
- **2026-08-01** Agent 身份 `agent_name` 先行；Tier 1 快速文档为默认；UI 照抄 AgentSpace 页面功能/操作/布局，样式用工作台（dashboard）。
- **2026-08-01** 复用边界：docmgr 数据表 + collab 端点 / review gate（纯函数）/ AgentStore 可复用；extensions/project + workflow/Temporal **零引用**；**不调 import ProjectMember 的现有 service 函数**。
- **2026-08-01** 评审修正 v2：agent 在 **run 时**绑定——`agent_name` 放顶层 `body.context`（`_CONTEXT_CONFIGURABLE_KEYS` 白名单，经 `merge_run_context_overrides` 转发进 configurable+context），**不放 config.configurable**（被 build_run_config 丢弃）；桥加 CSRF header+cookie（镜像 `ChannelManager._get_client`）；publish-doc 为 per-section 操作 + snapshot NULL 跳过 + revision CAS；handoff 契约 = `.handoff.json` 4 态 schema；闸门生命周期 + deadline 惰性执行 + 零人类防退化；`collab_sections.revision` 内容锁；沙箱同步本地实现（不调 sync_thread_files，collab_versions 版本号走 REST 或 MAX+1）；KanbanBoard vendor 副本；endpoint 统一嵌套 `/projects/{id}/...`；kind 仅经 promote-to-report（含 S4 自动物化）变更。
- **2026-08-01** 评审修正 v3：run 完成检测用 **`GET /api/threads/{thread_id}/runs/{run_id}` 轮询**（thread_runs.py:930）至终态，**不用不存在的 `POST /runs/{run_id}/wait`**（/runs/wait 是 create+wait 会误建新 run）；spawn-run body 的 `context` 在**顶层**（thread_runs.py:124）；`/handoff` 端点仅供协调者手动记录（agent 走 `.handoff.json` 文件）；`POST /release` 内建 `scope=project_release` 闸门；S4 快照来源注明协编保存/发布写路径。
