# 投标报价分析(bid-quote)过滤条件增强 + 多家友商支持 设计

> 日期:2026-08-14
> 状态:已认可,待实现
> 关联前置:[2026-08-13-bid-quote-frontend-design.md](./2026-08-13-bid-quote-frontend-design.md)(bid-quote 初始模块设计,Route B 零后端增量)
> 方案:方案3 深度 —— 全局 + 每图双过滤器(维度自由组合)+ 货物级逐项下钻

---

## 1. 背景

bid-quote(投标报价分析)已上线:4 个罐装分析视图(投标总览 / 货物构成对比 / 按金额段中标率 / 项目报价对比)+ 查询页(3 tab)+ DrillDownModal 下钻。当前局限:

- 每个图表**无过滤条件**,只能看全量汇总,无法按项目 / 友商 / 自产外采切片
- 数据模型里**每项目仅 1 家友商**(`backend/scripts/seed_mock_market.py` 的 `COMP = "东方宏业"` 单常量),不符合现实(项目投标通常多家友商竞争)
- 缺少**自产/外采**维度的专项分析

用户要求:
1. 每个图表增加过滤条件:按项目 / 按自产外采 / 按友商
2. 数据模型支持多家友商(每项目 2-3 家)
3. 自产/外采三个分析维度都要(货物构成属性 / 自产·外购金额切换 / 投标自产率门槛),可新增图表

## 2. 目标与非目标

**目标**
- seed 支持多家友商(**零 schema 变更**)
- 4 个分析视图在多家友商下语义正确
- 全局过滤器(项目 / 友商 / 日期)+ 每图高级筛选(维度自由组合),合并规则无冲突
- 3 个自产/外采分析维度全部落地(2 新图 + 1 图增强)
- 货物级逐项自产/外购深度下钻
- 守住 **Route B 零后端增量**(纯前端拼只读 SQL,复用 `POST /data-sources/{sid}/query`)

**非目标**
- 不改 deer-flow 核心 / harness
- 不新建后端 router / 业务表
- 不改 data_source router(共享设施,影响 biz-pipeline / sales-personnel / spare-parts 三模块)
- 不重新设计图表视觉风格(沿用现有 cyber 风格保持一致;图表美化是独立任务)

## 3. 数据模型:多家友商 seed 改造

### 3.1 schema 不变
`mock_bid` / `mock_bid_item` 结构不动。`mock_bid` 已支持同 `project_name` 多 `bidder_name` 行:
```
mock_bid(bid_id TEXT PK, project_name, project_location, bid_date DATE,
         bidder_role TEXT, bidder_name, won BOOL, winning_price NUMERIC)
mock_bid_item(id SERIAL PK, bid_id FK→mock_bid ON DELETE CASCADE,
              goods_name, spec, quantity, unit, unit_price,
              self_amount DEFAULT 0, outsourced_amount DEFAULT 0, total_amount)
```

### 3.2 seed 改造(`backend/scripts/seed_mock_market.py`)
- `COMP = "东方宏业"` 单常量 → 友商池:
  ```python
  COMPETITORS = ["东方宏业", "华能重工", "中机国能", "江南重工", "海纳智造", "航天晨光"]
  ```
- 每项目从池中抽 **2-3 家友商**参与,各自报价 + 货物构成(每家友商货物自产/外购结构略异,体现各家优势不同)
- 每项目**仅 1 家 `won=true`**(中标方 = 我方或某家友商);其余参与方全部 `won=false`
- `bid_id` 命名保持唯一:`{project_slug}-{role}-{idx}`(我方 `ours`,友商按出现序 `c1`/`c2`/`c3`)
- TRUNCATE 顺序不变:`TRUNCATE mock_bid_item; TRUNCATE mock_bid RESTART IDENTITY CASCADE;`

### 3.3 数据故事(保留,扩充多家竞争)
| 项目 | 规模 | 中标方 | 参与友商(示例) |
|---|---|---|---|
| 华能铜川 | 小型 1850万 | 我方(自产核心设备) | 东方宏业、海纳智造 |
| 宁夏宝丰 | 大型 2650万 | 华能重工(自产大型塔器) | 华能重工、航天晨光 |
| 内蒙古久泰 | 中型 480万 | 中机国能(压价) | 东方宏业、中机国能、江南重工 |
| 大唐雷州 | 超大型 3200万 | 航天晨光(自产压缩机) | 华能重工、航天晨光 |
| 中天合创 | 微型 85万 | 我方 | 东方宏业 |
| 万华烟台 | 大型 2100万 | 江南重工(自产塔器) | 中机国能、江南重工、海纳智造 |

每项目其余友商流标,各自报价反映其货物自产/外购结构(大型设备自产率高、通用件外购)。

## 4. 四个罐装 SQL 多家友商语义复核

> 复核后 SQL 模板化进前端 `api.ts`,默认(无过滤)即下表 SQL;有过滤时由 `buildWhere()` 追加 WHERE。

### 4.1 `bid_summary` / 投标总览 —— 新增 `competitor_count`
多家友商下,competitor_bid/won 变多家汇总;新增友商家数列。
```sql
SELECT
  COUNT(DISTINCT project_name) AS project_count,
  COUNT(*) AS bid_count,
  COUNT(*) FILTER (WHERE bidder_role='ours') AS ours_bid,
  COUNT(*) FILTER (WHERE bidder_role='ours' AND won) AS ours_won,
  ROUND(100.0 * COUNT(*) FILTER (WHERE bidder_role='ours' AND won)
        / NULLIF(COUNT(*) FILTER (WHERE bidder_role='ours'), 0), 1) AS ours_win_rate_pct,
  COUNT(*) FILTER (WHERE bidder_role='competitor') AS competitor_bid,
  COUNT(DISTINCT bidder_name) FILTER (WHERE bidder_role='competitor') AS competitor_count,
  COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_won,
  ROUND(AVG(winning_price) FILTER (WHERE won), 2) AS avg_winning_price,
  MIN(bid_date) AS earliest_bid,
  MAX(bid_date) AS latest_bid
FROM mock_bid
```
> 注:`avg_winning_price` 改为仅中标价均值(`FILTER (WHERE won)`),多家下更合理。

### 4.2 `composition_compare_by_goods` / 货物构成对比 —— 主图按 role 聚合不变
多家友商在主图仍合并为 `competitor`。按具体友商拆分走前端拼 SQL(`bidder_name IN (...)`),模板:
```sql
SELECT
  i.goods_name,
  ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='ours')
        / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'), 0), 1) AS ours_self_pct,
  ROUND(100.0 * SUM(i.outsourced_amount) FILTER (WHERE b.bidder_role='ours')
        / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'), 0), 1) AS ours_outsourced_pct,
  ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='ours'), 2) AS ours_avg_unit_price,
  ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='competitor')
        / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor'), 0), 1) AS competitor_self_pct,
  ROUND(100.0 * SUM(i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor')
        / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor'), 0), 1) AS competitor_outsourced_pct,
  ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='competitor'), 2) AS competitor_avg_unit_price
FROM mock_bid_item i
JOIN mock_bid b ON i.bid_id = b.bid_id
GROUP BY i.goods_name
ORDER BY i.goods_name
```

### 4.3 `win_rate_by_segment` / 按金额段我方中标率 —— 仅我方,友商过滤用 EXISTS
仅统计我方,多家友商不影响分子分母。加"按友商过滤"时,用 EXISTS 限定"项目含选中友商才计入我方该标"。
```sql
SELECT
  CASE
    WHEN winning_price < 1000000 THEN '1_<100万'
    WHEN winning_price < 5000000 THEN '2_100-500万'
    WHEN winning_price < 20000000 THEN '3_500-2000万'
    ELSE '4_≥2000万'
  END AS amount_segment,
  COUNT(*) AS ours_bid,
  COUNT(*) FILTER (WHERE won) AS ours_won,
  ROUND(100.0 * COUNT(*) FILTER (WHERE won) / NULLIF(COUNT(*), 0), 1) AS ours_win_rate_pct
FROM mock_bid
WHERE bidder_role = 'ours'
GROUP BY amount_segment
ORDER BY amount_segment
```
> 友商过滤生效时,`buildWhere` 追加:`AND EXISTS (SELECT 1 FROM mock_bid c WHERE c.project_name = mock_bid.project_name AND c.bidder_role='competitor' AND c.bidder_name IN ('..','..'))`

### 4.4 `bqa_project_showdown` / 项目报价对比 —— competitor_price 改取中标友商价
原 `MAX(winning_price) FILTER (competitor)` 多家下取最高报价 ≠ 中标价,歧义。改为取中标友商价(每项目 won 且 competitor 唯一)。
```sql
SELECT
  project_name,
  MAX(winning_price) FILTER (WHERE bidder_role='ours') AS our_price,
  MAX(winning_price) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_price,
  BOOL_OR(bidder_role='ours' AND won) AS we_won,
  MAX(project_location) AS project_location
FROM mock_bid
GROUP BY project_name
ORDER BY MIN(bid_id)
```
> 我方中标时 `competitor_price` 为 NULL(无中标友商),合理。非中标友商报价不进主图,在下钻里看(§8.3)。

## 5. 过滤架构(方案3 + 冗余消化)

### 5.1 设计原则
方案3 要"全局 + 每图独立"。两套过滤器并存会冲突(图上维度与全局打架时谁优先)。消化方案:**全局作基础 WHERE,每图高级筛选叠加收紧**,合并规则无歧义。

### 5.2 FilterState(全局,仪表盘顶部 FilterBar)
```ts
interface FilterState {
  projects: string[];      // 选中 project_name;空 = 全部
  competitors: string[];   // 选中 bidder_name(role=competitor);空 = 全部
  dateFrom: string | null; // bid_date 起始(ISO yyyy-mm-dd)
  dateTo: string | null;   // bid_date 截止
}
const EMPTY_FILTERS: FilterState = { projects: [], competitors: [], dateFrom: null, dateTo: null };
```

### 5.3 ChartFilter(每图高级筛选,ChartFilterPopover)
```ts
type AmountSegment = 'lt100w' | '100to500w' | '500to2000w' | 'gt2000w';
type SelfAttribute = 'self_dominant' | 'outsource_dominant' | 'all';
interface ChartFilter {
  amountSegment?: AmountSegment;   // 金额段
  selfAttribute?: SelfAttribute;   // 自产属性
  goodsName?: string[];            // 特定货物
}
```
每图按适用维度启用子集(非所有图都支持全部维度,见 §5.5)。

### 5.4 `buildWhere(global: FilterState, chart?: ChartFilter): string`
纯函数,产出 SQL WHERE 子句片段(不含 `WHERE` 关键字,空过滤返回 `'1=1'`)。
```ts
function esc(v: string): string { return v.replace(/'/g, "''"); }

function buildWhere(g: FilterState, chart?: ChartFilter): string {
  const clauses: string[] = ['1=1'];
  // 全局:bid 级
  if (g.projects.length) {
    const list = g.projects.map(p => `'${esc(p)}'`).join(',');
    clauses.push(`project_name IN (${list})`);
  }
  if (g.competitors.length) {
    const list = g.competitors.map(c => `'${esc(c)}'`).join(',');
    clauses.push(`bidder_name IN (${list})`);
  }
  if (g.dateFrom) clauses.push(`bid_date >= '${esc(g.dateFrom)}'`);
  if (g.dateTo)   clauses.push(`bid_date <= '${esc(g.dateTo)}'`);
  // 每图:语义级
  if (chart?.amountSegment) {
    const seg: Record<AmountSegment, string> = {
      'lt100w':      'winning_price < 1000000',
      '100to500w':   'winning_price >= 1000000 AND winning_price < 5000000',
      '500to2000w':  'winning_price >= 5000000 AND winning_price < 20000000',
      'gt2000w':     'winning_price >= 20000000',
    };
    clauses.push(seg[chart.amountSegment]);
  }
  if (chart?.goodsName?.length) {
    const list = chart.goodsName.map(n => `'${esc(n)}'`).join(',');
    clauses.push(`goods_name IN (${list})`);
  }
  // 注:selfAttribute 不在此处理(本质是比例计算,不适合纯 WHERE 子句):
  //   货物构成图按查询返回的 ours_self_pct 做前端行过滤;
  //   自产率分布图的门槛线是渲染层高亮。见 §5.5 / §7。
  return clauses.join(' AND ');
}
```

### 5.5 各图过滤器适用维度
| 图 | 全局(项目/友商/日期) | amountSegment | selfAttribute | goodsName |
|---|---|---|---|---|
| 投标总览 KPI | ✓ | — | — | — |
| 按金额段中标率 | ✓(友商用 EXISTS) | — | — | — |
| 货物构成对比 | ✓ | — | ✓(item 级:`self_amount/(self+outsourced) >= 0.5`) | ✓ |
| 项目报价对比 | ✓ | — | — | — |
| 图B 自产vs外购 | ✓ | — | — | ✓ |
| 图C 自产率分布 | ✓ | — | ✓(bid 级:整标自产率) | — |

> `selfAttribute` **不进 SQL**:货物构成图按查询返回的 `ours_self_pct` 做前端行过滤;自产率分布图的门槛线是渲染层高亮。只有 `amountSegment` / `goodsName` / 全局三维度进 `buildWhere`。

### 5.6 合并规则
`每图最终SQL = SELECT模板 + ' WHERE ' + buildWhere(global, chart)`
- 全局 projects/competitors/date 作用于 bid 级
- 每图 chart 维度按该图语义级追加
- selfAttribute:货物构成图作用 item 级(HAVING 或子查询);自产率分布图作用 bid 级聚合
- **全局 + 每图 AND 叠加,每图只能收紧,不能放宽全局 → 无冲突**

## 6. 技术路线(Route B 零后端增量)

- 全走 `POST /data-sources/{sid}/query` body `{sql}`(已存在的只读查询端点,`assert_readonly_select` 守卫)
- 前端 `api.ts` 持 SQL 模板常量(§4 四个 + §7 新图)+ `buildWhere()`
- 过滤下拉选项取自 DB distinct 查询(`SELECT DISTINCT project_name`、`SELECT DISTINCT bidder_name WHERE role='competitor'`),`esc()` 转义后拼接
- 罐装 dataset 运行时调用统一替换为前端拼 SQL(无过滤 = 全量,即 §4 默认 SQL);`seed_mock_market.py` 里罐装 SQL 保留作"默认视图模板"来源,**不删**(向后兼容 + 文档)
- POST 端点在 CSRF Double-Submit 守卫下,`authFetch` 自动加 X-CSRF-Token

## 7. 新增分析图表(自产/外采三维度落地)

### 7.1 图A:货物构成对比 增强(自产属性切换)—— 维度 A
现有"货物构成对比"图加 `selfAttribute` 切换(全部 / 自产为主 / 外购为主):
- 自产为主:`self_amount / (self_amount + outsourced_amount) >= 0.5`
- 外购为主:`< 0.5`
切换后该图货物行集变化(item 级过滤)。UI:图卡内 segment toggle。

### 7.2 图B:自产 vs 外购金额对比(新)—— 维度 B
并排柱状(recharts BarChart,两 series)。视角切换(项目 / 货物),toggle。
- 项目视角:横轴 `project_name`,柱1 `SUM(self_amount)` / 柱2 `SUM(outsourced_amount)`(JOIN item+bid,按 project 聚合)
- 货物视角:横轴 `goods_name`,同(按 goods 聚合)
```ts
interface SelfVsOutsourceRow {
  label: string;        // project_name 或 goods_name
  self_amount: number;
  outsourced_amount: number;
}
```

### 7.3 图C:项目自产率分布(新)—— 维度 C
柱状/直方图。横轴项目(按自产率排序),纵轴 `self_rate = SUM(self) / (SUM(self) + SUM(outsourced))`。门槛线(默认 0.5,可拖),`>=` 高亮为"自产为主标"。
```sql
SELECT
  b.project_name,
  ROUND(100.0 * SUM(i.self_amount)
        / NULLIF(SUM(i.self_amount + i.outsourced_amount), 0), 1) AS self_rate,
  SUM(i.self_amount) AS total_self,
  SUM(i.outsourced_amount) AS total_outsourced
FROM mock_bid_item i
JOIN mock_bid b ON i.bid_id = b.bid_id
WHERE b.bidder_role = 'ours'
GROUP BY b.project_name
ORDER BY self_rate DESC
```
```ts
interface SelfRateRow {
  project_name: string;
  self_rate: number;       // 百分比 0-100
  total_self: number;
  total_outsourced: number;
}
```

## 8. 货物级深度下钻(方案3 独有)

### 8.1 下钻表增强
现有 `DrillDownModal` 结果表(动态列)对 item 级下钻增加列:`self_amount` / `outsourced_amount` / `self_pct`(`100*self/(self+outsourced)`)。修改对应下钻 SQL 的 SELECT 列。

### 8.2 下钻内二次筛选
下钻结果表上方加 `selfAttribute` 过滤(自产为主 / 外购为主 / 全部),**前端 filter**(结果已在内存,无需重查)。

### 8.3 项目报价对比图下钻 → 多友商对比
`bqa_project_showdown` 行点开 → 该项目**所有参与方**报价对比(不再是单一友商):
```sql
SELECT bidder_name, bidder_role, winning_price, won
FROM mock_bid
WHERE project_name = '<project>'
ORDER BY winning_price
```
中标方行高亮(`won=true`)。

## 9. 前端组件结构

在 `frontend/src/extensions/bid-quote/` 独立扩展内增强(**不动 dashboard/project/shell 核心**):
```
frontend/src/extensions/bid-quote/
├── api.ts          # 改:加 SQL 模板常量 + buildWhere() + distinct 选项查询
├── hooks.ts        # 改:各 hook 接 filters 参数;新增 useFilterOptions + 2 新图 hook
├── types.ts        # 改:FilterState / ChartFilter / 新图 row 类型
├── components/
│   ├── FilterBar.tsx            # 新:全局过滤器(项目/友商/日期多选)
│   ├── ChartFilterPopover.tsx   # 新:每图高级筛选(折叠 popover)
│   ├── DashboardView.tsx        # 改:挂 FilterBar + 各图接 filters + 2 新图卡
│   ├── QueryView.tsx            # 改:共享 FilterBar + tab 表格接 filters
│   ├── DrillDownModal.tsx       # 改:加自产外购列 + 二次筛选 + 多友商对比
│   ├── SelfRateDistChart.tsx    # 新(图C)
│   └── SelfVsOutsourceChart.tsx # 新(图B)
```
- FilterBar 状态由 DashboardView、QueryView **各自独立持有**(仪表盘与查询页过滤互不影响,无跨视图状态泄漏),通过 props 下发 filters + setFilters 给子图
- 各图组件接 `filters: FilterState` prop,内部调对应 hook
- ChartFilterPopover 接 `chart: ChartFilter` + `onChange`,挂在图卡右上角
- 沿用现有 cyber 视觉风格(颜色常量 BLUE/AMBER/GREEN/RED_55),新图配色一致

## 10. 测试策略

### 10.1 seed / SQL(后端脚本层)
- seed 重跑后断言:每项目恰 1 家 `won=true`;`competitor_count` 与实际参与友商家数一致;6 友商池均有出现
- 4 个模板 SQL 各跑一次,人工 + 断言核对多家语义(bid_summary.competitor_count、showdown.competitor_price = 中标友商价、win_rate 分母不受多家影响)

### 10.2 前端(`tests/unit/`,Rstest)
- `buildWhere` 纯函数单测:空过滤 → `'1=1'`;projects/competitors/date 各组合;chart amountSegment/goodsName;单引号转义(`O'Brien` → `O''Brien`)
- `useFilterOptions` 单测:distinct 选项正确返回
- 组件:`FilterBar` 渲染 + onChange 回调;`ChartFilterPopover` 折叠/展开 + 维度切换
- 现有 bid-quote 测试不回归

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 多家友商 SQL 语义错(showdown/segment) | TDD:每模板 SQL 先写期望断言再实现 |
| 全局 + 每图 WHERE 合并 bug | `buildWhere` 纯函数单测覆盖组合 |
| 过滤值含单引号(友商名/项目名) | `esc()` 强制转义 + 单测覆盖 |
| seed 数据一致性(每项目恰 1 won) | seed 后断言 |
| 友商过滤对"我方中标率图"语义混淆 | 文档明确 EXISTS 语义:筛选"有该友商参与的项目" |
| 全局/每图双过滤器用户困惑 | UI 默认每图折叠,跟随全局;展开才叠加;tooltip 说明 |

## 12. 落地顺序(TDD,每块独立可测可提交)

1. 多家友商 seed 改造 + 一致性断言
2. 4 SQL 模板化 + 多家语义复核 + 期望断言
3. `buildWhere` 纯函数 + 单测
4. `FilterBar` 全局过滤(DashboardView + QueryView 接入,distinct 选项)
5. 每图高级筛选 + 合并(`ChartFilterPopover`)
6. 图C 项目自产率分布
7. 图B 自产 vs 外购金额对比
8. 货物级下钻增强(自产外购列 + 二次筛选 + 多友商对比)

每步结束:`docker compose -p eai-docker restart frontend`(或 gateway 仅 seed 步骤),浏览器验证 + typecheck。
