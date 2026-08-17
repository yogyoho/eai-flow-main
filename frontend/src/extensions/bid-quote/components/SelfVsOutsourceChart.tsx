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

/** 横向 Y 轴名称截断:9 字比 truncateLabel(4 字)宽松——横排有整行宽度可用。 */
const trimLabel = (s: string | null | undefined) => {
  const v = s ?? "";
  return v.length > 9 ? v.slice(0, 9) + "…" : v;
};

/**
 * 图B:自产 vs 外购金额(万)——横向堆叠条形(自产+外购=总投标额,成本结构一眼可比)。
 * 按项目/按货物双视角切换(dim 进 queryKey,切换即重查);总额降序排列,
 * recharts 纵向布局 data[0] 在最顶部 → 总额最大者置顶(2026-08-17 由纵向柱改横向,长名不再重叠)。
 */
export function SelfVsOutsourceChart({
  filters,
  chart,
  action,
}: SelfVsOutsourceChartProps) {
  const [dim, setDim] = useState<"project" | "goods">("project");
  const q = useSelfVsOutsource(filters, dim, chart);

  // Decimal 经 JSON 序列化为 string;null 按金额 0 计,统一换算为万
  const data = (q.data ?? [])
    .map((r) => ({
      label: trimLabel(r.label),
      自产: Number(r.self_amount ?? 0) / 10000,
      外购: Number(r.outsourced_amount ?? 0) / 10000,
    }))
    .sort((a, b) => b.自产 + b.外购 - (a.自产 + a.外购));

  return (
    // isPlaceholderData:切视角瞬间仍显示旧视角数据,半透明提示非最新
    <div
      className={
        q.isPlaceholderData
          ? "opacity-60 transition-opacity"
          : "transition-opacity"
      }
    >
      <ChartCard
        title="自产 vs 外购金额(万)"
        meta="按总额排序 · 视角可切"
        action={action}
      >
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
        <div className="max-h-[280px] overflow-y-auto pr-1">
          <ResponsiveContainer
            width="100%"
            height={Math.max(data.length * 22 + 24, 120)}
          >
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} horizontal={false} />
              <XAxis
                type="number"
                tick={AXIS}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                width={44}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ ...AXIS, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={106}
              />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar
                dataKey="自产"
                stackId="a"
                fill={BLUE}
                barSize={12}
                isAnimationActive={false}
              />
              <Bar
                dataKey="外购"
                stackId="a"
                fill={AMBER}
                radius={[0, 3, 3, 0]}
                barSize={12}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    </div>
  );
}
