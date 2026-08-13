#!/usr/bin/env python3
"""模块① 投标报价分析 — mock 数据 + data_source 元数据 seed(幂等)。

EAI-CUSTOM: 市场部门模块①。真实投标库接入前的链路演示 mock(我编贴近真实样例)。
形态 = 路线 B(data_source 复用),零自建扩展代码。

在 gateway 容器内运行:
    docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_market.py

幂等:重复运行只重灌样例 + upsert 元数据,不产生重复行。

数据故事(供技能推理,非真实业绩):
- 我方(东智装备制造)在循环水泵/超滤装置等核心设备可自产 → 中小项目中标;
- 变换炉/压缩机/脱硫塔/丙烯塔等大型核心设备我方仅能外购 → 大项目成本高、落标;
- 友商(东方宏业)大型塔器/压缩机可自产 → 大项目低价中标。
结论预期:技能建议我方提升大型核心设备自产率以改善大项目中标率。
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
MOCK_DB = "mock_market"  # 独立 mock 库,隔离干净
SOURCE_NAME = "bid-quote"

# data_source 连接配置(运行时 gateway 经 SQLAlchemy async engine 连 mock_market)
# ponytail: _build_db_url 期望键 {driver,host,port,database,username,password};driver 走 asyncpg
SOURCE_CONNECTION_CONFIG = {
    "driver": "postgresql+asyncpg",
    "host": PG_HOST,
    "port": PG_PORT,
    "database": MOCK_DB,
    "username": PG_USER,
    "password": PG_PASS,
}

OURS = "东智装备制造"
COMP = "东方宏业"

# ── 6 个投标项目(每项目我方+友商各 1 条 bid)──
# item: (货物名, 规格型号, 数量, 单位, 自产金额万, 外购金额万)
#   脚本自动算 total = self+outsourced, unit_price = total/qty
PROJECTS = [
    {
        "name": "华能铜川电厂二期循环水系统", "loc": "陕西铜川", "date": "2025-03-15",
        "winner": "ours", "price": 18500000,  # 500-2000w 段
        "ours": [
            ("循环水泵", "300QH-600", 4, "台", 280, 20),
            ("冷却塔填料", "PVC复合", 1200, "m³", 0, 150),
            ("电动蝶阀", "DN800", 12, "台", 180, 0),
            ("管道及支架", "DN600", 850, "t", 350, 120),
            ("电气控制柜", "MNS型", 6, "面", 0, 250),
            ("安装调试", "—", 1, "项", 200, 0),
        ],
        "comp": [
            ("循环水泵", "300QH-600", 4, "台", 160, 120),
            ("冷却塔填料", "PVC复合", 1200, "m³", 0, 140),
            ("电动蝶阀", "DN800", 12, "台", 160, 20),
            ("管道及支架", "DN600", 850, "t", 300, 150),
            ("电气控制柜", "MNS型", 6, "面", 0, 230),
            ("安装调试", "—", 1, "项", 180, 0),
        ],
    },
    {
        "name": "宁夏宝丰甲醇项目净化装置", "loc": "宁夏宁东", "date": "2025-04-22",
        "winner": "competitor", "price": 26500000,  # ≥2000w 段
        "ours": [  # 我方核心设备全外购 → 高成本落标
            ("变换炉", "φ3200", 2, "台", 0, 650),
            ("吸收塔", "φ2800", 1, "台", 0, 520),
            ("换热器", "BIU1200", 8, "台", 180, 120),
            ("压缩机", "离心式", 1, "台", 0, 450),
            ("管道及支架", "各类", 1200, "t", 300, 100),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "comp": [  # 友商塔器/压缩机可自产 → 低价中标
            ("变换炉", "φ3200", 2, "台", 600, 50),
            ("吸收塔", "φ2800", 1, "台", 480, 40),
            ("换热器", "BIU1200", 8, "台", 200, 80),
            ("压缩机", "离心式", 1, "台", 420, 30),
            ("管道及支架", "各类", 1200, "t", 280, 90),
            ("安装调试", "—", 1, "项", 240, 0),
        ],
    },
    {
        "name": "内蒙古久泰乙二醇装置", "loc": "内蒙古鄂尔多斯", "date": "2025-06-10",
        "winner": "competitor", "price": 4800000,  # 100-500w 段
        "ours": [
            ("反应器", "φ2400", 1, "台", 0, 180),
            ("换热器", "BIU800", 4, "台", 120, 40),
            ("塔器", "φ1600", 2, "台", 80, 60),
            ("管道及支架", "各类", 320, "t", 40, 30),
            ("安装调试", "—", 1, "项", 20, 0),
        ],
        "comp": [
            ("反应器", "φ2400", 1, "台", 160, 20),
            ("换热器", "BIU800", 4, "台", 110, 30),
            ("塔器", "φ1600", 2, "台", 70, 40),
            ("管道及支架", "各类", 320, "t", 35, 25),
            ("安装调试", "—", 1, "项", 18, 0),
        ],
    },
    {
        "name": "大唐国际雷州电厂烟气脱硫", "loc": "广东雷州", "date": "2025-07-18",
        "winner": "competitor", "price": 32000000,  # ≥2000w 段(超大)
        "ours": [  # 脱硫塔/氧化风机我方外购 → 高成本落标
            ("脱硫塔", "φ18000", 1, "台", 0, 950),
            ("浆液循环泵", "TL800", 6, "台", 280, 120),
            ("氧化风机", "罗茨式", 4, "台", 0, 680),
            ("管道及支架", "各类", 1500, "t", 400, 150),
            ("电气系统", "—", 1, "套", 0, 350),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "comp": [  # 友商自产 → 低价中标
            ("脱硫塔", "φ18000", 1, "台", 880, 70),
            ("浆液循环泵", "TL800", 6, "台", 260, 100),
            ("氧化风机", "罗茨式", 4, "台", 630, 50),
            ("管道及支架", "各类", 1500, "t", 370, 130),
            ("电气系统", "—", 1, "套", 0, 320),
            ("安装调试", "—", 1, "项", 240, 0),
        ],
    },
    {
        "name": "中天合创煤化工水处理", "loc": "内蒙古鄂尔多斯", "date": "2025-09-05",
        "winner": "ours", "price": 850000,  # <100w 段(小项目,我方超滤自产)
        "ours": [
            ("超滤装置", "UF-160", 2, "套", 60, 5),
            ("反渗透膜", "BW-440", 30, "支", 0, 15),
            ("加药装置", "成套", 3, "套", 8, 2),
            ("管道及支架", "各类", 45, "t", 3, 2),
            ("安装调试", "—", 1, "项", 5, 0),
        ],
        "comp": [
            ("超滤装置", "UF-160", 2, "套", 55, 8),
            ("反渗透膜", "BW-440", 30, "支", 0, 14),
            ("加药装置", "成套", 3, "套", 7, 3),
            ("管道及支架", "各类", 45, "t", 2, 3),
            ("安装调试", "—", 1, "项", 4, 0),
        ],
    },
    {
        "name": "万华化学烟台PDH装置", "loc": "山东烟台", "date": "2025-11-12",
        "winner": "competitor", "price": 21000000,  # ≥2000w 段
        "ours": [  # 丙烯塔/压缩机我方外购 → 高成本落标
            ("丙烯塔", "φ4200", 1, "台", 0, 580),
            ("压缩机", "丙烷离心", 1, "台", 0, 620),
            ("反应器", "φ3000", 1, "台", 0, 450),
            ("换热器", "BIU1400", 6, "台", 200, 100),
            ("管道及支架", "各类", 980, "t", 150, 80),
            ("安装调试", "—", 1, "项", 100, 0),
        ],
        "comp": [  # 友商自产 → 低价中标
            ("丙烯塔", "φ4200", 1, "台", 540, 40),
            ("压缩机", "丙烷离心", 1, "台", 580, 50),
            ("反应器", "φ3000", 1, "台", 420, 30),
            ("换热器", "BIU1400", 6, "台", 180, 90),
            ("管道及支架", "各类", 980, "t", 140, 70),
            ("安装调试", "—", 1, "项", 95, 0),
        ],
    },
]

# ── 3 个罐装 dataset 的 default_query SQL(只读 SELECT,过 assert_readonly_select 守卫)──
DATASETS = [
    {
        "table_name": "bid_summary",
        "label": "投标总览",
        "description": "投标项目数、我方/友商中标数与中标率、中标均价、时间范围。",
        "default_query": """
            SELECT
              COUNT(DISTINCT project_name) AS project_count,
              COUNT(*) AS bid_count,
              COUNT(*) FILTER (WHERE bidder_role='ours') AS ours_bid,
              COUNT(*) FILTER (WHERE bidder_role='ours' AND won) AS ours_won,
              ROUND(100.0 * COUNT(*) FILTER (WHERE bidder_role='ours' AND won)
                    / NULLIF(COUNT(*) FILTER (WHERE bidder_role='ours'),0), 1) AS ours_win_rate_pct,
              COUNT(*) FILTER (WHERE bidder_role='competitor') AS competitor_bid,
              COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_won,
              ROUND(AVG(winning_price), 2) AS avg_winning_price,
              MIN(bid_date) AS earliest_bid,
              MAX(bid_date) AS latest_bid
            FROM mock_bid
        """.strip(),
    },
    {
        "table_name": "composition_compare_by_goods",
        "label": "货物构成对比(我方vs友商)",
        "description": "各货物我方自产%/外购% 对比 友商自产%/外购%,以及双方均价。①核心价值:看出哪些货物我方只能外购、友商可自产。",
        "default_query": """
            SELECT
              i.goods_name,
              ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='ours')
                    / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'),0), 1) AS ours_self_pct,
              ROUND(100.0 * SUM(i.outsourced_amount) FILTER (WHERE b.bidder_role='ours')
                    / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'),0), 1) AS ours_outsourced_pct,
              ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='ours'), 2) AS ours_avg_unit_price,
              ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='competitor')
                    / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor'),0), 1) AS competitor_self_pct,
              ROUND(100.0 * SUM(i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor')
                    / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor'),0), 1) AS competitor_outsourced_pct,
              ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='competitor'), 2) AS competitor_avg_unit_price
            FROM mock_bid_item i
            JOIN mock_bid b ON b.bid_id = i.bid_id
            GROUP BY i.goods_name
            ORDER BY i.goods_name
        """.strip(),
    },
    {
        "table_name": "win_rate_by_segment",
        "label": "按金额段我方中标率",
        "description": "按中标价金额段(<100万/100-500万/500-2000万/≥2000万)统计我方投标数、中标数、中标率。揭示大项目中标率短板。",
        "default_query": """
            SELECT
              CASE WHEN winning_price < 1000000 THEN '1_<100万'
                   WHEN winning_price < 5000000 THEN '2_100-500万'
                   WHEN winning_price < 20000000 THEN '3_500-2000万'
                   ELSE '4_≥2000万' END AS amount_segment,
              COUNT(*) AS ours_bid,
              COUNT(*) FILTER (WHERE won) AS ours_won,
              ROUND(100.0 * COUNT(*) FILTER (WHERE won) / COUNT(*), 1) AS ours_win_rate_pct
            FROM mock_bid
            WHERE bidder_role='ours'
            GROUP BY 1
            ORDER BY 1
        """.strip(),
    },
    {
        # EAI-CUSTOM: 仪表盘第3图「项目报价对比」专用 dataset(模块① 投标报价分析)
        # 注意:spec §4.2 草拟 SQL 用了 wid/customer 列,但 mock_bid 实际无这两列
        # (PK 是 bid_id,无 customer),此处按真实 schema 适配:bid_id 排序、project_location 取上下文。
        "table_name": "bqa_project_showdown",
        "label": "项目报价对比(我方vs友商)",
        "description": "每个项目我方报价 vs 友商(中标方)报价对比 + 我方是否中标。直接支撑报价区间建议。",
        "default_query": """
            SELECT project_name,
              MAX(winning_price) FILTER (WHERE bidder_role='ours') AS our_price,
              MAX(winning_price) FILTER (WHERE bidder_role='competitor') AS competitor_price,
              BOOL_OR(bidder_role='ours' AND won) AS we_won,
              MAX(project_location) AS project_location
            FROM mock_bid
            GROUP BY project_name
            ORDER BY MIN(bid_id)
        """.strip(),
    },
]


async def main() -> None:
    common = dict(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS)

    # 1. 建 mock_market 库(幂等)
    sys_conn = await asyncpg.connect(**common, database=EXT_DB)
    try:
        await sys_conn.execute(f'CREATE DATABASE "{MOCK_DB}"')
        print(f"[ok] 已建库 {MOCK_DB}")
    except asyncpg.DuplicateDatabaseError:
        print(f"[skip] 库 {MOCK_DB} 已存在")
    finally:
        await sys_conn.close()

    # 2. 建表 + 重灌样例(幂等)
    mock = await asyncpg.connect(**common, database=MOCK_DB)
    await mock.execute(
        """
        CREATE TABLE IF NOT EXISTS mock_bid (
          bid_id           TEXT PRIMARY KEY,
          project_name     TEXT NOT NULL,
          project_location TEXT,
          bid_date         DATE,
          bidder_role      TEXT NOT NULL,
          bidder_name      TEXT,
          won              BOOLEAN NOT NULL DEFAULT FALSE,
          winning_price    NUMERIC(14,2)
        );
        CREATE TABLE IF NOT EXISTS mock_bid_item (
          id                SERIAL PRIMARY KEY,
          bid_id            TEXT NOT NULL REFERENCES mock_bid(bid_id) ON DELETE CASCADE,
          goods_name        TEXT NOT NULL,
          spec              TEXT,
          quantity          NUMERIC(12,2),
          unit              TEXT,
          unit_price        NUMERIC(14,2),
          self_amount       NUMERIC(14,2) DEFAULT 0,
          outsourced_amount NUMERIC(14,2) DEFAULT 0,
          total_amount      NUMERIC(14,2)
        );
        """
    )
    await mock.execute("TRUNCATE mock_bid_item; TRUNCATE mock_bid RESTART IDENTITY CASCADE;")

    bid_rows, item_rows = [], []
    seq = 0
    for p in PROJECTS:
        for role, bidder, items in (("ours", OURS, p["ours"]), ("competitor", COMP, p["comp"])):
            seq += 1
            bid_id = f"BD-2025-{seq:03d}"
            won = role == p["winner"]
            bid_rows.append(
                (bid_id, p["name"], p["loc"], date.fromisoformat(p["date"]), role, bidder, won, p["price"])
            )
            for goods, spec, qty, unit, self_amt, out_amt in items:
                total = self_amt + out_amt  # 单位:万元
                # mock 表金额按元存(spec 标价以元为单位),万元 × 10000
                item_rows.append(
                    (
                        bid_id, goods, spec, qty, unit,
                        round(total * 10000 / qty, 2),       # unit_price(元)
                        round(self_amt * 10000, 2),          # self_amount(元)
                        round(out_amt * 10000, 2),           # outsourced_amount(元)
                        round(total * 10000, 2),             # total_amount(元)
                    )
                )

    await mock.executemany(
        "INSERT INTO mock_bid (bid_id,project_name,project_location,bid_date,bidder_role,bidder_name,won,winning_price) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        bid_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_bid_item (bid_id,goods_name,spec,quantity,unit,unit_price,self_amount,outsourced_amount,total_amount) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        item_rows,
    )
    print(f"[ok] 已灌 {len(bid_rows)} 条 bid / {len(item_rows)} 条 item")
    await mock.close()

    # 3. extensions 库 upsert data_source 连接 + 4 个 dataset(幂等)
    ext = await asyncpg.connect(**common, database=EXT_DB)
    cfg_json = json.dumps(SOURCE_CONNECTION_CONFIG)
    src_id = await ext.fetchval("SELECT id FROM data_sources WHERE name=$1", SOURCE_NAME)
    if src_id is None:
        src_id = await ext.fetchval(
            "INSERT INTO data_sources (id,name,description,type,connection_config,auth_type,sync_mode,status,created_at,updated_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4::jsonb,$5,$6,$7,now(),now()) RETURNING id",
            SOURCE_NAME,
            "模块① 投标报价分析 mock 数据源(结构化投标库,含我方/友商自产外购构成)。",
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
            "模块① 投标报价分析 mock 数据源(结构化投标库,含我方/友商自产外购构成)。",
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

    # 自检:汇总(肉眼校验数据故事)
    chk = await asyncpg.connect(**common, database=MOCK_DB)
    n_bid = await chk.fetchval("SELECT count(*) FROM mock_bid")
    n_item = await chk.fetchval("SELECT count(*) FROM mock_bid_item")
    ours_rate = await chk.fetchval(
        "SELECT round(100.0*count(*) filter(where bidder_role='ours' and won)/count(*) filter(where bidder_role='ours'),1) FROM mock_bid"
    )
    seg = await chk.fetch(
        "SELECT CASE WHEN winning_price<1000000 THEN '<100w' WHEN winning_price<5000000 THEN '100-500w' "
        "WHEN winning_price<20000000 THEN '500-2000w' ELSE '>=2000w' END seg, "
        "count(*) filter(where bidder_role='ours') bid, count(*) filter(where bidder_role='ours' and won) won "
        "FROM mock_bid GROUP BY 1 ORDER BY 1"
    )
    print("\n===== 自检 =====")
    print(f"bid={n_bid} item={n_item} 我方中标率={ours_rate}%")
    for r in seg:
        print(f"  金额段 {r['seg']}: 我方投 {r['bid']} 中 {r['won']}")
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
