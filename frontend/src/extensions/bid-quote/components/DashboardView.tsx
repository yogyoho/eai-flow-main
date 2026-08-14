"use client";

import {
  Activity,
  BarChart3,
  Crown,
  Gauge,
  RefreshCw,
  Scale,
  TrendingUp,
} from "lucide-react";
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
  CURSOR,
  GREEN,
  GRID,
  RED_55,
} from "@/extensions/bid-quote/components/chartTheme";
import { DrillDownModal } from "@/extensions/bid-quote/components/DrillDownModal";
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import { SelfRateDistChart } from "@/extensions/bid-quote/components/SelfRateDistChart";
import { SelfVsOutsourceChart } from "@/extensions/bid-quote/components/SelfVsOutsourceChart";
import { StatCard } from "@/extensions/bid-quote/components/StatCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import {
  useBidSummary,
  useComposition,
  useFilterOptions,
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

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  // 图2 货物构成:每图高级筛选(selfAttribute 前端行过滤 + goodsName 进 SQL)
  const [compChart, setCompChart] = useState<ChartFilter>({});
  // 图B:每图货物筛选;图C:每图自产属性(渲染层行过滤)——spec §5.5
  const [bChart, setBChart] = useState<ChartFilter>({});
  const [cChart, setCChart] = useState<ChartFilter>({});
  // 图3 下钻:点击“我方”柱 → 该项目全部投标明细(我方+多友商报价对比)
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
  // 货物选项(与 FilterBar 同 queryKey,TanStack Query 去重复用)
  const goodsOpts = useFilterOptions().data?.goods ?? [];

  const s = summaryQ.data?.[0];
  // 友商中标率(后端无此字段,前端算)
  const compRate =
    s && s.competitor_bid > 0
      ? Math.round((100 * s.competitor_won) / s.competitor_bid / 0.1) / 10
      : null;

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="border-primary/30 bg-primary/10 text-primary flex items-center justify-center rounded-sm border p-1">
            <Scale className="h-5 w-5" />
          </div>
          <h1 className="text-foreground text-shadow-glow text-2xl font-bold">
            投标报价分析
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

      {/* 全局过滤 */}
      <FilterBar filters={filters} onChange={setFilters} />

      {/* KPI 行 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard
          label="我方中标率"
          value={s ? `${s.ours_win_rate_pct ?? "—"}%` : "—"}
          icon={Gauge}
          color="primary"
        />
        <StatCard
          label="投标总数"
          value={s?.bid_count ?? "—"}
          icon={BarChart3}
          color="chart2"
        />
        <StatCard
          label="我方投 / 中"
          value={s ? `${s.ours_bid} / ${s.ours_won}` : "—"}
          icon={Activity}
          color="chart3"
        />
        <StatCard
          label="友商中标率"
          value={compRate !== null ? `${compRate}%` : "—"}
          icon={TrendingUp}
          color="destructive"
        />
        <StatCard
          label="平均中标价"
          value={s ? wan(s.avg_winning_price) : "—"}
          icon={Crown}
          color="chart5"
        />
      </div>

      {/* 图表 3 张 */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* 图1:按金额段我方中标率 */}
        <ChartCard title="按金额段 · 我方中标率" meta="≥2000万 段短板">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(segQ.data ?? []).map((r) => ({
                amount_segment: r.amount_segment,
                ours_win_rate_pct: toNum(r.ours_win_rate_pct),
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="segGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BLUE} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={BLUE} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="2 4"
                stroke={GRID}
                vertical={false}
              />
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
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Bar
                dataKey="ours_win_rate_pct"
                name="我方中标率"
                fill="url(#segGrad)"
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:货物构成对比 自产%(每图筛选:自产属性前端行过滤) */}
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
          <ResponsiveContainer width="100%" height={260}>
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
              <CartesianGrid
                strokeDasharray="2 4"
                stroke={GRID}
                vertical={false}
              />
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
                isAnimationActive
                animationDuration={900}
              />
              <Bar
                dataKey="competitor_self_pct"
                name="友商自产%"
                fill={AMBER}
                radius={[3, 3, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:项目报价对比 我方 vs 友商(胜负 Cell 色) */}
        <ChartCard
          title="项目报价对比 · 我方 vs 友商(万)"
          meta="报价区间建议"
          className="xl:col-span-2"
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
              <defs>
                <linearGradient id="ourGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={GREEN} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={GREEN} stopOpacity={0.25} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="2 4"
                stroke={GRID}
                vertical={false}
              />
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
                fill="url(#ourGrad)"
                radius={[3, 3, 0, 0]}
                isAnimationActive
                animationDuration={900}
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
                  <Cell key={i} fill={r.we_won ? "url(#ourGrad)" : RED_55} />
                ))}
              </Bar>
              <Bar
                dataKey="友商"
                fill={AMBER}
                radius={[3, 3, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图C:项目整标自产率分布(门槛滑杆 + 达标/未达标 Cell 色;每图自产属性筛选) */}
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

        {/* 图B:自产 vs 外购金额(项目/货物视角切换;每图货物筛选) */}
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

      {/* 图3 点击下钻弹层 */}
      <DrillDownModal
        title={drill?.title ?? ""}
        sql={drill?.sql ?? null}
        onClose={() => setDrill(null)}
      />
    </div>
  );
}
