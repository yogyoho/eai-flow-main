# 合同价格分析（CPA）UI 重构规范

> 来源：`D:\eai\2026-10-12-eia-p2-ui.html`（环评域数据工厂 P2/P3 高保真原型）。
> 本文先提取原型 UI 规范，再给出向本系统 token 体系的映射，最后列出 cpa 模块的重构落点。
> 原型中的 `.chrome` 左侧导航是评审框架，**明确标注非实现范围**，不在提取之列。

## 1. 原型设计令牌（提取）

| 组 | 值 |
|---|---|
| 主色 main | 靛蓝阶 `#4f46e5`(600) 为核心，50~1000 全阶 |
| 次色 second | 橙 `#f97316`(500)/`#ea580c`(600)，用于警示/未归并态 |
| 灰阶 gray | zinc 系 `#fafafa`→`#18181b`，`--text`=gray-900、`--text-2`=gray-600、`--text-3`=gray-500、`--hairline`=gray-200 |
| 状态 | success/error/warn/info 各 50/500/700 三档 |
| 等宽 | `--mono`（ui-monospace/Cascadia/Consolas）用于编号、代码、`.num` 数字列 |
| 阴影 | `--shadow-pop`（浮层专用，卡片不用阴影） |
| 暗色 | 全阶反转（原型 `.proto-dark`），机制=class 切换 |

**裁决（2026-10-16）**：原型令牌不整体引入。cpa 模块属"上游基准层"，按
`docs/designs/ui-style-spec.md` 只用语义层 + EAI 状态色；原型的**结构与密度习语**才是本次提取目标。
主色沿用系统 primary（深蓝 oklch 0.54 0.26 265.5），橙次色映射到 `amber-600 + dark:` 变体
（`text-warning` #faad14 对比度不足不作文字色——ui-style-spec §1 既有结论）。

## 2. 结构习语（本次提取并落地的 12 条）

| # | 习语 | 原型类 | 本系统实现 |
|---|---|---|---|
| 1 | **页头卡**：白卡 + 主色细网格底纹(1px 线/26px 网格，8% 透明) + 左实右透渐变遮罩 + 34px 图标容器(main-50 底) + 16px 标题/12px 副标题 + 右侧动作 | `.page-head` | `PageHeader`（细网格 `var(--color-primary)` linear-gradient，图标 `bg-primary/10`） |
| 2 | **指标格**：label 12px muted 上、数值 22px bold `tabular-nums` 下；accent 变体左侧 2px 主色竖条；warn 变体数值橙 | `.metric-cell` | `StatCard` 重写（去图标、tone=default/accent/warn） |
| 3 | **密集表格**：th 12px medium muted **非大写**；td 13px、`px-3 py-2`；行 hover gray-50；数值列右对齐 + `tabular-nums`；编号列 mono 12px | `.tbl` | `ui/table.tsx`（去 uppercase/tracking-wider，px-2→px-3） |
| 4 | **徽章 Pill**：20px 高圆角全圆、12px medium、语义色底 | `.pill` | 新 `components/ui/bits.tsx` `Pill`（primary/success/warn/error/gray/info 六 tone） |
| 5 | **筛选 chip**：28px 高、圆角 6px、带计数角标；激活 = 主色 50 底 + 主色字 + semibold | `.stage-chip` | shadcn `Tabs`/`Button` aria-pressed 已覆盖，不再造新件 |
| 6 | **说明条**：info 50 底、12px、圆角 6px、图标前置，页底放置 | `.note-bar` | `bits.tsx` `NoteBar` |
| 7 | **卡片头**：标题 14px semibold + 副标题 12px muted + 右侧动作，底部 hairline | `.card-hd` | shadcn `CardHeader` 现状即满足 |
| 8 | **进度条**：5px 高圆角、muted 底、主色填充、低值橙 | `.meter` | TasksView 既有 h-1.5 进度条对齐即可 |
| 9 | **数字排版**：数值列 `tabular-nums`、编号列 mono 12px | `.num`/`.mono` | 各视图已有，全局贯彻 |
| 10 | **表脚说明**：表格底部 12px muted 说明行 | `.tbl-foot` | 既有分页/计数行沿用 |
| 11 | **紧凑页距**：screen padding 20/24px、块间距 12px | `.screen` | 页容器 `p-8 space-y-6` → `p-6 space-y-4` |
| 12 | **弹窗/抽屉**：右缘抽屉 600px 级、弹窗 560px 级、遮罩 black/45 | `.drawer`/`.modal` | shadcn Dialog + 现有抽屉骨架，不动 |

## 3. cpa 模块落点清单（2026-10-16 执行）

**共享基元（改动自动传播到全部 8 视图）**
- `components/PageHeader.tsx` — 习语 1
- `components/StatCard.tsx` — 习语 2（API：`{label, value, hint?, tone?}`，icon/color 参数移除）
- `components/ui/table.tsx` — 习语 3
- `components/ui/bits.tsx`（新增）— 习语 4/6

**视图扫**（习语 9/11 + 徽章替换）
- `DashboardView` 手写页头 → 共享 `PageHeader`；指标卡 tone 化
- `ClustersView` 状态徽章 → `Pill`；统计四格 → 指标格样式
- `ContractsView` 裸表头去大写、行距收紧；docStage 徽章 → `Pill`；⚠ 提示 chip → `Pill warn`
- `ItemsView` STATUS_TONE → `Pill`；行 hover/选中色从 blue-* 换 muted/primary 语义 token
- `TermsView` SourceBadge → `Pill`；StatCard 调用点去 icon/color
- `TasksView` / `SettingsView` / `LibraryView` — 页距收紧，余自动继承

**排除区**（不改动）：`GoodsAnalysis`/`BoxPlot` 图表内部（图表=布局敏感区，ui-style-spec 既有排除）；
各抽屉/弹窗（习语 12 现状即同构）；模块级顶部 tab 导航（原型 chrome 非实现范围）。
