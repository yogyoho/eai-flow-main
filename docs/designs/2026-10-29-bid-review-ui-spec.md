# 投标方案审查子系统 UI 设计稿(eia-p2 习语落地)

> 依据链:设计文档 `2026-10-29-bid-review-design.md` §4.9/§4.10 → 原型 `D:\eai\2026-10-12-eia-p2-ui.html` → 令牌规则 `docs/designs/ui-style-spec.md` → 裁决先例 cpa 2026-10-16(同一原型:**只取习语,不引令牌**)。
> 本稿是 Task 12 / Task 17 / Task 21 的视觉契约:照抄实现,**勿自创样式**;与本稿冲突处以本稿为准。

## 0. 总则:原型 → 系统令牌映射(裁决沿 cpa)

原型的色值/字号**一律不进代码**;取其结构、密度、信息组织习语,颜色走语义层 + EAI 状态色,字号走四角色档。

| 原型 | 系统实现 | 备注 |
|---|---|---|
| `--main-500/600`(主色) | `primary` | 系统深蓝,不引原型蓝 |
| `--main-50` 淡底 | `bg-primary/10` | pill/选中态配方 |
| `--second-600`(警示红) | `text-(--error-700)` | gate 致命数字;`--error-500`(#ff4d4f)作大字对比度不足,globals.css:331 已有深档 |
| `--success-700` 零值绿 | `text-(--success-700)`(#389e0d) | 同上,大字须深档;暗色自动反转(:416-434 已定义) |
| `--hairline` | `border-border` / `divide-border` | |
| `--gray-0` 卡底 | `bg-card` | 卡规范 §6:禁 `bg-background/bg-white` |
| `--gray-50` hover | `hover:bg-muted/50` | |
| text/text-2/text-3 | `foreground` / `text-muted-foreground` | text-3 弱化信息同用 muted-foreground,不再细分 |
| 20px 指标数字 | `text-2xl font-semibold tabular-nums` | 字号规范 §2 指标档;原型 11px 提示 → `text-xs`(微标签层豁免不含此处) |
| 13px 列表主文 / 12px 辅助 | `text-sm` / `text-xs` | |
| 圆角 8px 卡 / 6px seg | `rounded-lg` / `rounded-md` | 卡禁 xl/2xl(§6.5) |
| `shadow-pop` 抽屉 | shadcn Sheet/Dialog 内建阴影 | 勿手写 rgba 阴影 |

Tailwind CSS 变量语法:`text-(--error-700)`;若仓库既有代码用 `text-[var(--error-700)]` 形态则从众。**实现时先 Grep 仓库既有 -700 深档用法选一种**。

## 1. 共享基元

**复用 cpa(直接 import,勿复制第六份拷贝——ui-style-spec §8 已挂账五份拷贝无同步机制)**:
- `PageHeader` / `StatCard` / `ui/table.tsx` / `ui/bits.tsx`(`Pill`/`NoteBar`)
- 路径:`@/extensions/contract-price/components/...`(先读 cpa `DashboardView.tsx` 确认导出名再 import)

**新增四件(全部落单文件 `frontend/src/extensions/bid-review/components/primitives.tsx`,~120 行,零新依赖;不进全局 `ui/`,若后续模块复用再晋升)**:

### 1.1 SplitPane(split)
原型 `:199`:`.split{display:grid;grid-template-columns:264px 1fr;gap:12px;align-items:start}`
```
grid grid-cols-1 md:grid-cols-[264px_1fr] gap-3 items-start
```
左列列表行(fam-item 习语):`relative flex items-center gap-2 px-3 py-2 text-sm border-b border-border cursor-pointer transition-colors hover:bg-muted/50`;
选中态:`bg-primary/10` + 左缘指示条 `<span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />`;
行内计数:`ml-auto text-xs text-muted-foreground tabular-nums`。
左列容器 `max-h-[560px] overflow-y-auto`(原型值)。md 以下单列:列表在上、详情在下。

### 1.2 SegmentedToggle(seg)
原型 `:240-244`:inline-flex 边框容器,button 5px 14px 13px 字,active 淡主底主字。
```
容器:inline-flex rounded-md border border-border overflow-hidden bg-card
按钮:px-3.5 py-[5px] text-sm text-muted-foreground(非首个加 border-l border-border)
active:bg-primary/10 text-primary font-medium
```
真 `<button>` + `aria-pressed`,键盘可达。
**语义豁免登记**:ui-style-spec §7 规定模式互斥切换首选 ui/tabs 白底凸起形态,本稿按设计文档 §4.9 钦定用原型 seg 形态(用户"完全参照原型"裁决)——此为 §7 之外的**获准变体,来源=设计文档,勿向其他页面扩散**。

### 1.3 GateMetricsRow(gate1-m)
原型 `:256-261`:grid 横条,baseline 排,左 hairline 分隔,数值 20px/700 tabular。
```
容器:rounded-lg border bg-card overflow-hidden
内 grid:grid grid-cols-2 md:grid-cols-4 divide-x divide-border
格:flex items-baseline gap-2 px-4 py-2.5
数值:text-2xl font-semibold tabular-nums
标签:text-xs text-muted-foreground
右提示:ml-auto text-xs text-muted-foreground
```
颜色语义:致命>0 → `text-(--error-700)`;=0 → `text-(--success-700)`;其余 `text-foreground`。
用法:工作台顶条(致命/主要/次要/待人工)、报告概览(同四格)。**任务列表页不用此件**(§3.1)。

### 1.4 GroupCard(layer-card)
原型 `:305-315`:hairline 白卡 p-4 flex-col,clickable hover 边框主色。
```
卡:rounded-lg border bg-card p-4 flex flex-col gap-1.5
可点卡(hover 三件套缺一不可,§6.1):+ transition-all hover:border-primary/20 hover:shadow-md cursor-pointer
标题:text-sm font-semibold(§6 统一,不取原型 13px)
mono 副标(text-xs text-muted-foreground font-mono)
计数:text-2xl font-semibold tabular-nums(+ small:text-xs font-normal text-muted-foreground ml-1)
描述:text-xs text-muted-foreground
```
两用:规则库 L1/L3 分组卡(§3.4)、工作台左栏问题条(§3.2,行态压缩版)。

## 2. 状态 Pill 配方(全视图统一)

复用 `bits.tsx` 的 `Pill`(读签名后调用)。语义→色系映射(配方=ui-style-spec §3:亮 `-50` 底/深字/`-100` 框 + dark 变体;`text-warning` 禁作文字色,warning 系文字用深调):

| 语义 | 色系 |
|---|---|
| severity `fatal` / 任务 `failed` | error 系 |
| severity `major` / 任务 `awaiting_confirm` | warning 系(文字用深档,勿 text-warning) |
| severity `minor` / 任务 `running` | info 系 |
| severity `info` / 任务 `created`/`pending` | muted(`bg-muted text-muted-foreground border-border`) |
| 任务 `completed` / 复核 `confirmed` | success 系 |
| 复核 `false_positive` | muted + 删除线文本(问题条) |

> **勘误(2026-10-29,Task 12 修复轮)**:上表"任务 `completed`"为笔误——landed 后端状态
> 词汇是 `created|parsing|extracting|awaiting_confirm|running|done|failed`
> (`bid_review/models.py:30`,worker 终态成功落 `done`),词汇表里没有 `completed`。
> 按 landed 后端实现:任务 `done` → success"已完成"(`completed` 仅作前端兼容别名);
> `parsing` → info"解析中"、`extracting` → info"基准提取中"(表中原缺这两态)。

NoteBar 同理:基准未确认=warning 深字;可提交判定=success/destructive;免责声明=muted。

## 3. 五视图规格

### 3.1 任务列表(`bid:page:tasks`,/bid-review)——Task 12
习语映射(设计文档 §4.9):PageHeader + 指标格 + 密集表格。
- `PageHeader`:标题"投标方案审查",右上 `Button` 主按钮"新建审查任务"
- 指标格 = **4× `StatCard`**(cpa 习语,非 GateMetricsRow):总任务/进行中/致命未处理(数值 error 深档)/待人工;数据=GET /tasks 聚合
- 密集表格(`ui/table.tsx`):列 = 任务名 / 模式 Pill(quick/deep)/ 状态 Pill(§2 映射)/ 进度(meter 习语:`h-1.5 rounded-full bg-muted` 内 `bg-primary` 按 pct)/ 致命数(tabular-nums,>0 `text-(--error-700)`)/ 更新时间(`text-xs text-muted-foreground`)/ 操作(查看工作台)
- 表脚:`flex items-center gap-2 px-4 py-2 text-xs text-muted-foreground`(tbl-foot 习语)
- 状态:loading=表格骨架行;empty=`rounded-lg border border-dashed py-16`(§6.4)+ CTA 按钮;错误=表格上方 `NoteBar` destructive + 重试
- 交互:新建=`Dialog`(模式 SegmentedToggle quick/deep + 说明文字;上传版 M3 补);行点击 → `/bid-review/tasks/{id}`
  - **勘误(2026-10-29,Task 12 修复轮)**:新建 Dialog 自带招标/投标文件上传(必选)——POST /tasks multipart 是后端唯一文档入口,零材料任务会被后端 `_enqueue_docs` 无条件直推空跑;"上传版 M3 补"仅指工作台的补充/重传文档。

### 3.2 审查工作台(`bid:page:workbench`,/bid-review/tasks/{id})——Task 17,核心
习语映射:新 4 条全用 + Pill/NoteBar/meter。
- 顶条:任务名(`text-lg font-semibold`)+ 状态 Pill + mode SegmentedToggle(只读)+ 复核进度 meter
- `GateMetricsRow` 四格:致命/主要/次要/待人工(致命>0 数值 error 深档,=0 success 深档)
- 基准提示:基准未确认时页顶 `NoteBar`(warning 深字)"基准未确认——基准错误将批量产生错误结论";确认后移除或转 muted
- 主体 `SplitPane`:
  - **左=问题列表**(264px):顶部过滤器 SegmentedToggle ×2(层级 全部/L1/L3;判定 violation/need_human);列表=GroupCard 行态压缩版:规则 id(mono xs)+ severity Pill + 消息一行截断(`truncate`)+ 复核状态(确认→success 勾,误报→muted 删除线);选中态=§1.1 配方
  - **右=证据面板**(1fr):证据锚点 chip(src-chip 习语:`inline-flex items-center gap-1 h-[22px] px-2.5 rounded-full border border-border bg-card text-xs text-muted-foreground`,doc_id + p.页码,点击→原文坐标跳转);摘录块=`rounded-md border-l-2 border-primary bg-primary/5 p-3 text-sm`,违规数值/关键句高亮 `bg-primary/15`(violation)或 `bg-(--error-50)`(dark:`bg-(--error-100)/20`)——零硬编码;字段对照小表:rule inputs → 提取值(值右对齐 `font-semibold tabular-nums`)
  - need_human 问题:右栏顶部 `NoteBar` info"证据不足,需人工定位后补锚点"
  - **复核三连**(设计文档钦定):右栏底部操作条——确认(`Button` primary)/ 误报(`outline`)/ 改严重度(`outline` 开 Sheet);左栏条目只显示复核后状态,不放按钮
- 抽屉(问题详情/改严重度):shadcn `Sheet`,`w-[600px] sm:max-w-[600px]`(cpa 裁决);表单行 frm-row 习语:label `text-xs font-medium text-muted-foreground` + 控件全宽
- 交互:issues `useQuery` + 选中 id 本地 state;复核 mutation → invalidate;确认门 409 → toast"存在未复核致命项"

### 3.3 基准确认(`bid:page:baseline`)——Task 17
- `PageHeader` + 进度(已确认 n/总 m,meter)
- 密集表格:每行=一条义务——clause_id(mono)/ 义务文本 / 出处锚点 chips(§3.2 chip 习语)/ 类型 Pill / 修正 checkbox(`styled-checkbox` 既有习语);表头"全选"=批量确认
- 页顶 `NoteBar`(warning 深字):"基准错误将批量产生错误结论——逐条核对后再确认"
- 确认门:主按钮置底 sticky;点击触发后端 409 收紧逻辑

### 3.4 规则库(`bid:page:rules`)——Task 17
- 类型过滤用 **`FilterPills`**(共享组件,ui-style-spec §7 内容过滤语义;勿手滚)
- 分组网格:L1/L3 两组,组标题 `text-base font-semibold` + 计数;卡 = `GroupCard` 三列 `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3`
- 卡内容:规则 id(mono)+ 名称(`text-sm font-semibold`)+ 类型 Pill(det/sem/hyb)+ severity Pill + 开关(shadcn `Switch`,disabled 卡整体 muted)+ 统计行(命中/误报/采纳,`text-xs tabular-nums`)

### 3.5 报告(/bid-review/tasks/{id}/report 或任务详情 tab)——Task 21
- `GateMetricsRow` 四格(同 §3.2)
- 可提交判定提示行:fatal violation=0 → `NoteBar` success"未命中致命红线,可进入人工终审";>0 → `NoteBar` destructive"命中致命红线 N 项,建议整改后重新审查"
- 否决项命中表(密集表格:rule_id/layer/severity Pill/message/证据页码)
- 响应偏离表(L1-013 逐条 verdict:full/partial/none/unclear Pill;unclear 用 muted)
- 免责声明 `NoteBar`(muted):"本报告为辅助提示,最终责任由投标主体承担"
- 导出:`Button` outline ×2(md/html,M4 接)
- 雷达图:v2(设计文档裁决),本轮不实现

## 4. 暗色 / 可达性 / 响应式

- **暗色**:全 token 零硬编码;状态深档 token 的暗色反转 globals.css 已定义(:416-434),勿手写 `dark:` 覆盖深档数值;高亮块 `bg-(--error-50)` 须带 dark 变体
- **可达性**:seg/FilterPills 真 button + `aria-pressed`;表格 `th scope`;Sheet focus-trap(shadcn 内建);severity 不裸靠色——Pill 一律带文字,色盲安全;对比度:状态文字只用 -700 深档(§0 映射已定)
- **响应式**:SplitPane md 以下单列(列表上/证据下);GateMetricsRow `grid-cols-2` 折行;表格横向滚动(`ui/table.tsx` 既有行为);触达目标:列表行 py-2 + text-sm ≈ 40px+,达标

## 5. 落地任务映射

| 任务 | 交付 | 本稿依据 |
|---|---|---|
| Task 12 | 任务列表页(api/types/TasksView;PageHeader/StatCard/table/bits 直接 import cpa) | §2、§3.1 |
| Task 17 | 工作台/基准确认/规则库 + `primitives.tsx` 四基元 | §1、§3.2-3.4 |
| Task 21 | 报告视图 + 导出 | §3.5 |

基元验收:四件全部 token 化(零 hex/零原始灰阶类)、暗色可切、`pnpm check` 过。
