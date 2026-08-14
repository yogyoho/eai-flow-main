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
 * 友商过滤对"仅我方"的查询:调用方传 useCompetitorExists=true → 追加 EXISTS 子查询。
 */
export function buildWhere(
  g: FilterState,
  chart?: ChartFilter,
  useCompetitorExists = false,
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
  const where = buildWhere(g, chart, key === "segment");
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
export async function fetchFilterOptions(): Promise<{
  projects: string[];
  competitors: string[];
}> {
  const sid = await resolveSourceId();
  const [pr, cr] = await Promise.all([
    querySql(
      sid,
      "SELECT DISTINCT project_name AS v FROM mock_bid ORDER BY project_name",
    ),
    querySql(
      sid,
      "SELECT DISTINCT bidder_name AS v FROM mock_bid WHERE bidder_role='competitor' ORDER BY bidder_name",
    ),
  ]);
  return {
    projects: (pr.rows as { v: string }[]).map((r) => r.v),
    competitors: (cr.rows as { v: string }[]).map((r) => r.v),
  };
}
