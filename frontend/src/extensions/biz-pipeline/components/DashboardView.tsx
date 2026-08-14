"use client";

import { GitCommitHorizontal, RefreshCw, TrendingDown, Wallet } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { clearBizPipelineCache } from "@/extensions/biz-pipeline/api";
import { ChartCard } from "@/extensions/biz-pipeline/components/ChartCard";
import { StatCard } from "@/extensions/biz-pipeline/components/StatCard";
import { TechTooltip } from "@/extensions/biz-pipeline/components/TechTooltip";
import { useContractRecon, useMonthlyBids, usePipelineFunnel } from "@/extensions/biz-pipeline/hooks";

// EAI-CUSTOM · dataviz: 调色板经 scripts/validate_palette.js 校验(CVD ΔE≥8),非凭眼选。
// ponytail: chart 标记用 light 模式字面 hex,不随 data-theme 切换(与 bid-quote/sales-personnel 一致)。
// 分类色板 slots 1-2(投标/中标 · 合同额/已开票)—— PASS light+dark。
const C_BLUE = "#2a78d6"; // slot1 投标 / 合同额 / 漏斗单色
const C_ORANGE = "#eb6834"; // slot2 中标 / 已开票

// dataviz chrome:后退的网格/轴线(弱化到次要),数值用 tabular-nums 对齐。
const GRID = "rgba(11,11,11,0.06)";
const AXIS_FILL = "#898781";
const TICK = { fontSize: 11, fill: AXIS_FILL, fontFamily: "inherit" } as const;
const TABULAR = { fontVariantNumeric: "tabular-nums" } as const;
const CURSOR = { fill: "rgba(42,120,214,0.08)" } as const;

// 月度节奏图例(分类色板 slots1-2):[名称, 色]
const BIDS_LEGEND: Array<[string, string]> = [
  ["投标", C_BLUE],
  ["中标", C_ORANGE],
];
// 待开票对账图例(分类色板 slots1-2):[名称, 色]
const RECON_LEGEND: Array<[string, string]> = [
  ["合同额", C_BLUE],
  ["已开票", C_ORANGE],
];

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

  // 金额漏斗(投标→中标→合同→开票,单位万)—— 单色实心柱 + 柱顶直接标值
  const funnelData = f
    ? [
        { stage: "投标总额", amount: toNum(f.bid_amount_total) / 10000, amlabel: `${(toNum(f.bid_amount_total) / 10000).toFixed(0)}万` },
        { stage: "中标总额", amount: toNum(f.won_amount_total) / 10000, amlabel: `${(toNum(f.won_amount_total) / 10000).toFixed(0)}万` },
        { stage: "合同总额", amount: toNum(f.contract_total) / 10000, amlabel: `${(toNum(f.contract_total) / 10000).toFixed(0)}万` },
        { stage: "已开票", amount: toNum(f.invoiced_total) / 10000, amlabel: `${(toNum(f.invoiced_total) / 10000).toFixed(0)}万` },
      ]
    : [];
  // 中标率:保留 1 位小数(1000 倍后取整再除回,避开浮点)
  const winRate = f && f.bid_count > 0 ? Math.round((1000 * f.won_count) / f.bid_count) / 10 : null;
  // 月度投标节奏(投标 vs 中标,次数)
  const monthlyData = (monthlyQ.data ?? []).map((r) => ({ ym: r.ym, 投标: r.bids, 中标: r.won }));
  // 待开票对账(合同额 vs 已开票,万)
  const reconData = (reconQ.data ?? []).map((r) => ({
    contract_no: r.contract_no,
    合同额: toNum(r.amount) / 10000,
    已开票: toNum(r.invoiced) / 10000,
  }));

  return (
    <div key={tick} className="space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-lg border border-primary/30 bg-primary/10 p-1 text-primary">
            <GitCommitHorizontal className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">管线查询</h1>
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
        {/* 图1:金额漏斗(单色实心柱 + 柱顶标值,逐级沉淀) */}
        <ChartCard title="金额漏斗 · 投标 → 中标 → 合同 → 开票(万)" meta="逐级沉淀">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={funnelData} margin={{ top: 22, right: 12, left: -12, bottom: 0 }} barCategoryGap="32%">
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="stage" tick={{ ...TICK, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis tick={{ ...TICK, ...TABULAR }} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip unit="万" />} cursor={CURSOR} />
              <Bar dataKey="amount" name="金额(万)" fill={C_BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} maxBarSize={72}>
                <LabelList dataKey="amlabel" position="top" style={{ ...TICK, ...TABULAR, fontSize: 11, fontWeight: 600, fill: AXIS_FILL }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:月度投标节奏(投标 vs 中标,分类色板 slots1-2) */}
        <ChartCard title="月度投标节奏 · 投标 vs 中标" meta="旺淡季">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={monthlyData} margin={{ top: 10, right: 12, left: -12, bottom: 0 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="ym" tick={TICK} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={{ ...TICK, ...TABULAR }} tickLine={false} axisLine={false} width={32} />
              <Tooltip content={<TechTooltip unit="次" />} cursor={CURSOR} />
              <Bar dataKey="投标" fill={C_BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} />
              <Bar dataKey="中标" fill={C_ORANGE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} />
            </BarChart>
          </ResponsiveContainer>
          {/* 自定义图例:色点 + 名称(分类色板,色随身份不随取值) */}
          <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
            {BIDS_LEGEND.map(([label, color]) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </ChartCard>

        {/* 图3:待开票合同对账(合同额 vs 已开票,分类色板 slots1-2) */}
        <ChartCard title="待开票合同 · 合同额 vs 已开票(万)" meta="催开票预警" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={reconData} margin={{ top: 10, right: 12, left: -12, bottom: 0 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="contract_no"
                tick={{ ...TICK, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
                angle={-12}
                textAnchor="end"
                height={50}
              />
              <YAxis tick={{ ...TICK, ...TABULAR }} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<TechTooltip unit="万" />} cursor={CURSOR} />
              <Bar dataKey="合同额" fill={C_BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} />
              <Bar dataKey="已开票" fill={C_ORANGE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} />
            </BarChart>
          </ResponsiveContainer>
          {/* 自定义图例:色点 + 名称 */}
          <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
            {RECON_LEGEND.map(([label, color]) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
