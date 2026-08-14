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
  sqlFor,
  sqlSelfVsOutsource,
} from "./api";
import type {
  BidItemRow,
  BidSummaryRow,
  ChartFilter,
  CompositionRow,
  FilterOptions,
  FilterState,
  QueryResult,
  SegmentRow,
  SelfRateRow,
  SelfVsOutsourceRow,
  ShowdownRow,
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
