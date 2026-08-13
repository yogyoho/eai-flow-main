/**
 * bid-quote TanStack Query hooks。queryKey 统一 ["bqa", ...] 命名空间。
 * 罐装视图:resolve source/dataset id(缓存)→ queryDataset;
 * 明细/下钻:raw SQL → querySql(后端 assert_readonly_select 守卫)。
 *
 * 铁律:dataset label 必须与 seed_mock_market.py 一字不差。
 */

import { useQuery } from "@tanstack/react-query";

import { queryDataset, querySql, resolveDatasetId, resolveSourceId } from "./api";
import type {
  BidItemRow,
  BidSummaryRow,
  CompositionRow,
  QueryResult,
  SegmentRow,
  ShowdownRow,
} from "./types";

export const KEYS = {
  summary: ["bqa", "summary"] as const,
  composition: ["bqa", "composition"] as const,
  segment: ["bqa", "segment"] as const,
  showdown: ["bqa", "showdown"] as const,
  bidlist: ["bqa", "bidlist"] as const,
  drilldown: (sql: string) => ["bqa", "drilldown", sql] as const,
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

export const useBidSummary = () => useDatasetQuery<BidSummaryRow>(KEYS.summary, "投标总览");
export const useComposition = () =>
  useDatasetQuery<CompositionRow>(KEYS.composition, "货物构成对比(我方vs友商)");
export const useWinRateBySegment = () => useDatasetQuery<SegmentRow>(KEYS.segment, "按金额段我方中标率");
export const useProjectShowdown = () => useDatasetQuery<ShowdownRow>(KEYS.showdown, "项目报价对比(我方vs友商)");

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
