# 项目概览 Tab 重设计 + Tab 合并

> 日期: 2026-06-04
> 状态: Approved
> 涉及文件: `frontend/src/extensions/project/` 目录下多个文件

## 背景

项目详情页存在以下设计问题：

**概览 tab 内部问题**：
1. "进入对话"按钮与 header 右侧按钮重复
2. 标题 + reportType badge 与 header 重复
3. "章节数"和"字数进度"统计不合理 — 章节动态变化，字数目标不可靠
4. 章节进度状态缺乏自动推断机制，进度计算方式不清晰

**Tab 结构问题**：
5. "流程看板"是独立 tab，但其信息本质上是项目全貌的一部分
6. "项目设置"包含的基本信息和成员管理与概览重叠
7. 5个 tab 对用户造成认知负担

## 设计决策

### Tab 合并策略

| 原始 Tab | 处理方式 | 理由 |
|----------|----------|------|
| 项目概览 | **扩展** — 吸收流程进度、成员管理、基本信息 | 信息天然属于"全貌" |
| 流程看板 | **合并** — 精简版入概览，完整版 Dialog 展开 | 进度是概览核心信息，画布太大需精简 |
| 项目设置 | **拆分** — 成员管理入概览，其余入 ⚙ Dialog | 低频管理操作不应占独立 tab |
| 审核工作台 | **不变** — 保持独立 tab | 独立工作面，合并会降低审核效率 |
| 文档编辑 | **不变** — 保持独立 tab | 核心编辑工作面 |

合并后：**3个 tab + ⚙ 图标入口**

### 状态自动推断 — 混合方案

不纠结于字数百分比进度，改为 **自动状态推断 + 活跃度标记**：

- **待编写 → 编写中**：自动（检测 `wordCountCurrent > 0`）
- **编写中 → 审核中**：由工作流或用户手动触发
- **审核中 → 已完成**：由工作流或审批人确认

### 进度展示 — 去掉百分比

- 去掉不可靠的 `wordCountCurrent / wordCountTarget` 百分比
- 用活跃度标记替代：`updatedAt` → "刚刚编辑" / "2小时前" / "3天前"
- 总字数降级为纯参考信息，不带目标和百分比

### 流程进度 — 完全数据驱动

流程节点 **不硬编码**，完全从 `WorkflowStatusResponse` 动态渲染：
- 节点名称来自 `WorkflowNodeStatus.label`（后端返回）
- 节点状态来自 `WorkflowNodeStatus.status`（后端返回）
- 不同项目可以有完全不同的流程节点和名称

---

## Header Tab 结构

### 改动前（5个 tab）
```
[项目概览] [流程看板] [文档编辑] [审核工作台] [项目设置]
```

### 改动后（3个 tab + ⚙ 图标）
```
[项目概览] [文档编辑] [审核工作台]              [⚙] [进入对话]
```

- ⚙ 图标仅在用户有 `settings:edit` / `project:edit` / `project:delete` 权限时显示
- 点击 ⚙ 打开 SettingsDialog（项目名称、状态、删除项目）

---

## 概览 Tab 详细设计

### 1. Header 区域（删除重复元素）

**删除**：
- "进入对话"按钮
- `project.name` 标题
- `reportType` badge
- `project.status` badge

**替换为**：
- `h2` 标题"项目概览"
- 保留创建时间

### 2. 统计卡片

| 改动前 | 改动后 | 理由 |
|--------|--------|------|
| 章节数 (`chapterCount`) | 活跃章节 (`3/8`) | 总数无意义，活跃数反映真实进展 |
| 成员数 | 成员数（不变） | — |
| 文件数 | 文件数（不变） | — |
| 字数进度 (`78%`) | 已写字数 (`15,200`, 累计) | 去掉不可靠的百分比 |

"活跃章节"计算：`flattenChapters(chapters).filter(ch => inferStatus(ch) === "writing").length` / `total`

### 3. 章节状态分布汇总条

在统计卡片和章节列表之间，新增一行：

```
● 待编写 3   ● 编写中 3   ● 审核中 1   ✓ 已完成 1
```

颜色：灰色(待编写)、蓝色(编写中)、琥珀色(审核中)、绿色(已完成)。

### 4. 流程进度精简版（数据驱动）

**从 `WorkflowStatusResponse.nodes` 动态渲染水平步骤条**：

```
✓ 资料收集 → ✓ 现状调查 → ▶ 影响预测(2/5) → ○ 措施建议 → ○ 审批
```

- 节点名称来自 `WorkflowNodeStatus.label`
- 节点状态来自 `WorkflowNodeStatus.status`
- 附加信息（如章节进度 `2/5`）来自 `chapterTotal` / `reviewTotal` 字段
- 不同项目可显示完全不同的节点

**显示条件**：项目有关联 `workflowId` → 显示；无 → 不显示不占空间

**"查看详情 →"按钮**：打开全屏 Dialog，内嵌完整 `WorkflowProgressView` ReactFlow 画布

**数据源**：
- `workflowGraph` 已在 `ProjectWorkspace` 中加载
- `useWorkflowStatus` hook 提供实时状态（概览用 30s 轮询，详情用 5s）

### 5. 章节状态自动推断

```ts
function inferStatus(ch: ProjectChapter): "draft" | "writing" | "review" | "completed" {
  if (["completed", "approved", "signed"].includes(ch.status)) return "completed";
  if (["in_review", "pending_review"].includes(ch.status)) return "review";
  if ((ch.wordCountCurrent ?? 0) > 0) return "writing";
  return "draft";
}
```

### 6. 章节列表改造

**去掉**：
- 每行的 `Progress` 进度条
- 百分比数字

**新增**：
- 状态标签（带颜色的小 badge）
- 活跃度标记（基于 `updatedAt`）：
  - < 5分钟 → "刚刚编辑"
  - < 60分钟 → "X分钟前"
  - < 24小时 → "X小时前"
  - ≥ 24小时 → "X天前"

**看板视图**保留拖拽功能，状态映射改用 `inferStatus()`。

### 7. 项目成员（可管理）

**有权限时**（`member:add` / `member:remove`）：
- 成员区域顶部显示"添加成员"按钮
- 角色显示为下拉选择（owner 除外）
- 非成员行显示删除按钮

**无权限时**：保持只读展示（现有行为）

**添加成员 Dialog**：从 SettingsTab 提取为独立共享组件 `AddMemberDialog`。

---

## ⚙ SettingsDialog

Header 齿轮图标点击后弹出 Dialog，仅包含：

- 项目名称（可编辑，需 `settings:edit` 权限）
- 报告类型（只读）
- 项目状态（可修改，需 `settings:edit` 权限）
- 创建/更新时间（只读）
- 删除项目（危险操作，需 `project:delete` 权限，需输入项目名确认）

无权限的用户看不到 ⚙ 图标。

---

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tabs/OverviewTab.tsx` | **重写** | 删重复、改统计、加状态分布、加流程精简版、成员可管理 |
| `ProjectWorkspace.tsx` | **修改** | 删 workflow/settings tab 渲染，加 ⚙ 按钮 + SettingsDialog |
| `tabRegistry.ts` | **修改** | 删除 workflow 和 settings tab 注册 |
| `components/WorkflowProgressCompact.tsx` | **新建** | 流程进度精简版（数据驱动） |
| `components/AddMemberDialog.tsx` | **新建** | 从 SettingsTab 提取的共享添加成员 Dialog |
| `components/SettingsDialog.tsx` | **新建** | 从 SettingsTab 提取的设置 Dialog |
| `tabs/SettingsTab.tsx` | **删除** | 逻辑已分散到概览和 SettingsDialog |

`types.ts` 无需改动 — `updatedAt`、`wordCountCurrent`、`status` 字段已存在。

## 不在范围内

- 后端 API 改动（章节状态自动推断纯前端计算）
- 审核工作台改动
- 文档编辑 tab 改动
- EditorTab 不变
