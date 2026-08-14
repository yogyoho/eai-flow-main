# 投标/合同/开票管线查询 (biz-pipeline) 前端设计

- **日期**:2026-08-14
- **模块**:③ 投标/合同/开票管线查询 (biz-pipeline)
- **状态**:设计已确认,待写实施计划
- **关联**: [[market-analysis-modules-design]] §7 · [[2026-08-13-bid-quote-frontend-design]](架构完全镜像,Route B 复用,data_source 查询端点已由①落地,零后端增量)

## 1. 背景与目标

模块③ 的 **agent 对话路径与前端架构已由①定型**(Route B:data_source + 罐装 dataset + SKILL.md;前端直调 data_source REST 查询端点)。本设计补齐**应用入口与可视化前端**:应用中心磁贴 → 「管线仪表盘」+「数据查询」两页。

**MVP 完成定义**:市场部用户点应用中心「管线查询」磁贴 → 看到管线漏斗仪表盘(投标→中标→合同→开票 KPI+图表)→ 进数据查询页看 3 个固定视图、点行按合同号下钻到「投标→合同→开票」全链路。

**硬约束(已锁)**:
- **Route B**:不建扩展包、不建 postgres-ext 业务表、**零后端增量**(① 已落地的 2 个 query 端点通用复用)。
- **风格**:项目管理页 list 浅色 + 图表 cyber 增强(同①)。
- **查询页**:固定视图(罐装 dataset / 明细直查)+ 行下钻 modal,不做自由 SQL、不做写操作。
- **统一合同号 `contract_no`** 作为投标↔合同↔开票跨系统 join key(umbrella §7 假设;mock 阶段由 seed 保证一致)。

## 2. 关键架构结论(零后端增量)

探索确认:① 已在 `data_source` 路由落地 2 个通用只读 query 端点(`POST /{sid}/datasets/{did}/query` 跑罐装 dataset;`POST /{sid}/query body{sql}` 跑参数化只读 SQL,过 `assert_readonly_select` 守卫)。**③ 直接复用,不改后端 Python**。

③ 全部工作量 = 数据(seed)+ 前端(镜像①)+ license/权限/磁贴足迹。**无 EAI-CUSTOM 后端注释**(没改 app 层 data_source 路由)。

## 3. 架构与数据流

```
应用中心磁贴(license=biz_pipeline, domain=市场营销)
  → /biz-pipeline (layout.tsx: navItems[dashboard, query], ShellLayout 包裹, canPage 过滤 tab)
     ├─ 管线仪表盘 bpp:page:dashboard  (DashboardView)
     │     └─ KPI 卡 ×5 + 图表 ×3
     └─ 数据查询   bpp:page:query      (QueryView)
          └─ 3 固定视图 tab + 行下钻 modal
                    │  TanStack Query (queryKey 命名空间 ["bpp", ...])
                    ▼
          extensions/biz-pipeline/api.ts (authFetch, base=/api/extensions)
                    │  resolveSource("biz-pipeline") 拿 source_id(缓存)
                    ▼
   POST /api/extensions/data-sources/{sid}/datasets/{did}/query   ← 罐装 dataset(按 id)
   POST /api/extensions/data-sources/{sid}/query  body{sql}       ← 下钻参数化只读 SQL
                    ▼  DataSourceService.run_readonly_query + assert_readonly_select(守卫)
                 mock_market (postgres-ext, ③ 新增 3 表 + seed)
```

Agent 对话路径(SKILL.md + MCP)与仪表盘**共用同一套 dataset/mock_market**,零数据重复(同①)。

## 4. 数据层(seed_mock_pipeline.py,新增,镜像 seed_mock_market.py 结构)

新增独立 seed 脚本 `backend/scripts/seed_mock_pipeline.py`(治理:datasets 当代码管,版本化 seed,镜像①)。**不建扩展包、不建 postgres-ext 表**;在已有 `mock_market` 库加 3 张表,在 `agentflow`(extensions 库)加第 2 条 data_source 连接 + ③ 的 dataset。

### 4.1 三张 mock 表(统一 `contract_no` join key)

```sql
-- 投标(CRM 来源)
CREATE TABLE IF NOT EXISTS mock_pipeline_bid (
  bid_id          TEXT PRIMARY KEY,        -- TB-2025-001
  project_name    TEXT NOT NULL,
  contract_no     TEXT,                    -- join key;落标为 NULL
  customer        TEXT,
  bid_date        DATE,
  our_bid_amount  NUMERIC(14,2),           -- 我方投标报价(含税)
  status          TEXT NOT NULL,           -- won / lost
  competitor_name TEXT
);
-- 合同(合同系统)
CREATE TABLE IF NOT EXISTS mock_contract (
  contract_no   TEXT PRIMARY KEY,          -- HT-2025-001 (join key)
  contract_name TEXT,
  customer      TEXT,
  sign_date     DATE,
  amount        NUMERIC(14,2),             -- 合同金额(含税)
  status        TEXT                       -- executing / completed / terminated
);
-- 开票(财务/金税)
CREATE TABLE IF NOT EXISTS mock_invoice (
  invoice_id   TEXT PRIMARY KEY,           -- FP-2025-001
  contract_no  TEXT NOT NULL REFERENCES mock_contract(contract_no) ON DELETE CASCADE,
  invoice_date DATE,
  amount       NUMERIC(14,2),              -- 不含税
  tax_amount   NUMERIC(14,2),
  total_amount NUMERIC(14,2),              -- 含税 = amount + tax_amount
  status       TEXT                        -- issued / voided
);
```

### 4.2 数据故事(贴近真实,支撑漏斗+对账)

8 个投标项目(2025 年),4 中标 → 4 合同 → 开票(2 全额、2 部分 → 有待开票余额):

| bid_id | 项目 | 中标? | 我方报价(万) | contract_no | 合同额(万) | 已开票(万) |
|---|---|---|---|---|---|---|
| TB-001 | 华能铜川电厂二期循环水系统 | ✓ | 1850 | HT-001 | 1800 | 1800(全额) |
| TB-002 | 宁夏宝丰甲醇项目净化装置 | ✗ | 2783 | — | — | — |
| TB-003 | 内蒙古久泰乙二醇装置 | ✗ | 518 | — | — | — |
| TB-004 | 大唐国际雷州电厂烟气脱硫 | ✗ | 3552 | — | — | — |
| TB-005 | 中天合创煤化工水处理 | ✓ | 85 | HT-002 | 82 | 82(全额) |
| TB-006 | 万华化学烟台PDH装置 | ✗ | 2394 | — | — | — |
| TB-007 | 陕西榆林煤化工气化装置 | ✓ | 4200 | HT-003 | 4000 | 2500(部分,待开1500) |
| TB-008 | 河北唐山钢铁余热锅炉 | ✓ | 1500 | HT-004 | 1450 | 800(部分,待开650) |

**漏斗**:8 投标 → 4 中标(50%) → 4 合同(总额 7332 万) → 已开票 5182 万,**待开票 2150 万**(HT-003/HT-004 余额)。落标方报价 = 中标价 × 上浮(同① option A 确定性,5%-17%)。

### 4.3 罐装 dataset(default_query,seed upsert,过只读守卫)

```python
DATASETS = [
  # 1) 管线漏斗汇总(单行,喂 KPI + 金额漏斗图)
  {"table_name": "bpp_funnel", "label": "管线漏斗总览",
   "default_query": """
     SELECT
       (SELECT COUNT(*) FROM mock_pipeline_bid) AS bid_count,
       (SELECT COUNT(*) FROM mock_pipeline_bid WHERE status='won') AS won_count,
       (SELECT COUNT(*) FROM mock_contract) AS contract_count,
       (SELECT COALESCE(SUM(our_bid_amount),0) FROM mock_pipeline_bid) AS bid_amount_total,
       (SELECT COALESCE(SUM(our_bid_amount),0) FROM mock_pipeline_bid WHERE status='won') AS won_amount_total,
       (SELECT COALESCE(SUM(amount),0) FROM mock_contract) AS contract_total,
       (SELECT COALESCE(SUM(total_amount),0) FROM mock_invoice WHERE status='issued') AS invoiced_total,
       (SELECT COALESCE(SUM(amount),0) FROM mock_contract)
         - (SELECT COALESCE(SUM(total_amount),0) FROM mock_invoice WHERE status='issued') AS uninvoiced_total
   """},
  # 2) 月度投标节奏(投标/中标 by 月,喂趋势图)
  {"table_name": "bpp_monthly", "label": "月度投标节奏",
   "default_query": """
     SELECT to_char(bid_date,'YYYY-MM') AS ym,
       COUNT(*) AS bids,
       COUNT(*) FILTER (WHERE status='won') AS won
     FROM mock_pipeline_bid GROUP BY 1 ORDER BY 1
   """},
  # 3) 合同-开票对账(每合同:额/已开/待开,喂对账图+查询页)
  {"table_name": "bpp_contract_recon", "label": "合同开票对账",
   "default_query": """
     SELECT c.contract_no, c.contract_name, c.customer, c.amount,
       COALESCE(SUM(i.total_amount) FILTER (WHERE i.status='issued'),0) AS invoiced,
       c.amount - COALESCE(SUM(i.total_amount) FILTER (WHERE i.status='issued'),0) AS uninvoiced
     FROM mock_contract c
     LEFT JOIN mock_invoice i ON i.contract_no = c.contract_no
     GROUP BY c.contract_no, c.contract_name, c.customer, c.amount
     ORDER BY uninvoiced DESC
   """},
]
```

data_source 连接:`SOURCE_NAME="biz-pipeline"`,连接配置同①(指向 mock_market 库)。seed 脚本幂等(TRUNCATE+CASCADE reseed 表;data_source/dataset upsert ON CONFLICT)。

## 5. 前端模块结构(镜像①,queryKey=`["bpp",...]`)

```
frontend/src/app/biz-pipeline/
  layout.tsx          # navItems: /biz-pipeline→bpp:page:dashboard, /biz-pipeline/query→bpp:page:query
                      #   <ShellLayout> 包裹; canPage(pageId) 过滤 tab
  page.tsx            # return <DashboardView/>
  query/page.tsx      # return <QueryView/>

frontend/src/extensions/biz-pipeline/
  api.ts              # resolveSourceId/queryDataset/querySql/resolveDatasetId(克隆①,source name="biz-pipeline")
  hooks.ts            # KEYS={funnel:["bpp","funnel"], monthly:["bpp","monthly"],
                      #        recon:["bpp","recon"], bidlist:["bpp","bidlist"], drilldown:(sql)=>["bpp","drilldown",sql]}
                      # usePipelineFunnel / useMonthlyBids / useContractRecon / useBidList(明细直查) / useDrillDown(sql)
  types.ts            # FunnelRow / MonthlyRow / ReconRow / BidRow(snake_case,Decimal→string)
  components/
    DashboardView.tsx     # 页头 + KPI 行 + 3 图表(克隆① DashboardView 改数据源/图表)
    QueryView.tsx         # 3 视图 tab + 下钻 modal(克隆①,改视图/下钻 SQL)
    DrillDownModal.tsx    # 通用下钻 modal(克隆①,可逐字复用)
    StatCard.tsx          # 克隆① StatCard(cyber)
    ChartCard.tsx         # 克隆① ChartCard(themed-card-sci)
    TechTooltip.tsx       # 克隆① TechTooltip
    ui/table.tsx          # 克隆① raw-HTML table 原语
```

**命名空间铁律**(同① bug-1188 类):全模块统一 `bpp` 前缀,`bpp:page:*` page id,`["bpp",...]` queryKey,`bpp_` dataset table_name。与①的 `bqa` 严格隔离。

## 6. 仪表盘设计(浅色页 + cyber 图表,克隆① DashboardView)

`<div className="cyber-scope">` 包裹;页头克隆① PageHeader(icon `git-commit-horizontal`/`workflow`,标题「管线查询」+ `.text-shadow-glow`)。

### 6.1 KPI 行(5 卡,`grid grid-cols-2 lg:grid-cols-5 gap-3`)
克隆① StatCard(角标点 + `font-cyber text-shadow-glow` + hover scale)。色取 `--chart-1..5`。

| KPI | 值(mock) | 色 |
|---|---|---|
| 投标总数 | 8 | primary |
| 中标率 | 50.0% | chart-2 |
| 合同总额 | 7332 万 | chart-3 |
| 已开票总额 | 5182 万 | chart-4 |
| 待开票总额 | 2150 万 | destructive(预警色) |

### 6.2 图表(3 张,`themed-card-sci rounded-xl p-5`,克隆① cyber 增强:`<defs>` 渐变 + `line-glow` filter + `TechTooltip` + monospace tick)

1. **金额漏斗**(dataset: 管线漏斗总览)— 柱状 4 段:投标总额(16882w)→中标总额(7635w)→合同总额(7332w)→已开票总额(5182w),垂直渐变 `#3b82f6`,直观展示金额逐级沉淀/漏损。
2. **月度投标节奏**(dataset: 月度投标节奏)— 分组柱(投标 vs 中标 by 月),定位投标旺淡季。
3. **待开票 TOP 合同**(dataset: 合同开票对账)— 横向柱(uninvoiced 降序),红色渐变标注待开票余额,直接支撑「催开票/催回款」预警。

## 7. 数据查询页(固定视图 + modal 下钻,克隆① QueryView)

`QueryView.tsx`:上方 3 视图 tab(pill),下方 `ui/table` 渲染当前视图行。`管线漏斗总览` dataset 不上查询页(只喂 KPI);查询页 tab1 用明细直查让每行可下钻。

| 视图 | 数据来源 | 行下钻(点行 → modal) |
|---|---|---|
| 投标明细 | raw:`SELECT * FROM mock_pipeline_bid ORDER BY bid_date DESC` | 按 contract_no(中标行)下钻:该合同开票明细 `SELECT invoice_id,invoice_date,amount,tax_amount,total_amount,status FROM mock_invoice WHERE contract_no='<X>' ORDER BY invoice_date`(落标行 contract_no 为 NULL,禁用下钻) |
| 合同开票对账 | dataset: 合同开票对账 | 按 contract_no 下钻:同上开票明细 |
| 月度投标节奏 | dataset: 月度投标节奏 | 按月份(ym)下钻:`SELECT bid_id,project_name,customer,bid_date,our_bid_amount,status,competitor_name FROM mock_pipeline_bid WHERE to_char(bid_date,'YYYY-MM')='<X>' ORDER BY bid_date` |

**下钻 modal**(`DrillDownModal.tsx`):逐字复用①通用 modal(标题+sql→明细 table)。下钻 SQL 前端按维度参数化拼接(白名单维度 contract_no/ym,值经单引号转义),走 raw-SQL 端点 `assert_readonly_select` 守卫。

## 8. 应用中心入口 + License/权限足迹(克隆①,改 key)

### 8.1 磁贴 seed(`backend/app/extensions/database.py` apps=[...] 加一条)
```python
{"app_id": "biz-pipeline", "name": "管线查询", "desc": "投标/合同/开票管线漏斗+对账",
 "icon": "workflow", "domain": "marketing", "stage": "analysis",
 "path": "/biz-pipeline", "license": "biz_pipeline", "admin": False,
 "sort": 11, "sort_key": "guanxianchaxun"}
```
- `domain` 用英文 key `marketing`(① 已新增该域;③ 复用,无需再加 domain)。
- `frontend/src/extensions/app-center/hooks/useApps.ts` deriveNavId 加 `"biz-pipeline": "nav:biz-pipeline"`。

### 8.2 License 4 点(同步,否则 test_license_modules_sync 挂)
- `backend/app/extensions/license/service.py:ALL_MODULES` 加 `"biz_pipeline"`
- `frontend/src/extensions/license/labels.ts:MODULE_LABELS` 加 `biz_pipeline: "管线查询"`
- `tools/license/license_generator.py:ALL_MODULES` 加 `"biz_pipeline"`
- `backend/tests/test_license_modules_sync.py:EXPECTED_KEYS` 加 `"biz_pipeline"`

### 8.3 permissions.yaml(克隆 `bid_quote:` 块 → `biz_pipeline:`)
```yaml
biz_pipeline:
  display_name: "管线查询"
  nav_id: "nav:biz-pipeline"
  pages:
    - { id: "bpp:page:dashboard" }
    - { id: "bpp:page:query" }
  data_scopes:
    - { id: "bpp_all", rule_template: {} }
```

### 8.4 roles_custom.yaml(project_manager + dept_head 各加)
nav 列加 `nav:biz-pipeline`;pages 列加 `bpp:page:dashboard`、`bpp:page:query`。superadmin `["*"]` 自动继承。

## 9. 非目标(YAGNI)

- ❌ 写操作(录入投标/合同/开票)— mock 数据,Route B 只读。
- ❌ 自由 SQL 输入框 — 仅下钻的参数化只读 SQL(白名单维度)。
- ❌ i18n key — 硬编码中文(同①/contract_price)。
- ❌ 真实 CRM/财务/合同系统接入 — mock_market;真库接入是后续。
- ❌ 整页暗色 cyber 主题 — 浅色页 + 图表 cyber 增强(同①)。
- ❌ 跨系统合同号主数据映射表(umbrella §12 未决项)— mock 保证 contract_no 一致;真系统若编号不统一再建映射。

## 10. 测试

- **后端**:零新代码,无新单测。license sync 测试加 `biz_pipeline` 后通过(4 点同步)。seed 脚本跑通后 curl 验证 3 dataset 出数 + 漏斗对账数(8/4/7332w/5182w/2150w)。
- **前端**:`pnpm typecheck`;DashboardView/QueryView 渲染;queryKey 命名空间 grep 确认无 `bqa`/`cpa` 残留(纯 `bpp`)。
- **E2E(手动)**:应用中心点磁贴 → 仪表盘显 50% + 3 图表(漏斗/月度/待开票)→ 数据查询 3 视图 → 点行出 modal 明细。

## 11. 落地顺序(给 writing-plans)

1. **数据**:seed_mock_pipeline.py(3 表 + data_source 连接 + 3 dataset)→ 容器内跑 → curl 验证出数。
2. **License/权限**:4 点 + permissions.yaml + roles_custom.yaml + 磁贴 seed + deriveNavId → restart gateway → 磁贴可见。
3. **前端骨架**:app/biz-pipeline 路由 + extensions/biz-pipeline(api/hooks/types + 克隆① ui 组件)→ typecheck。
4. **仪表盘**:DashboardView + 3 图表(cyber 增强,克隆①改数据源)。
5. **查询页**:QueryView + 3 视图 + DrillDownModal(克隆①改视图/下钻 SQL)。
6. **联调 + 截图验证**。

> 因①已落地通用后端端点 + 可复用前端组件,③ 比① 少一个后端任务(无 T1 端点、无 T3 第4 dataset 单独任务),工作量集中在数据 seed + 前端镜像改数。
