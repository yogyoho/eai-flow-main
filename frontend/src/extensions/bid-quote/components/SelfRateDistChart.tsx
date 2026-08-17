"use client";

import { type ComponentProps, type ReactNode, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Rectangle,
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

// 栈顶圆角规则:每根堆叠柱只有最上段带顶部圆角,下方段方角——
// 两段都圆会在接缝处各圆各的,露出背景缺口(2026-08-17 绿/琥珀圆角对齐)
type SegProps = ComponentProps<typeof Rectangle> & { payload?: Record<string, number> };
const R_TOP: [number, number, number, number] = [3, 3, 0, 0];
const R_NONE: [number, number, number, number] = [0, 0, 0, 0];

/** 绿段(底段):本桶"低于门槛"为 0 时自己即栈顶,才给圆角。 */
function GreenSeg({ payload: d, ...rest }: SegProps) {
  return <Rectangle {...rest} radius={(d?.["低于门槛"] ?? 0) > 0 ? R_NONE : R_TOP} />;
}
/** 琥珀段(顶段):计数 > 0 才渲染,恒为栈顶,恒带圆角。 */
function AmberSeg(props: SegProps) {
  return <Rectangle {...props} radius={R_TOP} />;
}

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
      {/* 门槛滑杆 + 低于门槛项目计数(灰轨加粗+绿thumb;文字 nowrap 单行,滑杆相应变短) */}
      <div className="mb-2 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={100}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          aria-label="自产率门槛"
          // 左绿右灰:thumb 左侧(已含入 ≥门槛 段)用 GREEN 渐变填充,右侧 GRID 灰;
          // 分界百分比 = 当前门槛值,随拖动即时重算(每次 setThreshold 都重渲染)
          style={{
            background: `linear-gradient(to right, ${GREEN} 0%, ${GREEN} ${threshold}%, ${GRID} ${threshold}%, ${GRID} 100%)`,
          }}
          className="h-1.5 max-w-[320px] flex-1 cursor-pointer appearance-none rounded-full focus-visible:ring-emerald-500/40 focus-visible:ring-2 focus-visible:outline-none [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:bg-emerald-500 [&::-moz-range-thumb]:shadow [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:bg-emerald-500 [&::-webkit-slider-thumb]:shadow"
        />
        <span className="text-muted-foreground shrink-0 text-right text-[11px] font-bold whitespace-nowrap">
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
            shape={<GreenSeg />}
          />
          <Bar
            dataKey="低于门槛"
            stackId="a"
            fill={AMBER}
            isAnimationActive={false}
            shape={<AmberSeg />}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
