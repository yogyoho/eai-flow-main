# 投标报价分析 · 仪表盘内容重构设计（三问框架 + DeepSeek 风格）

> 2026-08-15 brainstorming 定稿。三个原型区块（block1-overview / block2-pricing / block3-competitors）
> 均经用户浏览器确认"效果满意"，本 spec 是原型的一致化书面化。

## 1. 背景与目标

现有仪表盘 6 图全部是"结果归因"（输了为什么），缺"决策输入"（下次报多少）与"竞争情报"（对手是谁）。
本次重构为**三问框架**：单页三个可折叠区块，区块标题即使用者的问题：

1. **我们赢在哪、输在哪？**（归因——现有图为主，换肤）
2. **下次报多少？**（决策——2 张全新图 + 1 张迁入）
3. **对手是谁？**（情报——3 张全新图）

同时整体视觉从 cyber 暗色光晕风切换为 **DeepSeek usage 页风格**（暖白底/白卡细边/单主色蓝）。

已确认的关键决策：
- 三场景兼顾，优先级 决策 → 归因 → 情报。
- 数据量扩到 **2023–2025 三年、约 40 项目、120+ 投标行、6–8 家友商**（趋势/画像的统计意义底线）。
- **数据模型零新字段**：最终图表集全部可由现有 `mock_bid`/`mock_bid_item` 列推导
  （评标得分/业主等曾在澄清阶段考虑，最终图表集不需要——不加，YAGNI）。

## 2. 图表清单与归位（12 图）

### 区块① 我们赢在哪、输在哪？（归因）

| # | 图表 | 来源 | 设计变化 |
|---|---|---|---|
| 1 | KPI 行（5 卡） | 保留 | 同款白卡；每卡新增一行**同比/环比注脚**（如"较上年 +6.5pt"），主数字靠字重不靠颜色 |
| 2 | 按金额段 · 我方中标率 | 保留 | 换肤：单蓝柱、柱端 4px 圆角、去渐变；悬停看样本数 |
| 3 | **中标率时间趋势** | **新增** | 我方（主蓝折线+软面积渐隐）vs 友商（浅灰蓝弱化线）按季度双折线 |
| 4 | 货物自产率对比 我方 vs 友商 | 保留 | 换肤（我方蓝/友商琥珀） |
| 5 | 整标自产率分布（门槛滑杆） | 保留 | 换肤，交互不变 |
| 6 | 自产 vs 外购金额 | 保留 | 换肤，交互不变 |

### 区块② 下次报多少？（决策）

| # | 图表 | 来源 | 设计变化 |
|---|---|---|---|
| 7 | **胜率–溢价曲线** | **新增** | 横轴=我方报价相对该项目中标价的溢价率固定 6 桶（≤−5% / −5~0% / 0~+3% / +3~+6% / +6~+10% / >+10%），纵轴=胜率柱；红色虚线标**拐点**（首个胜率腰斩桶界）；每桶下注 n= 样本数 |
| 8 | **报价区间建议** | **新增** | 每金额段一行的区间条图：蓝带=历史中标价 **P25–P75**、绿竖线=**成本底线**（Σself_amount+Σoutsourced_amount）、蓝点=中位数；**成本线切进蓝带时转红并文字警示**（该段成本结构不支持竞争性报价） |
| 9 | 项目报价对比 我方 vs 友商 | 从区块①迁入 | 换肤：我方柱 胜=绿/负=红（半透明）、友商=浅灰蓝；点击下钻不变 |

### 区块③ 对手是谁？（情报）

| # | 图表 | 来源 | 设计变化 |
|---|---|---|---|
| 10 | **友商画像** | **新增** | 表+条混合：每行一家友商——中标率横条（灰竖标=市场均值线）/ 平均溢价（负值绿色=低价抢标型）/ 优势领域标签（chip）/ 同期项目数；点行下钻对阵明细 |
| 11 | **遭遇战** | **新增** | 友商下拉选择 → 与我方 head-to-head：胜负大数字 + 胜率天平条 + 分年度 mini 胜负柱；点卡下钻对阵明细 |
| 12 | **中标份额格局** | **新增** | 按年 100% 堆叠柱，6 色封顶（前 5 家+其他）；卡内自动标注趋势结论（"我方份额三连涨"等） |

全局过滤（项目单选/友商多选/日期范围）继续联动全部 12 图；每图高级筛选（自产属性/货物/金额段）沿用 `ChartFilterPopover`。

## 3. DeepSeek 风格 token（替换 cyber-scope）

| token | 值 |
|---|---|
| 页面底色 | `#fbfafa`（暖白） |
| 卡片 | `#ffffff`，`border 1px rgba(0,0,0,0.06)`，`radius 14px`，无重阴影 |
| 主色 | `#4D6BFE`（DeepSeek 蓝）；友商弱化色 `#c6cdf6` |
| 语义色 | 绿 `#20b26c`（胜/正向）、红 `#e5484d`（负/警示）、琥珀 `#f0a122`（友商对比） |
| 文字 | 主 `#1b1c1d` / 次 `#6b6c6e` / 弱 `#9c9da0` |
| 数字 | `font-variant-numeric: tabular-nums`，主数字 650 字重 |
| 网格线 | `#f0f0ef` 1px，无渐变光晕 |

落地方式：重写 `chartTheme.ts` 为上述 token；`DashboardView` 外层 `cyber-scope` 移除；
`StatCard` 改白卡+注脚样式。**数据查询 tab（QueryView）本次不动**（仅共享的 FilterBar 已是中性样式）。

## 4. 数据与 SQL

### 4.1 seed 扩量（`backend/scripts/seed_mock_market.py`）

- 40 个项目分布 2023Q1–2025Q3；每项目 1 行我方 + 2–3 家友商（共 6–8 家友商池）。
- 表结构**不动**；mock 数据须"演出"以下可读规律（确定性生成，非随机）：
  - 溢价-胜率单调递减 + **+3% 后腰斩**（区块②拐点标注有数据支撑）；
  - ≥2000万 段我方近乎全败，且该段成本底线切进历史中标 P25–P75；
  - 我方份额 2023→2025 三连涨（18%→24%→29%），东方宏业惯于低价（平均溢价负）；
  - 华能铜川等既有 6 项目名保留（回归既有测试/演示习惯）。

### 4.2 新增 SQL 模板（`frontend/src/extensions/bid-quote/api.ts::sqlFor`）

全部走 Route B 前端拼 SQL + `querySql()` 只读端点，零后端新增。

| key | 形状 |
|---|---|
| `trend` | 按季度（`date_trunc('quarter')`）我方/友商中标率两列 |
| `premiumCurve` | 我方行溢价率 = `(b.winning_price − w.winner_price)/w.winner_price`（w=同项目 won 行），`width_bucket` 6 桶 → 每桶胜率+样本数 |
| `priceBand` | 按金额段 `percentile_cont(0.25/0.5/0.75)` of 中标价（全部 won 行）+ 该段**我方行** items 的 Σself_amount+Σoutsourced_amount 作成本底线 |
| `competitorProfile` | 按 bidder_name：中标率 / 平均溢价 / 同期项目数；优势领域由其**中标**行的 goods_name Top2 前端聚合（复用 mock_bid_item） |
| `head2head` | 选定友商与我方同场（同 project_name）项目集 → 胜负计数 + 分年度 |
| `shareStack` | 按年中标金额份额（won 行 × winning_price），前 5 家+其他 |

约束（沿用既有铁律）：
- 友商过滤在所有新模板统一 **EXISTS 语义**，关联列按模板外层别名传 `outerProjectRef`（`buildWhere(g, outerProjectRef, chart?)`）；
- 单引号转义只走 `esc()`；50 阈值判定只走 `matchesSelfAttribute`。

## 5. 前端结构

```
extensions/bid-quote/
├── chartTheme.ts          # 重写为 DeepSeek token
├── components/
│   ├── StatCard.tsx        # 白卡+注脚
│   ├── SectionCard.tsx     # 新增:可折叠区块(标题=问题,默认展开)
│   ├── TrendChart.tsx      # 新增:图3 双折线
│   ├── PremiumCurveChart.tsx # 新增:图7 溢价柱+拐点
│   ├── PriceBandChart.tsx  # 新增:图8 区间条
│   ├── CompetitorProfileTable.tsx # 新增:图10 表+条
│   ├── HeadToHeadCard.tsx  # 新增:图11
│   ├── ShareStackChart.tsx # 新增:图12
│   └── (现有 4 图组件换肤)
└── hooks.ts               # 新 query: trend/premiumCurve/priceBand/competitorProfile/head2head/shareStack
```

页面标题已是"竞标战情总览"（本次确认改动）；三个区块用 `SectionCard` 分隔。

## 6. 测试

- `build-where.test.ts`（rstest）扩充：新模板的 EXISTS 关联列断言（每模板外层别名）。
- 新增 `sql-shape.test.ts`：6 个新模板 SQL 形状断言（bucket 边界/percentile/份额 Top5+其他折叠）。
- seed 规律断言（backend，pytest，直连 mock 库）：溢价单调性、拐点在 +3%、份额三连涨——防 seed 漂移破坏仪表盘故事。

## 7. 非目标（YAGNI）

- ❌ mock 表加列（owner/score/评标办法——最终图表集不需要）
- ❌ 地区/业主维度分析（未进三问框架，后续有需求再说）
- ❌ QueryView 数据查询 tab 换肤
- ❌ 报价建议的"预测模型"——只呈现历史区间规律，不建模预测

## 8. 落地顺序（给 writing-plans）

1. seed 扩量 + 规律断言（一切图表的数据底座）
2. chartTheme 重写 + StatCard + SectionCard（风格底座，现有图先换肤）
3. 区块① 时间趋势图
4. 区块② premiumCurve / priceBand + 图9 迁入
5. 区块③ competitorProfile / head2head / shareStack
6. 测试补齐 + 浏览器全页验证
