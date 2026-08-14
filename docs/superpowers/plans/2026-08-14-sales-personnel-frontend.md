# 销售人员查询 (sales-personnel) 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** 给模块②「销售人员查询」补上应用中心入口、HR 科技感仪表盘(出勤/差旅 KPI)、以人为中心的查询页 + 员工/部门下钻。镜像 ①③ 的 Route B 薄前端形态。

**Architecture:** Route B —— **零后端增量**(① 已落地 2 个通用只读 query 端点,直接复用)。新增独立 seed 脚本建 3 张 mock 表(统一 `employee_id` join key)+ 第 3 条 data_source 连接 + 3 个罐装 dataset。前端镜像 ③ biz-pipeline 结构(`spq` 命名空间)。

**Tech Stack:** FastAPI(无改动)、Next.js 16 / React 19 / Tailwind 4 / TanStack Query / recharts ^3.8.1、PostgreSQL(mock_market,`eai-flow-postgres-ext` 容器)、yaml 驱动权限。

**关联 spec:** `docs/superpowers/specs/2026-08-13-market-analysis-modules-design.md` §6
**镜像参考(逐字克隆来源):** `frontend/src/extensions/biz-pipeline/`(③,已 E2E 验证)
**用户决策:** 范围 = 镜像①③(mock+仪表盘+查询页);RBAC = mock 阶段推迟,留文档化 TODO(真实 HR 接入时再定 RLS vs 注入层)。

---

## Cerebrum 烘焙(执行前必读 —— ①③ 踩过的坑,本计划已规避)

1. **图表颜色用字面 hex。** chart/success/destructive CSS 变量是完整色(oklch/hex)非 HSL 通道。StatCard `style={{}}` + 8 位 hex alpha;图表 hex 常量(BLUE/AMBER/GREEN/RED)。
2. **noUncheckedIndexedAccess: true。** `arr[0]` 在 `.length` 守卫后仍 `T|undefined` → `Object.keys(arr[0] ?? {})`。
3. **no-base-to-string。** `String(unknown)` 报错,typeof 收窄不满足 → 显式 `as string|number|boolean` 或用 `cellText`/`esc` helper。
4. **non-nullable-type-assertion-style。** `x as string` 在 `enabled:!!x` 下 → 用 `x!`。`useDrillDown` 用 `sql!`。
5. **命名空间铁律。** 全模块 `spq` 前缀;dataset label 与 seed 一字不差;grep 确认无 `bqa`/`bpp` 残留。
6. **mock 库独立 + 正确容器名。** 表建在 `mock_market` 库;查表用 `docker exec eai-flow-postgres-ext psql -U agentflow -d mock_market`(注意:是 `eai-flow-postgres-ext`,非 CLAUDE.md 写的 `eai-docker-postgres-ext-1`)。

---

## File Structure

**Backend(新建 1,零后端代码改动):**
- `backend/scripts/seed_mock_sales.py` — 3 表(mock_market)+ 第 3 条 data_source + 3 dataset(幂等)

**License / 权限(改 7):** 同 ③,把 `biz_pipeline`→`sales_personnel`、`biz-pipeline`→`sales-personnel`、`bpp`→`spq`、`bpp_all`→`spq_all`。
- `backend/app/extensions/license/service.py` — `ALL_MODULES` 加 `sales_personnel`
- `frontend/src/extensions/license/labels.ts` — `MODULE_LABELS` 加 `sales_personnel`
- `tools/license/license_generator.py` — `ALL_MODULES` 加 `sales_personnel`
- `backend/tests/test_license_modules_sync.py` — `EXPECTED_KEYS` 加 `sales_personnel`
- `config/permissions.yaml` — 加 `sales_personnel:` 模块块
- `config/roles_custom.yaml` — project_manager / dept_head 各加 nav/page/data_scope
- `backend/app/extensions/database.py` — apps 加 sales-personnel 磁贴(marketing 域,sort=14)
- `frontend/src/extensions/app-center/hooks/useApps.ts` — `deriveNavId` 加 `"sales-personnel":"nav:sales-personnel"`

**Frontend(新建 11,全部克隆 ③ 改命名空间):**
- `frontend/src/app/sales-personnel/layout.tsx` / `page.tsx` / `query/page.tsx`
- `frontend/src/extensions/sales-personnel/types.ts` / `api.ts` / `hooks.ts`
- `frontend/src/extensions/sales-personnel/components/DashboardView.tsx` / `QueryView.tsx` / `DrillDownModal.tsx`
- `frontend/src/extensions/sales-personnel/components/StatCard.tsx` / `ChartCard.tsx` / `TechTooltip.tsx` / `ui/table.tsx`(4 个逐字克隆 ③)

---

## Task 1: 数据 seed(seed_mock_sales.py:3 表 + 连接 + 3 dataset)

**Files:** Create `backend/scripts/seed_mock_sales.py`

### 数据模型(mock_market 库,统一 employee_id join key)

```sql
-- 员工/履历
CREATE TABLE IF NOT EXISTS mock_employee (
  employee_id   TEXT PRIMARY KEY,      -- E001..E012
  name          TEXT NOT NULL,
  employee_no   TEXT NOT NULL,         -- 工号
  department    TEXT NOT NULL,         -- 销售一部/销售二部/技术支持部/市场部
  position      TEXT NOT NULL,
  hire_date     DATE NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active'  -- active/leave/resigned
);
-- 考勤(每天一行)
CREATE TABLE IF NOT EXISTS mock_attendance (
  id            SERIAL PRIMARY KEY,
  employee_id   TEXT NOT NULL REFERENCES mock_employee(employee_id),
  date          DATE NOT NULL,
  status        TEXT NOT NULL,         -- present/leave/absent/trip
  check_in      TIME,
  check_out     TIME
);
-- 差旅/报销
CREATE TABLE IF NOT EXISTS mock_travel (
  trip_id           TEXT PRIMARY KEY,  -- TR-2025-001..
  employee_id       TEXT NOT NULL REFERENCES mock_employee(employee_id),
  destination       TEXT NOT NULL,
  start_date        DATE NOT NULL,
  end_date          DATE NOT NULL,
  purpose           TEXT NOT NULL,
  amount            NUMERIC(14,2) NOT NULL,
  reimburse_status  TEXT NOT NULL      -- pending/approved/rejected
);
```

### Mock 数据故事(供技能推理,非真实员工)

- **12 名员工** 分布 4 部门:销售一部(E001-004)、销售二部(E005-007)、技术支持部(E008-010)、市场部(E011-012)。
  - 11 active + 1 resigned(E010,2025-08 离职,考勤只到 8 月)。
- **考勤**:2025-10/11/12 三个月,工作日(周一至周五)程序生成。权重:present ~85%、trip ~8%、leave ~4%、absent ~3%。离职员工只生成在职期间。check_in/check_out 仅 present 有值。
- **差旅**:~25 趟(2025-10~12),出差型员工(E001/E005/E008 等)多趟,内勤少趟。报销状态:approved ~60%、pending ~30%、rejected ~10%。金额 2000-15000 元/趟。

### 3 个罐装 dataset(只读 SELECT,过 assert_readonly_select 守卫)

```python
DATASETS = [
    {
        "table_name": "spq_attendance_summary",
        "label": "考勤汇总",
        "description": "按部门统计在岗/请假/缺勤/出差天数与出勤率。",
        "default_query": """
            SELECT e.department,
              COUNT(DISTINCT a.employee_id) AS emp_count,
              SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_days,
              SUM(CASE WHEN a.status='leave' THEN 1 ELSE 0 END) AS leave_days,
              SUM(CASE WHEN a.status='absent' THEN 1 ELSE 0 END) AS absent_days,
              SUM(CASE WHEN a.status='trip' THEN 1 ELSE 0 END) AS trip_days,
              ROUND(100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS attendance_rate
            FROM mock_attendance a JOIN mock_employee e ON a.employee_id=e.employee_id
            GROUP BY e.department ORDER BY e.department
        """,
    },
    {
        "table_name": "spq_dept_travel",
        "label": "部门差旅",
        "description": "按部门统计差旅总额、出差次数、人均差旅。",
        "default_query": """
            SELECT e.department,
              COUNT(*) AS trip_count,
              COALESCE(SUM(t.amount),0) AS total_amount,
              COUNT(DISTINCT t.employee_id) AS traveler_count,
              ROUND(COALESCE(SUM(t.amount),0)::numeric / NULLIF(COUNT(DISTINCT t.employee_id),0), 0) AS per_capita
            FROM mock_travel t JOIN mock_employee e ON t.employee_id=e.employee_id
            GROUP BY e.department ORDER BY total_amount DESC
        """,
    },
    {
        "table_name": "spq_reimburse_status",
        "label": "报销状态构成",
        "description": "按报销状态统计笔数与金额(approved/pending/rejected)。",
        "default_query": """
            SELECT reimburse_status,
              COUNT(*) AS cnt,
              COALESCE(SUM(amount),0) AS total_amount
            FROM mock_travel GROUP BY reimburse_status ORDER BY total_amount DESC
        """,
    },
]
```

### 自检(seed 末尾打印,验证一致性)

```
员工=12 在岗=11 离职=1
考勤记录=N(覆盖 2025-10~12)
差旅=25 趟 总额=X 元 待审批=Y 笔
出勤率(全员)=Z%
```

### 幂等 & asyncpg 注意(同 ③)

- 连接参数:`PG_HOST="postgres-ext"`(容器内),`EXT_DB="agentflow"`,`MOCK_DB="mock_market"`,`SOURCE_NAME="sales-personnel"`。
- 重灌用**单语句** `TRUNCATE mock_travel, mock_attendance, mock_employee RESTART IDENTITY CASCADE;`(被 FK 引用的表不能单独 TRUNCATE;顺序:先子表 mock_travel/mock_attendance 再父表 mock_employee,一起 CASCADE)。
- data_source 用 `INSERT...ON CONFLICT(name) DO UPDATE`;dataset 用 `(source_id, table_name)` 唯一 upsert。
- 运行:`docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_sales.py`。
- 验证查询(host):`docker exec eai-flow-postgres-ext psql -U agentflow -d mock_market -c "SELECT COUNT(*) FROM mock_employee"`

- [ ] Step 1: 建 seed 脚本
- [ ] Step 2: 容器内运行,自检数打印正确
- [ ] Step 3: host psql 抽查 3 表行数
- [ ] Step 4: Commit `feat(sales-personnel): seed 3 mock 表(员工/考勤/差旅,统一 employee_id)+ data_source + 3 dataset`

---

## Task 2: License 4 点同步

4 文件各加 `sales_personnel`(license key 用下划线,与 bid_quote/biz_pipeline 同形):
- `license/service.py` ALL_MODULES 末尾
- `labels.ts` MODULE_LABELS:`sales_personnel: "销售人员",`
- `license_generator.py` ALL_MODULES
- `test_license_modules_sync.py` EXPECTED_KEYS

- [ ] Step 1: 改 4 文件
- [ ] Step 2: host 验证 4 点一致(Python 一行跑 ALL_MODULES ∩ labels ∩ generator ∩ EXPECTED_KEYS)
- [ ] Step 3: Commit `feat(sales-personnel): license 注册 sales_personnel 模块(4 点同步)`

---

## Task 3: 权限 yaml + 磁贴 + nav 映射

- `config/permissions.yaml`:克隆 `biz_pipeline:` 块 → `sales_personnel:`,改 nav_id `nav:sales-personnel`、pages `spq:page:dashboard`/`spq:page:query`、data_scope `spq_all`。
- `config/roles_custom.yaml`:project_manager + dept_head 各加 `nav:sales-personnel` + `spq_all` scope + `spq:page:*` pages(同 ③ 给 biz-pipeline 的位置,用 Python 脚本幂等插入)。
- `database.py`:apps 列表加磁贴 `{"app_id":"sales-personnel","name":"销售人员","desc":"员工考勤/差旅/履历查询","icon":"users","domain":"marketing","stage":"analysis","path":"/sales-personnel","license":"sales_personnel","admin":False,"sort":14,"sort_key":"xiaoshourenyuan"}`,apps 计数 +1。
- `useApps.ts`:`deriveNavId` 加 `"sales-personnel": "nav:sales-personnel",`。

- [ ] Step 1: 改 4 处
- [ ] Step 2: `docker compose -p eai-docker restart gateway`,磁贴自动播种
- [ ] Step 3: Commit `feat(sales-personnel): 权限点 + roles_custom + 应用中心磁贴(marketing)+ nav 映射`

---

## Task 4: 前端骨架

逐字克隆 ③ 的 `biz-pipeline/` → `sales-personnel/`,改命名空间 `bpp`→`spq`、SOURCE_NAME `'biz-pipeline'`→`'sales-personnel'`、label 字符串。建:
- `types.ts`:EmployeeRow / AttendanceRow / TravelRow / DeptAttRow / DeptTravelRow / ReconRow(Record<string,string|number|null>)
- `api.ts`:resolveSourceId/queryDataset/querySql/resolveDatasetId/clearSalesCache(SOURCE_NAME='sales-personnel', API_BASE='/data-sources')
- `hooks.ts`:KEYS={all,source,funnel:用考勤汇总;...};useAttendanceSummary/useDeptTravel/useReimburseStatus(3 罐装,label 与 seed 一字不差);useEmployeeList(原始 SQL `SELECT * FROM mock_employee ORDER BY employee_id`);useTravelList(原始 SQL `SELECT trip_id,employee_id,(SELECT name FROM mock_employee e WHERE e.employee_id=t.employee_id) AS name,destination,start_date,end_date,amount,reimburse_status FROM mock_travel t ORDER BY start_date DESC`);useDrillDown(sql)
- `components/ui/table.tsx` / `StatCard.tsx` / `ChartCard.tsx` / `TechTooltip.tsx`(4 个逐字克隆)
- `app/sales-personnel/layout.tsx`(navItems: spq:page:dashboard/query,ShellLayout,canPage 过滤)+ `page.tsx`(DashboardView)+ `query/page.tsx`(QueryView)

- [ ] Step 1: 克隆 4 个纯组件(table/StatCard/ChartCard/TechTooltip)改 import 路径
- [ ] Step 2: 建 types/api/hooks
- [ ] Step 3: 建 app 路由 3 文件
- [ ] Step 4: typecheck + eslint 清
- [ ] Step 5: Commit `feat(sales-personnel): 前端骨架 T4(types/api/hooks + 路由 + 克隆组件)`

---

## Task 5: 仪表盘(DashboardView.tsx)

5 KPI + 3 图表(镜像 ③ DashboardView 的结构,recharts 字面 hex):

**5 KPI:**
1. 员工总数(`SELECT COUNT(*) FROM mock_employee` 或考勤汇总 sum emp_count)→ 用一个新单行 dataset 或前端算
2. 在岗人数(`status='active'`)
3. 月度出勤率(全员,present/总)
4. 差旅总额(∑ travel.amount)
5. 待审批报销(pending 笔数 + 金额)

> KPI 落地简化(ponytail):加一个罐装单行 dataset `spq_kpi`(label="HR总览")返回 employee_total/active_count/attendance_rate/travel_total/pending_count/pending_amount,DashboardView 取 `[0]`。避免前端 5 次往返。

**3 图表:**
1. **部门差旅对比**(BarChart,dept_travel:department vs total_amount,BLUE 渐变)—— 哪个部门花最多差旅
2. **出勤状态分布**(BarChart,attendance_summary 堆叠:present/leave/absent/trip 按部门)或(各部门 attendance_rate 对比)。选**各部门出勤率对比**(简洁,BLUE/AMBER)
3. **报销状态构成**(BarChart,reimburse_status:reimburse_status vs total_amount,pending 用 RED 渐变高亮)

- [ ] Step 1: seed 补 spq_kpi dataset(label="HR总览"),重跑 seed
- [ ] Step 2: hooks.ts 加 useHrKpi(label "HR总览")
- [ ] Step 3: 建 DashboardView(5 StatCard + 3 ChartCard)
- [ ] Step 4: typecheck + eslint
- [ ] Step 5: Commit `feat(sales-personnel): T5 仪表盘(5 KPI + 3 recharts 图表)`

---

## Task 6: 查询页(QueryView.tsx + DrillDownModal.tsx)

3 tab(以人为中心,镜像 ③ 的 pill tab + 行下钻):

1. **员工明细**(useEmployeeList):列 employee_id/name/employee_no/department/position/hire_date/status。点行 → 下钻 modal:该员工**考勤明细**(`SELECT date,status,check_in,check_out FROM mock_attendance WHERE employee_id='E001' ORDER BY date`)+ 标题 `员工考勤 · E001 姓名`。active 行可点;resigned 行仍可点(看历史,不禁用)。
2. **差旅报销**(useTravelList):列 trip_id/name(员工)/destination/start_date/end_date/amount/reimburse_status。点行 → 下钻 modal:该员工**全部差旅**(`SELECT trip_id,destination,start_date,end_date,amount,reimburse_status FROM mock_travel WHERE employee_id='E001' ORDER BY start_date`)+ 标题 `员工差旅 · E001 姓名`。
3. **部门考勤**(useAttendanceSummary):列 department/emp_count/present_days/leave_days/absent_days/trip_days/attendance_rate。点行 → 下钻 modal:该部门**考勤明细**(JOIN 取该部门全员考勤:`SELECT a.date,e.name,a.status,a.check_in,a.check_out FROM mock_attendance a JOIN mock_employee e ON a.employee_id=e.employee_id WHERE e.department='销售一部' ORDER BY a.date,e.name`)+ 标题 `部门考勤 · 销售一部`。

下钻 UX(同 ③):DrillDownModal 克隆;`esc()` 拼 SQL(单引号转义);表格显示单元格用 `cellText`(对象走 JSON),不用 esc。

- [ ] Step 1: 克隆 DrillDownModal.tsx 改 import 路径
- [ ] Step 2: 建 QueryView(3 tab + onRowDrill 分支)
- [ ] Step 3: typecheck + eslint
- [ ] Step 4: Commit `feat(sales-personnel): T6 查询页(员工/差旅/部门考勤 3 视图 + 行下钻 modal)`

---

## Task 7: 联调 + 全量验证

- [ ] Step 1: `cd frontend && pnpm typecheck`(sales-personnel 清)+ `pnpm lint`(或 npx eslint --fix)
- [ ] Step 2: `docker compose -p eai-docker restart gateway` → 磁贴自动播种;`restart frontend` 容器拾取
- [ ] Step 3: 浏览器 E2E:`/sales-personnel` 仪表盘 5 KPI + 3 图表(核对自检数);`/sales-personnel/query` 3 tab + 下钻(resigned 员工可点看历史、差旅→该员工全部差旅、部门→该部门考勤明细)
- [ ] Step 4: RBAC TODO 文档化 —— 在 seed 脚本 docstring +cerebrum 记「真实 HR 接入需行级 RBAC(RLS/注入层),mock 阶段 fail-closed 守卫已够」
- [ ] Step 5: OpenWolf bookkeeping(cerebrum/memory/anatomy)+ 最终 commit
- [ ] Step 6: (可选)designqc 截图

---

## Self-Review

- **Spec 覆盖:** §6 数据层(员工/考勤/差旅 3 视图)✓ T1;对话侧 MCP(罐装 dataset + 只读 SQL)✓ data_source 复用零自建;技能 `sales-personnel-query/SKILL.md` —— **本计划不含 skill**(前端模块优先,skill 可后补,非阻塞);🔒 行级权限 ✓ T7 Step 4 文档化 TODO(用户决策:mock 推迟);前端(仪表盘+查询)✓ T4-T6。
- **命名空间一致:** spq:page:* / ["spq",...] / spq_* / sales-personnel / nav:sales-personnel —— 全 spq,与 bqa/bpp 隔离。
- **类型一致:** hooks label 字符串与 seed DATASETS label 一字不差(考勤汇总/部门差旅/报销状态构成/HR总览)。
