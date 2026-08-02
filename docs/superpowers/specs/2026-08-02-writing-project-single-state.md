# 写作项目管理模块 · 单一状态集设计（ADR）

- **日期**: 2026-08-02
- **状态**: 设计定稿（待实施）
- **分支**: `main-dev-fork`
- **范围**: `extensions/project` 状态体系收敛 + `extensions/workflow` 进度游标降级 + 前端 / MCP / 技能契约对齐
- **验证**: 9-agent 工作流（5 消费者盘点 + 1 设计综合 + 3 对抗验证），验证发现已全部合入

---

## 1. 问题陈述

写作项目模块当前有 **3 套并行的进度机制** 和 **多套互不一致的状态词表**：

### 1.1 三套进度机制（同一行 `report_projects`）

| 字段 | 类型 | 取值 | 谁在推进 | 状态 |
|---|---|---|---|---|
| `status` | String(20) | `setup/outline/writing/editing/approval/in_progress/active/completed/archived` | `update_project`（唯一校验点）+ workflow/completion/finalize 等**绕过校验**的 writer | 活，但仅 1 处强制 |
| `current_stage` | Integer, default 1 | 1–6 | **无任何 writer**（三验证 agent 独立确认） | **死字段**，仅被 `get_project`/MCP/`ProjectOut` 读取并暴露给 agent |
| `current_phase_node` | String(50) | workflow DAG 节点 id（如 `phase-1`、`review-1`） | Temporal/workflow 引擎（init_phase/advance_phase/rollback） | 活，第二套推进机制 |

### 1.2 章节状态是自由字符串，四套词表并存

DB 列 `project_chapters.status` 是裸 `String(20)` 无约束。实际写入过的值：`pending/draft/writing/completed/approved/error/review/reviewed/in_review/editing/rejected/signed`。四套词表互不一致：

1. 状态机（`extensions/writing/state_machine.py`）：`pending→draft→completed→approved→error`
2. `_refresh_project_stats` 强写：`writing`（sync 后 clobber 一切信号）
3. MCP 白名单：`{pending, draft, completed}`
4. 前端 `inferStatus` 归并桶 / `StatusBadge`：`planning/finalizing/not_started/pending_review/signed`（部分值后端不存在）

### 1.3 根因

三代入积：Gen1 六阶段 `status` 状态机 → Gen2 workflow 图式推进（`current_phase_node`/`phase_node`/`phase_duties`）→ Gen3 agent 桥（死字段 `current_stage` + MCP 白名单）。每代因"别动现有模块"规则选择**加字段**而非重构。

---

## 2. 目标状态机（单一词表）

### 2.1 项目状态 —— 主轴 3 值 + 归档正交轴

| 状态 | 含义 | 覆盖现在的 |
|---|---|---|
| `draft` | 生产阶段（大纲/写作/协作编辑） | `setup / outline / writing / editing / in_progress / active` |
| `in_review` | 已提交审批 | `approval` |
| `approved` | 审批通过 = 完成 | `completed` |

**归档独立成正交字段 `archived_at`**（不占状态值）：status 保留归档前真实值，避免"归档即丢状态"。

转换（含 `approved→in_review` 重开，消除审批后单向陷阱）：

```
draft ──submit──▶ in_review ──approve──▶ approved
  ▲                  ▲                      │
  │                  └──reject/withdraw─────┘
  └────────────────re-open─────────────────┘
正交：* ──archive──▶ (status 原值保留 + archived_at 非空)
```

### 2.2 章节状态 —— 4 值

| 状态 | 含义 | 转换 |
|---|---|---|
| `pending` | 未开始（无内容） | → `draft` |
| `draft` | 编写中 / 有初稿 | → `reviewing`（提交审阅）/ `approved`（Tier 1 无审阅门直达） |
| `reviewing` | 已提交审阅 | → `draft`（退回+反馈）/ `approved` |
| `approved` | 审阅通过 | → `draft`（审批后大修，镜像项目级重开） |

- `rejected` **从状态降级为事件**：退回时章节回 `draft` 并挂审阅反馈（`last_review_verdict`），看板"退回修改"列由该字段驱动。
- `writing` **删除**：瞬态心跳（agent 中断会永久卡死），写入进行中由 `draft` + `updated_at` 表达。
- `error` **降为事件/记录**：AI 生成失败进 `ActivityLog`/重试待办，章节保持 `pending/draft`。

### 2.3 成员角色 —— 复用既有唯一词表

收敛 `ProjectMember.role` 到 `models/role_permission.py::ProjectRole`（已声明 "ONE taxonomy for the entire system"）：

```
{owner, phase_lead, writer, reviewer, approver}
```

删除 `phase_duties.duty` 的 9 个 key（与 role 大面积同义：lead≈leader 等），duty 由 role 按阶段派生。

---

## 3. 派生 Stage（删除 `current_stage`）

`current_stage`（int）**删除**：无任何 writer（三验证独立确认）、前端零引用、却经 MCP `get_project` 向 agent 暴露永久错误的信号 `1`。

六阶段进度条 = 纯函数，输入仅 `project.status` + 章节状态聚合（**不含 word_count**）：

```
1 Setup    项目存在且无章节
2 Outline  outline_confirmed 标志未置（大纲是 flag，不拆 draft 状态）
3 Writing  任一章节 = draft
4 Collab   全部章节 ∈ {reviewing, approved}
5 Approval 项目 = in_review
6 Export   项目 = approved 且无章节回退到 draft
```

- **Precedence**: `approved` 最高；若任一章节离开 `{reviewing, approved}`，降级到章节驱动阶段（项目级 `approved→in_review` 保证不一致不持续）。
- **与 workflow 进度条的关系（声明为契约）**: `current_phase_node` 保留为 **DAG 游标**，驱动 `WorkflowProgressCompact`；派生 stage 驱动 SciFi 阶段条。**两者是独立 widget，任何组件不得混用。** 残余双信号从"意外"变为"声明过的契约"。
- **派生 stage 默认只在 `ProjectOut` 暴露**：`list_projects` 聚合查询取不到全章节状态集，要么扩聚合查询，要么列表只显示规范 status（不显示 stage）。

---

## 4. 关键语义决定

1. **`completed` 的消失 —— 最重要的决定**。前端 `OverviewTab.tsx:220 handleMarkComplete` 写 `completed`；`writing_activities.py:250` 让 AI 生成成功就把章节标 `draft`。若 phase 完成门是"非 pending"，**AI 一出草稿阶段就自动完成、零人工确认**（语义回退）。
   - **修法**: "标记完成"按钮改为写 `reviewing`（= 人工确认后提交审阅）；**phase 完成门 = `status ∈ {reviewing, approved}`**。人工确认语义原样保留，AI-draft（`draft`）不算完成。
2. **`_refresh_project_stats` 停止碰状态**（service.py:786,808 现在 sync 后强写 `writing`，是毁掉 agent/状态信号的元凶）。改为**只更新 `word_count_current`**；仅当章节为 `pending` 时可置 `draft`。
3. **`in_review` 必须有明确 writer**：新增/迁移"提交审批"动作，经唯一 `validate_project_transition` 置 `in_review`（现无生产代码路径）。
4. **workflow 图 `set_project_status` 加校验**（system_nodes.py:128-133 现为自由字符串）：白名单 + 默认 `approved`。
5. **归档独立为正交字段**：`archived_at`，status 保留原值。备选（若坚持单枚举）为 4 值 `*→archived` 终结桶，但必须补归档 writer + SettingsDialog 禁改归档项目（验证确认当前无 writer，`archived` 实际不可达）。
6. **大纲不拆 `draft`**：`outline_confirmed` 布尔 + 服务层闸门（未确认禁写）。

---

## 5. 删除 / 降级清单

| 项 | 处置 |
|---|---|
| `report_projects.current_stage` | **删**（死字段，原子发布） |
| 项目 `setup/outline/writing/editing/in_progress/active/completed` | 收敛进 `{draft, in_review, approved}` |
| 章节 `writing` | 删（瞬态心跳 + clobber 源） |
| 章节 `completed` | 拆解：内容完成→`reviewing`，定稿→`approved` |
| 章节 `error` | 降为事件/记录 |
| 章节 `rejected/editing/review/reviewed/signed/in_review/pending_review` | 删/降（`reviewing` 为规范值） |
| `project_members.role` 的 `manager/member/editor/writer/leader` | 收敛到 `ProjectRole` 5 值 |
| MCP 白名单 `{pending, draft, completed}` | 改 `{pending, draft, reviewing}`（agent 可发起/提交审阅；`approved` 仍禁写防自批） |
| `workflow/local_executor.py` | 死代码，标注 |
| `approval_workflows/records`、`template_status`、`ai_documents.status`、`activity_logs` | **保留**（各自独立域） |

---

## 6. 迁移方案

### 6.1 数据回填（穷尽 CASE + 前后审计）

```sql
-- 项目（修复三验证独立确认的 bug：approval 必须映射 in_review）
UPDATE report_projects SET status = CASE status
  WHEN 'completed' THEN 'approved'
  WHEN 'approval'  THEN 'in_review'
  ELSE 'draft' END
WHERE status <> 'archived';

-- 章节（CASE 必须穷尽，ELSE 兜底，否则非法值存活）
UPDATE project_chapters SET status = CASE status
  WHEN 'pending'    THEN 'pending'
  WHEN 'draft'      THEN 'draft'
  WHEN 'writing'    THEN 'draft'
  WHEN 'rejected'   THEN 'draft'
  WHEN 'editing'    THEN 'draft'
  WHEN 'in_progress' THEN 'draft'
  WHEN 'review'     THEN 'reviewing'
  WHEN 'reviewed'   THEN 'approved'
  WHEN 'in_review'  THEN 'reviewing'
  WHEN 'completed'  THEN 'reviewing'   -- 内容完成未定稿；定稿由 finalize 改 'approved'
  WHEN 'approved'   THEN 'approved'
  ELSE 'draft' END;

-- 成员角色
UPDATE project_members SET role = CASE role
  WHEN 'manager' THEN 'phase_lead' WHEN 'leader' THEN 'phase_lead'
  WHEN 'editor'  THEN 'writer'     WHEN 'member'  THEN 'writer'
  WHEN 'writer'  THEN 'writer'
  ELSE role END;

-- 迁移前后审计
SELECT status, count(*) FROM report_projects GROUP BY status;
SELECT status, count(*) FROM project_chapters GROUP BY status;
-- 断言只剩规范值；异常行在 ELSE 折叠前先登记
```

### 6.2 强制兜底：DB CHECK 约束（关键）

至少 5 个 writer 走 raw table update 绕过校验：`routers.update_chapter_status`、`routers.finalize_document`、`docmgr/finalize.py`、`review/rollback.py`、`review_activities.handle_rejection`。**单靠 service 层收不齐，必须加 DB CHECK 兜底**：

```sql
ALTER TABLE report_projects  ADD CONSTRAINT ck_project_status
  CHECK (status IN ('draft','in_review','approved'));
ALTER TABLE project_chapters ADD CONSTRAINT ck_chapter_status
  CHECK (status IN ('pending','draft','reviewing','approved'));
```

### 6.3 发布顺序（原子窗口）

`current_stage` DROP COLUMN 不可逆且锁重（ACCESS EXCLUSIVE + 表重写），必须**同一次发布**内完成：

1. 冻结枚举 + 唯一 `validate_project_transition`/`validate_chapter_transition`
2. 数据回填 + 审计
3. DB CHECK 约束
4. 修 writer：`_refresh_project_stats`（只更字数）、`finalize_document`、`update_chapter_status`、workflow `set_project_status` 校验
5. **DROP `current_stage`（列 + SQLAlchemy 模型 + `ProjectOut` + `mcp.py` handler 原子同删）**
6. MCP 白名单 `{pending, draft, reviewing}` + **`coal-eia` SKILL.md 原子同发**（唯一 `write_chapter` 消费方，先改 MCP 后改 skill 会拒绝在途 agent 的 `completed`）
7. 前端：`PROJECT_STATUS_LABELS`/`STATUS_COLORS` 缩并（TS 兜底报错）、`OverviewTab.handleMarkComplete`→`reviewing`、看板 reverseMap、删死组件 `ApprovalTab.tsx`/`StatusBadge.tsx`
8. 测试更新（见 §7 清单）
9. 重启 gateway → 验证 dashboard/todo/reminder/kanban/workflow-status → 跑一次真实 coal-eia agent 写入 + 一次 Tier-1（sync-docs）确认 AIDocument 生成

### 6.4 迁移后必改的漏网消费者（验证点名）

| 位置 | 现逻辑 | 改后 |
|---|---|---|
| `get_phase_board`（project/service.py:1297） | `c.status == "completed"` 计数 | `∈ {reviewing, approved}`（否则完成数永远 0） |
| `get_phase_status` wf_status（project/routers.py:905-916） | `== 'completed'`→completed；`== 'in_progress'`→running | `approved`→completed；`in_review`→running；`draft`+`temporal_workflow_id`→running |
| `todo_aggregator.py:73-83` | 重试桶 key 在 `error` | 重派生 `draft AND word_count=0` |
| `dashboard/service.py:126,293,361` | `IN ('draft','writing')` | `draft AND word_count_current > 0`（查询形态变化） |
| `notification_activities.py:203` | `IN ('draft','completed','approved')` | 定稿为 `{draft, approved}` |
| `OverviewTab.tsx:220 handleMarkComplete` | 写 `completed` | 写 `reviewing` |
| `finalize_document`（routers.py:1216） | 写 `completed` | 写 `approved` |
| `system_nodes.py:128-133 set_project_status` | 自由字符串 | 白名单 + 默认 `approved` |
| `present_files→docmgr` | 回调已注册（gateway/app.py:285）但 `fire` 零调用 | Tier-1 同步真实路径 = `POST sync-docs` / `/docmgr/sync-thread-files`，需实测验证 |

---

## 7. 消费者清单（证据，供实施引用）

### 项目 status 的 writer（绕过校验者需逐一改）
- `service.py:571` create_project → `active`
- `service.py:634` copy_project → `active`
- `routers.py:154` create_project（auto-start workflow）→ `in_progress`
- `workflow/routers.py:673` start_workflow → `in_progress`
- `service.py:1053` approval_action（全部通过）→ `completed`
- `workflow/system_nodes.py:133` CompletionNode → 图配置自由字符串（默认 `completed`）
- `docmgr/finalize.py:166` finalize_report → `completed`
- `workflow/temporal/notification_activities.py:268` notify_workflow_complete → `completed`
- `service.py:885-906` update_project → 唯一经 `validate_status_transition` 校验的路径
- `models/__init__.py:569` 列默认 `setup`（无 creator 使用）

### 项目 status 的 reader
- `service.py:158-159` list_projects `!= 'archived'` 过滤
- `service.py:173-174` status 查询参数过滤
- `routers.py:898-901` get_phase_status available_actions `in ("in_progress","active")`
- `routers.py:905-916` get_phase_status wf_status
- `workflow/routers.py:485,571,608` project_done `== 'completed'`
- `dashboard/service.py:166,245,302,310-312`
- `schemas.py:46-51` validate_status_transition

### current_stage（死字段，全量）
- writer：**无**。仅列默认（`models/__init__.py:570`、`database.py:803`）
- reader：`service.py:323` get_project、`mcp.py:213` _handle_get_project、`schemas.py:175`、`tests/test_project_mcp.py:98-108`、`scripts/test_kanban.py`（mock）
- 前端：**零引用**（grep 确认）

### 章节 status 的 writer / reader（要点）
- `service.py:685` copy_project → `pending`
- `service.py:786,808` _refresh_project_stats → `writing`（**clobber 源，必改**）
- `routers.py:474+` update_chapter_status（raw table update，接受任意 status）
- `routers.py:1216` finalize_document → `completed`
- `docmgr/finalize.py` execute_finalize → `approved`
- `review/rollback.py:60-62` execute_rollback → `pending`
- `workflow/review_activities.py:318-321` handle_rejection → `pending`
- 前端 reader：`SciFiProjectDetail`（phaseIndex 由 status 推导）、`KanbanBoard`（6 列含 `editing`）、`ProjectList`（STATUS_COLORS）、`inferStatus`（归并桶）

---

## 8. 验证记录（9-agent 工作流，wf_5ae1636d-dcb）

| 验证 | 结果 | 独立问题数 | 关键发现 |
|---|---|---|---|
| coverage | 已合入 | 5 BLOCKING + 8 | `in_review` 无 writer、`OverviewTab` 写 `completed`、phase 门语义回退、`_refresh_project_stats` clobber、成员角色无迁移 |
| migration | 已合入 | 11 | **迁移 SQL 自相矛盾**（`approval`→`draft` 与 `in_review` 本义冲突）、phase-done 谓词过粗、3 个漏网消费者、approved 单向陷阱、word_count 死输入、MCP 契约歧义 |
| simplicity | 已合入 | 13 | DB CHECK 兜底必需、章节 CASE 需穷尽、DROP COLUMN 原子性、SKILL.md+MCP 原子同发、list 聚合算不出 stage、前端死组件 |

三个验证 agent **独立一致**地确认：`current_stage` 无 writer、前端零引用、`approval` 迁移必须映射 `in_review`。

---

## 9. 遗留决策与风险

- **归档形态**：正交 `archived_at`（本 ADR 选定）。备选单枚举 4 值需补 writer + 禁改 + 接受丢状态。
- **phase 完成门**：`∈ {reviewing, approved}`（本 ADR 选定，保留人工确认）。备选接受 AI-draft 即完成（弱化正式管线闸门）。
- **成员角色**：`ProjectRole` 5 值（本 ADR 选定，复用既有唯一词表）。
- **Tier-1 路径**：简单报告（消防专篇/给排水）不经项目模块，走 `write_file → present_files → docmgr`；`present_files→docmgr` 同步回调实际未触发（fire 零调用），真实路径需以 `sync-docs` 实测为准。此路径与项目模块并存，**内容真相源统一到 docmgr**（见双存储对账条目）。
- **双存储对账**：`ProjectChapter.content` 与 `AIDocument` 的双写是本状态收敛之外的第二主题（commit 798eb600），本 ADR 仅约定"状态单一权威"，内容单一权威另立文档。
