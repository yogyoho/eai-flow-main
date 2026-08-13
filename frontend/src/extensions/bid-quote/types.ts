/**
 * 投标报价分析(bid-quote)类型 —— 对齐 data_source 罐装 dataset 列。
 * Decimal/numeric 经 JSON 序列化为 string;bool 为 boolean|null;date 为 ISO string。
 */

export interface BidSummaryRow {
  project_count: number;
  bid_count: number;
  ours_bid: number;
  ours_won: number;
  ours_win_rate_pct: string | null;
  competitor_bid: number;
  competitor_won: number;
  avg_winning_price: string | null;
  earliest_bid: string | null;
  latest_bid: string | null;
}

export interface CompositionRow {
  goods_name: string;
  ours_self_pct: string | null;
  ours_outsourced_pct: string | null;
  ours_avg_unit_price: string | null;
  competitor_self_pct: string | null;
  competitor_outsourced_pct: string | null;
  competitor_avg_unit_price: string | null;
}

export interface SegmentRow {
  amount_segment: string;
  ours_bid: number;
  ours_won: number;
  ours_win_rate_pct: string | null;
}

export interface ShowdownRow {
  project_name: string;
  our_price: string | null;
  competitor_price: string | null;
  we_won: boolean | null;
  // EAI-CUSTOM: 对齐 T2 适配后的真实 schema —— mock_bid 无 customer 列,取 project_location 作上下文
  project_location: string | null;
}

/** mock_bid / mock_bid_item 明细行:列动态,用索引签名。 */
export type BidItemRow = Record<string, string | number | boolean | null>;

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  row_count: number;
  label?: string | null;
}
