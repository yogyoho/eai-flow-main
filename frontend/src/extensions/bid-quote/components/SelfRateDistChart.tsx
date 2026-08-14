"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
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
  THRESHOLD_RED,
  truncateLabel,
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
}

/**
 * 图C:项目整标自产率分布。门槛滑杆 0-100 可拖,≥门槛 绿色 / <门槛 琥珀色,
 * 红色虚线参考线标注当前门槛位置。
 */
export function SelfRateDistChart({
  filters,
  selfAttribute,
}: SelfRateDistChartProps) {
  const [threshold, setThreshold] = useState(50);
  const q = useSelfRateDist(filters);

  // Decimal 经 JSON 序列化为 string;null(我方无该标)按 0 计;名称经共享 truncateLabel 截断
  const data = (q.data ?? [])
    .filter((r) => matchesSelfAttribute(r.self_rate, selfAttribute))
    .map((r) => ({
      project_name: truncateLabel(r.project_name),
      self_rate: Number(r.self_rate ?? 0),
    }));

  return (
    <ChartCard title="项目自产率分布" meta="门槛线可拖">
      {/* 门槛滑杆 */}
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
        <span className="text-muted-foreground w-14 text-right text-[11px] font-bold">
          门槛 {threshold}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={data}
          margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
        >
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
          <YAxis
            domain={[0, 100]}
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            unit="%"
            width={40}
          />
          <Tooltip content={<TechTooltip />} cursor={CURSOR} />
          <ReferenceLine
            y={threshold}
            stroke={THRESHOLD_RED}
            strokeDasharray="4 4"
            label={{
              value: `门槛 ${threshold}%`,
              position: "right",
              fill: THRESHOLD_RED,
              fontSize: 10,
            }}
          />
          <Bar
            dataKey="self_rate"
            name="自产率"
            radius={[3, 3, 0, 0]}
            isAnimationActive
            animationDuration={900}
          >
            {data.map((d, i) => (
              <Cell key={i} fill={d.self_rate >= threshold ? GREEN : AMBER} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
