"use client";

import { Activity, BarChart3, Crown, Gauge, RefreshCw, Scale, TrendingUp } from "lucide-react";
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
import { clearBidQuoteCache } from "@/extensions/bid-quote/api";
import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import { FilterBar } from "@/extensions/bid-quote/components/FilterBar";
import { StatCard } from "@/extensions/bid-quote/components/StatCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import {
  useBidSummary,
  useComposition,
  useProjectShowdown,
  useWinRateBySegment,
} from "@/extensions/bid-quote/hooks";
import { EMPTY_FILTERS, type FilterState } from "@/extensions/bid-quote/types";

// EAI-CUSTOM: 项目 chart/success/destructive CSS 变量为完整颜色(非 HSL 通道),故图表用字面 hex
const GRID = "rgba(100,116,139,0.22)";
const AXIS_FILL = "#94a3b8";
const AXIS = { fontSize: 11, fill: AXIS_FILL };
const CURSOR = { fill: "rgba(148,163,184,0.15)" };
const BLUE = "#3b82f6";
const AMBER = "#f6bd16";
const GREEN = "#10b981";
const RED_55 = "#f43f5e8c"; // destructive @ ~55%

// Decimal/numeric 列经 JSON 序列化为 string;recharts 需 number → 统一转。
const toNum = (v: string | null): number => (v === null ? 0 : Number(v));
function wan(v: string | null): string {
  if (v === null) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const refresh = () => {
    clearBidQuoteCache();
    setTick((t) => t + 1);
  };

  const summaryQ = useBidSummary(filters);
  const segQ = useWinRateBySegment(filters);
  const compQ = useComposition(filters);
  const showdownQ = useProjectShowdown(filters);

  const s = summaryQ.data?.[0];
  // 友商中标率(后端无此字段,前端算)
  const compRate =
    s && s.competitor_bid > 0 ? Math.round((100 * s.competitor_won) / s.competitor_bid / 0.1) / 10 : null;

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-sm border border-primary/30 bg-primary/10 p-1 text-primary">
            <Scale className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold text-foreground text-shadow-glow">投标报价分析</h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={summaryQ.isFetching}>
          <RefreshCw className={summaryQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* 全局过滤 */}
      <FilterBar filters={filters} onChange={setFilters} />

      {/* KPI 行 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="我方中标率" value={s ? `${s.ours_win_rate_pct ?? "—"}%` : "—"} icon={Gauge} color="primary" />
        <StatCard label="投标总数" value={s?.bid_count ?? "—"} icon={BarChart3} color="chart2" />
        <StatCard label="我方投 / 中" value={s ? `${s.ours_bid} / ${s.ours_won}` : "—"} icon={Activity} color="chart3" />
        <StatCard
          label="友商中标率"
          value={compRate !== null ? `${compRate}%` : "—"}
          icon={TrendingUp}
          color="destructive"
        />
        <StatCard label="平均中标价" value={s ? wan(s.avg_winning_price) : "—"} icon={Crown} color="chart5" />
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
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="amount_segment" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="%" width={40} />
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

        {/* 图2:货物构成对比 自产% */}
        <ChartCard title="货物构成对比 · 自产率(我方 vs 友商)" meta="失标根因">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(compQ.data ?? []).map((r) => ({
                goods_name: r.goods_name,
                ours_self_pct: toNum(r.ours_self_pct),
                competitor_self_pct: toNum(r.competitor_self_pct),
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="goods_name"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="%" width={40} />
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
        <ChartCard title="项目报价对比 · 我方 vs 友商(万)" meta="报价区间建议" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={(showdownQ.data ?? []).map((r) => ({
                project_name: r.project_name,
                我方: r.our_price ? Number(r.our_price) / 10000 : 0,
                友商: r.competitor_price ? Number(r.competitor_price) / 10000 : 0,
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
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
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
              <Bar dataKey="我方" fill="url(#ourGrad)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900}>
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
      </div>
    </div>
  );
}
