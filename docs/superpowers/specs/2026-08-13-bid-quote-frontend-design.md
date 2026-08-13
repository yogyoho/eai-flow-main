# 投标报价分析 (bid-quote-analysis) 前端设计

- **日期**: 2026-08-13
- **模块**: ① 投标报价分析 (bid-quote-analysis)
- **状态**: 设计已确认,待写实施计划
- **关联**: [[market-analysis-modules-design]] · 复用 ④ contract-price 前端结构 + 项目管理 list 浅色风格 + cyber 图表

## 1. 背景与目标

模块① 的**数据层与 agent 对话路径已就绪**(Route B:data_source `bid-quote` + 3 罐装 dataset + `skills/public/bid-quote-analysis/SKILL.md`,agent 可在对话里答中标率并给报价/配比建议)。本设计补齐**应用入口与可视化前端**:在应用中心加一个磁贴,进入后提供「分析仪表盘」+「数据查询」两个页面。

**MVP 完成定义**:市场部用户点应用中心「投标报价分析」磁贴 → 看到科技感仪表盘(中标率/投标量/报价对比等 KPI+图表)→ 进数据查询页看 3 个固定视图、点行下钻到明细。

**硬约束(已锁)**:
- **Route B**:不建扩展包、不建 postgres-ext 业务表。前端直调 `data_source` 现有 REST(查询能力透出)。
- **风格**:项目管理页 list 浅色 + 图表 cyber 增强(代码库已自带 cyber 层,浅色下即可出科技感)。
- **查询页**:固定视图(3 个罐装 dataset)+ 行下钻 modal,不做自由 SQL 输入框、不做写操作。

## 2. 关键架构修正(重要)

探索发现:`data_source` 的查询能力(`run_readonly_query` / `assert_readonly_select`)**只在 MCP(`mcp.py`)里被调用,REST 路由没有 query 端点**(现有路由仅 list/create/get/delete/test/sync/datasets CRUD)。因此 Route B 薄前端需要一个**极小后端增量**:在现有 `data_source` 路由上加 2 个只读 query 端点,把 `DataSourceService` 里**已有**的查询能力透出 REST。

- 不建扩展包、不建业务表、不动 harness。
- 约 25 行后端(2 路由 + 复用 response model)。
- 改的是 app 层 `data_source` 路由 → **加 `EAI-CUSTOM` 注释**。

## 3. 架构与数据流

```
应用中心磁贴(license=bid_quote, domain=市场营销)
  → /bid-quote (layout.tsx: navItems[dashboard, query], 包 ShellLayout, canPage 过滤 tab)
     ├─ 分析仪表盘 bqa:page:dashboard  (DashboardView)
     │     └─ KPI 卡 ×5 + 图表 ×3
     └─ 数据查询   bqa:page:query      (QueryView)
          └─ 3 固定视图 tab + 行下钻 modal
                    │  TanStack Query (queryKey 命名空间 ["bqa", ...])
                    ▼
          extensions/bid-quote/api.ts (authFetch, base=/api/extensions)
                    │  先 resolveSource("bid-quote") 拿 source_id(缓存)
                    ▼
   POST /api/extensions/data-sources/{sid}/datasets/{did}/query   ← 罐装 dataset(按 id)
   POST /api/extensions/data-sources/{sid}/query  body{sql}       ← 下钻参数化只读 SQL
                    ▼  DataSourceService.run_readonly_query + assert_readonly_select(守卫)
                 mock_market (postgres-ext, 已 seed 就绪)
```

Agent 对话路径(SKILL.md + MCP)与仪表盘**共用同一套 dataset/mock_market**,零数据重复。

## 4. 后端增量

### 4.1 新增 2 个只读 query 端点(`backend/app/extensions/data_source/routers.py`)
均复用 `DataSourceService.get_by_id` + `run_readonly_query`;写操作/非 SELECT 由 `assert_readonly_select` fail-closed。

| 方法 & 路径 | body | 返回 | 用途 |
|---|---|---|---|
| `POST /{source_id}/datasets/{dataset_id}/query` | `{params?: dict}`(预留) | `{rows: list[dict], row_count: int, label: str}` | 跑该 dataset 的 `default_query`(仪表盘/查询页固定视图) |
| `POST /{source_id}/query` | `{sql: str, params?: dict}` | `{rows: list[dict], row_count: int}` | 下钻参数化只读 SQL(`assert_readonly_select(sql)` 先过) |

- response:直接返 `{rows: list[dict], row_count: int}`(FastAPI 自动序列化,不强制 response_model;需要时可收紧成 `QueryResultResponse` model)。
- 鉴权:走现有 data_source 路由的依赖(与 list/datasets 同级,已挂在 extensions 鉴权下)。
- **EAI-CUSTOM** 注释标注 2 个路由 + 说明"透出已有 MCP 查询能力供前端仪表盘使用,只读守卫不变"。

### 4.2 新增第 4 个罐装 dataset(`seed_mock_market.py` 增一行 upsert)
仪表盘第 3 张图需要「项目级我方 vs 友商报价对比」维度(区别于按金额段/货物构成)。在 seed 的 `DATASETS` 里加:

```python
("bid-quote", "项目报价对比", "bqa_project_showdown", """
    SELECT project_name,
      MAX(winning_price) FILTER (WHERE bidder_role='ours') AS our_price,
      MAX(winning_price) FILTER (WHERE bidder_role='competitor') AS competitor_price,
      BOOL_OR(bidder_role='ours' AND won) AS we_won,
      MAX(customer) AS customer
    FROM mock_bid GROUP BY project_name ORDER BY MIN(wid)
""")
```

> 该 dataset 与既有 3 个同表(`data_source_datasets`),seed 脚本已 idempotent(TRUNCATE+CASCADE reseed + ON CONFLICT upsert),重跑即生效。**不新建业务表**。

### 4.3 既有 dataset(沿用,不改)
`投标总览`(bid_summary)、`货物构成对比`(composition_compare_by_goods)、`按金额段我方中标率`(win_rate_by_segment)。

## 5. 前端模块结构(镜像 contract-price,queryKey=`["bqa",...]`)

```
frontend/src/app/bid-quote/
  layout.tsx          # navItems: /bid-quote→bqa:page:dashboard, /bid-quote/query→bqa:page:query
                      #   <ShellLayout> 包裹; canPage(pageId) 过滤 tab 可见
  page.tsx            # return <DashboardView/>  (7 行 stub)
  query/page.tsx      # return <QueryView/>

frontend/src/extensions/bid-quote/
  api.ts              # resolveSourceId(name) [list→name 匹配,缓存]
                      # queryDataset(sourceId, datasetId) → POST .../datasets/{did}/query
                      # querySql(sourceId, sql)            → POST .../query
                      # resolveDatasetId(sourceId, label)  [list datasets→label 匹配]
  hooks.ts            # KEYS = { summary:["bqa","summary"], composition:["bqa","composition"],
                      #          segment:["bqa","segment"], showdown:["bqa","showdown"],
                      #          bidlist:["bqa","bidlist"], drilldown:["bqa","drilldown"] }
                      # useBidSummary / useComposition / useWinRateBySegment
                      # / useProjectShowdown / useBidList(明细直查) / useDrillDown(sql)
  types.ts            # BidSummaryRow / CompositionRow / SegmentRow / ShowdownRow / BidItemRow
                      #   (snake_case,对齐 dataset 列;Decimal→string)
  components/
    DashboardView.tsx     # 页头 + KPI 行 + 3 图表
    QueryView.tsx         # 3 视图 tab + 下钻 modal
    StatCard.tsx          # clone contract-price StatCard + cyber(font-cyber/glow/角标点)
    ChartCard.tsx         # clone GoodsAnalysis ChartCard + themed-card-sci 面
    TechTooltip.tsx       # 新:cyber 自定义 tooltip
    DrillDownModal.tsx    # 通用下钻 modal(标题 + sql + 明细 table)
    ui/table.tsx          # clone contract-price 的 raw-HTML table 原语
```

**命名空间铁律**(避免 queryKey 串扰,见 bug-1188 类):全模块统一 `bqa` 前缀,`bqa:page:*` page id,`["bqa",...]` queryKey,`bqa_` dataset table_name——区分大小写、含与不含冒号变体逐一核对。

## 6. 仪表盘设计(项目管理 list 浅色 + cyber 图表)

整体:`<div className="cyber-scope">` 包裹(启用 Space Grotesk/JetBrains Mono + `.font-cyber`),页面背景保持浅色(项目管理 list 同款 `bg-background`),**仅图表面/KPI 数字走 cyber 增强**。

### 6.1 页头
克隆 `contract-price/PageHeader.tsx`,icon-box 由 `bg-blue-50 border-blue-200 text-blue-600` 换为 `bg-primary/10 border-primary/30 text-primary`;标题「投标报价分析」加 `.text-shadow-glow`;右侧「刷新」按钮(重拉所有 query)。

### 6.2 KPI 行(5 卡,`grid grid-cols-2 lg:grid-cols-5 gap-3`)
每卡:`rounded-xl p-4 border border-{c}/15 bg-{c}/5 relative overflow-hidden` + 右上角 `absolute top-0 right-0 w-2 h-2 bg-{c}/10` 角标点 + 数值 `text-3xl font-extrabold font-cyber text-{c} text-shadow-glow` + hover `transition-all hover:scale-[1.015]`。色取 `--chart-1..5`。

| KPI | 值(mock) | 色 |
|---|---|---|
| 我方中标率 | 33.3% | primary |
| 投标总数 | 12 | chart-2 |
| 我方投 / 中 | 6 / 2 | chart-3 |
| 友商中标率 | 66.7% | destructive |
| 平均中标价 | 1727.5 万 | chart-5 |

### 6.3 图表(3 张,每张 `themed-card-sci rounded-xl p-5`)
统一增强:`<defs>` 渐变 + `<filter id="line-glow">`(feGaussianBlur stdDeviation=3 + feMerge)、`isAnimationActive animationDuration=900`、`Tooltip content={<TechTooltip/>}`、`CartesianGrid strokeDasharray="2 4" stroke="rgba(100,116,139,0.22)"`、monospace tick。

1. **按金额段我方中标率**(dataset: 按金额段我方中标率)— 柱状,垂直渐变 `#3b82f6 .7→.15`,`radius=[4,4,0,0]`。核心洞察:≥2000w 段 0%。
2. **货物构成对比:自产 vs 外购**(dataset: 货物构成对比)— 分组柱(我方 self% vs 友商 self%),定位失标根因(塔器/压缩机/反应器我方 self_pct≈0)。
3. **项目报价对比:我方 vs 友商**(dataset: 项目报价对比)— 分组柱 per project,`our_price` vs `competitor_price`,胜负用 Cell 色(胜=success/负=destructive)标注。直接支撑「报价区间建议」。

## 7. 数据查询页(固定视图 + modal 下钻)

`QueryView.tsx`:上方 3 个视图 tab(pill 切换),下方 `ui/table` 渲染当前视图行(列排序 + 简单文本筛选)。`投标总览` dataset 不上查询页(只喂仪表盘 KPI);查询页 tab1 用明细直查,让每行可下钻。

| 视图 | 数据来源 | 行下钻(点行 → modal) |
|---|---|---|
| 投标明细 | raw:`SELECT * FROM mock_bid ORDER BY bid_date DESC` | 按 project_name 下钻:`SELECT * FROM mock_bid_item WHERE project_name=? ORDER BY total_amount DESC` |
| 货物构成对比 | dataset: 货物构成对比 | 按 goods_name 下钻:`SELECT * FROM mock_bid_item WHERE goods_name=? ORDER BY total_amount DESC` |
| 按金额段中标率 | dataset: 按金额段我方中标率 | 按金额段下钻:`SELECT * FROM mock_bid WHERE winning_price < <上界> AND winning_price >= <下界> ORDER BY winning_price DESC`(上下界由该行段定义推得) |

**下钻 modal**(`DrillDownModal.tsx`):标题(维度+值)+ 调 `querySql(sourceId, sql)` + 明细 table(项目/数量/单位/自产额/外购额/单价/胜负)。下钻 SQL 在前端按维度参数化拼接(白名单维度,值来自行数据),走 raw-SQL 只读端点的 `assert_readonly_select` 守卫。

## 8. 应用中心入口 + License/权限足迹

### 8.1 磁贴 seed(`backend/app/extensions/database.py:1610-1641` `apps=[...]`)
```python
{"app_id": "bid-quote", "name": "投标报价分析", "desc": "投标中标率/报价对比/自产外购构成分析",
 "icon": "gavel", "domain": "marketing", "stage": "analysis",
 "path": "/bid-quote", "license": "bid_quote", "admin": False,
 "sort": 10, "sort_key": "toubaoajiagenfenxi"}
```
- `domain` 用英文 key `marketing`(对齐 contract_price 的 `procurement` 英文 key 模式),显示名「市场营销」。若 `app_domains` seed 无 `marketing` 域,同步在 domains seed 新增(key=`marketing`,label「市场营销」)。
- `frontend/src/extensions/app-center/hooks/useApps.ts:77-83` `deriveNavId` 加 `"bid-quote": "nav:bid-quote"`(否则 nav 权限门静默隐藏磁贴)。

### 8.2 License 4 点(同步,否则 test_license_modules_sync 挂)
- `backend/app/extensions/license/service.py:ALL_MODULES` 加 `"bid_quote"`
- `frontend/src/extensions/license/labels.ts:MODULE_LABELS` 加 `bid_quote: "投标报价分析"`
- `tools/license/license_generator.py:ALL_MODULES` 加 `"bid_quote"`
- `backend/tests/test_license_modules_sync.py:EXPECTED_KEYS` 加 `"bid_quote"`

### 8.3 permissions.yaml(克隆 `spare_parts:` 块 → `bid_quote:`)
```yaml
bid_quote:
  display_name: "投标报价分析"
  nav_id: "nav:bid-quote"
  pages:
    - id: "bqa:page:dashboard"
    - id: "bqa:page:query"
  data_scopes:
    - { id: "bqa_all", rule_template: {} }
    - { id: "bqa_dept", rule_template: { dept_id IN: "$identity.dept_ids" } }
```

### 8.4 roles_custom.yaml(project_manager + dept_head 各加)
nav 列加 `nav:bid-quote`;pages 列加 `bqa:page:dashboard`、`bqa:page:query`;data_scopes 加 `bqa_dept`。superadmin `pages:["*"]`/`nav:["*"]` 自动继承,无需显式。permissions.yaml 的 dept_head/project_manager base 块同步加 `bqa_dept`。

## 9. 非目标(YAGNI)

- ❌ 写操作(录入/编辑/删除投标数据)— mock 数据,Route B 只读。
- ❌ 自由 SQL 输入框 — 仅下钻的参数化只读 SQL(白名单维度)。
- ❌ i18n key — 硬编码中文(同 contract_price)。
- ❌ 实时数据源接入 — mock_market;真库接入是后续(③② 同套 data_source 复用)。
- ❌ 整页暗色 cyber 主题 — 浅色页 + 图表 cyber 增强(项目管理 list 一致)。

## 10. 测试

- **后端**:2 个新端点的只读守卫单测(`assert_readonly_select` 拒 `INSERT/UPDATE/DELETE/DROP/`;非 SELECT 400);dataset-by-id 端点返正确行数;raw-SQL 端点带上钻 SQL 返明细。license sync 测试加 `bid_quote` 后通过。
- **前端**:`pnpm typecheck`;DashboardView/QueryView 渲染(可 mock api);queryKey 命名空间 grep 确认无 `cpa`/`csp` 残留。
- **E2E(手动)**:应用中心点磁贴 → 仪表盘显 33.3% + 3 图表 → 数据查询 3 视图 → 点行出 modal 明细。mock 数据已就绪。

## 11. 落地顺序(给 writing-plans)

1. 后端:2 query 端点 + 第 4 dataset(seed 重跑)+ EAI-CUSTOM 注释 → restart gateway → curl 验证。
2. License/权限:4 点 + permissions.yaml + roles_custom.yaml + 磁贴 seed + deriveNavId → restart → 磁贴可见。
3. 前端骨架:app/bid-quote 路由 + extensions/bid-quote(api/hooks/types)→ typecheck。
4. 仪表盘:DashboardView + StatCard/ChartCard/TechTooltip + 3 图表(cyber 增强)。
5. 查询页:QueryView + 3 视图 + DrillDownModal。
6. 联调 + 截图验证。
