"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  ACCENT_SOFT,
  AXIS,
  BLUE,
  CURSOR,
  GRID,
  INK,
  INK_3,
  RED,
} from "@/extensions/bid-quote/components/chartTheme";
import { usePremiumCurve } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

/** 固定 6 桶边界(与 SQL CASE 严格一致)。 */
const BUCKETS = [
  { idx: 0, label: "≤−5%" },
  { idx: 1, label: "−5~0%" },
  { idx: 2, label: "0~+3%" },
  { idx: 3, label: "+3~+6%" },
  { idx: 4, label: "+6~+10%" },
  { idx: 5, label: ">+10%" },
];
/** 桶透明度(原型:越往右越淡 = 越陪跑)。 */
const OPACITY = [1, 1, 1, 0.75, 0.5, 0.35];

/**
 * 图7(新增):胜率–溢价曲线 — 溢价 6 桶柱 + 红虚线拐点标注(+3% 桶界)+ 每桶 n= 样本数。
 * 原型 block2-pricing 图A。拐点取「首个胜率较前桶腰斩(≤50%)的桶界」自动判定。
 */
export function PremiumCurveChart({ filters }: { filters: FilterState }) {
  const q = usePremiumCurve(filters);
  const byIdx = new Map((q.data ?? []).map((r) => [Number(r.bucket), r]));
  const data = BUCKETS.map((b) => {
    const r = byIdx.get(b.idx);
    return {
      bucket: b.label,
      win_rate: r?.win_rate ? Number(r.win_rate) : 0,
      n: r?.n ?? 0,
    };
  });

  // 拐点:首个胜率 ≤ 前桶 50% 且有样本的桶(默认回退 +3~+6% 桶界)
  let inflection = BUCKETS[3]!.label; // 固定 6 桶常量,索引必存在
  for (let i = 1; i < data.length; i++) {
    const a = data[i - 1]!; // 循环边界保证存在
    const b = data[i]!;
    if (a.n > 0 && b.n > 0 && a.win_rate > 0 && b.win_rate <= a.win_rate / 2) {
      inflection = b.bucket;
      break;
    }
  }

  return (
    <ChartCard
      title="胜率 – 溢价曲线"
      meta="我方报价相对该项目友商最低价的溢价率 · 我方全部投标"
    >
      <ResponsiveContainer width="100%" height={215}>
        <BarChart
          data={data}
          margin={{ top: 22, right: 8, left: -14, bottom: 0 }}
        >
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="bucket"
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
          <Tooltip
            content={
              <TechTooltipWithN />
            }
            cursor={CURSOR}
          />
          <ReferenceLine
            x={inflection}
            stroke={RED}
            strokeDasharray="3 3"
            strokeOpacity={0.6}
            label={{
              value: `拐点 ${inflection}:再往上胜率腰斩`,
              position: "insideTopRight",
              fill: RED,
              fontSize: 11,
              fontWeight: 600,
            }}
          />
          <Bar
            dataKey="win_rate"
            name="胜率"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          >
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={BLUE}
                fillOpacity={OPACITY[i] ?? 1}
              />
            ))}
            <LabelList
              dataKey="win_rate"
              position="top"
              formatter={(v) => (Number(v) > 0 ? `${Math.round(Number(v))}%` : "—")}
              style={{ fill: INK, fontSize: 11, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/* 每桶样本数注脚(原型 n= 行) */}
      <div className="mt-1 grid grid-cols-6 text-center text-[10px] [font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
        {data.map((d, i) => (
          <span key={i}>n={d.n}</span>
        ))}
      </div>
      {/* 原型 insight 条 */}
      <div
        className="mt-3 rounded-xl px-4 py-3 text-[13px] leading-relaxed"
        style={{ background: ACCENT_SOFT }}
      >
        读法:横向看<b className="font-semibold" style={{ color: BLUE }}>「加价几个点会死」</b>
        ——溢价 ≤0% 时胜率最高,越过拐点后腰斩,超过 +10% 基本陪跑。柱下 n= 样本数。
      </div>
    </ChartCard>
  );
}

/** tooltip:胜率 + 该桶样本数(读 payload 原始 datum)。 */
function TechTooltipWithN(props: {
  active?: boolean;
  payload?: { payload?: { bucket: string; win_rate: number; n: number } }[];
}) {
  const { active, payload } = props;
  const d = payload?.[0]?.payload;
  if (!active || !d) return null;
  return (
    <div
      className="rounded-[10px] px-3 py-2 text-xs shadow-[0_4px_16px_rgba(0,0,0,0.08)]"
      style={{ background: "#fff", border: "1px solid rgba(0,0,0,0.08)" }}
    >
      <p className="mb-1 font-semibold" style={{ color: INK }}>
        {d.bucket}
      </p>
      <p className="[font-variant-numeric:tabular-nums]" style={{ color: INK }}>
        胜率 <b>{Math.round(d.win_rate)}%</b>
      </p>
      <p className="[font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
        样本 n={d.n}
      </p>
    </div>
  );
}
