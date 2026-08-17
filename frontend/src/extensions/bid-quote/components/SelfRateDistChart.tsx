"use client";

import { type ReactNode, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  AMBER,
  AXIS,
  CURSOR,
  GREEN,
  GRID,
} from "@/extensions/bid-quote/components/chartTheme";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { useSelfRateDist } from "@/extensions/bid-quote/hooks";
import {
  type FilterState,
  matchesSelfAttribute,
  type SelfAttribute,
} from "@/extensions/bid-quote/types";

interface SelfRateDistChartProps {
  filters: FilterState;
  /** 可选自产属性行过滤(与货物构成图共用 matchesSelfAttribute,阈值不发散)。 */
  selfAttribute?: SelfAttribute;
  /** 标题行操作区(每图筛选 Popover 等),由 DashboardView 注入。 */
  action?: ReactNode;
}

const BIN = 10; // 直方图桶宽 10%

/**
 * 图C:项目整标自产率分布——直方图(10% 一桶),每桶内按门槛拆两段堆叠:
 * ≥门槛 绿 / 低于门槛 琥珀。门槛滑杆 0-100 可拖,拖动即时重新分桶配色
 * (2026-08-17 由逐项目柱改直方图:长项目名不再挤爆 X 轴,"分布"语义成立)。
 */
export function SelfRateDistChart({
  filters,
  selfAttribute,
  action,
}: SelfRateDistChartProps) {
  const [threshold, setThreshold] = useState(50);
  const q = useSelfRateDist(filters);

  const rows0 = (q.data ?? []).filter((r) =>
    matchesSelfAttribute(r.self_rate, selfAttribute),
  );
  // Decimal 经 JSON 序列化为 string;null(我方无该标)按 0 计入 0–10% 桶
  const rows = Array.from({ length: 100 / BIN }, (_, i) => ({
    bin: `${i * BIN}–${i * BIN + BIN}%`,
    "≥门槛": 0,
    "低于门槛": 0,
  }));
  for (const r of rows0) {
    const rate = Number(r.self_rate ?? 0);
    const i = Math.min(Math.floor(rate / BIN), 9);
    rows[i]![rate >= threshold ? "≥门槛" : "低于门槛"]++;
  }
  const below = rows0.filter(
    (r) => Number(r.self_rate ?? 0) < threshold,
  ).length;

  return (
    <ChartCard
      title="项目自产率分布"
      meta="10% 分桶 · 门槛线可拖"
      action={action}
    >
      {/* 门槛滑杆 + 低于门槛项目计数 */}
      <div className="mb-2 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={100}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          aria-label="自产率门槛"
          className="h-1 flex-1 cursor-pointer accent-emerald-500"
        />
        <span className="text-muted-foreground w-24 text-right text-[11px] font-bold">
          门槛 {threshold}% · 低于 {below} 个
        </span>
      </div>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
          <XAxis
            dataKey="bin"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            interval={0}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={34}
          />
          <Tooltip content={<TechTooltip />} cursor={CURSOR} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar
            dataKey="≥门槛"
            stackId="a"
            fill={GREEN}
            isAnimationActive={false}
          />
          <Bar
            dataKey="低于门槛"
            stackId="a"
            fill={AMBER}
            radius={[3, 3, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
