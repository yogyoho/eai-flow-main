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
  // 项目首次投标日期(SQL MIN(bid_date),行序即时间序);Brush 时间窗文本用
  bid_dt: string | null;
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
export const EMPTY_FILTERS: FilterState = {
  projects: [],
  competitors: [],
  dateFrom: null,
  dateTo: null,
};

/** 每图高级筛选(按图适用维度启用子集)。 */
export type AmountSegment = "lt100w" | "100to500w" | "500to2000w" | "gt2000w";
export type SelfAttribute = "self_dominant" | "outsource_dominant" | "all";
export interface ChartFilter {
  amountSegment?: AmountSegment;
  selfAttribute?: SelfAttribute; // 不进 SQL:货物构成图前端行过滤 / 自产率图渲染门槛
  goodsName?: string[];
}

/**
 * selfAttribute 行过滤判定(货物构成图 + 图C 自产率图共用,保证阈值不发散)。
 * pct 为 null(我方无该行数据)时一律不匹配 —— 无自产属性可言。
 */
export function matchesSelfAttribute(
  pct: string | number | null | undefined,
  attr?: SelfAttribute,
): boolean {
  if (!attr || attr === "all") return true;
  if (pct === null || pct === undefined) return false;
  return attr === "self_dominant" ? Number(pct) >= 50 : Number(pct) < 50;
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
/** distinct 过滤选项(goods 供图B/货物构成每图筛选)。 */
export interface FilterOptions {
  projects: string[];
  competitors: string[];
  goods: string[];
}

// ── 2026-08-15 三问框架新图行类型(数值列 Decimal→string,同上) ──

/** 图3 中标率时间趋势(按季度)。 */
export interface TrendRow {
  qtr: string; // date_trunc('quarter') 时间戳 ISO 串
  ours_rate: string | null;
  comp_rate: string | null;
}

/** 图7 胜率-溢价曲线(固定 6 桶,0=≤−5% … 5=>+10%)。 */
export interface PremiumCurveRow {
  bucket: number;
  n: number;
  win_rate: string | null;
}

/** 图8 报价区间建议(按金额段)。 */
export interface PriceBandRow {
  seg: string; // '1_<100万' … '4_≥2000万'
  p25: string | null;
  p50: string | null;
  p75: string | null;
  cost_floor: string | null;
}

/** 图10 友商画像行。 */
export interface CompetitorProfileRow {
  bidder_name: string;
  bids: number;
  wins: number;
  win_rate: string | null;
  avg_premium_pct: string | null; // 负 = 惯于低价抢标
  projects: number;
}

/** 图10 优势领域聚合行(前端按友商取 Top2)。 */
export interface CompetitorGoodsRow {
  bidder_name: string;
  goods_name: string;
  amt: string | null;
}

/** 图11 遭遇战分年度行。 */
export interface Head2HeadRow {
  yr: number;
  ours_wins: number;
  comp_wins: number;
}

/** 图12 份额格局行(前端折叠 前5+其他)。 */
export interface ShareStackRow {
  yr: number;
  bidder_name: string;
  amt: string | null;
}

/** KPI 同比分年行。 */
export interface KpiByYearRow {
  yr: number;
  ours_bid: number;
  ours_won: number;
  comp_bid: number;
  comp_won: number;
}
