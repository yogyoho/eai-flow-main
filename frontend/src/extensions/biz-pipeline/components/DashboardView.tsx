"use client";

import { GitCommitHorizontal, RefreshCw, TrendingDown, Wallet } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { clearBizPipelineCache } from "@/extensions/biz-pipeline/api";
import { ChartCard } from "@/extensions/biz-pipeline/components/ChartCard";
import { StatCard } from "@/extensions/biz-pipeline/components/StatCard";
import { TechTooltip } from "@/extensions/biz-pipeline/components/TechTooltip";
import { useContractRecon, useMonthlyBids, usePipelineFunnel } from "@/extensions/biz-pipeline/hooks";

// EAI-CUSTOM: 项目 chart CSS 变量为完整颜色(非 HSL 通道),故图表用字面 hex
const GRID = "rgba(100,116,139,0.22)";
const AXIS_FILL = "#94a3b8";
const AXIS = { fontSize: 11, fill: AXIS_FILL };
const CURSOR = { fill: "rgba(148,163,184,0.15)" };
const BLUE = "#3b82f6";
const AMBER = "#f6bd16";
const RED = "#f43f5e";

// Decimal/numeric 列经 JSON 序为 string;recharts 需 number → 统一转。
const toNum = (v: string | null | undefined): number => (v === null || v === undefined ? 0 : Number(v));
function wan(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const refresh = () => {
    clearBizPipelineCache();
    setTick((t) => t + 1);
  };

  const funnelQ = usePipelineFunnel();
  const monthlyQ = useMonthlyBids();
  const reconQ = useContractRecon();

  const f = funnelQ.data?.[0];

  // 金额漏斗数据(投标总额→中标总额→合同总额→已开票总额,单位万)
  const funnelData = f
    ? [
        { stage: "投标总额", amount: toNum(f.bid_amount_total) / 10000 },
        { stage: "中标总额", amount: toNum(f.won_amount_total) / 10000 },
        { stage: "合同总额", amount: toNum(f.contract_total) / 10000 },
        { stage: "已开票", amount: toNum(f.invoiced_total) / 10000 },
      ]
    : [];
  // 中标率:保留 1 位小数(1000 倍后取整再除回,避开浮点)
  const winRate = f && f.bid_count > 0 ? Math.round((1000 * f.won_count) / f.bid_count) / 10 : null;

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-sm border border-primary/30 bg-primary/10 p-1 text-primary">
            <GitCommitHorizontal className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold text-foreground text-shadow-glow">管线查询</h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={funnelQ.isFetching}>
          <RefreshCw className={funnelQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* KPI 行(5 卡) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="投标总数" value={f?.bid_count ?? "—"} icon={GitCommitHorizontal} color="primary" />
        <StatCard label="中标率" value={winRate !== null ? `${winRate}%` : "—"} icon={TrendingDown} color="chart2" />
        <StatCard label="合同总额" value={f ? wan(f.contract_total) : "—"} icon={Wallet} color="chart3" />
        <StatCard label="已开票总额" value={f ? wan(f.invoiced_total) : "—"} icon={Wallet} color="chart5" />
        <StatCard label="待开票总额" value={f ? wan(f.uninvoiced_total) : "—"} icon={TrendingDown} color="destructive" />
      </div>

      {/* 图表 3 张 */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* 图1:金额漏斗 投标→中标→合同→开票 */}
        <ChartCard title="金额漏斗 · 投标 → 中标 → 合同 → 开票(万)" meta="逐级沉淀">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={funnelData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="funnelGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BLUE} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={BLUE} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="stage"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Bar
                dataKey="amount"
                name="金额(万)"
                fill="url(#funnelGrad)"
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:月度投标节奏 投标 vs 中标 */}
        <ChartCard title="月度投标节奏 · 投标 vs 中标" meta="旺淡季">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(monthlyQ.data ?? []).map((r) => ({ ym: r.ym, bids: r.bids, won: r.won }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="ym" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={32} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="bids" name="投标" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
              <Bar dataKey="won" name="中标" fill={AMBER} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:待开票合同对账(合同额 vs 已开票,红色渐变) */}
        <ChartCard title="待开票合同 · 合同额 vs 已开票(万)" meta="催开票预警" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={(reconQ.data ?? []).map((r) => ({
                contract_no: r.contract_no,
                合同额: toNum(r.amount) / 10000,
                已开票: toNum(r.invoiced) / 10000,
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="uninvGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={RED} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={RED} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="contract_no"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
                angle={-12}
                textAnchor="end"
                height={50}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="合同额" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
              <Bar dataKey="已开票" fill="url(#uninvGrad)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
