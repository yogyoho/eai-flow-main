/**
 * biz-pipeline TanStack Query hooks。queryKey 统一 ["bpp", ...] 命名空间。
 * 罐装视图:resolve source/dataset id(缓存)→ queryDataset;
 * 明细/下钻:raw SQL → querySql(后端 assert_readonly_select 守卫)。
 *
 * 铁律:dataset label 必须与 seed_mock_pipeline.py 一字不差。
 */

import { useQuery } from "@tanstack/react-query";

import { queryDataset, querySql, resolveDatasetId, resolveSourceId } from "./api";
import type { BidRow, FunnelRow, MonthlyRow, QueryResult, ReconRow } from "./types";

export const KEYS = {
  funnel: ["bpp", "funnel"] as const,
  monthly: ["bpp", "monthly"] as const,
  recon: ["bpp", "recon"] as const,
  bidlist: ["bpp", "bidlist"] as const,
  drilldown: (sql: string) => ["bpp", "drilldown", sql] as const,
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

export const usePipelineFunnel = () => useDatasetQuery<FunnelRow>(KEYS.funnel, "管线漏斗总览");
export const useMonthlyBids = () => useDatasetQuery<MonthlyRow>(KEYS.monthly, "月度投标节奏");
export const useContractRecon = () => useDatasetQuery<ReconRow>(KEYS.recon, "合同开票对账");

/** 明细:全量 mock_pipeline_bid,下钻来源。 */
export function useBidList(enabled = true) {
  return useQuery({
    queryKey: KEYS.bidlist,
    enabled,
    queryFn: async (): Promise<BidRow[]> => {
      const sid = await resolveSourceId();
      const res = await querySql(sid, "SELECT * FROM mock_pipeline_bid ORDER BY bid_date DESC");
      return res.rows as BidRow[];
    },
  });
}

/** 下钻:参数化只读 SQL(由查询页点击触发,sql=null 时不发)。 */
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
