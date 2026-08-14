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

# ── 8 个投标项目
# (bid_id, 项目, 客户, 日期, 是否中标, 我方报价万元, 合同号, 合同名, 合同额万, 已开票万列表)
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
    # FK:mock_invoice → mock_contract,必须同语句 CASCADE 截断(分语句会被 FK 阻止)
    await mock.execute(
        "TRUNCATE mock_invoice, mock_contract, mock_pipeline_bid RESTART IDENTITY CASCADE;"
    )

    bid_rows, contract_rows, invoice_rows = [], [], []
    inv_seq = 0
    for bid_id, proj, cust, bdate, won, bid_amt_w, cno, cname, camt_w, invoices_w in PROJECTS:
        status = "won" if won else "lost"
        bid_rows.append(
            (bid_id, proj, cno, cust, date.fromisoformat(bdate), round(bid_amt_w * 10000, 2), status, "东方宏业")
        )
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
    print(
        f"bid={n_bid} won={n_won} 合同总额={c_total/10000:.0f}万 已开票={i_total/10000:.0f}万 "
        f"待开票={(c_total-i_total)/10000:.0f}万"
    )
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
