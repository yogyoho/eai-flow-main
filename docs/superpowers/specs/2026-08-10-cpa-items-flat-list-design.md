# 分项校验 Tab:去分组,改扁平列表 + 任务筛选

- **日期**:2026-08-10
- **状态**:Approved(设计评审通过,待写实现计划)
- **范围**:`frontend/src/extensions/contract-price/components/ItemsView.tsx`(单文件)
- **后端改动**:无

## 1. 背景与问题

「分项校验」tab(`ItemsView.tsx`,页头标题"合同中提取出的货物价格校验")目前按**数据抽取任务(run)**对货物列表分组,但实际只能看到最新一个分组。

### 根因:分页与分组的顺序冲突(pagination-before-grouping)

后端在 DB 层就完成了「新建时间倒序 + 分页」:

```
backend/app/extensions/contract_price/crud.py:384
stmt.order_by(CpaItem.created_at.desc()).offset(skip).limit(limit)
```

前端先按 `PAGE_SIZE=50` 取一页,**再**对这 50 条做客户端分组:

```
ItemsView.tsx:163   useItems({ skip: page*50, limit: 50 })   // 已分页的窗口
ItemsView.tsx:186   groupByRun(items, runs)                   // 对窗口分组
```

由于一次抽取任务是**批量插入**的,它的所有货物 `created_at` 都比上一次任务新 → 第 1 页 50 条几乎全是「最新一次任务」的货物 → `groupByRun` 只能聚出 1 个分组;翻到第 2 页又是另一次任务独占一页。**UI 暗示的"多任务分组总览"永远不会出现**。分组被当成了叠在分页之上的展示层,两者互相打架。

### 为什么分组的主轴定位本身也偏了

该 tab 的职责是**价格校验**(待核验项需用溯源对照原文后修正)。校验者的心智轴是:"哪些要复核 / 这份合同的 / 这种货物",而 `run_id` 是**溯源/运维轴**(审计、整批作废 `deleteItemsByRun`)——适合当筛选条件,不适合当页面的常驻骨架。

## 2. 决策:方案 A — 扁平列表 + 「来源任务」筛选

在三个候选方案中选择 A:

- **A(选定)**:去掉 `groupByRun`,扁平表格 + 「来源任务」下拉筛选 + 来源任务列 + 常驻整批作废。后端零改动(`listItems` 已支持 `run_id`,`deleteItemsByRun` 已存在)。
- **B(否决)**:可折叠任务区段 + 每组懒加载。最忠于分组语义,但复杂度显著上升(每组独立分页/懒加载、run 多了列表很长),且"按批查看"是低频诉求,YAGNI。
- **C(否决)**:扁平 + 「按任务查看」开关。两套渲染路径常年停在扁平档,维护成本不值。

**选 A 的核心理由**:扁平列表与 DB 的扁平排序天然对齐 → 分页缺陷自动消失;任务总览/整批管理另一入口 = 现有 Tasks tab,不重复造;改动集中在一个文件。

## 3. 详细设计

### 3.1 数据流(修复缺陷的关键)

新增 `runFilter` state,注入 `useItems`:

```ts
const [runFilter, setRunFilter] = useState<string>("all"); // "all" | run_id

const { data } = useItems({
  goods_name: applied || undefined,
  source_contract_no: contractFilter === "all" ? undefined : contractFilter,
  run_id: runFilter === "all" ? undefined : runFilter,
  only_outliers: onlyOutliers,
  validation_status: onlyReview ? "needs_review" : undefined,
  skip: page * PAGE_SIZE,
  limit: onlyReview ? 500 : PAGE_SIZE,
});
```

`useItems(params)` 是泛型透传(hooks.ts:59),无需改 hook。`useRuns({ limit: 100 })` 与 `useDeleteItemsByRun()` 已存在,直接复用。

### 3.2 UI 增补

**(a)「来源任务」下拉** — 筛选条上,紧邻现有「来源合同」`<Select>`:

```tsx
<Select value={runFilter} onValueChange={(v) => { setRunFilter(v); setPage(0); }}>
  <SelectTrigger className="w-[220px] h-9"><SelectValue placeholder="来源任务" /></SelectTrigger>
  <SelectContent>
    <SelectItem value="all">全部任务</SelectItem>
    {runs.map((r) => (
      <SelectItem key={r.id} value={r.id}>{formatRunLabel(r, r.id)}</SelectItem>
    ))}
  </SelectContent>
</Select>
```

复用现有 `formatRunLabel`(ItemsView.tsx:241)与 `runs`(ItemsView.tsx:183)。

**(b)「来源任务」列** — 表格新增一列(在「来源合同」之后):

- 顶部 `runMap = new Map(runs.map((r) => [r.id, r]))`(从 `runs` 派生,useMemo)。
- 每行单元格:紧凑显示 `抽取 MM-DD HH:mm`(派生自 `run.started_at`),完整 `formatRunLabel` 放 `title` tooltip;`run_id` 为空显示"未关联"。
- 列头:`<TableHead className="whitespace-nowrap">来源任务</TableHead>`。

> 跨历史扁平列表里,这一列让每行的溯源可见——用户确认这是必要的,保留。

**(c) 常驻「整批作废」按钮** — 筛选条内、`ml-auto` 与已选条同侧(已选条出现时让位到其左侧),常驻可见,删除目标永远明确:

- **已选某任务筛选时**:点击 → 直接弹确认「删除任务 `<label>` 的全部 N 条?」→ `deleteItemsByRun(runFilter)`。
- **"全部任务"时**:点击 → 弹确认框,框内含一个任务 `<Select>`(默认"请选择任务"),必须选一个任务后「确认」才可执行 → `deleteItemsByRun(选中的 run_id)`。
- 成功后 invalidate(`useDeleteItemsByRun` 已 `invalidateQueries({ queryKey: ["cpa"] })`),并 `setRunFilter("all")` + `setPage(0)`。

### 3.3 删除项

- `groupByRun` 函数(ItemsView.tsx:117-142)
- `groups` useMemo(ItemsView.tsx:186)
- `collapsed` / `toggleCollapse` state 与 handler(156、208-214)
- 分组头 JSX 与 `groups.map(...)` 整块(338-624 的分组包装),改为直接渲染单个扁平 `<Table>`
- 未在渲染中使用的 `confirmGroupDelete` state(159)

### 3.4 选择行为

- `toggleSelectAll` 的入参由"某 group 的 items"改为**当前页 `items`**;表头全选 checkbox 的 `indeterminate`/`checked` 基于当前页。
- `selected` Set 跨页保留的现有行为不变;翻页/改筛选时仍 `setSelected(new Set())`(与现有翻页一致)。
- 顶部已选条(314-329)的「批量确认校验」保留;**新增并列的「批量删除」**(对 `selected` 调 `batchDeleteItems`),与分组头里原有的批量删除等价。

## 4. 边界情况

- **`onlyReview`(仅看待核验)**:仍 `limit: 500` 不分页,扁平列出 ≤500 条 `needs_review` 项。改完之后这里能**跨任务**看到所有待核验项——正是核心使用场景 2,此前因分组+分页基本看不到全貌。
- **`run_id` 为空的历史数据**:在「全部任务」下正常显示,来源任务列显示"未关联";选具体任务时自然不出现(后端 `run_id == null` 不匹配)。
- **任务很多**(>100):`useRuns({ limit: 100 })` 已截断;若不足再调大。下拉与整批作废的 picker 共享同一 `runs` 列表。
- **空状态**:保持现有"暂无明细"。

## 5. 测试

- **单测**:`formatRunLabel` 是纯函数,保留;若存在 `groupByRun` 的单测一并删除。
- **手动 QA**(四个关键路径):
  1. 翻页能依次看到不同抽取任务的货物(不再被锁在最新一组)。
  2. 「来源任务」下拉选中某任务 → 列表只剩该任务货物;切回「全部任务」恢复。
  3. 常驻「整批作废」:有筛选时直删该任务;无筛选时弹 picker 选任务后删除。
  4. 「仅看待核验」打开 → 跨任务聚合所有 `needs_review` 项。
- **回归**:批量确认校验、单行修正、溯源抽屉、异常价格高亮、来源合同筛选均不受影响。

## 6. 不在本次范围

- Tasks tab 的任务总览/整批管理(已有,不改)。
- 后端排序/分页逻辑(保持 `created_at desc + offset/limit`)。
- 其他 tab(Dashboard / Clusters / Contracts / GoodsAnalysis)。
