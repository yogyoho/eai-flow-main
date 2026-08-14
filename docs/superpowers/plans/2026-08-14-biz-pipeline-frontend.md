# 投标/合同/开票管线查询 (biz-pipeline) 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给模块③「管线查询」补上应用中心入口、科技感仪表盘(金额漏斗+月度节奏+待开票对账)、固定视图查询页 + 按合同号下钻,让市场部用户可视化使用。

**Architecture:** Route B 薄前端 —— **零后端增量**(① 已落地 2 个通用只读 query 端点,直接复用)。新增独立 seed 脚本建 3 张 mock 表(统一 `contract_no` join key)+ 第 2 条 data_source 连接 + 3 个罐装 dataset。前端镜像 ① bid-quote 结构(`bpp` 命名空间),项目管理 list 浅色 + 图表 cyber 增强。

**Tech Stack:** FastAPI(Python 3.12,无改动)、Next.js 16 / React 19 / Tailwind 4 / TanStack Query / recharts ^3.8.1、PostgreSQL(mock_market,postgres-ext)、yaml 驱动权限。

**关联 spec:** `docs/superpowers/specs/2026-08-14-biz-pipeline-frontend-design.md`
**镜像参考(逐字克隆来源):** `frontend/src/extensions/bid-quote/`(① 投标报价分析,已落地验证)

---

## Cerebrum 烘焙(执行前必读 —— ① 踩过的坑,本计划已规避)

1. **图表颜色用字面 hex,禁用 `hsl(var(--chart-X))`。** 本项目 chart/success/destructive CSS 变量是完整颜色(oklch/hex)非 HSL 通道。StatCard 用 `style={{}}` + 8 位 hex(末2位 alpha),图表用 hex 常量(BLUE=`#3b82f6`/AMBER=`#f6bd16`/GREEN=`#10b981`/RED=`#f43f5e`)。
2. **noUncheckedIndexedAccess: true。** `arr[0]` 在 `.length` 守卫后仍是 `T|undefined`(守卫不收窄索引访问)→ `Object.keys(arr[0])` 报 TS2769。用 `arr[0] ?? {}` 兜底。
3. **no-base-to-string。** `String(unknown)` 报错,`typeof` 收窄不满足该静态规则 → 显式 `v as string|number|boolean` 后再 String(),对象走 JSON。统一用模块级 `cellText`/`esc` helper。
4. **non-nullable-type-assertion-style。** `x as string` 在 `enabled: !!x` 守卫下 → 规则偏好 `x!`。`useDrillDown` 里用 `sql!`。
5. **命名空间铁律。** 全模块 `bpp` 前缀;dataset label 与 seed 一字不差;grep 确认无 `bqa`/`cpa`/`csp` 残留。
6. **mock 库独立。** 表建在 `mock_market` 库(非 agentflow);data_source 连接配置指向它。查表用 `docker exec eai-docker-postgres-ext-1 psql -U agentflow -d mock_market`。

---

## File Structure

**Backend(新建 1,零后端代码改动):**
- `backend/scripts/seed_mock_pipeline.py` — 新建:3 表(mock_market 库)+ 第 2 条 data_source 连接 + 3 dataset(幂等)

**License / 权限(改 7):**
- `backend/app/extensions/license/service.py` — `ALL_MODULES` 加 `biz_pipeline`
- `frontend/src/extensions/license/labels.ts` — `MODULE_LABELS` 加 `biz_pipeline`
- `tools/license/license_generator.py` — `ALL_MODULES` 加 `biz_pipeline`
- `backend/tests/test_license_modules_sync.py` — `EXPECTED_KEYS` 加 `biz_pipeline`
- `config/permissions.yaml` — 加 `biz_pipeline:` 模块块(克隆 bid_quote)
- `config/roles_custom.yaml` — user / dept_head 角色各加 nav/page/data_scope
- `backend/app/extensions/database.py` — apps 加 biz-pipeline 磁贴(marketing 域①已建,无需再加)
- `frontend/src/extensions/app-center/hooks/useApps.ts` — `deriveNavId` 加映射

**Frontend(新建 11):**
- `frontend/src/app/biz-pipeline/layout.tsx`
- `frontend/src/app/biz-pipeline/page.tsx`
- `frontend/src/app/biz-pipeline/query/page.tsx`
- `frontend/src/extensions/biz-pipeline/types.ts`
- `frontend/src/extensions/biz-pipeline/api.ts`
- `frontend/src/extensions/biz-pipeline/hooks.ts`
- `frontend/src/extensions/biz-pipeline/components/DashboardView.tsx`
- `frontend/src/extensions/biz-pipeline/components/QueryView.tsx`
- `frontend/src/extensions/biz-pipeline/components/StatCard.tsx`(克隆①)
- `frontend/src/extensions/biz-pipeline/components/ChartCard.tsx`(克隆①)
- `frontend/src/extensions/biz-pipeline/components/TechTooltip.tsx`(克隆①)
- `frontend/src/extensions/biz-pipeline/components/DrillDownModal.tsx`(克隆①)
- `frontend/src/extensions/biz-pipeline/components/ui/table.tsx`(克隆①)

---

## Task 1: 数据 seed(seed_mock_pipeline.py:3 表 + 连接 + 3 dataset)

**Files:**
- Create: `backend/scripts/seed_mock_pipeline.py`

### - [ ] Step 1: 建 seed 脚本

`backend/scripts/seed_mock_pipeline.py`(镜像 `seed_mock_market.py` 结构,改表/数据/连接名/dataset):

```python
#!/usr/bin/env python3
"""模块③ 投标/合同/开票管线查询 — mock 数据 + data_source 元数据 seed(幂等)。

EAI-CUSTOM: 市场部门模块③。真实 CRM/财务/合同系统接入前的链路演示 mock。
形态 = 路线 B(data_source 复用),零自建扩展代码。统一 contract_no 跨系统 join key。

在 gateway 容器内运行:
    docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_pipeline.py

幂等:重复运行只重灌样例 + upsert 元数据,不产生重复行。

数据故事(供技能推理,非真实业绩):
- 8 个投标项目(2025),4 中标 → 4 合同 → 开票(2 全额、2 部分);
- 漏斗:8 投标 → 4 中标(50%) → 4 合同(7332 万) → 已开票 5182 万,待开票 2150 万;
- 落标方报价 = 中标价 × 上浮(5%-17%),避免同比例无差异。
"""

import asyncio
import json
import os
from datetime import date

import asyncpg

# ── 连接参数(默认 docker 网络内 postgres-ext;gateway 容器视角)──
PG_HOST = os.environ.get("EXTENSIONS_DB_HOST", "postgres-ext")
PG_PORT = int(os.environ.get("EXTENSIONS_DB_PORT", "5432"))
PG_USER = os.environ.get("EXTENSIONS_DB_USER", "agentflow")
PG_PASS = os.environ.get("EXTENSIONS_DB_PASSWORD", "agentflow123")
EXT_DB = os.environ.get("EXTENSIONS_DB_NAME", "agentflow")  # extensions 库(data_sources 表所在)
MOCK_DB = "mock_market"  # 与①共用 mock 库,表名隔离(mock_pipeline_*)
SOURCE_NAME = "biz-pipeline"

SOURCE_CONNECTION_CONFIG = {
    "driver": "postgresql+asyncpg",
    "host": PG_HOST,
    "port": PG_PORT,
    "database": MOCK_DB,
    "username": PG_USER,
    "password": PG_PASS,
}

# ── 8 个投标项目(bid_no, 项目, 客户, 日期, 是否中标, 我方报价万元, 合同号, 合同名, 合同额万, 已开票万列表)──
# won=False 的行 contract_no=None;落标报价 = 中标报价 × 上浮(项目间 5%-17%)
# 金额单位:万元;seed 时 ×10000 存元。
PROJECTS = [
    ("TB-2025-001", "华能铜川电厂二期循环水系统", "华能铜川电厂", "2025-03-15", True, 1850.0,
     "HT-2025-001", "华能铜川电厂循环水系统设备合同", 1800.0, [1800.0]),
    ("TB-2025-002", "宁夏宝丰甲醇项目净化装置", "宁夏宝丰能源", "2025-04-22", False, 2782.5,
     None, None, 0, []),
    ("TB-2025-003", "内蒙古久泰乙二醇装置", "内蒙古久泰集团", "2025-06-10", False, 518.4,
     None, None, 0, []),
    ("TB-2025-004", "大唐国际雷州电厂烟气脱硫", "大唐国际雷州电厂", "2025-07-18", False, 3907.2,
     None, None, 0, []),
    ("TB-2025-005", "中天合创煤化工水处理", "中天合创能源", "2025-09-05", True, 85.0,
     "HT-2025-002", "中天合创煤化工水处理设备合同", 82.0, [82.0]),
    ("TB-2025-006", "万华化学烟台PDH装置", "万华化学集团", "2025-11-12", False, 2730.6,
     None, None, 0, []),
    ("TB-2025-007", "陕西榆林煤化工气化装置", "陕西榆林能源", "2025-10-20", True, 4200.0,
     "HT-2025-003", "陕西榆林煤化工气化装置合同", 4000.0, [2500.0]),  # 部分,待开 1500
    ("TB-2025-008", "河北唐山钢铁余热锅炉", "河北唐山钢铁", "2025-12-08", True, 1500.0,
     "HT-2025-004", "河北唐山钢铁余热锅炉合同", 1450.0, [800.0]),  # 部分,待开 650
]

# ── 3 个罐装 dataset(只读 SELECT,过 assert_readonly_select 守卫)──
DATASETS = [
    {
        "table_name": "bpp_funnel",
        "label": "管线漏斗总览",
        "description": "投标数/中标数/合同数 + 投标总额/中标总额/合同总额/已开票总额/待开票总额(单行汇总)。",
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
        """.strip(),
    },
    {
        "table_name": "bpp_monthly",
        "label": "月度投标节奏",
        "description": "按月统计投标数与中标数,定位投标旺淡季。",
        "default_query": """
            SELECT to_char(bid_date,'YYYY-MM') AS ym,
              COUNT(*) AS bids,
              COUNT(*) FILTER (WHERE status='won') AS won
            FROM mock_pipeline_bid GROUP BY 1 ORDER BY 1
        """.strip(),
    },
    {
        "table_name": "bpp_contract_recon",
        "label": "合同开票对账",
        "description": "每合同:合同额/已开票/待开票,待开票降序,支撑催开票预警。",
        "default_query": """
            SELECT c.contract_no, c.contract_name, c.customer, c.amount,
              COALESCE(SUM(i.total_amount) FILTER (WHERE i.status='issued'),0) AS invoiced,
              c.amount - COALESCE(SUM(i.total_amount) FILTER (WHERE i.status='issued'),0) AS uninvoiced
            FROM mock_contract c
            LEFT JOIN mock_invoice i ON i.contract_no = c.contract_no
            GROUP BY c.contract_no, c.contract_name, c.customer, c.amount
            ORDER BY uninvoiced DESC
        """.strip(),
    },
]


async def main() -> None:
    common = dict(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS)

    # 1. mock_market 库(① 已建,幂等跳过)
    sys_conn = await asyncpg.connect(**common, database=EXT_DB)
    try:
        await sys_conn.execute(f'CREATE DATABASE "{MOCK_DB}"')
        print(f"[ok] 已建库 {MOCK_DB}")
    except asyncpg.DuplicateDatabaseError:
        print(f"[skip] 库 {MOCK_DB} 已存在")
    finally:
        await sys_conn.close()

    # 2. 建 3 表 + 重灌(幂等)
    mock = await asyncpg.connect(**common, database=MOCK_DB)
    await mock.execute(
        """
        CREATE TABLE IF NOT EXISTS mock_pipeline_bid (
          bid_id          TEXT PRIMARY KEY,
          project_name    TEXT NOT NULL,
          contract_no     TEXT,
          customer        TEXT,
          bid_date        DATE,
          our_bid_amount  NUMERIC(14,2),
          status          TEXT NOT NULL,
          competitor_name TEXT
        );
        CREATE TABLE IF NOT EXISTS mock_contract (
          contract_no   TEXT PRIMARY KEY,
          contract_name TEXT,
          customer      TEXT,
          sign_date     DATE,
          amount        NUMERIC(14,2),
          status        TEXT
        );
        CREATE TABLE IF NOT EXISTS mock_invoice (
          invoice_id   TEXT PRIMARY KEY,
          contract_no  TEXT NOT NULL REFERENCES mock_contract(contract_no) ON DELETE CASCADE,
          invoice_date DATE,
          amount       NUMERIC(14,2),
          tax_amount   NUMERIC(14,2),
          total_amount NUMERIC(14,2),
          status       TEXT
        );
        """
    )
    await mock.execute("TRUNCATE mock_invoice; TRUNCATE mock_contract; TRUNCATE mock_pipeline_bid RESTART IDENTITY CASCADE;")

    bid_rows, contract_rows, invoice_rows = [], [], []
    inv_seq = 0
    for bid_id, proj, cust, bdate, won, bid_amt_w, cno, cname, camt_w, invoices_w in PROJECTS:
        status = "won" if won else "lost"
        bid_rows.append((bid_id, proj, cno, cust, date.fromisoformat(bdate), round(bid_amt_w * 10000, 2), status, "东方宏业"))
        if won and cno:
            sign_date = date.fromisoformat(bdate)  # mock:签约日同投标日
            contract_rows.append((cno, cname, cust, sign_date, round(camt_w * 10000, 2), "executing"))
            for amt_w in invoices_w:
                inv_seq += 1
                inv_id = f"FP-2025-{inv_seq:03d}"
                total = round(amt_w * 10000, 2)
                # mock:不含税额 = 含税/1.13,税额 = 含税 - 不含税
                base = round(total / 1.13, 2)
                tax = round(total - base, 2)
                invoice_rows.append((inv_id, cno, sign_date, base, tax, total, "issued"))

    await mock.executemany(
        "INSERT INTO mock_pipeline_bid (bid_id,project_name,contract_no,customer,bid_date,our_bid_amount,status,competitor_name) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        bid_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_contract (contract_no,contract_name,customer,sign_date,amount,status) "
        "VALUES ($1,$2,$3,$4,$5,$6)",
        contract_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_invoice (invoice_id,contract_no,invoice_date,amount,tax_amount,total_amount,status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7)",
        invoice_rows,
    )
    print(f"[ok] 已灌 {len(bid_rows)} bid / {len(contract_rows)} contract / {len(invoice_rows)} invoice")
    await mock.close()

    # 3. extensions 库 upsert 第 2 条 data_source 连接 + 3 dataset(幂等)
    ext = await asyncpg.connect(**common, database=EXT_DB)
    cfg_json = json.dumps(SOURCE_CONNECTION_CONFIG)
    src_id = await ext.fetchval("SELECT id FROM data_sources WHERE name=$1", SOURCE_NAME)
    if src_id is None:
        src_id = await ext.fetchval(
            "INSERT INTO data_sources (id,name,description,type,connection_config,auth_type,sync_mode,status,created_at,updated_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4::jsonb,$5,$6,$7,now(),now()) RETURNING id",
            SOURCE_NAME,
            "模块③ 管线查询 mock 数据源(CRM 投标/合同/财务开票,统一 contract_no)。",
            "database",
            cfg_json,
            "none",
            "manual",
            "connected",
        )
        print(f"[ok] 已建 data_source '{SOURCE_NAME}'")
    else:
        await ext.execute(
            "UPDATE data_sources SET description=$2, connection_config=$3::jsonb, status='connected' WHERE id=$1",
            src_id,
            "模块③ 管线查询 mock 数据源(CRM 投标/合同/财务开票,统一 contract_no)。",
            cfg_json,
        )
        print(f"[ok] 已更新 data_source '{SOURCE_NAME}'")

    for ds in DATASETS:
        await ext.execute(
            "INSERT INTO data_source_datasets (id,source_id,table_name,label,description,default_query,created_at,updated_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4,$5,now(),now()) "
            "ON CONFLICT (source_id, table_name) DO UPDATE SET "
            "  label=EXCLUDED.label, description=EXCLUDED.description, "
            "  default_query=EXCLUDED.default_query, updated_at=now()",
            src_id,
            ds["table_name"],
            ds["label"],
            ds["description"],
            ds["default_query"],
        )
    print(f"[ok] 已 upsert {len(DATASETS)} 个 dataset")
    await ext.close()

    # 自检(肉眼校验漏斗+对账)
    chk = await asyncpg.connect(**common, database=MOCK_DB)
    n_bid = await chk.fetchval("SELECT count(*) FROM mock_pipeline_bid")
    n_won = await chk.fetchval("SELECT count(*) FROM mock_pipeline_bid WHERE status='won'")
    c_total = await chk.fetchval("SELECT coalesce(sum(amount),0) FROM mock_contract")
    i_total = await chk.fetchval("SELECT coalesce(sum(total_amount),0) FROM mock_invoice WHERE status='issued'")
    print("\n===== 自检 =====")
    print(f"bid={n_bid} won={n_won} 合同总额={c_total/10000:.0f}万 已开票={i_total/10000:.0f}万 待开票={(c_total-i_total)/10000:.0f}万")
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
```

### - [ ] Step 2: 跑 seed(容器内,幂等)

```bash
docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/python scripts/seed_mock_pipeline.py'
```
Expected: `[ok] 已灌 8 bid / 4 contract / 4 invoice` + 自检打印 `bid=8 won=4 合同总额=7332万 已开票=5182万 待开票=2150万`。

### - [ ] Step 3: 重启 gateway(使 data_source 缓存感知 biz-pipeline 连接)

```bash
docker compose -p eai-docker restart gateway
```

### - [ ] Step 4: curl 验证 3 dataset 出数(经已就绪的 query 端点)

```bash
# 拿 biz-pipeline 的 source id
SID=$(docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -tAc "SELECT id FROM data_sources WHERE name='biz-pipeline'")
# 列 dataset(确认 3 条)
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT label, table_name FROM data_source_datasets WHERE source_id='$SID' ORDER BY label;"
```
Expected: 3 行(`合同开票对账 | bpp_contract_recon`、`月度投标节奏 | bpp_monthly`、`管线漏斗总览 | bpp_funnel`)。

### - [ ] Step 5: Commit

```bash
git add backend/scripts/seed_mock_pipeline.py
git commit -m "feat(biz-pipeline): seed 3 mock 表(投标/合同/开票,统一 contract_no)+ data_source 连接 + 3 dataset"
```

---

## Task 2: License 4 点同步

**Files:**
- Modify: `backend/app/extensions/license/service.py`(`ALL_MODULES`)
- Modify: `frontend/src/extensions/license/labels.ts`(`MODULE_LABELS`)
- Modify: `tools/license/license_generator.py`(`ALL_MODULES`)
- Modify: `backend/tests/test_license_modules_sync.py`(`EXPECTED_KEYS`)

### - [ ] Step 1: 先让同步测试失败(确认要改的 4 处)

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_license_modules_sync.py -v'`
Expected: FAIL,提示 `biz_pipeline` 缺失。

### - [ ] Step 2: 4 处各加 `biz_pipeline`

```bash
grep -n "bid_quote" backend/app/extensions/license/service.py frontend/src/extensions/license/labels.ts tools/license/license_generator.py backend/tests/test_license_modules_sync.py
```

在每处 `bid_quote` 条目旁加同形式的 `biz_pipeline`:
- `backend/app/extensions/license/service.py` 的 `ALL_MODULES`:加 `"biz_pipeline"`
- `frontend/src/extensions/license/labels.ts` 的 `MODULE_LABELS`:加 `biz_pipeline: "管线查询",`
- `tools/license/license_generator.py` 的 `ALL_MODULES`:加 `"biz_pipeline"`
- `backend/tests/test_license_modules_sync.py` 的 `EXPECTED_KEYS`:加 `"biz_pipeline"`

### - [ ] Step 3: 跑测试确认通过

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_license_modules_sync.py -v'`
Expected: PASS。

### - [ ] Step 4: Commit

```bash
git add backend/app/extensions/license/service.py frontend/src/extensions/license/labels.ts tools/license/license_generator.py backend/tests/test_license_modules_sync.py
git commit -m "feat(biz-pipeline): license 注册 biz_pipeline 模块(4 点同步)"
```

---

## Task 3: 权限 yaml + 应用中心磁贴 + nav 映射

**Files:**
- Modify: `config/permissions.yaml`(加 `biz_pipeline:` 模块块)
- Modify: `config/roles_custom.yaml`(user / dept_head 各加 nav/page)
- Modify: `backend/app/extensions/database.py`(apps 加 biz-pipeline 磁贴)
- Modify: `frontend/src/extensions/app-center/hooks/useApps.ts`(`deriveNavId` 加映射)

> 注意:`marketing` 域①已加(database.py domains seed + 已有库已补),③ 复用,无需再加。

### - [ ] Step 1: permissions.yaml 加 `biz_pipeline:` 模块块

在 `config/permissions.yaml` 的 `bid_quote:` 块之后插入(用 grep 定位 `bqa_dept`):

```bash
grep -n "bqa_dept\|bid_quote:" config/permissions.yaml
```

在 `bid_quote:` 块结束后(下一个模块块前)插入:

```yaml
  # ─── 管线查询（应用中心 → 市场营销；Route B 数据源只读视图）───
  biz_pipeline:
    display_name: "管线查询"
    nav_id: "nav:biz-pipeline"
    pages:
      - id: "bpp:page:dashboard"
        display_name: "管线仪表盘"
      - id: "bpp:page:query"
        display_name: "数据查询"
    data_scopes:
      - { id: "bpp_all", display_name: "全部管线数据", rule_template: {} }
```

同时在 `project_manager` 与 `dept_head` 角色块的 `data_scopes:` 列表里各加一行 `- bpp_all`(与既有 `- bqa_dept` 并列;若无 bqa_dept 则与 `- csp_dept` 并列)。

### - [ ] Step 2: roles_custom.yaml 给 user 角色加权限点

`config/roles_custom.yaml` 里 level 60 的角色。三处插入(用 grep 定位 bid-quote 的插入点 `nav:bid-quote` / `bqa_dept` / `bqa:page`):

**nav**(在 `- nav:bid-quote` 后加 `- nav:biz-pipeline`)
**data_scopes**(在 `bqa_dept` 后加 `bpp_all`)
**pages**(在 `- bqa:page:query` 后加 `- bpp:page:dashboard`、`- bpp:page:query`)

### - [ ] Step 3: roles_custom.yaml 给 dept_head 角色加权限点

`dept_head:` 角色块。三处插入(同样定位 bid-quote 既有插入点):
**nav** 加 `- nav:biz-pipeline`;**data_scopes** 加 `bpp_all`;**pages** 加 `- bpp:page:dashboard`、`- bpp:page:query`。

### - [ ] Step 4: database.py 加 biz-pipeline 磁贴

`backend/app/extensions/database.py` apps 列表,在 `bid-quote` 磁贴之后加:

```python
                    {"app_id": "bid-quote", "name": "投标报价分析", "desc": "投标中标率、我方与友商报价对比、自产外购构成分析",
                     "icon": "gavel", "domain": "marketing", "stage": "analysis",
                     "path": "/bid-quote", "license": "bid_quote", "admin": False, "sort": 12, "sort_key": "toubaoajiagenfenxi"},
                    {"app_id": "biz-pipeline", "name": "管线查询", "desc": "投标/合同/开票管线漏斗与对账",
                     "icon": "workflow", "domain": "marketing", "stage": "analysis",
                     "path": "/biz-pipeline", "license": "biz_pipeline", "admin": False, "sort": 13, "sort_key": "guanxianchaxun"},
```

> seed 日志计数:① 已改为 `6 domains + 12 apps`;③ 加 1 磁贴 → 改为 `6 domains + 13 apps`。用 grep 定位该字符串:
> `grep -n "domains + 12 apps" backend/app/extensions/database.py` → 改 `12 apps` 为 `13 apps`。

### - [ ] Step 5: useApps.ts 加 nav 映射

`frontend/src/extensions/app-center/hooks/useApps.ts` 的 `deriveNavId` mapping 加一行(在 `"bid-quote": "nav:bid-quote"` 后):

```typescript
    "bid-quote": "nav:bid-quote",
    "biz-pipeline": "nav:biz-pipeline",
```

### - [ ] Step 6: 重启 gateway + 补磁贴(已有库,ON CONFLICT DO NOTHING)

```bash
docker compose -p eai-docker restart gateway
# 已有库补 biz-pipeline 磁贴(marketing 域①已补,无需再加 domain)
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "INSERT INTO app_definitions (id,app_id,name,description,icon_name,business_domain,stage_tag,path,license_module,admin_only,sort_order,sort_key,is_builtin) VALUES (gen_random_uuid(),'biz-pipeline','管线查询','投标/合同/开票管线漏斗与对账','workflow','marketing','analysis','/biz-pipeline','biz_pipeline',false,13,'guanxianchaxun',true) ON CONFLICT (app_id) DO NOTHING;"
```

### - [ ] Step 7: 验证磁贴入库

```bash
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT app_id,name,license_module,business_domain FROM app_definitions WHERE app_id='biz-pipeline';"
```
Expected: 1 行 biz-pipeline。

### - [ ] Step 8: Commit

```bash
git add config/permissions.yaml config/roles_custom.yaml backend/app/extensions/database.py frontend/src/extensions/app-center/hooks/useApps.ts
git commit -m "feat(biz-pipeline): 权限点 + 应用中心磁贴(marketing 域)+ nav 映射"
```

---

## Task 4: 前端骨架(api/hooks/types + 路由 + table + layout)

**Files:**
- Create: `frontend/src/extensions/biz-pipeline/types.ts`
- Create: `frontend/src/extensions/biz-pipeline/api.ts`
- Create: `frontend/src/extensions/biz-pipeline/hooks.ts`
- Create: `frontend/src/extensions/biz-pipeline/components/ui/table.tsx`(克隆①)
- Create: `frontend/src/app/biz-pipeline/layout.tsx`
- Create: `frontend/src/app/biz-pipeline/page.tsx`
- Create: `frontend/src/app/biz-pipeline/query/page.tsx`

### - [ ] Step 1: types.ts

`frontend/src/extensions/biz-pipeline/types.ts`:

```typescript
/**
 * 管线查询(biz-pipeline)类型 —— 对齐 data_source 罐装 dataset 列。
 * Decimal/numeric 经 JSON 序列化为 string。
 */

export interface FunnelRow {
  bid_count: number;
  won_count: number;
  contract_count: number;
  bid_amount_total: string;
  won_amount_total: string;
  contract_total: string;
  invoiced_total: string;
  uninvoiced_total: string;
}

export interface MonthlyRow {
  ym: string;
  bids: number;
  won: number;
}

export interface ReconRow {
  contract_no: string;
  contract_name: string;
  customer: string;
  amount: string;
  invoiced: string;
  uninvoiced: string;
}

/** mock_pipeline_bid 明细行:列动态,用索引签名。 */
export type BidRow = Record<string, string | number | boolean | null>;

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  row_count: number;
  label?: string | null;
}
```

### - [ ] Step 2: api.ts(克隆①,改 source name)

`frontend/src/extensions/biz-pipeline/api.ts`:

```typescript
/**
 * biz-pipeline API client —— Route B 薄前端直调 data_source REST(零后端增量,复用①端点)。
 * base=/api/extensions(authFetch 默认),data-sources 路由前缀 /data-sources。
 */

import { authFetch } from "@/extensions/api/client";

import type { QueryResult } from "./types";

const API_BASE = "/data-sources";
const SOURCE_NAME = "biz-pipeline";

let sourceIdCache: string | null = null;
const datasetIdCache: Record<string, string> = {};

interface ListItem {
  id: string;
  name?: string;
  label?: string;
}

export async function resolveSourceId(name = SOURCE_NAME): Promise<string> {
  if (sourceIdCache) return sourceIdCache;
  const resp = await authFetch<{ items: ListItem[] }>(API_BASE);
  const hit = resp.items.find((s) => s.name === name);
  if (!hit) throw new Error(`数据源 "${name}" 未找到`);
  sourceIdCache = hit.id;
  return sourceIdCache;
}

export async function resolveDatasetId(sourceId: string, label: string): Promise<string> {
  if (datasetIdCache[label]) return datasetIdCache[label];
  const resp = await authFetch<{ items: ListItem[] }>(`${API_BASE}/${sourceId}/datasets`);
  const hit = resp.items.find((d) => d.label === label);
  if (!hit) throw new Error(`数据集 "${label}" 未找到`);
  datasetIdCache[label] = hit.id;
  return datasetIdCache[label];
}

export async function queryDataset(sourceId: string, datasetId: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/datasets/${datasetId}/query`, { method: "POST" });
}

export async function querySql(sourceId: string, sql: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export function clearBizPipelineCache() {
  sourceIdCache = null;
  for (const k of Object.keys(datasetIdCache)) delete datasetIdCache[k];
}
```

### - [ ] Step 3: hooks.ts

`frontend/src/extensions/biz-pipeline/hooks.ts`:

```typescript
/**
 * biz-pipeline TanStack Query hooks。queryKey 统一 ["bpp", ...] 命名空间。
 * 罐装视图:resolve source/dataset id(缓存)→ queryDataset;
 * 明细/下钻:raw SQL → querySql(后端 assert_readonly_select 守卫)。
 *
 * 铁律:dataset label 必须与 seed_mock_pipeline.py 一字不差。
 */

import { useQuery } from "@tanstack/react-query";

import { queryDataset, querySql, resolveDatasetId, resolveSourceId } from "./api";
import type { BidRow, FunnelRow, MonthlyRow, QueryResult, ReconRow } from "./types";

export const KEYS = {
  funnel: ["bpp", "funnel"] as const,
  monthly: ["bpp", "monthly"] as const,
  recon: ["bpp", "recon"] as const,
  bidlist: ["bpp", "bidlist"] as const,
  drilldown: (sql: string) => ["bpp", "drilldown", sql] as const,
};

function useDatasetQuery<T>(key: readonly string[], label: string, enabled = true) {
  return useQuery({
    queryKey: key,
    enabled,
    queryFn: async (): Promise<T[]> => {
      const sid = await resolveSourceId();
      const did = await resolveDatasetId(sid, label);
      const res = await queryDataset(sid, did);
      return res.rows as T[];
    },
  });
}

export const usePipelineFunnel = () => useDatasetQuery<FunnelRow>(KEYS.funnel, "管线漏斗总览");
export const useMonthlyBids = () => useDatasetQuery<MonthlyRow>(KEYS.monthly, "月度投标节奏");
export const useContractRecon = () => useDatasetQuery<ReconRow>(KEYS.recon, "合同开票对账");

/** 明细:全量 mock_pipeline_bid,下钻来源。 */
export function useBidList(enabled = true) {
  return useQuery({
    queryKey: KEYS.bidlist,
    enabled,
    queryFn: async (): Promise<BidRow[]> => {
      const sid = await resolveSourceId();
      const res = await querySql(sid, "SELECT * FROM mock_pipeline_bid ORDER BY bid_date DESC");
      return res.rows as BidRow[];
    },
  });
}

/** 下钻:参数化只读 SQL(由查询页点击触发,sql=null 时不发)。 */
export function useDrillDown(sql: string | null) {
  return useQuery({
    queryKey: KEYS.drilldown(sql ?? ""),
    enabled: !!sql,
    queryFn: async (): Promise<QueryResult> => {
      const sid = await resolveSourceId();
      return querySql(sid, sql!); // enabled: !!sql 保证此处非空,lint 偏好 ! 非 as 断言
    },
  });
}
```

### - [ ] Step 4: ui/table.tsx(逐字克隆①,仅改注释模块名)

`frontend/src/extensions/biz-pipeline/components/ui/table.tsx`:

```tsx
/**
 * Lightweight table primitives(raw HTML)—— biz-pipeline 模块用。
 * 本项目无 shadcn Table,沿用 contract-price / bid-quote 同款 API。
 */

import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-left border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("[&_tr]:border-b", className)} {...props} />;
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/50 cursor-pointer",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-10 px-2 text-start align-middle text-xs font-medium uppercase tracking-wider text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("p-2 align-middle", className)} {...props} />;
}
```

### - [ ] Step 5: layout.tsx(镜像① layout,改 nav/page id + 标题)

`frontend/src/app/biz-pipeline/layout.tsx`:

```tsx
"use client";

import { LayoutDashboard, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤
const navItems = [
  { href: "/biz-pipeline", label: "管线仪表盘", icon: LayoutDashboard, exact: true, pageId: "bpp:page:dashboard" },
  { href: "/biz-pipeline/query", label: "数据查询", icon: Search, pageId: "bpp:page:query" },
];

function BizPipelineLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-16 shrink-0 items-center border-b border-border bg-background px-6">
        <span className="mr-8 text-lg font-bold tracking-tight text-foreground">管线查询</span>
        <nav className="flex h-full items-center gap-6 text-sm font-medium text-muted-foreground">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive ? "border-primary text-primary" : "border-transparent hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

export default function BizPipelineLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <BizPipelineLayoutContent>{children}</BizPipelineLayoutContent>
    </ShellLayout>
  );
}
```

### - [ ] Step 6: 占位 page / query/page

`frontend/src/app/biz-pipeline/page.tsx`:

```tsx
import { DashboardView } from "@/extensions/biz-pipeline/components/DashboardView";

export default function BizPipelineDashboardPage() {
  return <DashboardView />;
}
```

`frontend/src/app/biz-pipeline/query/page.tsx`:

```tsx
import { QueryView } from "@/extensions/biz-pipeline/components/QueryView";

export default function BizPipelineQueryPage() {
  return <QueryView />;
}
```

> DashboardView / QueryView 在 Task 5/6 创建。本步 typecheck 会报「模块未找到」—— 预期。

### - [ ] Step 7: typecheck(预期 DashboardView/QueryView 未定义报错,先确认骨架无 import 错)

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm typecheck' 2>&1 | grep -E "biz-pipeline|error" | head -30`
Expected: 仅 DashboardView/QueryView 未定义错误(Task 5/6 消除),无 api/hooks/types/table/layout 错误。

### - [ ] Step 8: Commit

```bash
git add frontend/src/extensions/biz-pipeline frontend/src/app/biz-pipeline
git commit -m "feat(biz-pipeline): 前端骨架(api/hooks/types + 路由 + table + layout)"
```

---

## Task 5: 仪表盘(StatCard/ChartCard/TechTooltip/DashboardView + 3 图表 cyber 增强)

**Files:**
- Create: `frontend/src/extensions/biz-pipeline/components/StatCard.tsx`(克隆①)
- Create: `frontend/src/extensions/biz-pipeline/components/ChartCard.tsx`(克隆①)
- Create: `frontend/src/extensions/biz-pipeline/components/TechTooltip.tsx`(克隆①)
- Create: `frontend/src/extensions/biz-pipeline/components/DashboardView.tsx`

### - [ ] Step 1: StatCard.tsx(逐字克隆① —— 字面 hex,无 hsl(var))

`frontend/src/extensions/biz-pipeline/components/StatCard.tsx`:

```tsx
"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StatColor = "primary" | "chart2" | "chart3" | "destructive" | "chart5";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  color?: StatColor;
}

// EAI-CUSTOM: 本项目 chart/success/destructive CSS 变量为完整颜色(oklch/hex),非 HSL 通道,
// 故用字面 hex + 8 位 alpha(末2位=透明度:14≈8%/33≈20%),与 bid-quote / spare-parts 同法。
const HEX: Record<StatColor, { bg: string; border: string; text: string }> = {
  primary: { bg: "#3b82f614", border: "#3b82f633", text: "#3b82f6" },
  chart2: { bg: "#8b5cf614", border: "#8b5cf633", text: "#8b5cf6" },
  chart3: { bg: "#f6bd1614", border: "#f6bd1633", text: "#f6bd16" },
  destructive: { bg: "#f43f5e14", border: "#f43f5e33", text: "#f43f5e" },
  chart5: { bg: "#10b98114", border: "#10b98133", text: "#10b981" },
};

export function StatCard({ label, value, icon: Icon, hint, color = "primary" }: StatCardProps) {
  const c = HEX[color];
  return (
    <div
      className={cn("relative overflow-hidden rounded-xl p-4 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] transition-all hover:scale-[1.015]")}
      style={{ background: c.bg, borderColor: c.border, borderWidth: 1 }}
    >
      <span className="absolute right-0 top-0 h-2 w-2 rounded-bl-md" style={{ background: c.text }} />
      <div className="flex items-center gap-2 text-muted-foreground/70">
        <Icon className="h-4 w-4" />
        <p className="text-xs uppercase tracking-wide">{label}</p>
      </div>
      <p className="mt-2 font-cyber text-3xl font-extrabold tracking-tight text-shadow-glow" style={{ color: c.text }}>
        {value}
      </p>
      {hint ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
```

### - [ ] Step 2: ChartCard.tsx(逐字克隆①)

`frontend/src/extensions/biz-pipeline/components/ChartCard.tsx`:

```tsx
"use client";

import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
}

// themed-card-sci:cyber 浅色科技感卡片面
export function ChartCard({ title, meta, children, className }: ChartCardProps) {
  return (
    <div
      className={
        "themed-card-sci rounded-xl border border-border/60 bg-card/80 p-5 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] backdrop-blur-sm " +
        (className ?? "")
      }
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-cyber text-sm font-semibold tracking-wide text-muted-foreground">{title}</h3>
        {meta ? (
          <span className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-0.5 text-[11px] font-bold text-primary">
            {meta}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}
```

### - [ ] Step 3: TechTooltip.tsx(逐字克隆①)

`frontend/src/extensions/biz-pipeline/components/TechTooltip.tsx`:

```tsx
"use client";

// recharts 3.x:TooltipProps 不再带 payload/label,用内联结构接口。
interface TechTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string; color?: string }>;
  label?: string | number;
}

// cyber 浅色玻璃面自定义 tooltip
export function TechTooltip({ active, payload, label }: TechTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-primary/30 bg-card/95 px-3 py-2 font-cyber text-xs text-card-foreground shadow-lg backdrop-blur">
      {label !== undefined ? <p className="mb-1 font-bold text-primary text-shadow-glow">{label}</p> : null}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-bold">{p.value}</span>
        </p>
      ))}
    </div>
  );
}
```

### - [ ] Step 4: DashboardView.tsx(5 KPI + 3 图表:金额漏斗/月度节奏/待开票对账)

`frontend/src/extensions/biz-pipeline/components/DashboardView.tsx`:

```tsx
"use client";

import { GitCommitHorizontal, RefreshCw, TrendingDown, Wallet } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { ChartCard } from "@/extensions/biz-pipeline/components/ChartCard";
import { StatCard } from "@/extensions/biz-pipeline/components/StatCard";
import { TechTooltip } from "@/extensions/biz-pipeline/components/TechTooltip";
import { clearBizPipelineCache } from "@/extensions/biz-pipeline/api";
import { useContractRecon, useMonthlyBids, usePipelineFunnel } from "@/extensions/biz-pipeline/hooks";

// EAI-CUSTOM: 项目 chart CSS 变量为完整颜色(非 HSL 通道),故图表用字面 hex
const GRID = "rgba(100,116,139,0.22)";
const AXIS_FILL = "#94a3b8";
const AXIS = { fontSize: 11, fill: AXIS_FILL };
const CURSOR = { fill: "rgba(148,163,184,0.15)" };
const BLUE = "#3b82f6";
const AMBER = "#f6bd16";
const RED = "#f43f5e";

// Decimal/numeric 列经 JSON 序为 string;recharts 需 number → 统一转。
const toNum = (v: string | null | undefined): number => (v === null || v === undefined ? 0 : Number(v));
function wan(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const refresh = () => {
    clearBizPipelineCache();
    setTick((t) => t + 1);
  };

  const funnelQ = usePipelineFunnel();
  const monthlyQ = useMonthlyBids();
  const reconQ = useContractRecon();

  const f = funnelQ.data?.[0];

  // 金额漏斗数据(投标总额→中标总额→合同总额→已开票总额,单位万)
  const funnelData = f
    ? [
        { stage: "投标总额", amount: toNum(f.bid_amount_total) / 10000 },
        { stage: "中标总额", amount: toNum(f.won_amount_total) / 10000 },
        { stage: "合同总额", amount: toNum(f.contract_total) / 10000 },
        { stage: "已开票", amount: toNum(f.invoiced_total) / 10000 },
      ]
    : [];
  const winRate = f && f.bid_count > 0 ? Math.round((100 * f.won_count) / f.bid_count / 0.1) / 10 : null;

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-sm border border-primary/30 bg-primary/10 p-1 text-primary">
            <GitCommitHorizontal className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold text-foreground text-shadow-glow">管线查询</h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={funnelQ.isFetching}>
          <RefreshCw className={funnelQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* KPI 行(5 卡) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="投标总数" value={f?.bid_count ?? "—"} icon={GitCommitHorizontal} color="primary" />
        <StatCard label="中标率" value={winRate !== null ? `${winRate}%` : "—"} icon={TrendingDown} color="chart2" />
        <StatCard label="合同总额" value={f ? wan(f.contract_total) : "—"} icon={Wallet} color="chart3" />
        <StatCard label="已开票总额" value={f ? wan(f.invoiced_total) : "—"} icon={Wallet} color="chart5" />
        <StatCard label="待开票总额" value={f ? wan(f.uninvoiced_total) : "—"} icon={TrendingDown} color="destructive" />
      </div>

      {/* 图表 3 张 */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* 图1:金额漏斗 投标→中标→合同→开票 */}
        <ChartCard title="金额漏斗 · 投标 → 中标 → 合同 → 开票(万)" meta="逐级沉淀">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={funnelData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="funnelGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BLUE} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={BLUE} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="stage" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Bar dataKey="amount" name="金额(万)" fill="url(#funnelGrad)" radius={[4, 4, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:月度投标节奏 投标 vs 中标 */}
        <ChartCard title="月度投标节奏 · 投标 vs 中标" meta="旺淡季">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(monthlyQ.data ?? []).map((r) => ({ ym: r.ym, bids: r.bids, won: r.won }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="ym" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={32} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="bids" name="投标" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
              <Bar dataKey="won" name="中标" fill={AMBER} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:待开票 TOP 合同(对账,红色渐变) */}
        <ChartCard title="待开票合同 · 合同额 vs 已开票(万)" meta="催开票预警" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={(reconQ.data ?? []).map((r) => ({
                contract_no: r.contract_no,
                合同额: toNum(r.amount) / 10000,
                已开票: toNum(r.invoiced) / 10000,
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="uninvGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={RED} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={RED} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="contract_no" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} angle={-12} textAnchor="end" height={50} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="合同额" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
              <Bar dataKey="已开票" fill="url(#uninvGrad)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
```

### - [ ] Step 5: typecheck + lint(单模块)

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && npx tsc --noEmit 2>&1 | grep biz-pipeline; npx eslint src/extensions/biz-pipeline src/app/biz-pipeline 2>&1 | tail -20'`
Expected: 无 biz-pipeline 错误(typecheck 可能仍有全仓既有 debt,只看 biz-pipeline 行)。修掉任何 unused import。

### - [ ] Step 6: 重启 frontend + 截图验证仪表盘

```bash
docker compose -p eai-docker restart frontend
```
浏览器登录(admin@eai-flow.com / Admin@2026)→ 应用中心 → 市场营销 → 管线查询 → 仪表盘应显 5 KPI(投标总数 8 / 中标率 50% / 合同总额 7332万 / 已开票 5182万 / 待开票 2150万)+ 3 图表。若 HMR 未生效,restart frontend。

### - [ ] Step 7: Commit

```bash
git add frontend/src/extensions/biz-pipeline/components/StatCard.tsx frontend/src/extensions/biz-pipeline/components/ChartCard.tsx frontend/src/extensions/biz-pipeline/components/TechTooltip.tsx frontend/src/extensions/biz-pipeline/components/DashboardView.tsx
git commit -m "feat(biz-pipeline): 仪表盘(5 KPI + 3 图表:金额漏斗/月度节奏/待开票对账,cyber 增强)"
```

---

## Task 6: 查询页(QueryView 3 视图 + DrillDownModal)

**Files:**
- Create: `frontend/src/extensions/biz-pipeline/components/DrillDownModal.tsx`(克隆①)
- Create: `frontend/src/extensions/biz-pipeline/components/QueryView.tsx`

### - [ ] Step 1: DrillDownModal.tsx(克隆① —— 含 cellText + `rows[0] ?? {}` lint 规避)

`frontend/src/extensions/biz-pipeline/components/DrillDownModal.tsx`:

```tsx
"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

import { useDrillDown } from "@/extensions/biz-pipeline/hooks";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/biz-pipeline/components/ui/table";

interface DrillDownModalProps {
  title: string;
  /** 已拼好的参数化只读 SQL(白名单维度,值来自行数据)。null 时关闭。 */
  sql: string | null;
  onClose: () => void;
}

// 通用下钻 modal:标题 + sql → 明细 table。下钻 SQL 走后端 assert_readonly_select 守卫。
// no-base-to-string: 行单元格为 unknown(SQL JSON),收窄后再 String()。
const cellText = (v: unknown) =>
  v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v as string | number | boolean);

export function DrillDownModal({ title, sql, onClose }: DrillDownModalProps) {
  const { data, isLoading, error } = useDrillDown(sql);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (sql) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sql, onClose]);

  if (!sql) return null;
  const rows = data?.rows ?? [];
  // noUncheckedIndexedAccess: rows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const cols = rows.length ? Object.keys(rows[0] ?? {}) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-cyber text-sm font-bold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
          ) : error ? (
            <p className="py-8 text-center text-sm text-destructive">加载失败:{String(error)}</p>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">无明细数据</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {cols.map((c) => (
                    <TableHead key={c}>{c}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i} className="cursor-default">
                    {cols.map((c) => (
                      <TableCell key={c}>{cellText(r[c])}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <div className="border-t border-border px-5 py-2 text-[11px] text-muted-foreground/70">
          共 {data?.row_count ?? 0} 条 · {sql}
        </div>
      </div>
    </div>
  );
}
```

### - [ ] Step 2: QueryView.tsx(3 视图 + 行下钻,白名单维度 contract_no/ym)

`frontend/src/extensions/biz-pipeline/components/QueryView.tsx`:

```tsx
"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { DrillDownModal } from "@/extensions/biz-pipeline/components/DrillDownModal";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/biz-pipeline/components/ui/table";
import { useBidList, useContractRecon, useMonthlyBids } from "@/extensions/biz-pipeline/hooks";
import type { BidRow, MonthlyRow, ReconRow } from "@/extensions/biz-pipeline/types";

type TabKey = "bidlist" | "recon" | "monthly";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bidlist", label: "投标明细" },
  { key: "recon", label: "合同开票对账" },
  { key: "monthly", label: "月度投标节奏" },
];

// 清洗:单引号转义防 SQL 注入(值来自 DB 行数据,非用户自由输入)。
// no-base-to-string: v 为 unknown,需显式收窄后再 String()(对象走 JSON)。
const esc = (v: unknown) => {
  const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v as string | number | boolean);
  return s.replace(/'/g, "''");
};

export function QueryView() {
  const [tab, setTab] = useState<TabKey>("bidlist");
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(null);

  const bidQ = useBidList();
  const reconQ = useContractRecon();
  const monthlyQ = useMonthlyBids();

  const bidRows = bidQ.data ?? [];
  const reconRows = reconQ.data ?? [];
  const monthlyRows = monthlyQ.data ?? [];
  // 明细列动态(取首行列名);罐装视图列固定。
  // noUncheckedIndexedAccess: bidRows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const bidCols = bidRows.length ? Object.keys(bidRows[0] ?? {}) : [];

  const onRowDrill = (key: TabKey, row: BidRow | ReconRow | MonthlyRow) => {
    // 白名单维度:仅 contract_no / ym;值经 esc 转义后拼入只读 SELECT。
    if (key === "bidlist") {
      // 投标明细:仅中标行(contract_no 非空)可下钻到该合同开票明细;落标行禁用。
      const cn = (row as BidRow).contract_no;
      if (!cn) return;
      const v = esc(cn);
      setDrill({
        title: `合同开票明细 · ${v}`,
        sql: `SELECT invoice_id, invoice_date, amount, tax_amount, total_amount, status FROM mock_invoice WHERE contract_no='${v}' ORDER BY invoice_date`,
      });
    } else if (key === "recon") {
      const v = esc((row as ReconRow).contract_no);
      setDrill({
        title: `合同开票明细 · ${v}`,
        sql: `SELECT invoice_id, invoice_date, amount, tax_amount, total_amount, status FROM mock_invoice WHERE contract_no='${v}' ORDER BY invoice_date`,
      });
    } else {
      const v = esc((row as MonthlyRow).ym);
      setDrill({
        title: `月份投标明细 · ${v}`,
        sql: `SELECT bid_id, project_name, customer, bid_date, our_bid_amount, status, competitor_name FROM mock_pipeline_bid WHERE to_char(bid_date,'YYYY-MM')='${v}' ORDER BY bid_date`,
      });
    }
  };

  const loading = useMemo(
    () => (tab === "bidlist" ? bidQ.isLoading : tab === "recon" ? reconQ.isLoading : monthlyQ.isLoading),
    [tab, bidQ.isLoading, reconQ.isLoading, monthlyQ.isLoading],
  );

  const toWan = (v: unknown) => {
    const n = v === null || v === undefined ? null : Number(v);
    return n === null || Number.isNaN(n) ? "—" : `${(n / 10000).toFixed(1)}万`;
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">数据查询</h1>
      </div>

      {/* 视图 tab(pill) */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors " +
              (tab === t.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 当前视图表(点行下钻) */}
      <div className="rounded-xl border border-border bg-card p-4">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
        ) : tab === "bidlist" ? (
          <Table>
            <TableHeader>
              <TableRow>
                {bidCols.map((c) => (
                  <TableHead key={c}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {bidRows.map((r, i) => {
                const cn = r.contract_no;
                return (
                  <TableRow
                    key={i}
                    onClick={() => onRowDrill("bidlist", r)}
                    className={cn ? "cursor-pointer" : "cursor-default opacity-70"}
                  >
                    {bidCols.map((c) => (
                      <TableCell key={c}>{esc(r[c])}</TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : tab === "recon" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>合同号</TableHead>
                <TableHead>合同名称</TableHead>
                <TableHead>客户</TableHead>
                <TableHead>合同额</TableHead>
                <TableHead>已开票</TableHead>
                <TableHead>待开票</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reconRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("recon", r)}>
                  <TableCell>{r.contract_no}</TableCell>
                  <TableCell>{r.contract_name}</TableCell>
                  <TableCell>{r.customer}</TableCell>
                  <TableCell>{toWan(r.amount)}</TableCell>
                  <TableCell>{toWan(r.invoiced)}</TableCell>
                  <TableCell className={Number(r.uninvoiced) > 0 ? "font-bold text-destructive" : ""}>{toWan(r.uninvoiced)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>月份</TableHead>
                <TableHead>投标数</TableHead>
                <TableHead>中标数</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {monthlyRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("monthly", r)}>
                  <TableCell>{r.ym}</TableCell>
                  <TableCell>{r.bids}</TableCell>
                  <TableCell>{r.won}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DrillDownModal title={drill?.title ?? ""} sql={drill?.sql ?? null} onClose={() => setDrill(null)} />
    </div>
  );
}
```

### - [ ] Step 3: typecheck + lint(单模块)

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && npx tsc --noEmit 2>&1 | grep biz-pipeline; npx eslint src/extensions/biz-pipeline src/app/biz-pipeline 2>&1 | tail -20'`
Expected: 无 biz-pipeline 错误。

### - [ ] Step 4: 命名空间自查

Run: `grep -rnE "bqa:|csp:|cpa:|\"bqa\"|\"cpa\"" frontend/src/extensions/biz-pipeline frontend/src/app/biz-pipeline`
Expected: 无输出(纯 `bpp`,无①/④ 命名空间残留)。

### - [ ] Step 5: 重启 frontend + 验证查询页

```bash
docker compose -p eai-docker restart frontend
```
浏览器 → 管线查询 → 数据查询 → 3 tab(投标明细/合同开票对账/月度投标节奏)→ 投标明细点中标行出开票 modal;落标行(contract_no 空)不可点(opacity-70);对账行点出开票 modal;月度行点出该月投标明细 modal。

### - [ ] Step 6: Commit

```bash
git add frontend/src/extensions/biz-pipeline/components/DrillDownModal.tsx frontend/src/extensions/biz-pipeline/components/QueryView.tsx
git commit -m "feat(biz-pipeline): 查询页(3 固定视图 + 行下钻 modal,落标行禁用下钻)"
```

---

## Task 7: 联调 + 全量验证

### - [ ] Step 1: 后端 license 同步测试

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_license_modules_sync.py tests/test_data_source_routers.py -v'`
Expected: 全 PASS(license 含 biz_pipeline;data_source 端点①已落地)。

### - [ ] Step 2: 前端 typecheck(全量,看 biz-pipeline 干净)

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm typecheck 2>&1 | grep -c "biz-pipeline"'`
Expected: `0`(biz-pipeline 无类型错误;全仓既有 debt 不计)。

### - [ ] Step 3: 端到端手动验证(E2E)

用 `admin@eai-flow.com / Admin@2026` 登录 `localhost:2026`:
1. 应用中心 → 「市场营销」域 → 见「管线查询」磁贴(superadmin `nav:["*"]` 自动有)。
2. 点磁贴 → 仪表盘显:投标总数 8 / 中标率 50% / 合同总额 7332 万 / 已开票 5182 万 / 待开票 2150 万 + 3 图表(金额漏斗 16882→7635→7332→5182 / 月度节奏 / 待开票对账)。
3. 「数据查询」tab → 3 视图切换 → 投标明细点中标行(TB-001 等)→ modal 弹出该合同开票明细;落标行(TB-002 等)不可点。
4. 对账视图 → 点 HT-003(待开 1500 万)→ modal 显 2500 万开票;月度视图 → 点 2025-03 → modal 显该月投标明细。
5. 下钻 modal 底部 SQL 确认均为只读 SELECT。

### - [ ] Step 4: designqc 截图(可选,留档)

```bash
openwolf designqc --routes /biz-pipeline /biz-pipeline/query
```
读 `.wolf/designqc-captures/` 截图核对科技感与浅色风格,与① bid-quote 视觉一致。

### - [ ] Step 5: OpenWolf 收尾(anatomy/memory/cerebrum/buglog + commit)

按 OpenWolf 协议:
- `.wolf/anatomy.md` 加 biz-pipeline 各文件条目(若 auto-hook 未自动加)。
- `.wolf/memory.md` 追加任务行。
- 若有踩坑 → `.wolf/buglog.json` + `.wolf/cerebrum.md`。
- 若计划/seed 有别于 spec 的修正(如 mock 上浮系数),回写 spec。

```bash
git add .wolf/
git commit -m "chore(openwolf): biz-pipeline T1-T7 bookkeeping"
```

---

## Self-Review(写完后自查)

**1. Spec 覆盖:**
- spec §2 零后端增量 → 本计划无后端端点任务 ✓(复用①)
- spec §4 数据层(3 表 + 连接 + 3 dataset)→ Task 1 ✓
- spec §5 前端模块结构(api/hooks/types/components/路由)→ Task 4/5/6 ✓(命名空间 `bpp` 全程一致)
- spec §6 仪表盘(页头 + 5 KPI + 3 图表)→ Task 5 ✓(金额漏斗/月度/对账)
- spec §7 查询页(3 视图 + modal 下钻,白名单 contract_no/ym)→ Task 6 ✓(落标行禁用下钻)
- spec §8 应用中心入口 + License 4 点 + permissions/roles_custom → Task 2/3 ✓

**2. 占位符扫描:** 无 TBD/TODO;dataset label 在 seed/hooks 两处逐字一致(`管线漏斗总览`/`月度投标节奏`/`合同开票对账`);mock 数据 8/4/7332w/5182w/2150w 自洽。

**3. 类型一致性:** `QueryResult`(后端 schemas① 已有 ↔ 前端 types)字段一致;page id `bpp:page:dashboard|query` 在 permissions/roles_custom/layout/useApps 一致;nav id `nav:biz-pipeline` 在 permissions/roles_custom/deriveNavId 一致;license key `biz_pipeline` 4 点一致。

**4. Cerebrum 烘焙核验:**
- 颜色全字面 hex(StatCard `style` + 图表 hex 常量),无 `hsl(var(--chart-*))` ✓
- `rows[0] ?? {}` / `bidRows[0] ?? {}` 兜底 noUncheckedIndexedAccess ✓
- `cellText` / `esc` helper 收窄 no-base-to-string ✓
- `useDrillDown` 用 `sql!` 非 `as string` ✓

**5. 风险点(执行时留意):**
- `marketing` 域①已建,③ 仅加磁贴(Task 3 Step 4/6),不再加 domain。
- seed 日志计数从 `12 apps` → `13 apps`(Task 3 Step 4)。
- 端到端需 admin 已授权 `nav:biz-pipeline`(superadmin `["*"]` 自动有)。
- mock_invoice 税额用 `/1.13` 反算(mock,非真实税率;真库接入时由财务系统提供)。
