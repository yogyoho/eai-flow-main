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
  competitor_count: number;
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
