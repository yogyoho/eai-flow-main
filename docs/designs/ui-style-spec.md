# UI 样式规范（基准：deer-flow 对话页）

> 2026-09-26 全库扫描后沉淀。基准 = 对话页（`components/workspace/chats/`）；权威 token 定义 = `frontend/src/styles/globals.css`，EAI 加固 = `styles/eai-overrides.css`。

## 1. 设计 Token 体系（三层色彩）

| 层 | 内容 | 用法 |
|---|---|---|
| 语义层（上游 shadcn） | `background / foreground / card / popover / primary / secondary / muted / muted-foreground / accent / destructive / border / input / ring` + `chart-1..5` + `sidebar-*` | 页面默认只用这一层 |
| 中性色 | Yuxi 暖灰阶 `--gray-50..1000`（#f5f7f7→#151616，暗色全量反转） | 不要直接用 `gray-*/slate-*` Tailwind 原始类 |
| 主色 | `oklch(0.54 0.26 265.5)` ≈ #0746ff 深蓝；暗色仅提亮度（0.62）不换色相 | `primary` / `ring` |
| 状态色（EAI 扩展，合法 token） | `success`(#52c41a) / `warning`(#faad14) / `info`(#1890ff) / `error→destructive`(#ff4d4f)，Ant 系五档（-50/-100/-500/-700/-900） | 状态语义优先用；**注意 `text-warning`（#faad14）对比度不足，勿作文字色**，文字用 amber-600 一类深调 + `dark:` 变体 |

圆角体系：`--radius: 0.625rem`，派生 `radius-sm..4xl`（勿写 `rounded-[14px]` 类 arbitrary，除非隔离风格层内部）。

暗色机制：`.dark` class（`@custom-variant dark`）+ token 全量反转；`eai-overrides.css` 为所有 `var(--border)` 提供灰回退防 FOUC 黑边框——**该文件独立于上游同步，勿把规则内联回 globals.css**。

## 2. 字号规范（四角色，全站统一）

| 角色 | 类 | 备注 |
|---|---|---|
| 说明文字 / caption / 时间戳 / 表头辅助 | `text-xs text-muted-foreground` | 12px |
| 正文 / 按钮 / 输入框 / 表格单元格 | `text-sm` | 14px；shadcn `Button`/`Input` 默认即此档 |
| 副标题 / 区块标题 / 卡片标题 | `text-base font-semibold` | 16px |
| 页面标题 | `text-lg` ~ `text-xl font-semibold` | 18–20px |
| 指标大数字（仪表盘 metric） | `text-2xl`+ | 各模块仪表盘自定义，不强制 |
| 微标签层（例外） | `text-[10px]` / `text-[11px]` | **仅限**：React Flow 画布节点/连线、图表刻度、uppercase eyebrow 标签；页面常规 UI 禁用 |

字重：正文 `font-normal`，强调 `font-medium`，标题 `font-semibold`（勿用 `font-[650]` 类 arbitrary，已统一为 `font-semibold`）。

**2026-09-26 已执行的统一映射**（89 文件，排除画布/图表/编辑器内部）：
`text-[11px]/[12px]/[12.5px]→text-xs`；`text-[13px]/[14px]/[14.5px]→text-sm`；`text-[15px]/[16px]→text-base`；`text-[17px]→text-lg`；`text-[20px]→text-xl`；`font-[650]→font-semibold`。
排除区（有意保留 px 值）：`workflow/nodes|edges`、图表组件内部、`TiptapEditor`、`landing*`、`components/ui|ai-elements`（生成物）。

## 3. 对话页基准用法（新增页面对照此写）

- 布局：`ChatBox` 可调三栏；页头 `h-12` + `bg-background/80 backdrop-blur shadow-xs`；内容宽 `max-w-(--container-width-md)`（816px）
- 输入区 `rounded-2xl`；chips/徽章 `rounded-full border px-2 py-0.5 text-xs`
- 零硬编码色；条件类一律 `cn()`（`@/lib/utils`）
- 组件只用 `components/ui/`（shadcn）、`components/workspace/`、`components/ai-elements/`；**勿手滚 button/dialog/table**（shadcn `Button` 之外的手写按钮需有理由）
- 状态 pill 配方：亮色 `-50 底 / -600字 / -200框` + `dark:-950/40 底 / -300字 / -800框`；或语义恰配时直接 `bg-success/10 text-success border-success/20`（warning 除外，见上）

## 4. 全库三层格局与契约

1. **上游基准层**（token 原生，可作样例）：对话页、auth、settings、workspace 首页、shell、data-source、admin、app-center、eia-samples、knowledge-factory
2. **EAI 合法扩展层**：状态色 token、`admin-select`、`styled-checkbox`、五份拷贝的 `ui/table.tsx`（bid-quote/biz-pipeline/contract-price/geo-samples/spare-parts——约定式复制，改表格样式需五处同步或收敛到 `@/components/ui`）、`.font-cyber`（globals.css 全局定义，赛博风数字排版专用）
3. **模块自有风格层（有意保留，新页面不得效仿）**：
   - dashboard：`extensions/dashboard/dashboard.css` 的 `--db-*` 平行 token 体系（有暗色支持、内部自洽）
   - analytics 四模块（bid-quote / geo-samples / biz-pipeline / sales-personnel）：`chartTheme.ts` TS hex 常量 + inline style，**浅色单主题，原型即验收标准**，不随暗色切换
   - project 详情页：`cyber-*` 赛博主题层（`.cyber-scope` 作用域内）
   - landing-new：营销页独立 CSS

## 5. 新页面约定（硬规则）

1. 颜色只用 token（语义层 + 状态色）；禁止 `slate-/gray-/zinc--NNN` 原始类和 hex/rgba 类名
2. 字号只用第 2 节四档；禁止页面级 `text-[Npx]` arbitrary
3. 暗色必读过：每个写死的浅底色都要有 `dark:` 变体，或直接换 token
4. 按钮用 shadcn `Button`（`text-sm` 内建）；徽章用 `Badge`
5. 状态语义色：`success/warning/info/destructive`；`text-warning` 勿作文字色

## 6. Card 样式规范（2026-09-26 定稿，基准：项目管理页项目卡 ProjectList.tsx:519）

**基准 = 项目卡真实配方**（经真实浏览器 hover 计算样式验证）：

```
"group border-border bg-card hover:border-primary/20 flex cursor-pointer rounded-lg border transition-all hover:shadow-md"
```

- 圆角 **`rounded-lg`（10px，源码 `rounded-[10px]` 的 token 写法）**
- hover：`transition-all` + `hover:border-primary/20`（边框染主色）+ `hover:shadow-md` —— 三件套缺一不可
- 标题 `text-sm font-semibold line-clamp-1`，无悬停变色

### 6.1 可点击/列表卡片（主配方）

基准配方照抄；布局按内容选横向 `flex items-center gap-4 px-4 py-3` 或纵向 `flex-col p-4`。`cursor-pointer` 必带。

### 6.2 统计小卡（StatCard，ProjectList.tsx:446 变体）

`rounded-md border bg-card p-4`（或行式 `px-4 py-3`）+ 图标盒 `h-10 w-10 rounded-lg`；数值 `text-2xl font-semibold tabular-nums`。静态卡 hover 仅 `hover:shadow-sm`。**禁止硬编码 rgba 阴影**。

### 6.3 表单/内容大卡

shadcn `<Card>` 需覆写 `<Card className="rounded-lg gap-4 py-4">`；默认 rounded-xl 形态不再新增。

### 6.4 空状态

`rounded-lg border border-dashed py-16`。

### 6.5 禁止清单

- 卡底 `bg-background` / `bg-white` / `bg-muted`
- 卡片 `rounded-xl` / `rounded-2xl`（卡片圆角 = lg/10px；md/8px 仅统计小卡）
- `shadow-xl`、硬编码 rgba 阴影
- hover 用 `hover:bg-accent`、`-translate-y`；可点卡的 hover 配方之外自创透明度（/30 /35 /40 统一为 /20）

### 6.6 豁免层

dashboard `.db-card`、project 详情 `.themed-card-sci`、React Flow 节点、对话输入区 `rounded-2xl`。

### 6.7 现状偏离摘要（待逐页收敛）

- hover 三件套缺失/变体：`hover:border-primary/30·35·40·50`、纯 `hover:shadow-sm/md`、`-translate-y` → 统一基准三件套
- 圆角：`rounded-xl`/`rounded-2xl` 卡片 → `rounded-lg`
- 卡底：`bg-background`/`bg-white` → `bg-card`
- 阴影：硬编码 rgba 阴影（spare/contract StatCard 孪生）→ token 化
- 标题：非 `text-sm font-semibold` 的卡标题统一

## 7. Tab / 分类过滤习语决策表（2026-09-26 定稿）

**结论：形态不统一**。五种习语各自绑定不同任务语义，抹平反而损失信息。新页面按语义对号入座，**禁止发明第六种无语义变体**。

| 习语 | 适用语义 | 基准实现 | 备注 |
|---|---|---|---|
| 侧栏模块导航 tab | 模块/页面切换 | `TabNavigation.tsx`（KF）：`px-3 py-3 rounded-xl`，active `bg-secondary text-primary` + 左缘 `w-1 h-6 bg-primary` 指示条 | 竖排、带图标 |
| 白底凸起 segmented | 视图/状态互斥切换 | `components/ui/tabs.tsx` variant=default（`bg-muted rounded-lg` 容器 + active `bg-background shadow-sm`）；图标钮变体见 docmgr 视图切换（`bg-secondary rounded-md p-0.5` 容器，凹槽灰比 muted 深一档） | **键盘可达，优先用**；分组审核、docmgr 全部/收藏与视图切换同此语言 |
| 淡主色过滤 pill | 列表内容过滤 | **共享组件 `FilterPills`**（extensions/project/components）：`rounded-md px-3 py-1.5 text-sm`，active `bg-primary/10 text-primary` | 新页面一律复用组件勿手滚（workflow-admin 已并入） |
| 全圆计数 pill | 分类浏览（带数量） | `CategoryTabs.tsx`（app-center）：`rounded-full px-3 py-1 text-xs` + 内嵌计数徽章，active `bg-primary` 白字 | aria-pressed |
| 空心 segmented | 图标视图切换 | `rounded-sm border bg-card h-[30px]` 容器 + 图标钮 | 项目页视图切换 |

**语义红线**：内容过滤 ≠ Radix Tabs 的 tabpanel 语义——过滤场景用 pill/segmented 手滚或 Tabs 但知悉语义偏移（分组审核现状，容忍）。

## 8. 偏离台账（记录在案，未修，待专项裁决）

| 项 | 位置 | 规模 |
|---|---|---|
| 原始调色板类 | `extensions/workflow/`（编辑器/监控） | 328 raw vs 165 token，零 dark: |
| 原始调色板类 | `extensions/project/ProjectCreateWizard.tsx` | 59 处 |
| 蓝灰 icon-badge 习语（无 dark:） | settings:41 / knowledge:399 / app-center:72 / contract-price PageHeader:19 / spare-parts DashboardView 等 | 6 处重复，可抽 IconBadge |
| `ui/table.tsx` 五份拷贝 | analytics 五模块 | 无同步机制 |
| 画布/图表内部 px 字号 | workflow nodes/edges、各 Chart 组件 | 有意保留 |
| `License` 页原始色 | `extensions/license/` | 26 处（独立锁定页，低优先） |

## 9. OntoStudio 前端字号规范（2026-10-01 定稿）

OntoStudio（`ontostudio/frontend/`，Vite + Tailwind 4，令牌内联自持于 `src/index.css`，色板与主系统对齐）此前 82% 文字 ≤11px（250+ 处，含大量 `text-[10px]/[10.5px]/[11px]/[11.5px]` 魔法值），用户反馈「列表/panel/按钮/下拉框主文字太小」。已全量归位为三档阶梯：

| 档 | px | 类 | 用途 |
|---|---|---|---|
| 主内容 | 14 | `text-sm` | 列表记录、panel 正文、按钮、输入框/下拉框、表格单元格 |
| 次要 | 13 | `text-[13px]` | 卡片副标题、说明文字（OntoStudio 本地档；主系统同位用 `text-base` 16px，待用户看过实效再裁决是否拉齐） |
| 辅助 | 12 | `text-xs` | badge、时间戳、计数、图例 chip、画布叠加标签；**全站最小档** |

2026-10-01 已执行映射（19 文件 299 处）：`text-xs→text-sm`；`text-[10px]/[10.5px]/[11px]/[11.5px]→text-xs`；`text-[12px]→text-[13px]`。

**豁免区**（同 §2 微标签例外，有意保留小字号）：`explorer/graphTheme.ts` Sigma 画布 chip（zoom 分级渲染，chip 10/max 11、角标 badge 8 为单字母 I/T/P）、图表轴刻度（`OverviewPanel` AXIS 11px）、`OntologyCanvas` 边标签（11px，节点标签已 13px）。

**注意与 2026-08-06 偏好的张力**：用户曾在主系统排版模板编辑器要求 label 调小至 11px（紧凑表单偏好）。那是**输出扩展表单 label** 场景；本次是 OntoStudio **数据浏览主内容**场景，用户明确要求调大。两偏好并存不矛盾——勿拿本次结论反向「修复」主系统表单，也不要拿旧偏好缩回 OntoStudio。
