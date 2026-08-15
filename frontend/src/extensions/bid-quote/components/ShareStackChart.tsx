"use client";

import { useMemo } from "react";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  BLUE,
  INK_2,
  INK_3,
} from "@/extensions/bid-quote/components/chartTheme";
import { useShareStack } from "@/extensions/bid-quote/hooks";
import type { FilterState, ShareStackRow } from "@/extensions/bid-quote/types";

/** 我方(种子数据固定名);泛化失败时退化为普通着色。 */
const OURS = "东智装备制造";
/** 友商整体排名调色板(原型:非我方一律弱色系)。 */
const RIVAL_PALETTE = ["#7c9dfd", "#f0a122", "#20b26c", "#e07b9a"];
const OTHER_COLOR = "#c9c9c7";

const W = 560;
const COL_W = 130; // 每年一列
const GAP = 46;

/**
 * 图12(新增):份额格局 — 按年 100% 堆叠柱(自绘 SVG):我方主蓝,
 * 其余按金额取前5、剩下折「其他」;我方份额连年上涨时右侧给趋势注解。
 */
export function ShareStackChart({ filters }: { filters: FilterState }) {
  const q = useShareStack(filters);

  // 折叠:每年 Top5 + 其他;着色按全体年份合并排名(同名跨年同色)
  const { years, cols, legend, rising } = useMemo(
    () => foldRows(q.data ?? []),
    [q.data],
  );

  const H = 210;
  const top = 18;
  const bottom = 34;
  const barH = H - top - bottom;

  return (
    <ChartCard
      title="份额格局"
      meta="按年 · 各家中标金额份额(100% 堆叠)· 看格局变迁"
    >
      {/* 图例 */}
      <div className="mb-2 flex flex-wrap gap-3 text-xs" style={{ color: INK_2 }}>
        {legend.map((l) => (
          <span key={l.name} className="flex items-center gap-1.5">
            <i
              className="inline-block h-2.5 w-2.5 rounded-[3px]"
              style={{ background: l.color }}
            />
            {l.name}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        {years.map((yr, yi) => {
          const x0 = 40 + yi * (COL_W + GAP);
          let y = top;
          const col = cols[yi] ?? []; // noUncheckedIndexedAccess:空数组兜底
          return (
            <g key={yr}>
              {col.map((seg) => {
                const h = (seg.share / 100) * barH;
                const rectY = y;
                y += h;
                return (
                  <g key={seg.name}>
                    <rect
                      x={x0}
                      y={rectY + 1}
                      width={COL_W}
                      height={Math.max(h - 2, 0)}
                      fill={seg.color}
                    />
                    {seg.share >= 8 ? (
                      <text
                        x={x0 + COL_W / 2}
                        y={rectY + h / 2 + 4}
                        textAnchor="middle"
                        fontSize={10.5}
                        fill="#fff"
                      >
                        {seg.name === OURS ? "我方" : seg.name}{" "}
                        {Math.round(seg.share)}%
                      </text>
                    ) : null}
                  </g>
                );
              })}
              <text
                x={x0 + COL_W / 2}
                y={H - 12}
                textAnchor="middle"
                fontSize={12}
                fill={INK_3}
              >
                {yr}
              </text>
            </g>
          );
        })}
        {rising ? (
          <text
            x={W - 8}
            y={top + 12}
            textAnchor="end"
            fontSize={12}
            fill={INK_2}
          >
            → 我方份额逐年上涨
          </text>
        ) : null}
      </svg>
    </ChartCard>
  );
}

interface Seg {
  name: string;
  share: number;
  color: string;
}

/** 年折叠 + 全局着色 + 我方上涨判定(≥2 年且严格递增)。 */
function foldRows(rows: ShareStackRow[]): {
  years: number[];
  cols: Seg[][];
  colorOf: (name: string) => string;
  legend: { name: string; color: string }[];
  rising: boolean;
} {
  const byYear = new Map<number, { name: string; amt: number }[]>();
  for (const r of rows) {
    const yr = Number(r.yr);
    const amt = Number(r.amt ?? 0);
    const list = byYear.get(yr) ?? [];
    list.push({ name: r.bidder_name, amt });
    byYear.set(yr, list);
  }
  const years = [...byYear.keys()].sort((a, b) => a - b);

  // 全局金额排名(我方除外,固定主蓝)
  const totals = new Map<string, number>();
  for (const list of byYear.values()) {
    for (const { name, amt } of list) totals.set(name, (totals.get(name) ?? 0) + amt);
  }
  const rank = [...totals.entries()]
    .filter(([n]) => n !== OURS)
    .sort((a, b) => b[1] - a[1])
    .map(([n]) => n);
  const colorOf = (name: string) =>
    name === OURS
      ? BLUE
      : RIVAL_PALETTE[Math.min(rank.indexOf(name), RIVAL_PALETTE.length - 1)] ?? OTHER_COLOR;

  const cols = years.map((yr) => {
    const list = [...(byYear.get(yr) ?? [])].sort((a, b) => b.amt - a.amt);
    const top5 = list.slice(0, 5);
    const rest = list.slice(5);
    const tot = list.reduce((s, x) => s + x.amt, 0) || 1;
    const segs: Seg[] = top5.map((x) => ({
      name: x.name,
      share: (100 * x.amt) / tot,
      color: colorOf(x.name),
    }));
    if (rest.length) {
      segs.push({
        name: "其他",
        share: (100 * rest.reduce((s, x) => s + x.amt, 0)) / tot,
        color: OTHER_COLOR,
      });
    }
    return segs;
  });

  // 我方份额逐年严格上涨 → 注解(泛化:不看友商名)
  const oursShare = cols.map((segs) => segs.find((s) => s.name === OURS)?.share ?? 0);
  const rising =
    oursShare.length >= 2 && oursShare.every((v, i) => i === 0 || v > (oursShare[i - 1] ?? 0));

  // 图例顺序:我方 + 友商全局排名前3 + 其他
  const legendNames = [OURS, ...rank.slice(0, 3)];
  if (cols.some((c) => c.some((s) => s.name === "其他"))) legendNames.push("其他");
  const legend = legendNames.map((n) => ({
    name: n === OURS ? "我方" : n,
    color: n === "其他" ? OTHER_COLOR : colorOf(n),
  }));

  return { years, cols, colorOf, legend, rising };
}
