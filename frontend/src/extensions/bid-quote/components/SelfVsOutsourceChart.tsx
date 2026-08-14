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
  BLUE,
  CURSOR,
  GRID,
  truncateLabel,
} from "@/extensions/bid-quote/components/chartTheme";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { useSelfVsOutsource } from "@/extensions/bid-quote/hooks";
import {
  type ChartFilter,
  type FilterState,
} from "@/extensions/bid-quote/types";

interface SelfVsOutsourceChartProps {
  filters: FilterState;
  /** 每图高级筛选(货物维度,spec §5.5)。 */
  chart?: ChartFilter;
  /** 标题行操作区(每图筛选 Popover 等),由 DashboardView 注入。 */
  action?: ReactNode;
}

/**
 * 图B:自产 vs 外购金额(万)。按项目/按货物双视角切换,dim 进 queryKey,
 * 切换即重查;名称经 truncateLabel 截断,长项目/货物名不挤爆 X 轴。
 */
export function SelfVsOutsourceChart({
  filters,
  chart,
  action,
}: SelfVsOutsourceChartProps) {
  const [dim, setDim] = useState<"project" | "goods">("project");
  const q = useSelfVsOutsource(filters, dim, chart);

  // Decimal 经 JSON 序列化为 string;null 按金额 0 计,统一换算为万
  const data = (q.data ?? []).map((r) => ({
    label: truncateLabel(r.label),
    自产: Number(r.self_amount ?? 0) / 10000,
    外购: Number(r.outsourced_amount ?? 0) / 10000,
  }));

  return (
    // isPlaceholderData:切视角瞬间仍显示旧视角数据,半透明提示非最新
    <div
      className={
        q.isPlaceholderData
          ? "opacity-60 transition-opacity"
          : "transition-opacity"
      }
    >
      <ChartCard title="自产 vs 外购金额(万)" meta="视角可切" action={action}>
        {/* 视角切换:项目 / 货物 */}
        <div
          role="group"
          aria-label="视角"
          className="mb-2 flex items-center gap-1"
        >
          {(["project", "goods"] as const).map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={dim === d}
              onClick={() => setDim(d)}
              className={
                "rounded border px-1.5 py-0.5 text-[11px] " +
                (dim === d
                  ? "border-primary text-primary"
                  : "border-border text-muted-foreground")
              }
            >
              {d === "project" ? "按项目" : "按货物"}
            </button>
          ))}
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={data}
            margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="2 4"
              stroke={GRID}
              vertical={false}
            />
            <XAxis
              dataKey="label"
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
              dataKey="自产"
              fill={BLUE}
              radius={[3, 3, 0, 0]}
              isAnimationActive
              animationDuration={900}
            />
            <Bar
              dataKey="外购"
              fill={AMBER}
              radius={[3, 3, 0, 0]}
              isAnimationActive
              animationDuration={900}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
