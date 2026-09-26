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

## 6. 偏离台账（记录在案，未修，待专项裁决）

| 项 | 位置 | 规模 |
|---|---|---|
| 原始调色板类 | `extensions/workflow/`（编辑器/监控） | 328 raw vs 165 token，零 dark: |
| 原始调色板类 | `extensions/project/ProjectCreateWizard.tsx` | 59 处 |
| 蓝灰 icon-badge 习语（无 dark:） | settings:41 / knowledge:399 / app-center:72 / contract-price PageHeader:19 / spare-parts DashboardView 等 | 6 处重复，可抽 IconBadge |
| `ui/table.tsx` 五份拷贝 | analytics 五模块 | 无同步机制 |
| 画布/图表内部 px 字号 | workflow nodes/edges、各 Chart 组件 | 有意保留 |
| `License` 页原始色 | `extensions/license/` | 26 处（独立锁定页，低优先） |
