"use client";

import { Scale, RefreshCw } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { clearBidQuoteCache, esc } from "@/extensions/bid-quote/api";
import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import { ChartFilterPopover } from "@/extensions/bid-quote/components/ChartFilterPopover";
import {
  AMBER,
  AXIS,
  BLUE,
  COMPETITOR,
  CURSOR,
  GREEN,
  GRID,
  INK,
  INK_3,
  PAGE_BG,
  RED_55,
} from "@/extensions/bid-quote/components/chartTheme";
import { CompetitorProfileTable } from "@/extensions/bid-quote/components/CompetitorProfileTable";
import { DrillDownModal } from "@/extensions/bid-quote/components/DrillDownModal";
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import { HeadToHeadCard } from "@/extensions/bid-quote/components/HeadToHeadCard";
import { PremiumCurveChart } from "@/extensions/bid-quote/components/PremiumCurveChart";
import { PriceBandChart } from "@/extensions/bid-quote/components/PriceBandChart";
import { SectionCard } from "@/extensions/bid-quote/components/SectionCard";
import { SelfRateDistChart } from "@/extensions/bid-quote/components/SelfRateDistChart";
import { SelfVsOutsourceChart } from "@/extensions/bid-quote/components/SelfVsOutsourceChart";
import { ShareStackChart } from "@/extensions/bid-quote/components/ShareStackChart";
import { StatCard, Delta } from "@/extensions/bid-quote/components/StatCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { TrendChart } from "@/extensions/bid-quote/components/TrendChart";
import {
  useBidSummary,
  useComposition,
  useFilterOptions,
  useKpiByYear,
  useProjectShowdown,
  useWinRateBySegment,
} from "@/extensions/bid-quote/hooks";
import {
  type ChartFilter,
  EMPTY_FILTERS,
  type FilterState,
  matchesSelfAttribute,
} from "@/extensions/bid-quote/types";

// Decimal/numeric 列经 JSON 序列化为 string;recharts 需 number → 统一转。
const toNum = (v: string | null): number => (v === null ? 0 : Number(v));
function wan(v: string | null): string {
  if (v === null) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

/**
 * 仪表盘 tab(2026-08-15 三问框架重设计,原型 block1/2/3):
 * ①我们赢在哪、输在哪 ②下次报多少 ③对手是谁。DeepSeek usage 风格(浅色单主题)。
 * EAI-CUSTOM: 不随暗色主题切换——本页走独立浅色 token(chartTheme),原型即验收标准。
 */
export function DashboardView() {
  const [tick, setTick] = useState(0);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  // 图2 货物构成:每图高级筛选(selfAttribute 前端行过滤 + goodsName 进 SQL)
  const [compChart, setCompChart] = useState<ChartFilter>({});
  // 图B:每图货物筛选;图C:每图自产属性(渲染层行过滤)
  const [bChart, setBChart] = useState<ChartFilter>({});
  const [cChart, setCChart] = useState<ChartFilter>({});
  // 下钻:项目报价柱 / 友商画像行 / 遭遇战卡片共用一个弹层通道
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(
    null,
  );
  const refresh = () => {
    clearBidQuoteCache();
    setTick((t) => t + 1);
  };

  const summaryQ = useBidSummary(filters);
  const segQ = useWinRateBySegment(filters);
  const compQ = useComposition(filters, compChart);
  const showdownQ = useProjectShowdown(filters);
  const kpiQ = useKpiByYear(filters);
  // 货物选项(与 FilterBar 同 queryKey,TanStack Query 去重复用);友商列表给遭遇战下拉
  const opts = useFilterOptions().data;
  const goodsOpts = opts?.goods ?? [];
  const competitors = opts?.competitors ?? [];

  const s = summaryQ.data?.[0];

  // KPI 同比注脚:最近两年 我方/友商 中标率差(pt)
  const kpiRows = kpiQ.data ?? [];
  const latest = kpiRows.length ? kpiRows[kpiRows.length - 1] : null;
  const prev = kpiRows.length > 1 ? kpiRows[kpiRows.length - 2] : null;
  const rateOf = (won: number, bid: number) =>
    bid > 0 ? (100 * Number(won)) / Number(bid) : null;
  const oursNow = latest ? rateOf(latest.ours_won, latest.ours_bid) : null;
  const oursPrev = prev ? rateOf(prev.ours_won, prev.ours_bid) : null;
  const compNow = latest ? rateOf(latest.comp_won, latest.comp_bid) : null;
  const compPrev = prev ? rateOf(prev.comp_won, prev.comp_bid) : null;
  const yearSpan =
    kpiRows.length > 1
      ? `${kpiRows[0]!.yr}–${kpiRows[kpiRows.length - 1]!.yr} 三年` // length>1 保证两端存在
      : latest
        ? `${latest.yr} 年度`
        : "";
  const partRate =
    s && s.bid_count > 0 ? `${((100 * s.ours_bid) / s.bid_count).toFixed(0)}% 参与率` : "";

  return (
    <div
      key={tick}
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Scale className="h-5 w-5" style={{ color: BLUE }} />
          <h1 className="text-[22px] font-bold" style={{ color: INK }}>
            竞标战情总览
          </h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refresh}
          disabled={summaryQ.isFetching}
        >
          <RefreshCw
            className={
              summaryQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"
            }
          />
          刷新
        </Button>
      </div>

      {/* ── 三问 ①:我们赢在哪、输在哪? ───────────────────── */}
      <SectionCard
        badge="①"
        title="我们赢在哪、输在哪?"
        sub="战绩归因 · 按金额段 / 货物 / 时间三个轴定位输赢原因"
      >
        {/* KPI 行(同比注脚) */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard
            label="我方中标率"
            value={s ? `${s.ours_win_rate_pct ?? "—"}%` : "—"}
            delta={
              oursNow !== null && oursPrev !== null ? (
                <Delta pt={oursNow - oursPrev} />
              ) : undefined
            }
          />
          <StatCard label="投标总数" value={s?.bid_count ?? "—"} delta={yearSpan} />
          <StatCard
            label="我方投 / 中"
            value={s ? `${s.ours_bid} / ${s.ours_won}` : "—"}
            delta={partRate}
          />
          <StatCard
            label="友商中标率"
            value={
              s && s.competitor_bid > 0
                ? `${Math.round((100 * s.competitor_won) / s.competitor_bid / 0.1) / 10}%`
                : "—"
            }
            delta={
              compNow !== null && compPrev !== null ? (
                <Delta pt={compNow - compPrev} />
              ) : undefined
            }
          />
          <StatCard
            label="平均中标价"
            value={s ? wan(s.avg_winning_price) : "—"}
            delta="我方中标口径"
          />
        </div>

        {/* 全局过滤(KPI 之下) */}
        <FilterBar filters={filters} onChange={setFilters} />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {/* 图1:按金额段我方中标率(纯色蓝柱,无渐变) */}
          <ChartCard title="按金额段 · 我方中标率" meta="≥2000万 段短板">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart
                data={(segQ.data ?? []).map((r) => ({
                  amount_segment: r.amount_segment,
                  ours_win_rate_pct: toNum(r.ours_win_rate_pct),
                  ours_bid: r.ours_bid,
                  ours_won: r.ours_won,
                }))}
                margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
              >
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="amount_segment"
                  tick={AXIS}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                />
                <YAxis
                  tick={AXIS}
                  tickLine={false}
                  axisLine={false}
                  unit="%"
                  width={40}
                />
                <Tooltip content={<SegTooltip />} cursor={CURSOR} />
                <Bar
                  dataKey="ours_win_rate_pct"
                  name="我方中标率"
                  fill={BLUE}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* 图3(新):中标率时间趋势 */}
          <TrendChart filters={filters} />

          {/* 图2:货物构成对比 自产%(每图筛选) */}
          <ChartCard
            title="货物构成对比 · 自产率(我方 vs 友商)"
            meta="失标根因"
            action={
              <ChartFilterPopover
                chart={compChart}
                onChange={setCompChart}
                enable={{ selfAttribute: true, goodsName: goodsOpts }}
              />
            }
          >
            <ResponsiveContainer width="100%" height={250}>
              <BarChart
                data={(compQ.data ?? [])
                  .filter((r) =>
                    matchesSelfAttribute(
                      r.ours_self_pct,
                      compChart.selfAttribute,
                    ),
                  )
                  .map((r) => ({
                    goods_name: r.goods_name,
                    ours_self_pct: toNum(r.ours_self_pct),
                    competitor_self_pct: toNum(r.competitor_self_pct),
                  }))}
                margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
              >
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="goods_name"
                  tick={{ ...AXIS, fontSize: 10 }}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  interval={0}
                />
                <YAxis
                  tick={AXIS}
                  tickLine={false}
                  axisLine={false}
                  unit="%"
                  width={40}
                />
                <Tooltip content={<TechTooltip />} cursor={CURSOR} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar
                  dataKey="ours_self_pct"
                  name="我方自产%"
                  fill={BLUE}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="competitor_self_pct"
                  name="友商自产%"
                  fill={AMBER}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* 图C:项目整标自产率分布 */}
          <SelfRateDistChart
            filters={filters}
            selfAttribute={cChart.selfAttribute}
            action={
              <ChartFilterPopover
                chart={cChart}
                onChange={setCChart}
                enable={{ selfAttribute: true }}
              />
            }
          />
        </div>

        {/* 图B:自产 vs 外购金额(整行,不进两列网格) */}
        <div className="mt-5">
          <SelfVsOutsourceChart
            filters={filters}
            chart={bChart}
            action={
              <ChartFilterPopover
                chart={bChart}
                onChange={setBChart}
                enable={{ goodsName: goodsOpts }}
              />
            }
          />
        </div>
      </SectionCard>

      {/* ── 三问 ②:下次报多少? ─────────────────────────── */}
      <SectionCard badge="②" title="下次报多少?" sub="报价决策 · 溢价拐点 / 区间建议 / 单项目复盘">
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <PremiumCurveChart filters={filters} />
          <PriceBandChart filters={filters} />
        </div>

        {/* 图4:项目报价对比(迁入本节;我方=胜绿/负红半透明,友商弱化灰蓝) */}
        <ChartCard
          title="项目报价对比 · 我方 vs 友商(万)"
          meta="点击我方柱 → 全部投标明细"
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={(showdownQ.data ?? []).map((r) => ({
                project_name: r.project_name,
                我方: r.our_price ? Number(r.our_price) / 10000 : 0,
                友商: r.competitor_price
                  ? Number(r.competitor_price) / 10000
                  : 0,
                we_won: r.we_won,
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis
                dataKey="project_name"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
                angle={-12}
                textAnchor="end"
                height={50}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar
                dataKey="我方"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
                onClick={(_d: unknown, idx: number) => {
                  // recharts Bar onClick(data, index):按索引回查原始行;esc 单引号转义防 SQL 注入(与 api.ts 同源,勿内联第三份)
                  const r = showdownQ.data?.[idx];
                  if (r) {
                    const v = esc(r.project_name);
                    setDrill({
                      title: `项目报价 · ${r.project_name}`,
                      sql: `SELECT bidder_name, bidder_role, winning_price, won FROM mock_bid WHERE project_name='${v}' ORDER BY winning_price`,
                    });
                  }
                }}
              >
                {(showdownQ.data ?? []).map((r, i) => (
                  <Cell key={i} fill={r.we_won ? GREEN : RED_55} />
                ))}
              </Bar>
              <Bar
                dataKey="友商"
                fill={COMPETITOR}
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </SectionCard>

      {/* ── 三问 ③:对手是谁? ───────────────────────────── */}
      <SectionCard badge="③" title="对手是谁?" sub="竞争情报 · 友商画像 / 遭遇战 / 份额格局">
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.4fr_1fr]">
          <CompetitorProfileTable filters={filters} onDrill={setDrill} />
          <HeadToHeadCard
            filters={filters}
            competitors={competitors}
            onDrill={setDrill}
          />
        </div>
        <ShareStackChart filters={filters} />
      </SectionCard>

      {/* 下钻弹层(项目柱 / 友商行 / 遭遇战共用) */}
      <DrillDownModal
        title={drill?.title ?? ""}
        sql={drill?.sql ?? null}
        onClose={() => setDrill(null)}
      />
    </div>
  );
}

/** 金额段 tooltip:胜率 + 该段我方投/中样本数。 */
function SegTooltip(props: {
  active?: boolean;
  payload?: {
    payload?: {
      amount_segment: string;
      ours_win_rate_pct: number;
      ours_bid: number;
      ours_won: number;
    };
  }[];
}) {
  const d = props.payload?.[0]?.payload;
  if (!props.active || !d) return null;
  return (
    <div
      className="rounded-[10px] px-3 py-2 text-xs shadow-[0_4px_16px_rgba(0,0,0,0.08)]"
      style={{ background: "#fff", border: "1px solid rgba(0,0,0,0.08)" }}
    >
      <p className="mb-1 font-semibold" style={{ color: INK }}>
        {d.amount_segment}
      </p>
      <p className="[font-variant-numeric:tabular-nums]" style={{ color: INK }}>
        中标率 <b>{Math.round(d.ours_win_rate_pct)}%</b>
      </p>
      <p className="[font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
        {d.ours_won}/{d.ours_bid}
      </p>
    </div>
  );
}
