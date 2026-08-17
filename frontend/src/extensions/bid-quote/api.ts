/**
 * bid-quote API client —— Route B 薄前端直调 data_source REST。
 * base=/api/extensions(authFetch 默认),data-sources 路由前缀 /data-sources。
 */

import { authFetch } from "@/extensions/api/client";

import type { ChartFilter, FilterState, QueryResult } from "./types";

const API_BASE = "/data-sources";
const SOURCE_NAME = "bid-quote";

// ponytail: 模块级缓存 source/dataset id(resolve 一次后复用),刷新时 clearBidQuoteCache 清掉
let sourceIdCache: string | null = null;
const datasetIdCache: Record<string, string> = {};

interface ListItem {
  id: string;
  name?: string;
  label?: string;
}

/** 列出数据源,按 name 匹配拿 id(模块固定 'bid-quote'),结果缓存。 */
export async function resolveSourceId(name = SOURCE_NAME): Promise<string> {
  if (sourceIdCache) return sourceIdCache;
  const resp = await authFetch<{ items: ListItem[] }>(API_BASE);
  const hit = resp.items.find((s) => s.name === name);
  if (!hit) throw new Error(`数据源 "${name}" 未找到`);
  sourceIdCache = hit.id;
  return sourceIdCache;
}

/** 按 label 匹配拿 dataset id(罐装视图),结果缓存。 */
export async function resolveDatasetId(
  sourceId: string,
  label: string,
): Promise<string> {
  if (datasetIdCache[label]) return datasetIdCache[label];
  const resp = await authFetch<{ items: ListItem[] }>(
    `${API_BASE}/${sourceId}/datasets`,
  );
  const hit = resp.items.find((d) => d.label === label);
  if (!hit) throw new Error(`数据集 "${label}" 未找到`);
  datasetIdCache[label] = hit.id;
  return datasetIdCache[label];
}

/** 跑罐装 dataset 的 default_query(POST,无 body)。 */
export async function queryDataset(
  sourceId: string,
  datasetId: string,
): Promise<QueryResult> {
  return authFetch<QueryResult>(
    `${API_BASE}/${sourceId}/datasets/${datasetId}/query`,
    {
      method: "POST",
    },
  );
}

/** 跑下钻参数化只读 SQL(POST body {sql})。 */
export async function querySql(
  sourceId: string,
  sql: string,
): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

/** 清缓存(刷新按钮用)。 */
export function clearBidQuoteCache() {
  sourceIdCache = null;
  for (const k of Object.keys(datasetIdCache)) delete datasetIdCache[k];
}

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
 * selfAttribute 不在此处理:货物构成图前端 filter / 自产率图渲染层。
 * 友商过滤为行级语义(2026-08-17 从 EXISTS 项目集语义改):保留我方行 + 选中友商行,
 * 所有"我方 vs 友商"聚合(中标率/自产率/溢价曲线友商最低价/报价对比友商柱)只统计选中友商;
 * 裸 bidder_name IN 不带 OR ours 会把"仅我方"查询清成空集,故必须带上。
 * outerProjectRef = 外层查询的项目列引用,随模板外层表别名变化:
 *   未别名 mock_bid → "mock_bid.project_name";JOIN 别名 b → "b.project_name"。
 */
export function buildWhere(
  g: FilterState,
  outerProjectRef: string,
  chart?: ChartFilter,
): string {
  const c: string[] = ["1=1"];
  // IN 列表先排序:SQL 进 queryKey,选择顺序不同会碎片化缓存;排序后同集合 = 同 key
  const sorted = (xs: string[]) =>
    [...xs].sort((a, b) => a.localeCompare(b, "zh-Hans-u-co-pinyin"));
  if (g.projects.length) {
    c.push(
      `project_name IN (${sorted(g.projects)
        .map((p) => `'${esc(p)}'`)
        .join(",")})`,
    );
  }
  if (g.competitors.length) {
    const list = sorted(g.competitors)
      .map((x) => `'${esc(x)}'`)
      .join(",");
    // 行级:我方行恒保留 + 友商仅统计选中几家(列引用前缀随外层表别名)
    const pfx = outerProjectRef.slice(0, -"project_name".length);
    c.push(`(${pfx}bidder_name IN (${list}) OR ${pfx}bidder_role='ours')`);
  }
  if (g.dateFrom) c.push(`bid_date >= '${esc(g.dateFrom)}'`);
  if (g.dateTo) c.push(`bid_date <= '${esc(g.dateTo)}'`);
  if (chart?.amountSegment) {
    const seg = SEG_WHERE[chart.amountSegment];
    if (seg) c.push(seg); // noUncheckedIndexedAccess:索引可能 undefined,判空后再 push
  }
  if (chart?.goodsName?.length) {
    // 与 projects/competitors 同理:IN 列表排序,queryKey 对选择顺序不敏感
    c.push(
      `goods_name IN (${sorted(chart.goodsName)
        .map((n) => `'${esc(n)}'`)
        .join(",")})`,
    );
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
  key: keyof Pick<
    typeof TPL,
    "summary" | "composition" | "segment" | "showdown" | "selfRate"
  >,
  g: FilterState,
  chart?: ChartFilter,
): string {
  const tail: Record<string, string> = {
    summary: "",
    composition: " GROUP BY i.goods_name ORDER BY i.goods_name",
    segment: " GROUP BY 1 ORDER BY 1",
    showdown: " GROUP BY project_name ORDER BY MIN(bid_id)",
  };
  // EXISTS 外层关联列随模板外层表别名:未别名 mock_bid vs JOIN 别名 b(传错=恒真/不可解析)
  const OUTER_REF = {
    summary: "mock_bid.project_name",
    composition: "b.project_name",
    segment: "mock_bid.project_name",
    showdown: "mock_bid.project_name",
    selfRate: "b.project_name",
  } as const;
  const where = buildWhere(g, OUTER_REF[key], chart);
  const base = TPL[key];
  // EAI-CUSTOM(bid-quote 过滤): selfRate 仅我方标 —— base 无 WHERE 子句,
  // 直接内联拼 `WHERE bidder_role='ours' AND <过滤>` 再补 GROUP BY/ORDER 尾部
  // (spec-review 修正:原 replace 写法对 base 是 no-op,会丢掉全部过滤和 GROUP BY)。
  if (key === "selfRate") {
    return `${base} WHERE b.bidder_role='ours' AND ${where} GROUP BY b.project_name ORDER BY self_rate DESC`;
  }
  if (key === "summary") return `${base} WHERE ${where}`;
  // EAI-CUSTOM(bid-quote 过滤): 修正计划自带的 bug —— segment 模板本身已含
  // `WHERE bidder_role='ours'`,若走 `${base} WHERE ${where}` 会拼出两个 WHERE 子句
  // 导致 SQL 语法错误;应把 buildWhere 结果用 AND 接在已有 WHERE 之后。
  if (key === "segment") return `${base} AND ${where}${tail[key]}`;
  // composition/showdown 尾部 GROUP BY;WHERE 插在 GROUP 前
  const t = tail[key];
  return `${base} WHERE ${where}${t}`;
}

/** 图B 自产vs外购(项目/货物视角)。 */
export function sqlSelfVsOutsource(
  g: FilterState,
  dim: "project" | "goods",
  chart?: ChartFilter,
): string {
  const where = buildWhere(g, "b.project_name", chart);
  const grp = dim === "project" ? "b.project_name" : "i.goods_name";
  return `${TPL.selfVsOutsource(dim)} WHERE ${where} GROUP BY ${grp} ORDER BY ${grp}`;
}

// ── 2026-08-15 仪表盘三问框架新模板(三区块原型落地)──
// 统一约定:过滤先压进单表 CTE base(别名内列不带歧义),再在 CTE 之上做 join/聚合,
// EXISTS 友商过滤的 outerProjectRef 始终是 base 的 FROM 表列(未别名 mock_bid)。

/** 图3 中标率时间趋势:按季度 我方/友商 双列。 */
export function sqlTrend(g: FilterState): string {
  return `WITH base AS (SELECT bidder_role, won, bid_date FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")}),
q AS (SELECT date_trunc('quarter', bid_date) AS qtr, bidder_role, won FROM base)
SELECT to_char(qtr, 'YY"Q"Q') AS qtr, -- timestamptz 序列化为 UTC 串,前端 new Date 再取 UTC 会整体错一季,直接在 SQL 出标签
  ROUND(100.0 * COUNT(*) FILTER (WHERE bidder_role='ours' AND won) / NULLIF(COUNT(*) FILTER (WHERE bidder_role='ours'), 0), 1) AS ours_rate,
  ROUND(100.0 * COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) / NULLIF(COUNT(*) FILTER (WHERE bidder_role='competitor'), 0), 1) AS comp_rate
FROM q GROUP BY qtr ORDER BY qtr`;
}

/** 图7 胜率-溢价曲线:我方报价相对同项目【友商最低价】的溢价率固定 6 桶(PG 无数组版 width_bucket,CASE 等价)。
 *  注意口径:不能相对"中标价"算——我方胜出时我方报价=中标价,溢价恒 0,胜场全塌进 0~+3% 桶,曲线退化。
 *  相对友商最低价:胜场可分布在负桶(压价幅度不同),正桶也可能胜(靠评分赢),曲线才有形状。 */
export function sqlPremiumCurve(g: FilterState): string {
  return `WITH base AS (SELECT bid_id, project_name, bidder_role, won, winning_price FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")}),
cmin AS (SELECT project_name, MIN(winning_price) AS cmin_price FROM base WHERE bidder_role='competitor' GROUP BY 1),
ours AS (
  SELECT b.won, (b.winning_price - c.cmin_price) / c.cmin_price AS prem
  FROM base b JOIN cmin c ON c.project_name = b.project_name
  WHERE b.bidder_role='ours'
),
t AS (SELECT won, CASE WHEN prem <= -0.05 THEN 0 WHEN prem < 0 THEN 1 WHEN prem < 0.03 THEN 2 WHEN prem < 0.06 THEN 3 WHEN prem < 0.10 THEN 4 ELSE 5 END AS bucket FROM ours)
SELECT bucket, COUNT(*) AS n,
  ROUND(100.0 * COUNT(*) FILTER (WHERE won) / NULLIF(COUNT(*), 0), 1) AS win_rate
FROM t GROUP BY bucket ORDER BY bucket`;
}

/** 图8 报价区间建议:按金额段 中标价 P25/P50/P75 + 该段我方行 items 成本底线(Σself+Σoutsourced)。 */
export function sqlPriceBand(g: FilterState): string {
  return `WITH base AS (SELECT bid_id, project_name, bidder_role, won, winning_price FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")}),
wp AS (SELECT project_name,
    MAX(winning_price) FILTER (WHERE won) AS win_price,
    CASE WHEN MAX(winning_price) FILTER (WHERE won) < 1000000 THEN '1_<100万'
         WHEN MAX(winning_price) FILTER (WHERE won) < 5000000 THEN '2_100-500万'
         WHEN MAX(winning_price) FILTER (WHERE won) < 20000000 THEN '3_500-2000万'
         ELSE '4_≥2000万' END AS seg
  FROM base GROUP BY project_name HAVING BOOL_OR(won)),
pc AS (SELECT b.project_name, SUM(i.self_amount + i.outsourced_amount) AS cost
  FROM base b JOIN mock_bid_item i ON i.bid_id = b.bid_id
  WHERE b.bidder_role='ours' GROUP BY 1),
cost AS (SELECT wp.seg, AVG(pc.cost) AS cost_floor
  FROM wp JOIN pc ON pc.project_name = wp.project_name GROUP BY wp.seg)
SELECT wp.seg,
  percentile_cont(0.25) WITHIN GROUP (ORDER BY wp.win_price) AS p25,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY wp.win_price) AS p50,
  percentile_cont(0.75) WITHIN GROUP (ORDER BY wp.win_price) AS p75,
  MAX(c.cost_floor) AS cost_floor
FROM wp LEFT JOIN cost c ON c.seg = wp.seg
GROUP BY wp.seg ORDER BY wp.seg`;
}

/** 图10 友商画像:按 bidder_name 中标率/平均溢价(相对同项目中标价)/同期项目数。 */
export function sqlCompetitorProfile(g: FilterState): string {
  return `WITH base AS (SELECT * FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")}),
w AS (SELECT project_name, winning_price AS win_price FROM base WHERE won)
SELECT b.bidder_name,
  COUNT(*) AS bids,
  COUNT(*) FILTER (WHERE b.won) AS wins,
  ROUND(100.0 * COUNT(*) FILTER (WHERE b.won) / NULLIF(COUNT(*), 0), 1) AS win_rate,
  ROUND(100.0 * AVG((b.winning_price - w.win_price) / w.win_price), 1) AS avg_premium_pct,
  COUNT(DISTINCT b.project_name) AS projects
FROM base b JOIN w ON w.project_name = b.project_name
WHERE b.bidder_role='competitor'
GROUP BY b.bidder_name ORDER BY wins DESC, b.bidder_name`;
}

/** 图10 优势领域 chips:友商中标行的货物金额(前端按友商取 Top2)。 */
export function sqlCompetitorGoods(g: FilterState): string {
  return `SELECT b.bidder_name, i.goods_name, SUM(i.self_amount + i.outsourced_amount) AS amt
FROM mock_bid b JOIN mock_bid_item i ON i.bid_id = b.bid_id
WHERE b.bidder_role='competitor' AND b.won AND ${buildWhere(g, "b.project_name")}
GROUP BY b.bidder_name, i.goods_name`;
}

/** 图11 遭遇战:选定友商与我方同场(同项目)对局,分年度胜负计数。 */
export function sqlHead2Head(g: FilterState, competitor: string): string {
  const c = esc(competitor);
  return `WITH base AS (SELECT * FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")}),
both_in AS (SELECT project_name FROM base
  WHERE (bidder_role='ours' OR bidder_name='${c}')
  GROUP BY project_name
  HAVING BOOL_OR(bidder_role='ours') AND BOOL_OR(bidder_name='${c}')),
pair AS (SELECT b.project_name,
    BOOL_OR(b.bidder_role='ours' AND b.won) AS ours_won,
    BOOL_OR(b.bidder_name='${c}' AND b.won) AS comp_won
  FROM base b JOIN both_in ON both_in.project_name = b.project_name
  WHERE b.bidder_role='ours' OR b.bidder_name='${c}'
  GROUP BY b.project_name),
d AS (SELECT project_name, MIN(bid_date) AS bid_date FROM base GROUP BY project_name)
SELECT EXTRACT(YEAR FROM d.bid_date)::INT AS yr,
  COUNT(*) FILTER (WHERE p.ours_won) AS ours_wins,
  COUNT(*) FILTER (WHERE p.comp_won) AS comp_wins
FROM pair p JOIN d ON d.project_name = p.project_name
GROUP BY 1 ORDER BY 1`;
}

/** 图12 中标份额格局:按年各 bidder 中标金额(前端折叠 前5+其他)。 */
export function sqlShareStack(g: FilterState): string {
  return `WITH base AS (SELECT bidder_name, won, winning_price, bid_date FROM mock_bid WHERE won AND ${buildWhere(g, "mock_bid.project_name")})
SELECT EXTRACT(YEAR FROM bid_date)::INT AS yr, bidder_name, SUM(winning_price) AS amt
FROM base GROUP BY 1, 2 ORDER BY 1, 3 DESC`;
}

/** KPI 同比:分年度 我方/友商 投与中(最新年 vs 上一年算 delta 注脚)。 */
export function sqlKpiByYear(g: FilterState): string {
  return `SELECT EXTRACT(YEAR FROM bid_date)::INT AS yr,
  COUNT(*) FILTER (WHERE bidder_role='ours') AS ours_bid,
  COUNT(*) FILTER (WHERE bidder_role='ours' AND won) AS ours_won,
  COUNT(*) FILTER (WHERE bidder_role='competitor') AS comp_bid,
  COUNT(*) FILTER (WHERE bidder_role='competitor' AND won) AS comp_won
FROM mock_bid WHERE ${buildWhere(g, "mock_bid.project_name")} GROUP BY 1 ORDER BY 1`;
}

/** 跑过滤后的 SQL → querySql。 */
export async function queryFiltered(sql: string): Promise<QueryResult> {
  const sid = await resolveSourceId();
  return querySql(sid, sql);
}

/** distinct 过滤选项(项目 + 友商 + 货物,货物供图B/货物构成每图筛选)。 */
export async function fetchFilterOptions(): Promise<{
  projects: string[];
  competitors: string[];
  goods: string[];
}> {
  const sid = await resolveSourceId();
  const [pr, cr, gd] = await Promise.all([
    querySql(
      sid,
      "SELECT DISTINCT project_name AS v FROM mock_bid ORDER BY project_name",
    ),
    querySql(
      sid,
      "SELECT DISTINCT bidder_name AS v FROM mock_bid WHERE bidder_role='competitor' ORDER BY bidder_name",
    ),
    querySql(
      sid,
      "SELECT DISTINCT goods_name AS v FROM mock_bid_item ORDER BY goods_name",
    ),
  ]);
  return {
    projects: (pr.rows as { v: string }[]).map((r) => r.v),
    competitors: (cr.rows as { v: string }[]).map((r) => r.v),
    goods: (gd.rows as { v: string }[]).map((r) => r.v),
  };
}
