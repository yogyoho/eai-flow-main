/**
 * bid-quote TanStack Query hooks。queryKey 统一 ["bqa", ...] 命名空间。
 * 罐装视图:sqlFor(key, filters, chart) 拼 SQL → queryFiltered(后端 assert_readonly_select 守卫);
 * 明细/下钻:raw SQL → querySql。
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  buildWhere,
  fetchFilterOptions,
  queryFiltered,
  querySql,
  resolveSourceId,
  sqlCompetitorGoods,
  sqlCompetitorProfile,
  sqlFor,
  sqlHead2Head,
  sqlKpiByYear,
  sqlPremiumCurve,
  sqlPriceBand,
  sqlSelfVsOutsource,
  sqlShareStack,
  sqlTrend,
} from "./api";
import type {
  BidItemRow,
  BidSummaryRow,
  ChartFilter,
  CompetitorGoodsRow,
  CompetitorProfileRow,
  CompositionRow,
  FilterOptions,
  FilterState,
  Head2HeadRow,
  KpiByYearRow,
  PremiumCurveRow,
  PriceBandRow,
  QueryResult,
  SegmentRow,
  SelfRateRow,
  SelfVsOutsourceRow,
  ShareStackRow,
  ShowdownRow,
  TrendRow,
} from "./types";

export const KEYS = {
  filterOptions: ["bqa", "filterOptions"] as const,
  drilldown: (sql: string) => ["bqa", "drilldown", sql] as const,
};

/** 过滤驱动的罐装视图查询。filters/chart 变 → SQL 变 → queryKey 变 → 自动重查。 */
function useFilteredQuery<T>(
  keyBase: string,
  tplKey: "summary" | "composition" | "segment" | "showdown" | "selfRate",
  filters: FilterState,
  chart?: ChartFilter,
) {
  const sql = sqlFor(tplKey, filters, chart);
  return useQuery({
    queryKey: ["bqa", keyBase, sql] as const,
    queryFn: async (): Promise<T[]> => {
      const res = await queryFiltered(sql);
      return res.rows as T[];
    },
    // 切过滤时保留旧数据,避免图表闪空
    placeholderData: keepPreviousData,
  });
}

export const useBidSummary = (f: FilterState) =>
  useFilteredQuery<BidSummaryRow>("summary", "summary", f);
export const useComposition = (f: FilterState, chart?: ChartFilter) =>
  useFilteredQuery<CompositionRow>("composition", "composition", f, chart);
export const useWinRateBySegment = (f: FilterState) =>
  useFilteredQuery<SegmentRow>("segment", "segment", f);
export const useProjectShowdown = (f: FilterState) =>
  useFilteredQuery<ShowdownRow>("showdown", "showdown", f);
export const useSelfRateDist = (f: FilterState) =>
  useFilteredQuery<SelfRateRow>("selfRate", "selfRate", f);

/** 图B:自产 vs 外购金额(项目/货物视角切换 + 每图货物筛选)。模板是 dim 参数化函数,不走 useFilteredQuery。 */
export function useSelfVsOutsource(
  filters: FilterState,
  dim: "project" | "goods",
  chart?: ChartFilter,
) {
  const sql = sqlSelfVsOutsource(filters, dim, chart);
  return useQuery({
    queryKey: ["bqa", "selfVsOutsource", dim, sql] as const,
    queryFn: async (): Promise<SelfVsOutsourceRow[]> => {
      const res = await queryFiltered(sql);
      // QueryResult.rows 默认 Record<string, unknown>[],闭接口无隐式索引签名,须经 unknown 中转
      return res.rows as unknown as SelfVsOutsourceRow[];
    },
    // 切视角/过滤时保留旧数据,避免图表闪空
    placeholderData: keepPreviousData,
  });
}

/** 明细:mock_bid 走全局过滤(与图表联动),下钻来源。SQL 进 queryKey。 */
// ── 2026-08-15 三问框架新图 hooks(裸 SQL 进 queryKey,与罐装视图同法)──

/** 通用:拼好的 SQL 直接查(SQL 已含全局过滤,进 queryKey 自动重查)。 */
function useSqlQuery<T>(keyBase: string, sql: string) {
  return useQuery({
    queryKey: ["bqa", keyBase, sql] as const,
    queryFn: async (): Promise<T[]> => {
      const res = await queryFiltered(sql);
      // QueryResult.rows 默认 Record<string, unknown>[],闭接口无隐式索引签名,须经 unknown 中转
      return res.rows as unknown as T[];
    },
    placeholderData: keepPreviousData,
  });
}

/** 图3 中标率时间趋势(我方 vs 友商,按季度)。 */
export const useTrend = (f: FilterState) =>
  useSqlQuery<TrendRow>("trend", sqlTrend(f));
/** 图7 胜率-溢价曲线(固定 6 桶)。 */
export const usePremiumCurve = (f: FilterState) =>
  useSqlQuery<PremiumCurveRow>("premiumCurve", sqlPremiumCurve(f));
/** 图8 报价区间建议(P25–P75 + 成本底线)。 */
export const usePriceBand = (f: FilterState) =>
  useSqlQuery<PriceBandRow>("priceBand", sqlPriceBand(f));
/** 图10 友商画像。 */
export const useCompetitorProfile = (f: FilterState) =>
  useSqlQuery<CompetitorProfileRow>(
    "competitorProfile",
    sqlCompetitorProfile(f),
  );
/** 图10 优势领域聚合(按友商取 Top2 在前端做)。 */
export const useCompetitorGoods = (f: FilterState) =>
  useSqlQuery<CompetitorGoodsRow>("competitorGoods", sqlCompetitorGoods(f));
/** 图11 遭遇战(选定友商;competitor=null 时不发请求)。 */
export function useHead2Head(f: FilterState, competitor: string | null) {
  const sql = competitor ? sqlHead2Head(f, competitor) : null;
  return useQuery({
    queryKey: ["bqa", "head2head", sql ?? ""] as const,
    enabled: !!sql,
    queryFn: async (): Promise<Head2HeadRow[]> => {
      const res = await queryFiltered(sql!); // enabled: !!sql 保证非空
      return res.rows as unknown as Head2HeadRow[];
    },
    placeholderData: keepPreviousData,
  });
}
/** 图12 中标份额格局(按年,前端折叠前5+其他)。 */
export const useShareStack = (f: FilterState) =>
  useSqlQuery<ShareStackRow>("shareStack", sqlShareStack(f));
/** KPI 同比(分年度)。 */
export const useKpiByYear = (f: FilterState) =>
  useSqlQuery<KpiByYearRow>("kpiByYear", sqlKpiByYear(f));

export function useBidList(filters: FilterState, enabled = true) {
  const sql = `SELECT * FROM mock_bid WHERE ${buildWhere(filters, "mock_bid.project_name")} ORDER BY bid_date DESC`;
  return useQuery({
    queryKey: ["bqa", "bidlist", sql] as const,
    enabled,
    queryFn: async (): Promise<BidItemRow[]> => {
      const res = await queryFiltered(sql);
      return res.rows as BidItemRow[];
    },
    // 切过滤时保留旧数据,避免表格闪空(与其他罐装视图一致)
    placeholderData: keepPreviousData,
  });
}

/** 下钻:参数化只读 SQL(由查询页/图表点击触发,sql=null 时不发)。 */
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

/** distinct 过滤选项(项目 + 友商),供 FilterBar 下拉。 */
export function useFilterOptions() {
  return useQuery({
    queryKey: KEYS.filterOptions,
    queryFn: async (): Promise<FilterOptions> => fetchFilterOptions(),
  });
}
