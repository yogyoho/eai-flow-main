/**
 * 管线查询(biz-pipeline)类型 —— 对齐 data_source 罐装 dataset 列。
 * Decimal/numeric 经 JSON 序列化为 string。
 */

export interface FunnelRow {
  bid_count: number;
  won_count: number;
  contract_count: number;
  bid_amount_total: string;
  won_amount_total: string;
  contract_total: string;
  invoiced_total: string;
  uninvoiced_total: string;
}

export interface MonthlyRow {
  ym: string;
  bids: number;
  won: number;
}

export interface ReconRow {
  contract_no: string;
  contract_name: string;
  customer: string;
  amount: string;
  invoiced: string;
  uninvoiced: string;
}

/** mock_pipeline_bid 明细行:列动态,用索引签名。 */
export type BidRow = Record<string, string | number | boolean | null>;

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  row_count: number;
  label?: string | null;
}
