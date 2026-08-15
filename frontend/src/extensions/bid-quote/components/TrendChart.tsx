"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  AXIS,
  BLUE,
  COMPETITOR,
  CURSOR,
  GRID,
} from "@/extensions/bid-quote/components/chartTheme";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";
import { useTrend } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

/** qtr(时间戳 ISO 串)→ "25Q1" 短标签;解析失败原样返回。 */
function qtrLabel(qtr: string): string {
  // SQL 已用 to_char 出 "23Q1" 标签;此处仅兜底解析失败原样返回
  const d = new Date(qtr);
  if (Number.isNaN(d.getTime())) return qtr;
  const q = Math.floor(d.getUTCMonth() / 3) + 1;
  return `${String(d.getUTCFullYear()).slice(2)}Q${q}`;
}

/**
 * 图3(新增):中标率时间趋势 — 我方(主蓝折线+软面积渐隐)vs 友商(浅灰蓝弱化线),
 * 按季度。原型 block1-overview 图B。
 */
export function TrendChart({ filters }: { filters: FilterState }) {
  const q = useTrend(filters);
  const data = (q.data ?? []).map((r) => ({
    qtr: qtrLabel(r.qtr),
    我方: r.ours_rate === null ? null : Number(r.ours_rate),
    友商: r.comp_rate === null ? null : Number(r.comp_rate),
  }));

  return (
    <ChartCard title="中标率时间趋势" meta="季度 · 我方 vs 友商">
      {/* 原型图例:小色块 + 次级文字 */}
      <div className="mb-2 flex gap-3.5 text-xs text-[#6b6c6e]">
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: BLUE }} />
          我方
        </span>
        <span className="flex items-center gap-1.5">
          <i
            className="inline-block h-2.5 w-2.5 rounded-[3px]"
            style={{ background: "#d8dcf8" }}
          />
          友商
        </span>
      </div>
      <ResponsiveContainer width="100%" height={230}>
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 8, left: -14, bottom: 0 }}
        >
          <defs>
            <linearGradient id="trendFade" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={BLUE} stopOpacity={0.16} />
              <stop offset="100%" stopColor={BLUE} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="qtr"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: GRID }}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={42}
            unit="%"
          />
          <Tooltip content={<TechTooltip />} cursor={CURSOR} />
          {/* 友商:浅灰蓝弱化线,无数据点 */}
          <Line
            dataKey="友商"
            stroke={COMPETITOR}
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4, fill: COMPETITOR }}
            connectNulls
            isAnimationActive={false}
          />
          {/* 我方:主蓝折线 + 软面积渐隐 */}
          <Area
            dataKey="我方"
            stroke="none"
            fill="url(#trendFade)"
            isAnimationActive={false}
          />
          <Line
            dataKey="我方"
            stroke={BLUE}
            strokeWidth={2.5}
            dot={{ r: 3.5, fill: BLUE, strokeWidth: 0 }}
            activeDot={{ r: 4.5, fill: BLUE }}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
