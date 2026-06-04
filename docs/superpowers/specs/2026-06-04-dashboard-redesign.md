# 工作台页面全面重设计方案

> 日期: 2026-06-04
> 状态: 待实施
> 范围: `frontend/src/extensions/dashboard/` + `backend/app/extensions/dashboard/`

## 背景

工作台页面（`/dashboard`）存在四个核心设计问题：

1. "今日待办"始终为空，即便用户已被分配任务
2. 头部四个按钮混合了动作和导航，语义不清
3. 消息通知使用 emoji 图标，按钮过小，UI 不够专业
4. "我的项目"标题样式与其他区域不一致

本方案对工作台进行全面重设计，解决以上所有问题并建立统一的设计基础。

## 设计基础

### DashboardCard 通用组件

所有区域统一使用 `DashboardCard` 包装组件：

```tsx
interface DashboardCardProps {
  title: string;
  icon?: LucideIcon;
  badge?: ReactNode;       // 标题右侧徽章
  action?: ReactNode;      // 标题右侧操作
  children: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}
```

统一样式 token：

| 属性 | 值 |
|------|-----|
| 圆角 | `rounded-xl` |
| 边框 | `border border-border` |
| 背景 | `bg-card` |
| 内边距 | `p-5` |
| 标题 | `text-sm font-semibold text-foreground` |
| 标题图标 | `h-4 w-4 text-muted-foreground mr-2` |
| 卡片间距 | `gap-5` |
| 阴影 | `shadow-sm` |

### 页面网格

```
┌─────────────────────────────────────────────────────────────┐
│  Header: 问候语 + 待办摘要 + 日期      [新建项目] [AI写作]  │
├──────────────────────────────────┬──────────────────────────┤
│  左列 (flex-1, min-w-0)         │  右列 (w-[320px])        │
│                                  │                          │
│  DashboardCard: 我的待办         │  DashboardCard: 快捷入口  │
│  DashboardCard: 我的项目         │  DashboardCard: 消息通知  │
│                                  │  DashboardCard: 我的统计  │
│                                  │  DashboardCard: 日程      │
└──────────────────────────────────┴──────────────────────────┘
```

- 响应式断点：`lg` 以下变为单列（右列移到左列下方）
- 左右列间距：`gap-5`

## 各区域设计

### 1. 页头 (Header)

**改动**：从"我的工作台"标题 + 4混合按钮 → 问候语 + 状态摘要 + 纯动作按钮

```
┌─────────────────────────────────────────────────────────────┐
│  早上好，Admin                                  2026年6月4日 │
│  今天有 3 项待办任务                                        │
│                                          [新建项目] [AI写作] │
└─────────────────────────────────────────────────────────────┘
```

- 问候语根据时间变化：`6-11` 早上好、`11-14` 中午好、`14-18` 下午好、`18-6` 晚上好
- 待办摘要从 `my-tasks` API 的 `total_count` 和 `urgent_count` 生成
- 动作按钮只有两个：**新建项目**（主按钮 `bg-primary text-primary-foreground`）+ **AI 写作**（次按钮 `border border-border`）
- 右上角显示中文格式日期

**移除的按钮**："项目看板"、"我的文档"移到快捷入口卡片

### 2. 我的待办卡片（原"今日待办"）

**改名**：`今日待办` → `我的待办`

**前端改动**：
- 卡片头部：`ListTodo` 图标 + "我的待办" + 逾期/紧急徽章
- 展示所有待办任务（不限制为"今日"），按后端优先级排序
- 逾期任务用红色左边框 `border-l-2 border-red-500` 标识
- 紧急任务标题旁显示 `!` 紧急标识
- 空状态：`"✨ 所有任务已完成"`，配合 `CheckCircle2` 图标

**后端改动**：
- 排查 `get_my_tasks()` 查询，确保三种任务来源（审核、撰写、阶段负责人）都正确关联到当前用户
- 验证 `ProjectMember.user_id`、`PhaseReview.reviewer_id`、`ProjectChapter.assigned_to` 的数据关联

### 3. 我的项目卡片

**改动**：包裹到 `DashboardCard`，标题样式统一

- 卡片头部：`FolderKanban` 图标 + "我的项目" + 项目总数徽章
- 标题降级为 `text-sm font-semibold`（与所有区域一致）
- 保持现有按角色分组（`GROUP_LABELS`）+ 折叠功能
- `ProjectMiniCard` 样式不变

### 4. 快捷入口卡片（新增）

**位置**：右侧边栏顶部

```
┌─ 快捷入口 ──────────────────────┐
│  ┌──────────┐  ┌──────────┐    │
│  │ LayoutGrid│  │FolderOpen│    │
│  │  项目看板 │  │  我的文档 │    │
│  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐    │
│  │ FileText │  │ Settings │    │
│  │ 模板中心 │  │   设置    │    │
│  └──────────┘  └──────────┘    │
└─────────────────────────────────┘
```

- `grid grid-cols-2 gap-3` 布局
- 每个格子：Lucide 图标（`h-5 w-5`）+ 文字标签，居中排列
- 格子样式：`rounded-lg border border-border p-3 hover:bg-accent transition-colors`
- 链接目标：`/projects`、`/documents`、`/projects?action=create`、`/settings`（或其他合适路径）

### 5. 消息通知卡片（美化）

**改动**：

a) **Emoji → Lucide 图标**：

| 原 emoji | 新图标 | 通知类型 |
|----------|--------|---------|
| 🚀 | `Rocket` | phase_start |
| 🔍 | `SearchCheck` | review_pending |
| ✅ | `CheckCircle2` | review_complete |
| 🎉 | `PartyPopper` | workflow_complete |
| ⏰ | `AlarmClock` | deadline |
| 💬 | `MessageCircle` | mention |
| 🔔 | `Bell` | 默认 |

b) **按钮放大**：图标从 `h-3 w-3` → `h-4 w-4`，点击区域从 `p-1` → `p-1.5`

c) **未读/已读区分增强**：
- 未读：左侧加 `border-l-2 border-primary` 竖条
- 已读：取消 `opacity-60`，改为 `text-muted-foreground`（更自然）

d) **卡片头部**：`Bell` 图标 + "消息通知" + 未读数圆点徽章 + "全部已读"文字按钮

e) **底部**：将"显示前 20 条"改为可点击的"查看全部通知"链接

### 6. 我的统计卡片

**改动**：从 4 行竖排 → 2×2 网格

```
┌─ 我的统计 ─────────────────────┐
│  ┌────────────┐ ┌────────────┐│
│  │ 📁 3       │ │ 🔍 2       ││
│  │ 进行中项目  │ │ 待审核     ││
│  └────────────┘ └────────────┘│
│  ┌────────────┐ ┌────────────┐│
│  │ ✏️ 5       │ │ ⚠️ 1       ││
│  │ 待编写      │ │ 逾期       ││
│  └────────────┘ └────────────┘│
└─────────────────────────────────┘
```

- 每个数据块：图标 + 大号数字 + 标签文字
- 各项保持原有颜色标识：primary、amber、blue、red

### 7. 日程卡片

保持现有 `MiniCalendar` 设计不变，仅统一包裹到 `DashboardCard`。

## 文件改动清单

### 新增文件

| 文件 | 用途 |
|------|------|
| `frontend/src/extensions/dashboard/components/DashboardCard.tsx` | 通用卡片组件 |
| `frontend/src/extensions/dashboard/components/QuickLinks.tsx` | 快捷入口网格 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/extensions/dashboard/DashboardPage.tsx` | 重写布局 + Header |
| `frontend/src/extensions/dashboard/components/TodayTasks.tsx` | 改名 + 重构为"我的待办" |
| `frontend/src/extensions/dashboard/components/MyProjects.tsx` | 包裹 DashboardCard |
| `frontend/src/extensions/dashboard/components/NotificationFeed.tsx` | 图标替换 + 按钮放大 + 未读样式 |
| `frontend/src/extensions/dashboard/components/StatsPanel.tsx` | 改为 2×2 网格布局 |
| `frontend/src/extensions/dashboard/components/MiniCalendar.tsx` | 包裹 DashboardCard |
| `frontend/src/extensions/dashboard/components/QuickActions.tsx` | 移除（功能拆分到 Header + QuickLinks） |
| `backend/app/extensions/dashboard/service.py` | 排查 my-tasks 查询逻辑 |

### 删除文件

| 文件 | 原因 |
|------|------|
| `frontend/src/extensions/dashboard/components/QuickActions.tsx` | 功能拆分到 Header 按钮和 QuickLinks |

## 不在范围内

- 通知偏好设置面板（保持现有设计）
- `NotificationPreferencePanel` 组件不变
- 后端新增 API 端点（只修复现有 `my-tasks` 查询）
