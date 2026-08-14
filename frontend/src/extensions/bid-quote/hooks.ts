/**
 * bid-quote TanStack Query hooks。queryKey 统一 ["bqa", ...] 命名空间。
 * 罐装视图:sqlFor(key, filters, chart) 拼 SQL → queryFiltered(后端 assert_readonly_select 守卫);
 * 明细/下钻:raw SQL → querySql。
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchFilterOptions, queryFiltered, querySql, resolveSourceId, sqlFor } from "./api";
import type {
  BidItemRow,
  BidSummaryRow,
  ChartFilter,
  CompositionRow,
  FilterOptions,
  FilterState,
  QueryResult,
  SegmentRow,
  ShowdownRow,
} from "./types";

export const KEYS = {
  filterOptions: ["bqa", "filterOptions"] as const,
  bidlist: ["bqa", "bidlist"] as const,
  drilldown: (sql: string) => ["bqa", "drilldown", sql] as const,
};

/** 过滤驱动的罐装视图查询。filters/chart 变 → SQL 变 → queryKey 变 → 自动重查。 */
function useFilteredQuery<T>(
  keyBase: string,
  tplKey: "summary" | "composition" | "segment" | "showdown",
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

export const useBidSummary = (f: FilterState) => useFilteredQuery<BidSummaryRow>("summary", "summary", f);
export const useComposition = (f: FilterState, chart?: ChartFilter) =>
  useFilteredQuery<CompositionRow>("composition", "composition", f, chart);
export const useWinRateBySegment = (f: FilterState) => useFilteredQuery<SegmentRow>("segment", "segment", f);
export const useProjectShowdown = (f: FilterState) => useFilteredQuery<ShowdownRow>("showdown", "showdown", f);

/** 明细:全量 mock_bid,下钻来源。 */
export function useBidList(enabled = true) {
  return useQuery({
    queryKey: KEYS.bidlist,
    enabled,
    queryFn: async (): Promise<BidItemRow[]> => {
      const sid = await resolveSourceId();
      const res = await querySql(sid, "SELECT * FROM mock_bid ORDER BY bid_date DESC");
      return res.rows as BidItemRow[];
    },
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
