# 项目概览 Tab 重设计

> 日期: 2026-06-04
> 状态: Approved
> 涉及文件: `frontend/src/extensions/project/tabs/OverviewTab.tsx`

## 背景

项目详情页的概览 tab 存在以下设计问题：
1. "进入对话"按钮与 header 右侧按钮重复
2. 标题 + reportType badge 与 header 重复
3. "章节数"和"字数进度"统计不合理 — 章节动态变化，字数目标不可靠
4. 章节进度状态缺乏自动推断机制，进度计算方式不清晰

## 设计决策

### 状态自动推断 — 混合方案

不纠结于字数百分比进度，改为 **自动状态推断 + 活跃度标记**：

- **待编写 → 编写中**：自动（检测 `wordCountCurrent > 0`）
- **编写中 → 审核中**：由工作流或用户手动触发
- **审核中 → 已完成**：由工作流或审批人确认

### 进度展示 — 去掉百分比

- 去掉不可靠的 `wordCountCurrent / wordCountTarget` 百分比
- 用活跃度标记替代：`updatedAt` → "刚刚编辑" / "2小时前" / "3天前"
- 总字数降级为纯参考信息，不带目标和百分比

## 改动清单

### 1. 删除重复元素

**删除 overview tab 内**：
- "进入对话"按钮（header 已有）
- `project.name` 标题
- `reportType` badge（如 `fire_protection`）
- `project.status` badge

**替换为**：
- `h2` 标题"项目概览"
- 保留创建时间

### 2. 统计卡片重设计

| 改动前 | 改动后 | 理由 |
|--------|--------|------|
| 章节数 (`chapterCount`) | 活跃章节 (`3/8`) | 总数无意义，活跃数反映真实进展 |
| 成员数 | 成员数（不变） | — |
| 文件数 | 文件数（不变） | — |
| 字数进度 (`78%`) | 已写字数 (`15,200`, 累计) | 去掉不可靠的百分比 |

### 3. 新增：章节状态分布汇总条

在统计卡片和章节列表之间，新增一行汇总：

```
● 待编写 3   ● 编写中 3   ● 审核中 1   ✓ 已完成 1
```

每个状态有独立颜色：灰色(待编写)、蓝色(编写中)、琥珀色(审核中)、绿色(已完成)。

### 4. 章节状态自动推断函数

```ts
function inferStatus(ch: ProjectChapter): "draft" | "writing" | "review" | "completed" {
  if (["completed", "approved", "signed"].includes(ch.status)) return "completed";
  if (["in_review", "pending_review"].includes(ch.status)) return "review";
  if ((ch.wordCountCurrent ?? 0) > 0) return "writing";
  return "draft";
}
```

### 5. 章节列表改造

**去掉**：
- 每行的 `Progress` 进度条
- 百分比数字

**新增**：
- 状态标签（带颜色的小 badge）
- 活跃度标记（"刚刚编辑" / "X分钟前" / "X小时前" / "X天前"）

```tsx
function ActivityMarker({ updatedAt }: { updatedAt: string | null }) {
  if (!updatedAt) return null;
  const diff = Date.now() - new Date(updatedAt).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 5) return "刚刚编辑";
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes/60)}小时前`;
  return `${Math.floor(minutes/1440)}天前`;
}
```

### 6. 看板视图

- 保留现有 KanbanBoard 拖拽功能
- 状态映射改用 `inferStatus()` 自动推断
- 拖拽仍用于手动推进到审核/完成状态

## 涉及文件

| 文件 | 改动类型 |
|------|----------|
| `frontend/src/extensions/project/tabs/OverviewTab.tsx` | 重设计 |

`types.ts` 无需改动 — `updatedAt`、`wordCountCurrent`、`status` 字段已存在。

## 不在范围内

- 后端 API 改动（章节状态自动推断纯前端计算）
- 工作流集成（工作流进度条是独立功能，不在本次范围）
- header 改动（header 保持不变）
