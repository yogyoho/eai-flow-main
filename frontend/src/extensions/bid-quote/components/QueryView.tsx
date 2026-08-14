"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { DrillDownModal } from "@/extensions/bid-quote/components/DrillDownModal";
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/bid-quote/components/ui/table";
import {
  useBidList,
  useComposition,
  useWinRateBySegment,
} from "@/extensions/bid-quote/hooks";
import {
  EMPTY_FILTERS,
  type BidItemRow,
  type CompositionRow,
  type FilterState,
  type SegmentRow,
} from "@/extensions/bid-quote/types";

type TabKey = "bidlist" | "composition" | "segment";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bidlist", label: "投标明细" },
  { key: "composition", label: "货物构成对比" },
  { key: "segment", label: "按金额段中标率" },
];

// 金额段定义(与 seed win_rate_by_segment 一致)→ 下钻 SQL 上下界
const SEG_BOUNDS: Record<string, [number, number]> = {
  "1_<100万": [0, 1_000_000],
  "2_100-500万": [1_000_000, 5_000_000],
  "3_500-2000万": [5_000_000, 20_000_000],
  "4_≥2000万": [20_000_000, Number.MAX_SAFE_INTEGER],
};

// 清洗:单引号转义防 SQL 注入(值来自 DB 行数据,非用户自由输入)。
// no-base-to-string: v 为 unknown,需显式收窄后再 String()(对象走 JSON)。
const esc = (v: unknown) => {
  const s =
    v === null || v === undefined
      ? ""
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v as string | number | boolean);
  return s.replace(/'/g, "''");
};

export function QueryView() {
  const [tab, setTab] = useState<TabKey>("bidlist");
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(
    null,
  );

  const bidQ = useBidList(filters);
  const compQ = useComposition(filters);
  const segQ = useWinRateBySegment(filters);

  const bidRows = bidQ.data ?? [];
  const compRows = compQ.data ?? [];
  const segRows = segQ.data ?? [];
  // 明细列动态(取首行列名);罐装视图列固定
  // noUncheckedIndexedAccess: bidRows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const bidCols = bidRows.length ? Object.keys(bidRows[0] ?? {}) : [];

  const onRowDrill = (
    key: TabKey,
    row: BidItemRow | CompositionRow | SegmentRow,
  ) => {
    // 白名单维度:仅 project_name / goods_name / amount_segment;值经 esc 转义后拼入只读 SELECT。
    // EAI-CUSTOM: mock_bid_item 无 project_name 列(在 mock_bid 上),故明细下钻走 bid_id JOIN。
    if (key === "bidlist") {
      const v = esc((row as BidItemRow).project_name);
      setDrill({
        title: `项目明细 · ${v}`,
        sql: `SELECT i.goods_name, i.spec, i.quantity, i.unit, i.unit_price, i.self_amount, i.outsourced_amount, i.total_amount, b.bidder_role, b.won FROM mock_bid_item i JOIN mock_bid b ON i.bid_id=b.bid_id WHERE b.project_name='${v}' ORDER BY i.total_amount DESC`,
      });
    } else if (key === "composition") {
      const v = esc((row as CompositionRow).goods_name);
      setDrill({
        title: `货物明细 · ${v}`,
        sql: `SELECT * FROM mock_bid_item WHERE goods_name='${v}' ORDER BY total_amount DESC`,
      });
    } else {
      const seg = (row as SegmentRow).amount_segment;
      const [lo, hi] = SEG_BOUNDS[seg] ?? [0, Number.MAX_SAFE_INTEGER];
      setDrill({
        title: `金额段明细 · ${seg}`,
        sql: `SELECT * FROM mock_bid WHERE winning_price >= ${lo} AND winning_price < ${hi} ORDER BY winning_price DESC`,
      });
    }
  };

  const loading = useMemo(
    () =>
      tab === "bidlist"
        ? bidQ.isLoading
        : tab === "composition"
          ? compQ.isLoading
          : segQ.isLoading,
    [tab, bidQ.isLoading, compQ.isLoading, segQ.isLoading],
  );

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <Search className="text-primary h-5 w-5" />
        <h1 className="text-foreground text-2xl font-bold">数据查询</h1>
      </div>

      {/* 全局过滤 */}
      <FilterBar filters={filters} onChange={setFilters} />

      {/* 视图 tab(pill) */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors " +
              (tab === t.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 当前视图表(点行下钻) */}
      <div className="border-border bg-card rounded-xl border p-4">
        {loading ? (
          <p className="text-muted-foreground py-8 text-center text-sm">
            加载中…
          </p>
        ) : tab === "bidlist" ? (
          <Table>
            <TableHeader>
              <TableRow>
                {bidCols.map((c) => (
                  <TableHead key={c}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {bidRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("bidlist", r)}>
                  {bidCols.map((c) => (
                    <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : tab === "composition" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>货物</TableHead>
                <TableHead>我方自产%</TableHead>
                <TableHead>友商自产%</TableHead>
                <TableHead>我方均价</TableHead>
                <TableHead>友商均价</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {compRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("composition", r)}>
                  <TableCell>{r.goods_name}</TableCell>
                  <TableCell>{r.ours_self_pct ?? "—"}</TableCell>
                  <TableCell>{r.competitor_self_pct ?? "—"}</TableCell>
                  <TableCell>{r.ours_avg_unit_price ?? "—"}</TableCell>
                  <TableCell>{r.competitor_avg_unit_price ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>金额段</TableHead>
                <TableHead>投标数</TableHead>
                <TableHead>中标数</TableHead>
                <TableHead>中标率</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {segRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("segment", r)}>
                  <TableCell>{r.amount_segment.replace(/^\d+_/, "")}</TableCell>
                  <TableCell>{r.ours_bid}</TableCell>
                  <TableCell>{r.ours_won}</TableCell>
                  <TableCell>{r.ours_win_rate_pct ?? "—"}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DrillDownModal
        title={drill?.title ?? ""}
        sql={drill?.sql ?? null}
        onClose={() => setDrill(null)}
      />
    </div>
  );
}
