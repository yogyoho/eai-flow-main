# 投标报价分析 过滤条件 + 多家友商 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 bid-quote 每个分析图表加过滤条件(项目/友商/日期全局 + 每图高级筛选),seed 支持多家友商,新增自产/外采 2 图 + 货物级下钻增强。

**Architecture:** 纯前端拼参数化只读 SQL(Route B 零后端增量),全走 `POST /data-sources/{sid}/query`;seed 重构支持多家友商(零 schema 变更);4 罐装 SQL 多家语义复核。设计依据:`docs/superpowers/specs/2026-08-14-bid-quote-filter-multicompetitor-design.md`。

**Tech Stack:** Python 3.12 + asyncpg(seed);Next.js 16 / React 19 / TypeScript / TanStack Query / recharts(前端);Docker `eai-docker` 组。

**环境约束(每步生效):**
- 后端/seed 改动 → `docker compose -p eai-docker restart gateway`
- 前端改动 → `docker compose -p eai-docker restart frontend`(HMR 不可靠)
- 跑 seed → `docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_market.py`
- 前端 typecheck/test → `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck'` / `pnpm test`
- 提交仅 `main-dev-fork` 分支;**commit 前必查 `git diff --cached --name-only`**(并发会话坑,见 bug-1186);用 `git commit -m ... -- <文件>` 精确提交
- 所有代码用中文注释;EAI 定制加 `EAI-CUSTOM` 注释

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/scripts/seed_mock_market.py` | 改 | 多家友商 PROJECTS + 循环;4 SQL 多家语义复核;自检断言 |
| `frontend/src/extensions/bid-quote/types.ts` | 改 | FilterState/ChartFilter/新图 row 类型;BidSummaryRow 加 competitor_count |
| `frontend/src/extensions/bid-quote/api.ts` | 改 | SQL 模板常量 + buildWhere() + esc() + queryFiltered() |
| `frontend/src/extensions/bid-quote/hooks.ts` | 改 | 各 hook 接 filters;useFilterOptions;2 新图 hook |
| `frontend/src/extensions/bid-quote/components/FilterBar.tsx` | 新 | 全局过滤器(项目/友商/日期) |
| `frontend/src/extensions/bid-quote/components/ChartFilterPopover.tsx` | 新 | 每图高级筛选 popover |
| `frontend/src/extensions/bid-quote/components/SelfRateDistChart.tsx` | 新 | 图C 项目自产率分布 |
| `frontend/src/extensions/bid-quote/components/SelfVsOutsourceChart.tsx` | 新 | 图B 自产vs外购金额 |
| `frontend/src/extensions/bid-quote/components/DashboardView.tsx` | 改 | 挂 FilterBar + 各图接 filters + 2 新图卡 |
| `frontend/src/extensions/bid-quote/components/QueryView.tsx` | 改 | 共享 FilterBar + tab 接 filters + showdown 多友商下钻 |
| `frontend/src/extensions/bid-quote/components/DrillDownModal.tsx` | 改 | 自产外购列高亮 + 二次筛选 |
| `frontend/tests/unit/extensions/bid-quote/build-where.test.ts` | 新 | buildWhere 纯函数单测 |

---

## Task 1: 多家友商 seed 改造 + 一致性断言

**Files:**
- Modify: `backend/scripts/seed_mock_market.py`(整体重构 PROJECTS + 循环 + DATASETS SQL + 自检)

- [ ] **Step 1: 改头部常量 + 加 variant helper**

把 `backend/scripts/seed_mock_market.py:46-47` 的:
```python
OURS = "东智装备制造"
COMP = "东方宏业"
```
替换为:
```python
OURS = "东智装备制造"
# EAI-CUSTOM: 多家友商(原单常量 COMP)。每项目 2-3 家友商竞争,1 家中标。
COMPETITORS_POOL = ["东方宏业", "华能重工", "中机国能", "江南重工", "海纳智造", "航天晨光"]


def _variant(base, k):
    """友商货物清单变体:模拟不同友商的自产能力。
    k=1.0 基准;k<1 自产弱(自产×k,外购补足);k>1 自产强。
    base = [(货物,规格,数量,单位,自产万,外购万), ...]
    """
    return [(g, s, q, u, round(sm * k), round(om * (2 - k))) for g, s, q, u, sm, om in base]
```

- [ ] **Step 2: 改 PROJECTS 结构(每项目多家友商 + 具体 winner)**

把 `seed_mock_market.py:52-169` 整个 `PROJECTS = [...]` 替换为(沿用现有数据故事,每项目主友商 = 原 comp 清单,额外友商 = variant;winner 改为具体中标方 identity):
```python
PROJECTS = [
    {
        "name": "华能铜川电厂二期循环水系统", "loc": "陕西铜川", "date": "2025-03-15",
        "price": 18500000, "winner": "ours",
        "ours": [
            ("循环水泵", "300QH-600", 4, "台", 280, 20),
            ("冷却塔填料", "PVC复合", 1200, "m³", 0, 150),
            ("电动蝶阀", "DN800", 12, "台", 180, 0),
            ("管道及支架", "DN600", 850, "t", 350, 120),
            ("电气控制柜", "MNS型", 6, "面", 0, 250),
            ("安装调试", "—", 1, "项", 200, 0),
        ],
        "main_competitor": "东方宏业",
        "comp": [  # 主友商清单
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
        "name": "宁夏宝丰甲醇项目净化装置", "loc": "宁夏宁东", "date": "2025-04-22",
        "price": 26500000, "winner": "华能重工",
        "ours": [
            ("变换炉", "φ3200", 2, "台", 0, 650),
            ("吸收塔", "φ2800", 1, "台", 0, 520),
            ("换热器", "BIU1200", 8, "台", 180, 120),
            ("压缩机", "离心式", 1, "台", 0, 450),
            ("管道及支架", "各类", 1200, "t", 300, 100),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "main_competitor": "华能重工",
        "comp": [
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
        "name": "内蒙古久泰乙二醇装置", "loc": "内蒙古鄂尔多斯", "date": "2025-06-10",
        "price": 4800000, "winner": "中机国能",
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
        "name": "大唐国际雷州电厂烟气脱硫", "loc": "广东雷州", "date": "2025-07-18",
        "price": 32000000, "winner": "航天晨光",
        "ours": [
            ("脱硫塔", "φ18000", 1, "台", 0, 950),
            ("浆液循环泵", "TL800", 6, "台", 280, 120),
            ("氧化风机", "罗茨式", 4, "台", 0, 680),
            ("管道及支架", "各类", 1500, "t", 400, 150),
            ("电气系统", "—", 1, "套", 0, 350),
            ("安装调试", "—", 1, "项", 250, 0),
        ],
        "main_competitor": "航天晨光",
        "comp": [
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
        "name": "中天合创煤化工水处理", "loc": "内蒙古鄂尔多斯", "date": "2025-09-05",
        "price": 850000, "winner": "ours",
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
        "name": "万华化学烟台PDH装置", "loc": "山东烟台", "date": "2025-11-12",
        "price": 21000000, "winner": "江南重工",
        "ours": [
            ("丙烯塔", "φ4200", 1, "台", 0, 580),
            ("压缩机", "丙烷离心", 1, "台", 0, 620),
            ("反应器", "φ3000", 1, "台", 0, 450),
            ("换热器", "BIU1400", 6, "台", 200, 100),
            ("管道及支架", "各类", 980, "t", 150, 80),
            ("安装调试", "—", 1, "项", 100, 0),
        ],
        "main_competitor": "江南重工",
        "comp": [
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
```

- [ ] **Step 3: 重写灌数循环(多家友商)**

把 `seed_mock_market.py:299-335` 的(从 `bid_rows, item_rows = [], []` 到 `await mock.executemany(... item_rows ...)` 含两个 executemany)替换为:
```python
    bid_rows, item_rows = [], []
    seq = 0

    def emit(p, role, bidder, items, won, pi):
        """生成 1 条 bid + 其 item 行。price: 中标方按 base,落标方按 base×上浮。"""
        nonlocal seq
        seq += 1
        bid_id = f"BD-2025-{seq:03d}"
        markup = 0.05 + (pi % 5) * 0.03  # EAI-CUSTOM: 落标方上浮,避免全同比例
        price = round(p["price"] * (1.0 if won else (1.0 + markup)), 2)
        bid_rows.append(
            (bid_id, p["name"], p["loc"], date.fromisoformat(p["date"]), role, bidder, won, price)
        )
        for goods, spec, qty, unit, self_amt, out_amt in items:
            total = self_amt + out_amt  # 万元
            item_rows.append(
                (
                    bid_id, goods, spec, qty, unit,
                    round(total * 10000 / qty, 2),   # unit_price(元)
                    round(self_amt * 10000, 2),      # self_amount(元)
                    round(out_amt * 10000, 2),       # outsourced_amount(元)
                    round(total * 10000, 2),         # total_amount(元)
                )
            )

    for pi, p in enumerate(PROJECTS):
        # 我方
        emit(p, "ours", OURS, p["ours"], p["winner"] == "ours", pi)
        # 主友商(清单 = comp)
        emit(p, "competitor", p["main_competitor"], p["comp"], p["winner"] == p["main_competitor"], pi)
        # 额外友商(清单 = comp 的 variant)
        for cname, k in p.get("extra_competitors", []):
            emit(p, "competitor", cname, _variant(p["comp"], k), p["winner"] == cname, pi)

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
```

- [ ] **Step 4: 改 4 个 DATASETS SQL(多家语义复核)**

`bid_summary` 的 `default_query`(`seed_mock_market.py:177-191`)替换为(加 `competitor_count`,`avg_winning_price` 改仅中标价):
```python
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
```
`bqa_project_showdown` 的 `default_query`(`seed_mock_market.py:242-251`)替换为(competitor_price 取中标友商价):
```python
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
```
> `composition_compare_by_goods` 与 `win_rate_by_segment` 多家下语义本就正确(按 role 聚合 / 仅我方),不改。

- [ ] **Step 5: 自检段加多家一致性断言**

把 `seed_mock_market.py:381-398` 的自检段(从 `chk = await asyncpg.connect(...)` 到 `await chk.close()`)替换为:
```python
    # 自检:汇总 + 多家一致性断言(肉眼校验数据故事 + 防 seed 错配)
    chk = await asyncpg.connect(**common, database=MOCK_DB)
    n_bid = await chk.fetchval("SELECT count(*) FROM mock_bid")
    n_item = await chk.fetchval("SELECT count(*) FROM mock_bid_item")
    ours_rate = await chk.fetchval(
        "SELECT round(100.0*count(*) filter(where bidder_role='ours' and won)/count(*) filter(where bidder_role='ours'),1) FROM mock_bid"
    )
    # 断言1:每项目恰 1 家中标(won=true)
    bad_projects = await chk.fetch(
        "SELECT project_name, count(*) c FROM mock_bid WHERE won GROUP BY project_name HAVING count(*) <> 1"
    )
    assert not bad_projects, f"每项目须恰 1 中标,违规: {[dict(r) for r in bad_projects]}"
    # 断言2:友商家数 > 1(多家生效)
    comp_count = await chk.fetchval(
        "SELECT count(DISTINCT bidder_name) FROM mock_bid WHERE bidder_role='competitor'"
    )
    assert comp_count >= 3, f"友商家数应 ≥3(多家),实际 {comp_count}"
    seg = await chk.fetch(
        "SELECT CASE WHEN winning_price<1000000 THEN '<100w' WHEN winning_price<5000000 THEN '100-500w' "
        "WHEN winning_price<20000000 THEN '500-2000w' ELSE '>=2000w' END seg, "
        "count(*) filter(where bidder_role='ours') bid, count(*) filter(where bidder_role='ours' and won) won "
        "FROM mock_bid GROUP BY 1 ORDER BY 1"
    )
    print("\n===== 自检 =====")
    print(f"bid={n_bid} item={n_item} 我方中标率={ours_rate}% 友商家数={comp_count}")
    for r in seg:
        print(f"  金额段 {r['seg']}: 我方投 {r['bid']} 中 {r['won']}")
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")
```

- [ ] **Step 6: 跑 seed 验证**

Run: `docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_market.py`
Expected: 输出 `bid=` 数 > 12(原 12,现多家更多),`友商家数=` ≥3,无 AssertionError;金额段统计正常。若断言失败,检查 PROJECTS 的 winner 与 main_competitor/extra_competitors 名字一致。

Run: `docker compose -p eai-docker restart gateway`
Expected: gateway 重启,data_source 缓存刷新。

- [ ] **Step 7: 提交**

```bash
git diff --cached --name-only   # 确认无并发会话 staged 文件后
git add backend/scripts/seed_mock_market.py
git commit -m "feat(bid-quote): seed 多家友商(每项目2-3家)+4SQL多家语义复核" -- backend/scripts/seed_mock_market.py
```

---

## Task 2: 前端类型 + SQL 模板 + buildWhere + 单测

**Files:**
- Modify: `frontend/src/extensions/bid-quote/types.ts`
- Modify: `frontend/src/extensions/bid-quote/api.ts`
- Create: `frontend/tests/unit/extensions/bid-quote/build-where.test.ts`

- [ ] **Step 1: types.ts 加过滤类型 + 新图 row + competitor_count**

在 `types.ts:17`(BidSummaryRow 的 `competitor_won` 行后)加一行:
```typescript
  competitor_count: number;
```
在 `types.ts` 末尾(`QueryResult` interface 之后)追加:
```typescript
/** 全局过滤状态(仪表盘/查询页各自独立持有)。空数组/null = 不过滤。 */
export interface FilterState {
  projects: string[];
  competitors: string[]; // bidder_name(role=competitor)
  dateFrom: string | null; // ISO yyyy-mm-dd
  dateTo: string | null;
}
export const EMPTY_FILTERS: FilterState = { projects: [], competitors: [], dateFrom: null, dateTo: null };

/** 每图高级筛选(按图适用维度启用子集)。 */
export type AmountSegment = "lt100w" | "100to500w" | "500to2000w" | "gt2000w";
export type SelfAttribute = "self_dominant" | "outsource_dominant" | "all";
export interface ChartFilter {
  amountSegment?: AmountSegment;
  selfAttribute?: SelfAttribute; // 不进 SQL:货物构成图前端行过滤 / 自产率图渲染门槛
  goodsName?: string[];
}

/** 图C 项目自产率分布 row。 */
export interface SelfRateRow {
  project_name: string;
  self_rate: string | null; // 百分比 0-100
  total_self: string | null;
  total_outsourced: string | null;
}
/** 图B 自产vs外购 row。 */
export interface SelfVsOutsourceRow {
  label: string; // project_name 或 goods_name
  self_amount: string | null;
  outsourced_amount: string | null;
}
/** distinct 过滤选项。 */
export interface FilterOptions {
  projects: string[];
  competitors: string[];
}
```

- [ ] **Step 2: api.ts 加 esc + buildWhere + SQL 模板 + queryFiltered**

在 `api.ts` 末尾(`clearBidQuoteCache` 之后)追加:
```typescript
import type { ChartFilter, FilterState } from "./types";

/** 单引号转义(值来自 DB distinct 行,非用户自由输入;只读 SELECT)。 */
export function esc(v: string): string {
  return v.replace(/'/g, "''");
}

const SEG_WHERE: Record<string, string> = {
  lt100w: "winning_price < 1000000",
  "100to500w": "winning_price >= 1000000 AND winning_price < 5000000",
  "500to2000w": "winning_price >= 5000000 AND winning_price < 20000000",
  gt2000w: "winning_price >= 20000000",
};

/**
 * 拼 WHERE 子句片段(不含 WHERE 关键字)。全局 + 每图 AND 叠加。
 * selfAttribute 不在此处理(spec §5.4):货物构成图前端 filter / 自产率图渲染层。
 * 友商过滤对"仅我方"的查询:调用方传 useCompetitorExists=true → 追加 EXISTS 子查询。
 */
export function buildWhere(
  g: FilterState,
  chart?: ChartFilter,
  useCompetitorExists = false,
): string {
  const c: string[] = ["1=1"];
  if (g.projects.length) {
    c.push(`project_name IN (${g.projects.map((p) => `'${esc(p)}'`).join(",")})`);
  }
  if (g.competitors.length) {
    const list = g.competitors.map((x) => `'${esc(x)}'`).join(",");
    if (useCompetitorExists) {
      // 仅我方查询:筛"有选中友商参与的项目"
      c.push(
        `EXISTS (SELECT 1 FROM mock_bid c2 WHERE c2.project_name = mock_bid.project_name AND c2.bidder_role='competitor' AND c2.bidder_name IN (${list}))`,
      );
    } else {
      c.push(`bidder_name IN (${list})`);
    }
  }
  if (g.dateFrom) c.push(`bid_date >= '${esc(g.dateFrom)}'`);
  if (g.dateTo) c.push(`bid_date <= '${esc(g.dateTo)}'`);
  if (chart?.amountSegment) c.push(SEG_WHERE[chart.amountSegment]);
  if (chart?.goodsName?.length) {
    c.push(`goods_name IN (${chart.goodsName.map((n) => `'${esc(n)}'`).join(",")})`);
  }
  return c.join(" AND ");
}

// ── SQL 模板常量(无过滤 = 全量,即罐装默认视图)──
const TPL = {
  summary: `SELECT
    COUNT(DISTINCT project_name) AS project_count, COUNT(*) AS bid_count,
    COUNT(*) FILTER (WHERE bidder_role='ours') AS ours_bid,
    COUNT(*) FILTER (WHERE bidder_role='ours' AND won) AS ours_won,
    ROUND(100.0 * COUNT(*) FILTER (WHERE bidder_role='ours' AND won)
      / NULLIF(COUNT(*) FILTER (WHERE bidder_role='ours'),0), 1) AS ours_win_rate_pct,
    COUNT(*) FILTER (WHERE bidder_role='competitor') AS competitor_bid,
    COUNT(DISTINCT bidder_name) FILTER (WHERE bidder_role='competitor') AS competitor_count,
    COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_won,
    ROUND(AVG(winning_price) FILTER (WHERE won), 2) AS avg_winning_price,
    MIN(bid_date) AS earliest_bid, MAX(bid_date) AS latest_bid
    FROM mock_bid`,
  composition: `SELECT i.goods_name,
    ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='ours')
      / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'),0), 1) AS ours_self_pct,
    ROUND(100.0 * SUM(i.outsourced_amount) FILTER (WHERE b.bidder_role='ours')
      / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='ours'),0), 1) AS ours_outsourced_pct,
    ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='ours'), 2) AS ours_avg_unit_price,
    ROUND(100.0 * SUM(i.self_amount) FILTER (WHERE b.bidder_role='competitor')
      / NULLIF(SUM(i.self_amount + i.outsourced_amount) FILTER (WHERE b.bidder_role='competitor'),0), 1) AS competitor_self_pct,
    ROUND(AVG(i.unit_price) FILTER (WHERE b.bidder_role='competitor'), 2) AS competitor_avg_unit_price
    FROM mock_bid_item i JOIN mock_bid b ON b.bid_id = i.bid_id`,
  segment: `SELECT
    CASE WHEN winning_price < 1000000 THEN '1_<100万'
         WHEN winning_price < 5000000 THEN '2_100-500万'
         WHEN winning_price < 20000000 THEN '3_500-2000万'
         ELSE '4_≥2000万' END AS amount_segment,
    COUNT(*) AS ours_bid, COUNT(*) FILTER (WHERE won) AS ours_won,
    ROUND(100.0 * COUNT(*) FILTER (WHERE won) / NULLIF(COUNT(*),0), 1) AS ours_win_rate_pct
    FROM mock_bid WHERE bidder_role='ours'`,
  showdown: `SELECT project_name,
    MAX(winning_price) FILTER (WHERE bidder_role='ours') AS our_price,
    MAX(winning_price) FILTER (WHERE bidder_role='competitor' AND won) AS competitor_price,
    BOOL_OR(bidder_role='ours' AND won) AS we_won,
    MAX(project_location) AS project_location
    FROM mock_bid`,
  selfRate: `SELECT b.project_name,
    ROUND(100.0 * SUM(i.self_amount) / NULLIF(SUM(i.self_amount + i.outsourced_amount), 0), 1) AS self_rate,
    SUM(i.self_amount) AS total_self, SUM(i.outsourced_amount) AS total_outsourced
    FROM mock_bid_item i JOIN mock_bid b ON b.bid_id = i.bid_id`,
  selfVsOutsource: (dim: "project" | "goods") =>
    `SELECT ${dim === "project" ? "b.project_name" : "i.goods_name"} AS label,
    SUM(i.self_amount) AS self_amount, SUM(i.outsourced_amount) AS outsourced_amount
    FROM mock_bid_item i JOIN mock_bid b ON b.bid_id = i.bid_id`,
} as const;

/** 拼最终 SQL:模板 + WHERE + GROUP BY/ORDER(各模板尾部固定)。 */
export function sqlFor(
  key: keyof Pick<typeof TPL, "summary" | "composition" | "segment" | "showdown" | "selfRate">,
  g: FilterState,
  chart?: ChartFilter,
): string {
  const tail: Record<string, string> = {
    summary: "",
    composition: " GROUP BY i.goods_name ORDER BY i.goods_name",
    segment: " GROUP BY 1 ORDER BY 1",
    showdown: " GROUP BY project_name ORDER BY MIN(bid_id)",
    selfRate: " WHERE b.bidder_role='ours' GROUP BY b.project_name ORDER BY self_rate DESC",
  };
  const where = buildWhere(g, chart, key === "segment");
  const base = TPL[key];
  if (key === "selfRate") {
    // selfRate 已含 WHERE bidder_role='ours';把 buildWhere 合并进去
    return base.replace("WHERE b.bidder_role='ours'", `WHERE b.bidder_role='ours' AND ${where}`) + "";
  }
  if (key === "summary") return `${base} WHERE ${where}`;
  // composition/showdown/segment 尾部 GROUP BY;WHERE 插在 GROUP 前
  const t = tail[key];
  return `${base} WHERE ${where}${t}`;
}

/** 图B 自产vs外购(项目/货物视角)。 */
export function sqlSelfVsOutsource(g: FilterState, dim: "project" | "goods", chart?: ChartFilter): string {
  const where = buildWhere(g, chart);
  const grp = dim === "project" ? "b.project_name" : "i.goods_name";
  return `${TPL.selfVsOutsource(dim)} WHERE ${where} GROUP BY ${grp} ORDER BY ${grp}`;
}

/** 跑过滤后的 SQL → querySql。 */
export async function queryFiltered(sql: string): Promise<QueryResult> {
  const sid = await resolveSourceId();
  return querySql(sid, sql);
}

/** distinct 过滤选项(项目 + 友商)。 */
export async function fetchFilterOptions(): Promise<{ projects: string[]; competitors: string[] }> {
  const sid = await resolveSourceId();
  const [pr, cr] = await Promise.all([
    querySql(sid, "SELECT DISTINCT project_name AS v FROM mock_bid ORDER BY project_name"),
    querySql(sid, "SELECT DISTINCT bidder_name AS v FROM mock_bid WHERE bidder_role='competitor' ORDER BY bidder_name"),
  ]);
  return {
    projects: (pr.rows as { v: string }[]).map((r) => r.v),
    competitors: (cr.rows as { v: string }[]).map((r) => r.v),
  };
}
```
> `import type { ChartFilter, FilterState }` 必须在文件顶部 import 区(ESLint import/order)。实际写入时把该行合并到文件顶部现有 `import type { QueryResult }` 旁:
```typescript
import type { ChartFilter, FilterState, QueryResult } from "./types";
```
(删掉末尾追加的重复 import 行)

- [ ] **Step 3: 写 buildWhere 单测**

Create `frontend/tests/unit/extensions/bid-quote/build-where.test.ts`:
```typescript
import { describe, expect, it } from "rstest/context";

import { buildWhere, esc } from "@/extensions/bid-quote/api";
import { EMPTY_FILTERS, type ChartFilter, type FilterState } from "@/extensions/bid-quote/types";

describe("esc", () => {
  it("转义单引号", () => {
    expect(esc("O'Brien")).toBe("O''Brien");
    expect(esc("正常")).toBe("正常");
  });
});

describe("buildWhere", () => {
  it("空过滤返回 1=1", () => {
    expect(buildWhere(EMPTY_FILTERS)).toBe("1=1");
  });
  it("projects → IN", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲", "乙"] };
    expect(buildWhere(g)).toBe("1=1 AND project_name IN ('甲','乙')");
  });
  it("competitors → bidder_name IN(普通模式)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    expect(buildWhere(g)).toBe("1=1 AND bidder_name IN ('友A')");
  });
  it("competitors + useCompetitorExists → EXISTS(仅我方查询)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    const w = buildWhere(g, undefined, true);
    expect(w).toContain("EXISTS");
    expect(w).toContain("c2.bidder_name IN ('友A')");
  });
  it("日期范围", () => {
    const g: FilterState = { ...EMPTY_FILTERS, dateFrom: "2025-01-01", dateTo: "2025-12-31" };
    expect(buildWhere(g)).toBe("1=1 AND bid_date >= '2025-01-01' AND bid_date <= '2025-12-31'");
  });
  it("chart.amountSegment", () => {
    const chart: ChartFilter = { amountSegment: "100to500w" };
    expect(buildWhere(EMPTY_FILTERS, chart)).toContain("winning_price >= 1000000 AND winning_price < 5000000");
  });
  it("chart.goodsName", () => {
    const chart: ChartFilter = { goodsName: ["塔器"] };
    expect(buildWhere(EMPTY_FILTERS, chart)).toBe("1=1 AND goods_name IN ('塔器')");
  });
  it("单引号转义进 SQL", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["O'Brien厂"] };
    expect(buildWhere(g)).toBe("1=1 AND project_name IN ('O''Brien厂')");
  });
  it("全局 + 每图 AND 叠加", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲"] };
    const chart: ChartFilter = { amountSegment: "lt100w" };
    const w = buildWhere(g, chart);
    expect(w).toBe("1=1 AND project_name IN ('甲') AND winning_price < 1000000");
  });
});
```

- [ ] **Step 4: 跑单测**

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm test -- build-where'`
Expected: 9 passed。

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck'`
Expected: 无错误。

- [ ] **Step 5: 提交**

```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/types.ts frontend/src/extensions/bid-quote/api.ts frontend/tests/unit/extensions/bid-quote/build-where.test.ts
git commit -m "feat(bid-quote): SQL模板+buildWhere+过滤类型(纯函数,9单测)" -- frontend/src/extensions/bid-quote/types.ts frontend/src/extensions/bid-quote/api.ts frontend/tests/unit/extensions/bid-quote/build-where.test.ts
```

---

## Task 3: FilterBar 组件 + useFilterOptions + DashboardView/QueryView 挂载

**Files:**
- Create: `frontend/src/extensions/bid-quote/components/FilterBar.tsx`
- Modify: `frontend/src/extensions/bid-quote/hooks.ts`
- Modify: `frontend/src/extensions/bid-quote/components/DashboardView.tsx`
- Modify: `frontend/src/extensions/bid-quote/components/QueryView.tsx`

- [ ] **Step 1: hooks.ts 加 useFilterOptions**

在 `hooks.ts` 的 `KEYS` 对象内(`drilldown` 行后)加:
```typescript
  filterOptions: ["bqa", "filterOptions"] as const,
```
在 `hooks.ts` 末尾追加:
```typescript
import { fetchFilterOptions } from "./api";
import type { FilterOptions } from "./types";

/** distinct 过滤选项(项目 + 友商),供 FilterBar 下拉。 */
export function useFilterOptions() {
  return useQuery({
    queryKey: KEYS.filterOptions,
    queryFn: async (): Promise<FilterOptions> => fetchFilterOptions(),
  });
}
```

- [ ] **Step 2: 建 FilterBar 组件**

Create `frontend/src/extensions/bid-quote/components/FilterBar.tsx`:
```typescript
"use client";

import { Filter } from "lucide-react";

import { useFilterOptions } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

interface FilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

// 多选下拉:点击 chip 切换选中。选项来自 distinct 查询。
function MultiSelect({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1">
        {options.length === 0 ? (
          <span className="text-[11px] text-muted-foreground/60">加载中…</span>
        ) : (
          options.map((o) => {
            const on = selected.includes(o);
            return (
              <button
                key={o}
                onClick={() => onToggle(o)}
                className={
                  "rounded border px-2 py-0.5 text-[11px] transition-colors " +
                  (on
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground")
                }
              >
                {o}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const optsQ = useFilterOptions();
  const opts = optsQ.data ?? { projects: [], competitors: [] };
  const toggle = (key: "projects" | "competitors", v: string) => {
    const cur = filters[key];
    onChange({ ...filters, [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] });
  };

  return (
    <div className="rounded-xl border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Filter className="h-3.5 w-3.5" />
        全局过滤(所有图表联动)
        {(filters.projects.length > 0 || filters.competitors.length > 0 || filters.dateFrom || filters.dateTo) && (
          <button
            onClick={() => onChange({ projects: [], competitors: [], dateFrom: null, dateTo: null })}
            className="ml-auto text-[11px] text-primary hover:underline"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <MultiSelect label="项目" options={opts.projects} selected={filters.projects} onToggle={(v) => toggle("projects", v)} />
        <MultiSelect label="友商" options={opts.competitors} selected={filters.competitors} onToggle={(v) => toggle("competitors", v)} />
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">投标日期</span>
          <div className="flex items-center gap-1">
            <input
              type="date"
              value={filters.dateFrom ?? ""}
              onChange={(e) => onChange({ ...filters, dateFrom: e.target.value || null })}
              className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px]"
            />
            <span className="text-[11px] text-muted-foreground">~</span>
            <input
              type="date"
              value={filters.dateTo ?? ""}
              onChange={(e) => onChange({ ...filters, dateTo: e.target.value || null })}
              className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 改 hooks.ts — 各罐装 hook 接 filters(走 queryFiltered)**

把 `hooks.ts:30-47` 的 `useDatasetQuery` 函数 + 4 个 `useBidSummary/useComposition/useWinRateBySegment/useProjectShowdown` 导出整体替换为:
```typescript
import { queryFiltered, sqlFor } from "./api";
import type { ChartFilter, FilterState } from "./types";

/** 过滤驱动的罐装视图查询。filters 变 → queryKey 变 → 自动重查。 */
function useFilteredQuery<T>(keyBase: string, tplKey: "summary" | "composition" | "segment" | "showdown", filters: FilterState, chart?: ChartFilter) {
  const sql = sqlFor(tplKey, filters, chart);
  return useQuery({
    queryKey: ["bqa", keyBase, sql] as const,
    queryFn: async (): Promise<T[]> => {
      const res = await queryFiltered(sql);
      return res.rows as T[];
    },
  });
}

export const useBidSummary = (f: FilterState) => useFilteredQuery<BidSummaryRow>("summary", "summary", f);
export const useComposition = (f: FilterState, chart?: ChartFilter) =>
  useFilteredQuery<CompositionRow>("composition", "composition", f, chart);
export const useWinRateBySegment = (f: FilterState) => useFilteredQuery<SegmentRow>("segment", "segment", f);
export const useProjectShowdown = (f: FilterState) => useFilteredQuery<ShowdownRow>("showdown", "showdown", f);
```
> `useBidList` 保持原样(查询页明细暂不接全局过滤,下个 task 的 showdown 下钻处理多友商)。删掉原 `useDatasetQuery`/`resolveDatasetId` 调用(不再用罐装 dataset 运行时查询);`resolveDatasetId` import 若变 unused 则从 api 调用方移除(api.ts 里保留函数定义无害)。

- [ ] **Step 4: DashboardView 挂 FilterBar + 传 filters**

`DashboardView.tsx` 顶部 import 区加:
```typescript
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import { EMPTY_FILTERS, type FilterState } from "@/extensions/bid-quote/types";
```
把 `DashboardView.tsx:47` 的 `const [tick, setTick] = useState(0);` 下一行加:
```typescript
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
```
把 4 个 hook 调用(`DashboardView.tsx:53-56`)改为传 filters:
```typescript
  const summaryQ = useBidSummary(filters);
  const segQ = useWinRateBySegment(filters);
  const compQ = useComposition(filters);
  const showdownQ = useProjectShowdown(filters);
```
在 `<div key={tick} className="cyber-scope space-y-5 p-6">` 内、`{/* KPI 行 */}` 注释前插入:
```tsx
      <FilterBar filters={filters} onChange={setFilters} />
```

- [ ] **Step 5: QueryView 挂 FilterBar + 传 filters**

`QueryView.tsx` 顶部 import 区加:
```typescript
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import { useBidSummary } from "@/extensions/bid-quote/hooks";  // 若展示总览 KPI(可选)
import { EMPTY_FILTERS, type FilterState } from "@/extensions/bid-quote/types";
```
> QueryView 用 useBidList/useComposition/useWinRateBySegment。`useComposition`/`useWinRateBySegment` 现需 filters 参数。把 `QueryView.tsx:42` 的 `const [tab, setTab] = useState<TabKey>("bidlist");` 下一行加 `const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);`;把 `const compQ = useComposition();` → `useComposition(filters)`;`const segQ = useWinRateBySegment();` → `useWinRateBySegment(filters)`。`useBidList()` 暂不接(filters 仅影响 comp/seg 视图;bidlist 明细下一步可接,本 task 先保持)。
在 `<div className="space-y-4 p-6">` 内、视图 tab 前(`<h1>数据查询</h1>` 块之后)插入 `<FilterBar filters={filters} onChange={setFilters} />`。

- [ ] **Step 6: typecheck + 浏览器验证**

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck'`
Expected: 无错误(若有 "需 N 个参数" 错误,检查所有 useBidSummary/useComposition/useWinRateBySegment/useProjectShowdown 调用点都传了 filters)。

Run: `docker compose -p eai-docker restart frontend`,然后浏览器开 `http://localhost:2026/bid-quote`,点项目/友商 chip,确认图表联动刷新。

- [ ] **Step 7: 提交**

```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/components/FilterBar.tsx frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/DashboardView.tsx frontend/src/extensions/bid-quote/components/QueryView.tsx
git commit -m "feat(bid-quote): 全局FilterBar(项目/友商/日期)+各图hook接filters" -- frontend/src/extensions/bid-quote/components/FilterBar.tsx frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/DashboardView.tsx frontend/src/extensions/bid-quote/components/QueryView.tsx
```

---

## Task 4: ChartFilterPopover + 每图高级筛选

**Files:**
- Create: `frontend/src/extensions/bid-quote/components/ChartFilterPopover.tsx`
- Modify: `frontend/src/extensions/bid-quote/components/DashboardView.tsx`(图2 货物构成接 selfAttribute)

- [ ] **Step 1: 建 ChartFilterPopover**

Create `frontend/src/extensions/bid-quote/components/ChartFilterPopover.tsx`:
```typescript
"use client";

import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import type { ChartFilter, SelfAttribute } from "@/extensions/bid-quote/types";

interface Props {
  chart: ChartFilter;
  onChange: (c: ChartFilter) => void;
  /** 启用的维度子集。 */
  enable: { selfAttribute?: boolean; goodsName?: string[] };
}

// 每图高级筛选 popover(折叠态跟随全局,展开叠加收紧)。selfAttribute 不进 SQL(前端 filter/渲染)。
export function ChartFilterPopover({ chart, onChange, enable }: Props) {
  const [open, setOpen] = useState(false);
  const setAttr = (a: SelfAttribute) => onChange({ ...chart, selfAttribute: a });
  const toggleGoods = (g: string) => {
    const cur = chart.goodsName ?? [];
    onChange({ ...chart, goodsName: cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g] });
  };
  const active = chart.selfAttribute || (chart.goodsName?.length ?? 0) > 0;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={
          "flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors " +
          (active ? "border-primary text-primary" : "border-border text-muted-foreground hover:text-foreground")
        }
      >
        <SlidersHorizontal className="h-3 w-3" />
        筛选
      </button>
      {open && (
        <div className="absolute right-0 top-7 z-20 w-48 rounded-lg border border-border bg-popover p-2 shadow-xl">
          {enable.selfAttribute && (
            <div className="mb-2">
              <div className="mb-1 text-[11px] text-muted-foreground">自产属性</div>
              {(["all", "self_dominant", "outsource_dominant"] as SelfAttribute[]).map((a) => (
                <button
                  key={a}
                  onClick={() => setAttr(a)}
                  className={
                    "mr-1 rounded px-1.5 py-0.5 text-[11px] " +
                    ((chart.selfAttribute ?? "all") === a ? "bg-primary/15 text-primary" : "text-muted-foreground")
                  }
                >
                  {a === "all" ? "全部" : a === "self_dominant" ? "自产为主" : "外购为主"}
                </button>
              ))}
            </div>
          )}
          {enable.goodsName && enable.goodsName.length > 0 && (
            <div>
              <div className="mb-1 text-[11px] text-muted-foreground">货物</div>
              <div className="flex max-h-32 flex-wrap gap-1 overflow-auto">
                {enable.goodsName.map((g) => (
                  <button
                    key={g}
                    onClick={() => toggleGoods(g)}
                    className={
                      "rounded border px-1.5 py-0.5 text-[11px] " +
                      ((chart.goodsName ?? []).includes(g)
                        ? "border-primary text-primary"
                        : "border-border text-muted-foreground")
                    }
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: DashboardView 图2 货物构成接 selfAttribute(前端行过滤)**

`DashboardView.tsx` 顶部加 import:
```typescript
import { ChartFilterPopover } from "@/extensions/bid-quote/components/ChartFilterPopover";
import type { ChartFilter } from "@/extensions/bid-quote/types";
```
在 DashboardView 函数体内 `const [filters, setFilters]` 旁加:
```typescript
  const [compChart, setCompChart] = useState<ChartFilter>({});
```
把 `const compQ = useComposition(filters);` 改为 `useComposition(filters, compChart)`。
把图2 `ChartCard` 标题行改为带 popover(meta 区放 popover):
```tsx
        <ChartCard title="货物构成对比 · 自产率(我方 vs 友商)" meta="失标根因">
```
改为(在 ChartCard 内顶部插一行 popover —— 若 ChartCard 不支持 children header,则在 ChartCard 上方加一个 flex 行):
```tsx
        <div className="xl:col-span-1">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">自产率(我方 vs 友商)</span>
            <ChartFilterPopover
              chart={compChart}
              onChange={setCompChart}
              enable={{ selfAttribute: true }}
            />
          </div>
          <ChartCard title="货物构成对比" meta="失标根因">
```
并把图2 的 `data={(compQ.data ?? []).map(...)}` 前加前端行过滤(基于 ours_self_pct):
```typescript
              data={(compQ.data ?? [])
                .filter((r) => {
                  if (!compChart.selfAttribute || compChart.selfAttribute === "all") return true;
                  const pct = Number(r.ours_self_pct ?? 0);
                  return compChart.selfAttribute === "self_dominant" ? pct >= 50 : pct < 50;
                })
                .map((r) => ({
                  goods_name: r.goods_name,
                  ours_self_pct: toNum(r.ours_self_pct),
                  competitor_self_pct: toNum(r.competitor_self_pct),
                }))}
```
> 图2 用 `goodsName` 维度可选(enable 加 goodsName 传 compQ 的 distinct 货物名),本 task 先只接 selfAttribute;货物名过滤走 Task 5(图B 复用)。注意 ChartCard 若是单 title prop 容器,包裹结构调整后确保原 `</ChartCard>` 闭合对应。

- [ ] **Step 3: typecheck + 浏览器验证**

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck'`
Run: `docker compose -p eai-docker restart frontend`,浏览器验证图2「自产为主/外购为主」切换后货物行变化。

- [ ] **Step 4: 提交**

```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/components/ChartFilterPopover.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
git commit -m "feat(bid-quote): 每图高级筛选Popover+货物构成图自产属性切换" -- frontend/src/extensions/bid-quote/components/ChartFilterPopover.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
```

---

## Task 5: 图C 项目自产率分布

**Files:**
- Modify: `frontend/src/extensions/bid-quote/hooks.ts`
- Create: `frontend/src/extensions/bid-quote/components/SelfRateDistChart.tsx`
- Modify: `frontend/src/extensions/bid-quote/components/DashboardView.tsx`

- [ ] **Step 1: hooks.ts 加 useSelfRateDist**

在 `hooks.ts` 末尾追加:
```typescript
import { sqlFor } from "./api";  // 若已 import 则不重复
import type { SelfRateRow } from "./types";

/** 图C:项目自产率分布(仅我方标)。 */
export function useSelfRateDist(filters: FilterState) {
  const sql = sqlFor("selfRate", filters);
  return useQuery({
    queryKey: ["bqa", "selfRate", sql] as const,
    queryFn: async (): Promise<SelfRateRow[]> => {
      const res = await queryFiltered(sql);
      return res.rows as SelfRateRow[];
    },
  });
}
```
> 若 `sqlFor`/`queryFiltered`/`FilterState` 已在 Task 2/3 import,不重复。

- [ ] **Step 2: 建 SelfRateDistChart**

Create `frontend/src/extensions/bid-quote/components/SelfRateDistChart.tsx`:
```typescript
"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { useSelfRateDist } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

const GRID = "rgba(100,116,139,0.22)";
const AXIS = { fontSize: 11, fill: "#94a3b8" };
const GREEN = "#10b981";
const AMBER = "#f6bd16";

// 图C:项目整标自产率分布,门槛线(默认50%)上方=自产为主标(绿),下方=外购为主(琥珀)。
export function SelfRateDistChart({ filters }: { filters: FilterState }) {
  const q = useSelfRateDist(filters);
  const [threshold, setThreshold] = useState(50);
  const data = (q.data ?? []).map((r) => ({
    project_name: r.project_name.replace(/.{6,}?[市省]/, (m) => m.slice(0, 4) + "…"),
    self_rate: Number(r.self_rate ?? 0),
  }));

  return (
    <ChartCard title="项目自产率分布" meta="门槛线可拖">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
        门槛
        <input
          type="range"
          min={0}
          max={100}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
        />
        <span className="text-primary">{threshold}%</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
          <XAxis dataKey="project_name" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} angle={-12} textAnchor="end" height={50} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="%" width={40} />
          <Tooltip content={<TechTooltip />} cursor={{ fill: "rgba(148,163,184,0.15)" }} />
          <Bar dataKey="self_rate" name="自产率" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.self_rate >= threshold ? GREEN : AMBER} />
            ))}
          </Bar>
          <Line type="monotone" dataKey={() => threshold} stroke="#f43f5e" strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false}>
            <Label position="right" value={`门槛 ${threshold}%`} fill="#f43f5e" fontSize={10} />
          </Line>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
```

- [ ] **Step 3: DashboardView 加图C 卡**

`DashboardView.tsx` import 加 `import { SelfRateDistChart } from "@/extensions/bid-quote/components/SelfRateDistChart";`
在图3 `</ChartCard>` 之后(图表 grid 内)加:
```tsx
        <SelfRateDistChart filters={filters} />
```

- [ ] **Step 4: typecheck + 浏览器验证 + 提交**

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck'`
Run: `docker compose -p eai-docker restart frontend`,浏览器看图C 自产率柱 + 门槛滑块。
```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/SelfRateDistChart.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
git commit -m "feat(bid-quote): 图C项目自产率分布(门槛线可拖)" -- frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/SelfRateDistChart.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
```

---

## Task 6: 图B 自产 vs 外购金额对比

**Files:**
- Modify: `frontend/src/extensions/bid-quote/hooks.ts`
- Create: `frontend/src/extensions/bid-quote/components/SelfVsOutsourceChart.tsx`
- Modify: `frontend/src/extensions/bid-quote/components/DashboardView.tsx`

- [ ] **Step 1: hooks.ts 加 useSelfVsOutsource**

在 `hooks.ts` 末尾追加:
```typescript
import { sqlSelfVsOutsource } from "./api";  // 若已 import 则不重复
import type { SelfVsOutsourceRow } from "@/extensions/bid-quote/types";

/** 图B:自产 vs 外购金额(项目/货物视角切换)。 */
export function useSelfVsOutsource(filters: FilterState, dim: "project" | "goods") {
  const sql = sqlSelfVsOutsource(filters, dim);
  return useQuery({
    queryKey: ["bqa", "selfVsOutsource", dim, sql] as const,
    queryFn: async (): Promise<SelfVsOutsourceRow[]> => {
      const res = await queryFiltered(sql);
      return res.rows as SelfVsOutsourceRow[];
    },
  });
}
```

- [ ] **Step 2: 建 SelfVsOutsourceChart**

Create `frontend/src/extensions/bid-quote/components/SelfVsOutsourceChart.tsx`:
```typescript
"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { useSelfVsOutsource } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

const GRID = "rgba(100,116,139,0.22)";
const AXIS = { fontSize: 11, fill: "#94a3b8" };
const BLUE = "#3b82f6";
const AMBER = "#f6bd16";

// 图B:自产 vs 外购金额并排柱,视角切换(项目/货物)。金额万元。
export function SelfVsOutsourceChart({ filters }: { filters: FilterState }) {
  const [dim, setDim] = useState<"project" | "goods">("project");
  const q = useSelfVsOutsource(filters, dim);
  const data = (q.data ?? []).map((r) => ({
    label: r.label,
    自产: Number(r.self_amount ?? 0) / 10000,
    外购: Number(r.outsourced_amount ?? 0) / 10000,
  }));

  return (
    <ChartCard title="自产 vs 外购金额(万)" meta="视角可切">
      <div className="mb-1 flex gap-1 text-[11px]">
        {(["project", "goods"] as const).map((d) => (
          <button
            key={d}
            onClick={() => setDim(d)}
            className={
              "rounded border px-2 py-0.5 " +
              (dim === d ? "border-primary text-primary" : "border-border text-muted-foreground")
            }
          >
            {d === "project" ? "按项目" : "按货物"}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} angle={-12} textAnchor="end" height={50} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <Tooltip content={<TechTooltip />} cursor={{ fill: "rgba(148,163,184,0.15)" }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="自产" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
          <Bar dataKey="外购" fill={AMBER} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
```

- [ ] **Step 3: DashboardView 加图B 卡**

import 加 `import { SelfVsOutsourceChart } from "@/extensions/bid-quote/components/SelfVsOutsourceChart";`,在图C 卡旁加 `<SelfVsOutsourceChart filters={filters} />`。

- [ ] **Step 4: typecheck + 浏览器验证 + 提交**

Run typecheck + restart frontend + 浏览器看图B 并排柱 + 视角切换。
```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/SelfVsOutsourceChart.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
git commit -m "feat(bid-quote): 图B自产vs外购金额(项目/货物视角切换)" -- frontend/src/extensions/bid-quote/hooks.ts frontend/src/extensions/bid-quote/components/SelfVsOutsourceChart.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
```

---

## Task 7: 货物级下钻增强(自产外购列高亮 + 二次筛选 + 多友商对比)

**Files:**
- Modify: `frontend/src/extensions/bid-quote/components/DrillDownModal.tsx`
- Modify: `frontend/src/extensions/bid-quote/components/QueryView.tsx`(showdown 下钻分支)

- [ ] **Step 1: DrillDownModal 加二次筛选 + 自产外购列高亮**

把 `DrillDownModal.tsx:27-87` 的 `DrillDownModal` 函数体替换为(加 `selfAttribute` 本地过滤 + self/outsourced 列高亮):
```typescript
export function DrillDownModal({ title, sql, onClose }: DrillDownModalProps) {
  const { data, isLoading, error } = useDrillDown(sql);
  const [attr, setAttr] = useState<"all" | "self_dominant" | "outsource_dominant">("all");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (sql) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sql, onClose]);

  if (!sql) return null;
  const rawRows = (data?.rows ?? []) as Record<string, unknown>[];
  // 二次筛选:仅对含 self_amount/outsourced_amount 的行(货物级下钻)生效
  const isItemRows = rawRows.length > 0 && "self_amount" in (rawRows[0] ?? {});
  const rows = isItemRows
    ? rawRows.filter((r) => {
        if (attr === "all") return true;
        const s = Number(r.self_amount ?? 0);
        const o = Number(r.outsourced_amount ?? 0);
        const pct = s + o > 0 ? (s / (s + o)) * 100 : 0;
        return attr === "self_dominant" ? pct >= 50 : pct < 50;
      })
    : rawRows;
  const cols = rows.length ? Object.keys(rows[0] ?? {}) : [];
  const isSelfCol = (c: string) => c === "self_amount";
  const isOutCol = (c: string) => c === "outsourced_amount";

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
        {isItemRows && (
          <div className="flex gap-1 border-b border-border px-5 py-2 text-[11px]">
            <span className="text-muted-foreground">货物筛选:</span>
            {(["all", "self_dominant", "outsource_dominant"] as const).map((a) => (
              <button
                key={a}
                onClick={() => setAttr(a)}
                className={
                  "rounded px-1.5 py-0.5 " +
                  (attr === a ? "bg-primary/15 text-primary" : "text-muted-foreground")
                }
              >
                {a === "all" ? "全部" : a === "self_dominant" ? "自产为主" : "外购为主"}
              </button>
            ))}
          </div>
        )}
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
                    <TableHead key={c} className={isSelfCol(c) ? "text-green-500" : isOutCol(c) ? "text-amber-500" : ""}>
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i} className={i === 0 ? "" : "cursor-default"}>
                    {cols.map((c) => (
                      <TableCell key={c} className={isSelfCol(c) ? "font-medium text-green-600" : isOutCol(c) ? "font-medium text-amber-600" : ""}>
                        {/* 中标标记:won 列 true 高亮 */}
                        {c === "won" && r[c] === true ? "✓ 中标" : cellText(r[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <div className="border-t border-border px-5 py-2 text-[11px] text-muted-foreground/70">
          共 {rows.length} 条 · {sql}
        </div>
      </div>
    </div>
  );
}
```
> `useState` 需加入 import:`import { useEffect, useState } from "react";`。`cellText` 保留原定义。

- [ ] **Step 2: QueryView showdown 下钻分支(多友商对比)**

当前 QueryView 无 showdown tab(showdown 在 DashboardView)。DashboardView 的图3 showdown 点击下钻需新增。在 `DashboardView.tsx` import 加 `import { DrillDownModal } from "@/extensions/bid-quote/components/DrillDownModal";`,函数体内加 `const [drill, setDrill] = useState<{ title: string; sql: string } | null>(null);`,在图3 `<BarChart>` 的 `<Bar dataKey="我方" ...>` 加 `onClick={(_d, idx) => { const r = showdownQ.data?.[idx ?? 0]; if (r) setDrill({ title: \`项目报价 · ${r.project_name}\`, sql: \`SELECT bidder_name, bidder_role, winning_price, won FROM mock_bid WHERE project_name='${r.project_name.replace(/'/g, "''")}' ORDER BY winning_price\` }); }}`。在 DashboardView return 末尾(`</div>` 前)加 `<DrillDownModal title={drill?.title ?? ""} sql={drill?.sql ?? null} onClose={() => setDrill(null)} />`。

- [ ] **Step 3: typecheck + 浏览器验证 + 提交**

Run typecheck + restart frontend。浏览器:DashboardView 图3 点某项目柱 → modal 显示该项目所有友商报价 + 中标标记(✓);QueryView 货物明细下钻 → self/outsourced 列高亮 + 货物筛选切换。
```bash
git diff --cached --name-only
git add frontend/src/extensions/bid-quote/components/DrillDownModal.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx frontend/src/extensions/bid-quote/components/QueryView.tsx
git commit -m "feat(bid-quote): 货物级下钻增强(自产外购高亮+二次筛选+多友商对比)" -- frontend/src/extensions/bid-quote/components/DrillDownModal.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx frontend/src/extensions/bid-quote/components/QueryView.tsx
```

---

## Task 8: 收尾验证(全量回归)

- [ ] **Step 1: 全量 seed 重跑 + 断言**

Run: `docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_market.py`
Expected: 无 AssertionError,友商家数 ≥3,每项目恰 1 中标。

- [ ] **Step 2: 前端 typecheck + 单测全量**

Run: `docker compose -p eai-docker exec -T frontend sh -c 'cd /app/frontend && pnpm typecheck && pnpm test'`
Expected: 0 type error;单测全过(含 build-where 9 条 + 既有测试不回归)。

- [ ] **Step 3: 浏览器端到端走查**

Run: `docker compose -p eai-docker restart frontend`,浏览器 `http://localhost:2026/bid-quote`(admin@eai-flow.com / Admin@2026):
- 全局 FilterBar 选项目/友商 → KPI + 4 图 + 图B/C 联动
- 图2 自产属性切换 → 货物行变化
- 图C 门槛滑块 → 柱色变化
- 图B 视角切换 → 项目/货物
- 图3 点柱 → 多友商报价 modal(中标标记)
- 查询页 tab + FilterBar + 下钻(自产外购列高亮 + 货物筛选)

- [ ] **Step 4: 更新 anatomy/memory/cerebrum(OpenWolf)**

记录 bid-quote 模块新增 FilterBar/ChartFilterPopover/SelfRateDistChart/SelfVsOutsourceChart 组件 + buildWhere/sqlFor API;memory.md 追加本次落地行。

- [ ] **Step 5: 最终提交(若有散落改动)**

```bash
git diff --cached --name-only && git status
# 仅提交本任务相关文件,绝不裸 git commit
```

---

## Self-Review(写计划后)

**Spec coverage:** §1 多家友商(Task1)✓ §2 四SQL复核(Task1 Step4)✓ §3 过滤架构(Task2 buildWhere + Task3 FilterBar + Task4 Popover)✓ §4 技术路线(全 querySql)✓ §5 三维度(Task4 图A + Task6 图B + Task5 图C)✓ §6 下钻(Task7)✓ §9 组件结构(全文件)✓ §10 测试(Task2 单测 + Task8 回归)✓ §12 落地顺序(8 task 对应)✓

**Placeholder scan:** 无 TBD/TODO;所有代码块完整。Task4 Step2 的 ChartCard 包裹结构标注了"若 ChartCard 不支持 children header"的适配说明——实现者需读 ChartCard 确认其 props(单 title 还是 children),这是必要的运行时确认点而非 placeholder。

**Type consistency:** `FilterState`/`ChartFilter`/`SelfRateRow`/`SelfVsOutsourceRow`/`FilterOptions` 定义(Task2)与使用(Task3-7)一致;`buildWhere(g, chart?, useCompetitorExists?)` 签名与 `sqlFor` 内部调用一致;hook 名 useSelfRateDist/useSelfVsOutsource 与组件引用一致。

**已知实现注意点(非 placeholder,实现时确认):**
1. `ChartCard` 组件 props 结构(Task4 Step2)—— 实现时读 `components/ChartCard.tsx` 确认是 `title+meta+children` 还是仅 title 容器,据此调整 popover 挂载位置。
2. hooks.ts 多次追加 import(Task2/3/5/6 都加 import)—— 合并到文件顶部一次,避免重复 import 报错。
3. recharts `Line` 用 `dataKey={() => threshold}` 画水平门槛线 —— 若 recharts ^3 不支持函数 dataKey,改用 `<ReferenceLine y={threshold}>`(需 import `ReferenceLine`)。实现时验证。
