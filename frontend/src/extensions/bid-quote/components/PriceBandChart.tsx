"use client";

import {
  ACCENT_SOFT,
  BLUE,
  CARD,
  CARD_BORDER,
  GREEN,
  INK,
  INK_2,
  INK_3,
  RED,
} from "@/extensions/bid-quote/components/chartTheme";
import { usePriceBand } from "@/extensions/bid-quote/hooks";
import type { FilterState, PriceBandRow } from "@/extensions/bid-quote/types";

const SEG_LABEL: Record<string, string> = {
  "1_<100万": "<100万",
  "2_100-500万": "100–500万",
  "3_500-2000万": "500–2000万",
  "4_≥2000万": "≥2000万",
};

const W = 520; // 与原型同 viewBox 宽
const TRACK_X0 = 90;
const TRACK_X1 = 480;

const toNum = (v: string | null): number => (v === null ? 0 : Number(v));
const wan = (v: number) => `${(v / 10000).toFixed(0)}万`;

/**
 * 图8(新增):报价区间建议 — 每金额段一行的区间条图(原型 block2-pricing 图B):
 * 蓝带 = 历史中标价 P25–P75,竖线 = 成本底线(我方行 Σ自产+外购),圆点 = 中位数。
 * 成本线切进蓝带(≥P25)时转红并文字警示。自绘 SVG(recharts 无原生区间条)。
 */
export function PriceBandChart({ filters }: { filters: FilterState }) {
  const q = usePriceBand(filters);
  const rows = q.data ?? [];

  // 全段共用线性标尺(诚实可比;小段会偏左挤,可接受)。cost=0/null 的段不参与标尺。
  const vals = rows.flatMap((r) => {
    const xs = [toNum(r.p25), toNum(r.p75)];
    const c = toNum(r.cost_floor);
    if (c > 0) xs.push(c);
    return xs;
  });
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  const pad = (hi - lo) * 0.08 || 1;
  const min = lo - pad;
  const max = hi + pad;
  const x = (v: number) =>
    TRACK_X0 + ((v - min) / (max - min)) * (TRACK_X1 - TRACK_X0);

  const rowH = 45;
  const legendY = rows.length * rowH + 16;
  const H = legendY + 18;

  return (
    <div
      className="rounded-[14px] p-5"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <div className="mb-3.5">
        <h3 className="text-[14.5px] font-semibold" style={{ color: INK }}>
          报价区间建议
        </h3>
        <p className="mt-0.5 text-xs" style={{ color: INK_3 }}>
          按金额段 · 历史中标价 <b style={{ color: INK_2 }}>P25–P75</b> · 成本底线(自产+外购)
        </p>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="overflow-visible">
        {rows.map((r, i) => (
          <BandRow key={r.seg} r={r} y={i * rowH + 40} x={x} />
        ))}
        {/* 图例(原型同款) */}
        <g fontSize={11} fill={INK_2}>
          <rect
            x={90}
            y={legendY}
            width={18}
            height={10}
            rx={5}
            fill={BLUE}
            opacity={0.22}
          />
          <text x={114} y={legendY + 9}>
            建议区间 P25–P75
          </text>
          <line
            x1={250}
            y1={legendY}
            x2={250}
            y2={legendY + 10}
            stroke={GREEN}
            strokeWidth={2.5}
          />
          <text x={258} y={legendY + 9}>
            成本底线
          </text>
          <circle cx={340} cy={legendY + 5} r={4.5} fill={BLUE} />
          <text x={350} y={legendY + 9}>
            历史中标中位
          </text>
        </g>
      </svg>
      {/* 原型 insight 条 */}
      <div
        className="mt-3 rounded-xl px-4 py-3 text-[13px] leading-relaxed"
        style={{ background: ACCENT_SOFT }}
      >
        读法:蓝带=<b className="font-semibold" style={{ color: BLUE }}>历史中标价 P25–P75</b>
        (报带内胜率最高);绿线=<b className="font-semibold" style={{ color: BLUE }}>成本底线</b>
        (报低于它必亏);红线切进蓝带的段 → 该段成本结构不支持竞争性报价。
      </div>
    </div>
  );
}

function BandRow({
  r,
  y,
  x,
}: {
  r: PriceBandRow;
  y: number;
  x: (v: number) => number;
}) {
  const p25 = toNum(r.p25);
  const p50 = toNum(r.p50);
  const p75 = toNum(r.p75);
  const cost = toNum(r.cost_floor);
  const hasCost = cost > 0;
  // 危险判定:成本线切进建议带(cost ≥ p25 且落在带内或压过中位)
  const dangerous = hasCost && cost >= p25;
  const lineColor = dangerous ? RED : GREEN;
  const bx0 = x(p25);
  const bw = Math.max(x(p75) - bx0, 8);
  const midX = x(p50);
  const labelLeft = midX > TRACK_X1 - 70; // 中位标签靠右时左移防溢出

  return (
    <g>
      <text x={0} y={y + 4} fontSize={12} fill={INK_2}>
        {SEG_LABEL[r.seg] ?? r.seg}
      </text>
      {/* 底轨 */}
      <line
        x1={TRACK_X0}
        y1={y}
        x2={TRACK_X1}
        y2={y}
        stroke="#f0f0ef"
        strokeWidth={8}
        strokeLinecap="round"
      />
      {/* 蓝带 P25–P75 */}
      <rect
        x={bx0}
        y={y - 6}
        width={bw}
        height={12}
        rx={6}
        fill={BLUE}
        opacity={0.22}
      />
      {/* 成本底线竖标 */}
      {hasCost ? (
        <>
          <line
            x1={x(cost)}
            y1={y - 10}
            x2={x(cost)}
            y2={y + 10}
            stroke={lineColor}
            strokeWidth={2.5}
          />
          {dangerous ? (
            <text
              x={Math.min(x(cost) + 6, TRACK_X1 - 150)}
              y={y + 20}
              fontSize={10}
              fill={RED}
            >
              成本 {wan(cost)} 已切进区间 → 报价空间被成本吃死
            </text>
          ) : null}
        </>
      ) : null}
      {/* 中位数圆点 + 标签 */}
      <circle cx={midX} cy={y} r={5} fill={BLUE} />
      <text
        x={labelLeft ? midX - 8 : midX}
        y={y - 14}
        fontSize={10.5}
        fill={INK}
        fontWeight={600}
        textAnchor={labelLeft ? "end" : "middle"}
      >
        中位 {wan(p50)}
      </text>
    </g>
  );
}
