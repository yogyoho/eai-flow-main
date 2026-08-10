# 项目详情页 · 入口态与分工视图设计（ADR）

- **日期**: 2026-08-10
- **状态**: 设计定稿（待评审 → 待实施）
- **分支**: `main-dev-fork`
- **范围**: `extensions/project` 前端 `OverviewTab`「章节进度」区块 + 项目新增 `assignment_strategy` 字段
- **继承/兼容**: 与 [2026-08-09 写作项目合并收敛 ADR](./2026-08-09-writing-project-consolidation.md) 的 Tier 模型方向一致（本设计的纯函数状态机是 Tier 派生的兼容子集），与 [2026-08-02 单一状态 ADR](./2026-08-02-writing-project-single-state.md) 的状态值词表不冲突。
- **门禁**: 本文档为设计，不含实现代码。

---

## 1. 背景与问题

用户在创建项目时选择了报告大纲，创建后进入项目详情页（`/projects/[id]` → `ProjectWorkspace` → `OverviewTab`），「章节进度」区块（`OverviewTab.tsx:376-432`）**立即把 `project.chapters` 渲染成完整大纲树**——即便此时一行内容都还没生成。

问题：
- **正确性（前瞻动机）**：产品意图是 AI 生成初稿时**允许改写大纲**（增删/重命名章节），最终结构可能与创建时选定的不同。进入即展示选定大纲树 = 展示一个**可能过时**的结构。> 注：该改写能力本身是 deferred 的独立 spec（见 §6）；当前代码（`writing_activities.py` 的 `start_ai_writing`）实为往固定大纲填内容。隐藏树的 UX 收益**与该能力是否落地无关**——即便今天 AI 不改结构，入口态用 CTA 引导也优于展示空树，且将来 AI-revise 落地时不会再有"过时树"问题。
- **体验**：未生成状态下展示一棵全空的章节树，缺乏引导，用户不知下一步该做什么。

流程进度（`WorkflowProgressCompact`）已能反映工作流节点，但「章节进度」区块与生成状态脱钩，总是静态铺开大纲。

---

## 2. 已确认的设计参数（brainstorming 结论）

| 决策点 | 结论 |
|---|---|
| AI 与大纲关系 | **AI 可改写大纲**。创建时选定的大纲是 AI 的*输入引导*，不是固定脚手架。隐藏树 = 防止显示过时结构（正确性动机）。 |
| 入口态内容 | 主 CTA「开始 AI 生成初稿」+ **流程说明**（AI 生成 → 人工修改确认 → 届时按策略分工）。不展示大纲树。 |
| 分工策略 | 两种：`by_chapter`（按章节）/ `by_role`（按职责）。在**创建向导**设置（默认 `by_chapter`），**项目设置**可改。在「人工修改确认」阶段应用。 |
| `by_role` v1 落地 | 「按职责」v1 落地为**按角色**（作者/审校/审批，跨全文各司其职），最贴合现有 `ProjectMember.role` 数据。`by_domain`（按专业领域）/ `by_phase`（按阶段）作为 enum 扩展位保留，不在 v1 实现。 |
| 生成触发 | 手动（既有 `start_workflow` 端点；`auto_start_workflow` 默认 `False`）。CTA = 把该能力浮上来，**不造新后端动作**。 |

---

## 3. 选定方案：状态驱动区块 + 极简后端（方案 A）

### 3.1 三个方案（已评估）

- **A（选定）**：把「章节进度」区块改成**由项目状态驱动的动态视图**（3 态状态机，纯前端从现成信号派生）+ 项目加一个 `assignment_strategy` 字段。CTA 接既有 `start_workflow`。AI 改写大纲机制 **deferred**。
- **B（否决）**：作为 2026-08-09 合并 ADR 的 Tier-1 落地，引入 Tier 派生纯函数。触面大、多阶段、风险高，对一个聚焦 UX 调整属过度建设。
- **C（否决）**：A + 本 spec 内同时建 AI 改写大纲机制（Temporal 生成流改写 + 回写 chapters）。耦合两件事、改生成流，除非现在就要让 AI 自由改大纲否则不必。

选 A 的理由：最小可行、低风险、与 Tier 模型与 AI 改写大纲两个 deferred 方向都前向兼容。

### 3.2 核心状态机

「章节进度」区块内容由一个 3 态状态机驱动。**用 `chapter.content` 是否存在作为生成中↔人工修改的分界线**，不去识别工作流里具体的「AI 生成节点 / 人工修改节点」类型：

| 状态 | 判定信号（现成） | 区块显示 |
|---|---|---|
| **① 未生成** `not_generated` | `project.temporalWorkflowId` 为空（工作流未启动） | 「开始 AI 生成初稿」主 CTA + 流程说明面板 |
| **② 生成中** `generating` | 工作流已启动，但**无任何章节有 content** | 生成进度 / 章节填充指示 |
| **③ 人工修改确认** `human_edit` | **至少一个章节有 content**（初稿已产出） | 分工视图（按 `assignment_strategy`） |

**为何用 `chapter.content` 做分界**：
- 健壮——不依赖节点 label/type/位置（随模板变）；`chapter.content` 非空是稳定物理事实。
- 语义准——「初稿已产出」恰是「人可以开始改」的充要条件。
- ponytail——零新机制，纯前端从 `project.chapters` + workflow status 派生。

**CTA 行为**：点「开始 AI 生成初稿」→ 调既有 `POST /api/extensions/workflow/projects/{project_id}/start-workflow`，body `{ "workflow_id": project.workflowId }`（`routers.py:639`）→ 后端写回 `temporal_workflow_id` → 状态自动翻到 ②。
- **复用 `project.workflowId`**（创建时绑定的工作流定义）；无 `workflowId` 的项目，CTA 置灰并提示「请先在设置关联工作流」。
- **后端自带防重复启动**（`temporal_workflow_id` 已设则 400，`routers.py:654`），与状态机天然一致——已启动即离开状态①。
- **权限**：该端点要 `WorkflowAdmin`。CTA 按 `identity` 权限网关（无权置灰/隐藏），与现有「阶段推进」按钮同一套权限判定。

**AI 改写大纲的承接**：本设计不含该机制，但状态③读 `project.chapters` 的*当前*值——无论创建时填的还是 AI 改写后回写的，UI 都一样。将来 AI-revise 落地只需回写 chapters，无需改本设计。

---

## 4. 各状态 UI 细节

### 状态 ① 未生成 — CTA + 流程说明
引导面板（不再是空树）：
- 主按钮「**开始 AI 生成初稿**」：`temporalWorkflowId` 为空时高亮可点；已启动置灰。
- 下方 3 步小时间线，让用户预期全程：
  1. AI 按所选大纲生成初稿（**可能调整结构**）
  2. 进入「人工修改确认」
  3. 按「{当前策略}」分工修改确认
- 策略名动态回显（如「按章节」），让用户知道分工方式已定、届时才出现。

### 状态 ② 生成中 — 进度指示
- 复用 `WorkflowProgressCompact` 已有节点流水线（running 节点 + `chapterCompleted/chapterTotal`）。
- 区块主体：「AI 正在生成初稿…」+ 章节填充进度（已有信号）；CTA 隐藏/置灰。

### 状态 ③ 人工修改确认 — 分工视图（按策略）
`chapter.content` 出现后才显示。**同一棵章节树，策略改变的是「分工叠加层」**：

- **`by_chapter`（默认）**：复用现有 `ChapterNode` 列表 / `KanbanBoard`（已显示 `assignedName` + 状态 `draft→reviewing→approved`）。每人认领/被分配若干章节，改完提交审核。→ 即把现有多章节视图**门控到状态③**，几乎零新 UI。
- **`by_role`**：成员**按角色分组**的职责板（作者组 / 审校组 / 审批组，跨全文各司其职），改/审/批按角色网关。v1 用现有 `ProjectMember.role` 渲染角色分组看板（最小新 UI）。

---

## 5. 改动清单

### 5.1 后端（极小，无新端点）
| 文件 | 改动 |
|---|---|
| `extensions/models/__init__.py:635` `ReportProject` | 加 `assignment_strategy: Mapped[str] = mapped_column(String(20), default="by_chapter", nullable=False)` + EAI-CUSTOM 注释 |
| `extensions/database.py` | 迁移：`ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS assignment_strategy VARCHAR(20) NOT NULL DEFAULT 'by_chapter'`（照搬既有 `IF NOT EXISTS` 风格） |
| `extensions/project/schemas.py` | `ProjectCreate`(:102) / `ProjectUpdate`(:150) / `ProjectOut`(:158) 各加 `assignment_strategy: Literal["by_chapter","by_role"] = "by_chapter"` |
| `extensions/project/service.py` / `routers.py` | create/update 透传字段（复用 `routers.py:154` auto_start_workflow 那段位置） |

CTA 不造新后端动作——调既有 `start_workflow` 端点。

### 5.2 前端
| 文件 | 改动 |
|---|---|
| `types.ts`(:49) `ReportProject` | 加 `assignmentStrategy?: "by_chapter" \| "by_role"` |
| `OverviewTab.tsx` | 把「章节进度」静态树区块 → **状态驱动渲染器**：抽纯函数 `deriveBlockState()`，按状态渲染 CTA 面板 / 生成进度 / 分工视图 |
| `ProjectCreateWizard.tsx` | 成员步骤加策略单选（默认 `by_chapter`） |
| `SettingsDialog.tsx` | 加同款单选 |
| `api.ts` | create/update payload 带 `assignmentStrategy` |

状态③ `by_chapter` 视图 = 现有 `ChapterNode`/`KanbanBoard` 原样搬进状态③分支；`by_role` = 新建角色分组看板。

### 5.3 状态推导 = 纯函数（可单测）
```
deriveBlockState(temporalWorkflowId, hasAnyChapterContent):
  temporalWorkflowId == null            → "not_generated"   // CTA 面板
  else if !hasAnyChapterContent         → "generating"      // 进度
  else                                  → "human_edit"      // 分工视图
```

---

## 6. 边界（本设计不含，但兼容）

- **AI 改写大纲机制** → 单独 spec。本设计状态③读 `project.chapters` 当前值，天然兼容回写。
- **Tier 模型** → 不引入。状态机是其兼容子集；将来 Tier 派生落地时本状态机可被其吸收。
- **`by_domain` / `by_phase` 分工** → enum 扩展位，v1 不实现。

## 7. 不做什么（scope guard）

- 不改 harness 核心（`deerflow.*`）——遵守 harness/app 边界。
- 不引入新模块 / 新依赖——本设计是减少复杂度（静态树 → 按需视图）。
- 不改状态值词表——2026-08-02 ADR 已收敛，本设计复用 `pending/draft/reviewing/approved`。
- 不动 contract_price 等其它扩展。
- 不重写工作流引擎——CTA 复用既有 `start_workflow`。

---

## 8. 测试

- **后端单测**：`ProjectCreate/Update/Out` 携带 `assignment_strategy`、默认 `by_chapter`；迁移加列带默认值；`by_role` 值被接受。
- **前端单测（rstest node 纯函数）**：`deriveBlockState` 真值表 3 态；CTA 可点 iff `temporalWorkflowId == null`。
- 纯函数无需 DOM 测试，符合 `frontend/AGENTS.md` 的 node vs happy-dom 项目约定。

---

## 9. 规范注释

全部改动在 app 层 `extensions/`（非 harness 核心），按 EAI-CUSTOM 规范加注释（docstring 声明 + 行内注释）即可，harness 边界零触碰。

---

## 10. 开放决策（实施时定）

| # | 决策 | 默认 |
|---|---|---|
| α | `by_role` 视图：独立角色看板 vs 在章节树上叠加角色筛选 | 独立角色看板（更清晰） |
| β | 切换策略是否重算已有章节指派 | 不自动重算（仅改叠加层），避免破坏进行中的工作 |
| γ | 状态②进度是否轮询 | 沿用 `WorkflowProgressCompact` 现有「mount 取一次、不轮询」策略，靠 `visibilitychange` 与事件刷新 |
