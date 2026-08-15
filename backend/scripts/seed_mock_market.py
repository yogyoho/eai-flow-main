#!/usr/bin/env python3
"""模块① 投标报价分析 — mock 数据 + data_source 元数据 seed(幂等)。

EAI-CUSTOM: 市场部门模块①。真实投标库接入前的链路演示 mock(我编贴近真实样例)。
形态 = 路线 B(data_source 复用),零自建扩展代码。

在 gateway 容器内运行:
    docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_market.py

幂等:重复运行只重灌样例 + upsert 元数据,不产生重复行。

数据故事(供技能推理,非真实业绩):
- 数据规模: 6 个手写 2025 样例 + 34 个确定性生成的 2023-2025 项目(共 40),三年趋势可读;
- 报价溢价规律: 我方报价相对该项目友商最低价 cmin 的溢价越低胜率越高,
  拐点在 +3% 附近(±3% 内五五开,越过 +4.5% 胜率骤降);
- 大项目短板: ≥2000万 段我方全败(大型核心设备外购 → 成本劣势);
- 三年趋势: 年度配额 2023(2胜9负)→2024(5胜7负)→2025(8胜3负),我方中标金额份额逐年抬升;
- 东方宏业画像: 参与即报 0.955×基准价 → 平均溢价为负(低价抢标型友商);
- 我方(东智装备制造)在循环水泵/超滤装置等核心设备可自产 → 中小项目中标;
- 变换炉/压缩机/脱硫塔/丙烯塔等大型核心设备我方仅能外购 → 大项目成本高、落标;
- 友商(东方宏业/华能重工/江南重工/航天晨光等,每项目 2-3 家)大型塔器/压缩机可自产 → 大项目低价中标。
结论预期:技能建议我方提升大型核心设备自产率以改善大项目中标率。

生成逻辑全部为确定性字面量表驱动(零随机),便于 pytest 直接 import 校验规律:
- gen_bid_plan(): 34 条 {year, seg, our_won, prem, comp_idx} 计划;
- gen_projects(): 把计划展开成完整项目行(我方 + 2-3 家友商,每行 3 条 items)。
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
# EAI-CUSTOM: 多家友商(原单常量 COMP)。手写项目每项目 1-3 家友商竞争,1 家中标(项目5仅1家);
# 生成项目每项目 2-3 家友商(确定性索引从池里取)。
COMPETITORS_POOL = ["东方宏业", "华能重工", "中机国能", "江南重工", "海纳智造", "航天晨光"]
LOW_BALLER = "东方宏业"  # 低价抢标型友商: 参与即报 0.955×基准价 → 平均溢价为负


def _variant(base, k):
    """友商货物清单变体:模拟不同友商的自产能力。
    k=1.0 基准;k<1 自产弱(自产×k,外购补足);k>1 自产强。
    base = [(货物,规格,数量,单位,自产万,外购万), ...]
    """
    return [(g, s, q, u, round(sm * k), round(om * (2 - k))) for g, s, q, u, sm, om in base]


# ── 6 个手写投标项目(每项目我方 + 1-3 家友商竞标,恰 1 家中标)──
# item: (货物名, 规格型号, 数量, 单位, 自产金额万, 外购金额万)
#   脚本自动算 total = self+outsourced, unit_price = total/qty
PROJECTS = [
    {
        "name": "华能铜川电厂二期循环水系统",
        "loc": "陕西铜川",
        "date": "2025-03-15",
        "price": 18500000,
        "winner": "ours",  # 500-2000w 段
        "ours": [
            ("循环水泵", "300QH-600", 4, "台", 280, 20),
            ("冷却塔填料", "PVC复合", 1200, "m³", 0, 150),
            ("电动蝶阀", "DN800", 12, "台", 180, 0),
            ("管道及支架", "DN600", 850, "t", 350, 120),
            ("电气控制柜", "MNS型", 6, "面", 0, 250),
            ("安装调试", "—", 1, "项", 200, 0),
        ],
        "main_competitor": "东方宏业",
        "comp": [
            ("循环水泵", "300QH-600", 4, "台", 160, 120),
            ("冷却塔填料", "PVC复合", 1200, "m³", 0, 140),
            ("电动蝶阀", "DN800", 12, "台", 160, 20),
            ("管道及支架", "DN600", 850, "t", 300, 150),
            ("电气控制柜", "MNS型", 6, "面", 0, 230),
            ("安装调试", "—", 1, "项", 180, 0),
        ],
        "extra_competitors": [("海纳智造", 0.7)],  # (友商名, variant系数)
    },
    {
        "name": "宁夏宝丰甲醇项目净化装置",
        "loc": "宁夏宁东",
        "date": "2025-04-22",
        "price": 26500000,
        "winner": "华能重工",  # ≥2000w 段
        "ours": [  # 我方核心设备全外购 → 高成本落标
            ("变换炉", "φ3200", 2, "台", 0, 650),
            ("吸收塔", "φ2800", 1, "台", 0, 520),
            ("换热器", "BIU1200", 8, "台", 180, 120),
            ("压缩机", "离心式", 1, "台", 0, 450),
            ("管道及支架", "各类", 1200, "t", 300, 100),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "main_competitor": "华能重工",
        "comp": [  # 友商塔器/压缩机可自产 → 低价中标
            ("变换炉", "φ3200", 2, "台", 600, 50),
            ("吸收塔", "φ2800", 1, "台", 480, 40),
            ("换热器", "BIU1200", 8, "台", 200, 80),
            ("压缩机", "离心式", 1, "台", 420, 30),
            ("管道及支架", "各类", 1200, "t", 280, 90),
            ("安装调试", "—", 1, "项", 240, 0),
        ],
        "extra_competitors": [("航天晨光", 0.9)],
    },
    {
        "name": "内蒙古久泰乙二醇装置",
        "loc": "内蒙古鄂尔多斯",
        "date": "2025-06-10",
        "price": 4800000,
        "winner": "中机国能",  # 100-500w 段
        "ours": [
            ("反应器", "φ2400", 1, "台", 0, 180),
            ("换热器", "BIU800", 4, "台", 120, 40),
            ("塔器", "φ1600", 2, "台", 80, 60),
            ("管道及支架", "各类", 320, "t", 40, 30),
            ("安装调试", "—", 1, "项", 20, 0),
        ],
        "main_competitor": "东方宏业",
        "comp": [
            ("反应器", "φ2400", 1, "台", 160, 20),
            ("换热器", "BIU800", 4, "台", 110, 30),
            ("塔器", "φ1600", 2, "台", 70, 40),
            ("管道及支架", "各类", 320, "t", 35, 25),
            ("安装调试", "—", 1, "项", 18, 0),
        ],
        "extra_competitors": [("中机国能", 1.1), ("江南重工", 0.8)],
    },
    {
        "name": "大唐国际雷州电厂烟气脱硫",
        "loc": "广东雷州",
        "date": "2025-07-18",
        "price": 32000000,
        "winner": "航天晨光",  # ≥2000w 段(超大)
        "ours": [  # 脱硫塔/氧化风机我方外购 → 高成本落标
            ("脱硫塔", "φ18000", 1, "台", 0, 950),
            ("浆液循环泵", "TL800", 6, "台", 280, 120),
            ("氧化风机", "罗茨式", 4, "台", 0, 680),
            ("管道及支架", "各类", 1500, "t", 400, 150),
            ("电气系统", "—", 1, "套", 0, 350),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "main_competitor": "航天晨光",
        "comp": [  # 友商自产 → 低价中标
            ("脱硫塔", "φ18000", 1, "台", 880, 70),
            ("浆液循环泵", "TL800", 6, "台", 260, 100),
            ("氧化风机", "罗茨式", 4, "台", 630, 50),
            ("管道及支架", "各类", 1500, "t", 370, 130),
            ("电气系统", "—", 1, "套", 0, 320),
            ("安装调试", "—", 1, "项", 240, 0),
        ],
        "extra_competitors": [("华能重工", 0.95)],
    },
    {
        "name": "中天合创煤化工水处理",
        "loc": "内蒙古鄂尔多斯",
        "date": "2025-09-05",
        "price": 850000,
        "winner": "ours",  # <100w 段(小项目,我方超滤自产)
        "ours": [
            ("超滤装置", "UF-160", 2, "套", 60, 5),
            ("反渗透膜", "BW-440", 30, "支", 0, 15),
            ("加药装置", "成套", 3, "套", 8, 2),
            ("管道及支架", "各类", 45, "t", 3, 2),
            ("安装调试", "—", 1, "项", 5, 0),
        ],
        "main_competitor": "东方宏业",
        "comp": [
            ("超滤装置", "UF-160", 2, "套", 55, 8),
            ("反渗透膜", "BW-440", 30, "支", 0, 14),
            ("加药装置", "成套", 3, "套", 7, 3),
            ("管道及支架", "各类", 45, "t", 2, 3),
            ("安装调试", "—", 1, "项", 4, 0),
        ],
        "extra_competitors": [],
    },
    {
        "name": "万华化学烟台PDH装置",
        "loc": "山东烟台",
        "date": "2025-11-12",
        "price": 21000000,
        "winner": "江南重工",  # ≥2000w 段
        "ours": [  # 丙烯塔/压缩机我方外购 → 高成本落标
            ("丙烯塔", "φ4200", 1, "台", 0, 580),
            ("压缩机", "丙烷离心", 1, "台", 0, 620),
            ("反应器", "φ3000", 1, "台", 0, 450),
            ("换热器", "BIU1400", 6, "台", 200, 100),
            ("管道及支架", "各类", 980, "t", 150, 80),
            ("安装调试", "—", 1, "项", 100, 0),
        ],
        "main_competitor": "江南重工",
        "comp": [  # 友商自产 → 低价中标
            ("丙烯塔", "φ4200", 1, "台", 540, 40),
            ("压缩机", "丙烷离心", 1, "台", 580, 50),
            ("反应器", "φ3000", 1, "台", 420, 30),
            ("换热器", "BIU1400", 6, "台", 180, 90),
            ("管道及支架", "各类", 980, "t", 140, 70),
            ("安装调试", "—", 1, "项", 95, 0),
        ],
        "extra_competitors": [("中机国能", 0.85), ("海纳智造", 0.75)],
    },
]

# ════════════════════════════════════════════════════════════════════
# EAI-CUSTOM: 确定性扩量生成器(2023-2025 三年 34 个项目,零随机)
# ════════════════════════════════════════════════════════════════════

# 金额段(与仪表盘 <100万/100-500万/500-2000万/≥2000万 对齐)
SEGS = ["lt100w", "100to500w", "500to2000w", "gt2000w"]
# 各段基准价(万元),× (1+(i%5)*0.07) 制造项目间差异
SEG_BASE = {"lt100w": 75, "100to500w": 280, "500to2000w": 1100, "gt2000w": 2600}
# 我方成本/报价比例(gt2000w 0.93 → 成本切进历史中标 P25-P75 带,即大项目我方成本几乎吃掉报价)
COST_RATIO = {"lt100w": 0.62, "100to500w": 0.65, "500to2000w": 0.72, "gt2000w": 0.93}
# 我方自产率(分段不同体现自产能力差异: 小项目超滤/泵类自产,大项目塔器/压缩机全外购)
OUR_SELF_SHARE = {"lt100w": 0.80, "100to500w": 0.60, "500to2000w": 0.55, "gt2000w": 0.12}

# 溢价桶计划: (我方报价相对该项目友商最低价 cmin 的溢价, 我方胜数, 我方负数)
# 胜率单调递减: 75% → 71.4% → 57.1% → 28.6% → 20% → 0%,拐点在 +3% 附近(第3→4桶骤降 28.6pt)
PREM_BUCKETS = [
    (-0.08, 3, 1),
    (-0.02, 5, 2),
    (0.015, 4, 3),
    (0.045, 2, 5),
    (0.08, 1, 4),
    (0.15, 0, 4),
]
# 年度配额 {年: (我方胜数, 我方负数)} — 三年我方中标份额逐年抬升(15胜+19负=34)
YEAR_QUOTA = {2023: (2, 9), 2024: (5, 7), 2025: (8, 3)}
YEAR_ORDER = [2023, 2024, 2025]

# 各段 3 条货物(货物名, 规格, 数量, 单位, 成本占比) — 占比合计 1.0
SEG_GOODS = {
    "lt100w": [
        ("超滤装置", "UF-160", 2, "套", 0.50),
        ("加药装置", "成套", 3, "套", 0.20),
        ("管道及支架", "各类", 45, "t", 0.30),
    ],
    "100to500w": [
        ("反应器", "φ2400", 1, "台", 0.45),
        ("换热器", "BIU800", 4, "台", 0.30),
        ("塔器", "φ1600", 2, "台", 0.25),
    ],
    "500to2000w": [
        ("循环水泵", "300QH-600", 4, "台", 0.35),
        ("换热器", "BIU1200", 8, "台", 0.30),
        ("电气控制柜", "MNS型", 6, "面", 0.35),
    ],
    "gt2000w": [
        ("变换炉", "φ3200", 2, "台", 0.40),
        ("压缩机", "离心式", 1, "台", 0.35),
        ("吸收塔", "φ2800", 1, "台", 0.25),
    ],
}

# 生成项目名后缀(前缀 = 年-序号,如 "2023-01化工检修项目")与项目所在地,均确定性轮转
NAME_SUFFIX = ["化工检修", "煤化工气化装置", "热电联产改造", "炼化装置余热回收", "空分装置扩能"]
GEN_LOCS = ["江苏张家港", "山东淄博", "河北唐山", "辽宁大连", "浙江宁波", "广东茂名", "湖南岳阳", "湖北宜昌"]


def _alloc_year(remaining, pointer):
    """按轮转指针从 YEAR_ORDER 里取下一个还有配额余额的年份(保证同桶内年份交错)。"""
    for _ in range(len(YEAR_ORDER)):
        y = YEAR_ORDER[pointer[0] % len(YEAR_ORDER)]
        pointer[0] += 1
        if remaining[y] > 0:
            remaining[y] -= 1
            return y
    raise AssertionError("年度配额耗尽,计划与配额不一致")


def gen_bid_plan():
    """生成 34 条投标计划(纯函数,零随机)。

    每条: {year, seg, our_won, prem, comp_idx}
    - prem 桶固定胜/负数(胜率随溢价单调递减);
    - 年度配额轮转交错分配(2023 不会全是负);
    - seg 按 SEGS 轮转,但 ≥2000w 段我方全败(胜单强制降到 500to2000w)。
    """
    w_rem = {y: q[0] for y, q in YEAR_QUOTA.items()}
    l_rem = {y: q[1] for y, q in YEAR_QUOTA.items()}
    w_ptr, l_ptr = [0], [0]  # 用列表包一层模拟可变指针
    plan = []
    i = 0  # 全局序号(seg 轮转/差异系数都用它,保证确定性)
    for prem, n_won, n_lost in PREM_BUCKETS:
        for _ in range(n_won):
            year = _alloc_year(w_rem, w_ptr)
            seg = SEGS[i % len(SEGS)]
            if seg == "gt2000w":
                seg = "500to2000w"  # ≥2000万 我方全败 → 胜单降段
            plan.append({"year": year, "seg": seg, "our_won": True, "prem": prem, "comp_idx": (i * 2) % 6})
            i += 1
        for _ in range(n_lost):
            year = _alloc_year(l_rem, l_ptr)
            plan.append({"year": year, "seg": SEGS[i % len(SEGS)], "our_won": False, "prem": prem, "comp_idx": (i * 2) % 6})
            i += 1
    assert len(plan) == 34
    return plan


def _mk_items(seg, cost_wan, self_share):
    """按段的固定货物表把总成本(万元)拆成 3 条 items(自产/外购按 self_share 分割)。"""
    items = []
    for goods, spec, qty, unit, share in SEG_GOODS[seg]:
        c = cost_wan * share
        items.append((goods, spec, qty, unit, round(c * self_share, 1), round(c * (1 - self_share), 1)))
    return items


def gen_projects():
    """把 gen_bid_plan() 展开成完整项目行(纯函数,零随机)。

    每项目: {name, loc, date, year, seg, rows: [{role, bidder, won, price(万元), items}, ...]}
    - 我方 1 行 + 友商 2-3 行;恰好一家 won=True(我方胜则我方,否则指定赢家友商 j=i%n_comp);
    - 友商取池索引 (i*2)%6 为锚,+3/+1 错开保证互不重名(字面公式 (i*2+j*3)%6 在 j=2 时与 j=0 撞名,故微调);
    - 东方宏业参与即报 0.955×基准价(低价抢标画像 → 平均溢价为负);
    - 我方报价 = 该项目实际友商最低价 cmin × (1 + prem + 微扰((i%3)-1)*0.004);
    - 我方成本 = 我方报价 × COST_RATIO[seg];友商成本 = 友商报价 × (COST_RATIO-0.08)(可自产更省)。
    """
    projects = []
    for i, e in enumerate(gen_bid_plan()):
        seg, year, prem, our_won = e["seg"], e["year"], e["prem"], e["our_won"]
        # 友商 2-3 家(确定性索引,互不重名)
        n_comp = 2 + (i % 2)
        base = e["comp_idx"]
        idxs = [base, (base + 3) % 6] + ([(base + 1) % 6] if n_comp == 3 else [])
        wj = i % n_comp  # 我方输时,赢家友商的下标
        # 基准价(万元)× 差异系数
        b = SEG_BASE[seg] * (1 + (i % 5) * 0.07)
        # 友商报价: 东方宏业 0.955×b;指定赢家 0.98×b;其余 +3%~+8%(确定性系数)
        comp_prices = []
        for j, ci in enumerate(idxs):
            name = COMPETITORS_POOL[ci]
            if name == LOW_BALLER:
                comp_prices.append(b * 0.955)
            elif (not our_won) and j == wj:
                comp_prices.append(b * 0.98)
            else:
                comp_prices.append(b * (1.03 + ((i + j * 2) % 6) * 0.01))
        cmin = min(comp_prices)  # 该项目友商最低价(可能就是东方宏业)
        our_price = cmin * (1 + prem + ((i % 3) - 1) * 0.004)
        # 行组装: 我方 + 友商
        rows = [
            {
                "role": "ours",
                "bidder": OURS,
                "won": our_won,
                "price": our_price,
                "items": _mk_items(seg, our_price * COST_RATIO[seg], OUR_SELF_SHARE[seg]),
            }
        ]
        for j, ci in enumerate(idxs):
            price = comp_prices[j]
            # 友商自产率 = 我方 + 0.35(封顶 1.0) → 同货物自产成本占比高于我方
            rows.append(
                {
                    "role": "competitor",
                    "bidder": COMPETITORS_POOL[ci],
                    "won": (not our_won) and j == wj,
                    "price": price,
                    "items": _mk_items(seg, price * max(0.45, COST_RATIO[seg] - 0.08), min(1.0, OUR_SELF_SHARE[seg] + 0.35)),
                }
            )
        projects.append(
            {
                "name": f"{year}-{i + 1:02d}{NAME_SUFFIX[(year + i) % len(NAME_SUFFIX)]}项目",
                "loc": GEN_LOCS[(i * 3) % len(GEN_LOCS)],
                "date": f"{year}-{1 + (i * 5) % 12:02d}-{5 + (i % 20):02d}",
                "year": year,
                "seg": seg,
                "rows": rows,
            }
        )
    return projects


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
              COUNT(DISTINCT bidder_name) FILTER (WHERE bidder_role='competitor') AS competitor_count,
              COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_won,
              ROUND(AVG(winning_price) FILTER (WHERE won), 2) AS avg_winning_price,
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
              MAX(winning_price) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_price,
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

    def emit(name, loc, bid_date_iso, role, bidder, items, won, price_yuan):
        """生成 1 条 bid + 其 item 行(显式价格,万元 items 自动换算成元)。"""
        nonlocal seq
        seq += 1
        bid_id = f"BD-{seq:03d}"
        bid_rows.append((bid_id, name, loc, date.fromisoformat(bid_date_iso), role, bidder, won, price_yuan))
        for goods, spec, qty, unit, self_amt, out_amt in items:
            total = self_amt + out_amt  # 单位:万元
            # mock 表金额按元存(spec 标价以元为单位),万元 × 10000
            item_rows.append(
                (
                    bid_id,
                    goods,
                    spec,
                    qty,
                    unit,
                    round(total * 10000 / qty, 2),  # unit_price(元)
                    round(self_amt * 10000, 2),  # self_amount(元)
                    round(out_amt * 10000, 2),  # outsourced_amount(元)
                    round(total * 10000, 2),  # total_amount(元)
                )
            )

    # 2a. 手写 6 项目(沿用旧 emit 语义: 中标方按 base 价,落标方按 base × 上浮 5%-17%)
    for pi, p in enumerate(PROJECTS):
        markup = 0.05 + (pi % 5) * 0.03

        def _legacy_price(won):
            # EAI-CUSTOM(option A): 中标方按 base 价,落标方按 base × 上浮(落标=报价更高才落标)。
            return round(p["price"] * (1.0 if won else (1.0 + markup)), 2)

        emit(p["name"], p["loc"], p["date"], "ours", OURS, p["ours"], p["winner"] == "ours", _legacy_price(p["winner"] == "ours"))
        emit(p["name"], p["loc"], p["date"], "competitor", p["main_competitor"], p["comp"], p["winner"] == p["main_competitor"], _legacy_price(p["winner"] == p["main_competitor"]))
        for cname, k in p.get("extra_competitors", []):
            emit(p["name"], p["loc"], p["date"], "competitor", cname, _variant(p["comp"], k), p["winner"] == cname, _legacy_price(p["winner"] == cname))

    # 2b. 生成 34 项目(2023-2025 三年,确定性规律,价格/清单由 gen_projects 精确给定)
    for gp in gen_projects():
        for r in gp["rows"]:
            emit(gp["name"], gp["loc"], gp["date"], r["role"], r["bidder"], r["items"], r["won"], round(r["price"] * 10000, 2))

    await mock.executemany(
        "INSERT INTO mock_bid (bid_id,project_name,project_location,bid_date,bidder_role,bidder_name,won,winning_price) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        bid_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_bid_item (bid_id,goods_name,spec,quantity,unit,unit_price,self_amount,outsourced_amount,total_amount) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
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
            "INSERT INTO data_sources (id,name,description,type,connection_config,auth_type,sync_mode,status,created_at,updated_at) VALUES (gen_random_uuid(),$1,$2,$3,$4::jsonb,$5,$6,$7,now(),now()) RETURNING id",
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

    # 自检:汇总 + 多家一致性断言(肉眼校验数据故事 + 防 seed 错配)
    chk = await asyncpg.connect(**common, database=MOCK_DB)
    n_bid = await chk.fetchval("SELECT count(*) FROM mock_bid")
    n_item = await chk.fetchval("SELECT count(*) FROM mock_bid_item")
    ours_rate = await chk.fetchval("SELECT round(100.0*count(*) filter(where bidder_role='ours' and won)/count(*) filter(where bidder_role='ours'),1) FROM mock_bid")
    # 断言1:每项目恰 1 家中标(won=true)
    bad_projects = await chk.fetch("SELECT project_name, count(*) c FROM mock_bid WHERE won GROUP BY project_name HAVING count(*) <> 1")
    assert not bad_projects, f"每项目须恰 1 中标,违规: {[dict(r) for r in bad_projects]}"
    # 断言2:友商家数 > 1(多家生效)
    comp_count = await chk.fetchval("SELECT count(DISTINCT bidder_name) FROM mock_bid WHERE bidder_role='competitor'")
    assert comp_count >= 3, f"友商家数应 ≥3(多家),实际 {comp_count}"
    # 断言3:PROJECTS 里出现的友商名必须在池内(防拼写漂移静默造出新公司)
    used = {p["main_competitor"] for p in PROJECTS} | {c for p in PROJECTS for c, _ in p.get("extra_competitors", [])}
    assert used <= set(COMPETITORS_POOL), f"友商名不在池内: {used - set(COMPETITORS_POOL)}"
    # EAI-CUSTOM 扩量自检:
    # 断言4:项目总数 = 40(6 手写 + 34 生成)
    n_projects = await chk.fetchval("SELECT count(DISTINCT project_name) FROM mock_bid")
    assert n_projects == 40, f"项目数应为 40(6 手写 + 34 生成),实际 {n_projects}"
    # 断言5:≥2000万 段我方胜率 = 0(大项目短板故事)
    gt = await chk.fetchrow("SELECT count(*) AS bid, count(*) FILTER (WHERE won) AS won FROM mock_bid WHERE bidder_role='ours' AND winning_price >= 20000000")
    assert gt["won"] == 0, f"≥2000万段我方应全败,实际中标 {gt['won']}/{gt['bid']}"
    # 断言6:三年(2023-2025)都有中标记录
    year_rows = await chk.fetch("SELECT EXTRACT(YEAR FROM bid_date) AS y, count(*) AS c FROM mock_bid WHERE won GROUP BY 1 ORDER BY 1")
    assert sorted(int(r["y"]) for r in year_rows) == [2023, 2024, 2025], f"应覆盖 2023-2025 三年,实际 {[dict(r) for r in year_rows]}"
    seg = await chk.fetch(
        "SELECT CASE WHEN winning_price<1000000 THEN '<100w' WHEN winning_price<5000000 THEN '100-500w' "
        "WHEN winning_price<20000000 THEN '500-2000w' ELSE '>=2000w' END seg, "
        "count(*) filter(where bidder_role='ours') bid, count(*) filter(where bidder_role='ours' and won) won "
        "FROM mock_bid GROUP BY 1 ORDER BY 1"
    )
    print("\n===== 自检 =====")
    print(f"bid={n_bid} item={n_item} 我方中标率={ours_rate}% 友商家数={comp_count} 项目数={n_projects}")
    for r in seg:
        print(f"  金额段 {r['seg']}: 我方投 {r['bid']} 中 {r['won']}")
    for r in year_rows:
        print(f"  {int(r['y'])} 年中标记录 {r['c']} 条")
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
