"use client";

import { useMemo } from "react";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  BLUE,
  INK,
  INK_2,
} from "@/extensions/bid-quote/components/chartTheme";
import { useShareStack } from "@/extensions/bid-quote/hooks";
import type { FilterState, ShareStackRow } from "@/extensions/bid-quote/types";

/** 我方(种子数据固定名);泛化失败时退化为普通着色。 */
const OURS = "东智装备制造";
/** 友商整体排名调色板(原型:非我方一律弱色系,4 色 + 其他灰 = 6 色封顶)。 */
const RIVAL_PALETTE = ["#7c9dfd", "#f0a122", "#20b26c", "#e07b9a"];
const OTHER_COLOR = "#c9c9c7";

// 几何严格对齐原型 block3 图C:年份标签在柱顶、柱体 26~174、注解在末列右侧
const W = 700;
const H = 210;
const TOP = 26;
const BAR_H = 148;
const COL_W = 120;
const GAP = 80;
/** 柱内白字标签的最小段高(px)——原型只在足够高的段(我方/头部友商)上落字。 */
const LABEL_MIN_H = 30;

/** 2~9 的中文数字(「三连涨」文案用,超出退回阿拉伯数字)。 */
const CN_NUM = ["", "", "二", "三", "四", "五", "六", "七", "八", "九"] as const;

/**
 * 图12(新增):中标份额格局 — 按年 100% 堆叠柱(自绘 SVG,样式对齐原型 block3 图C):
 * 年份标签置顶加粗、我方段固定置顶、段间无缝、图例沉底(前 4 友商 + 其他)、
 * 末列右侧双行注解(我方连涨 + 最大退场友商)。
 */
export function ShareStackChart({ filters }: { filters: FilterState }) {
  const q = useShareStack(filters);

  // 折叠:每年 我方置顶 + Top4 + 其他;着色按全体年份合并排名(同名跨年同色)
  const { years, cols, legend, rising, decliner } = useMemo(
    () => foldRows(q.data ?? []),
    [q.data],
  );

  return (
    <ChartCard
      title="中标份额格局"
      meta={
        <>
          按年 · 各家中标金额份额(100% 堆叠)·{" "}
          <b>看格局变迁:谁在扩张、谁在退场</b>
        </>
      }
    >
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        {years.map((yr, yi) => {
          const x0 = 40 + yi * (COL_W + GAP);
          const cx = x0 + COL_W / 2;
          let y = TOP;
          const col = cols[yi] ?? []; // noUncheckedIndexedAccess:空数组兜底
          return (
            <g key={yr}>
              {/* 年份标签:柱顶加粗主色(原型 y=20 的 12.5px semibold) */}
              <text
                x={cx}
                y={16}
                textAnchor="middle"
                fontSize={12.5}
                fontWeight={600}
                fill={INK}
              >
                {yr}
              </text>
              {col.map((seg) => {
                const h = (seg.share / 100) * BAR_H;
                const rectY = y;
                y += h;
                return (
                  <g key={seg.name}>
                    {/* 原型为无缝连续堆叠(无段间隙、无圆角) */}
                    <rect x={x0} y={rectY} width={COL_W} height={h} fill={seg.color} />
                    {h >= LABEL_MIN_H ? (
                      <text
                        x={cx}
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
            </g>
          );
        })}
        {/* 末列右侧注解(原型 x=960 双行:扩张 + 退场) */}
        {rising ? (
          <text x={575} y={60} fontSize={11} fill={INK_2}>
            → 我方份额{CN_NUM[years.length] ?? years.length}连涨
          </text>
        ) : null}
        {decliner ? (
          <text x={575} y={78} fontSize={11} fill={INK_2}>
            → {decliner.name} {decliner.first}%→{decliner.last}%
          </text>
        ) : null}
      </svg>
      {/* 图例:沉底一行(原型在柱体下方的 svg 内,等价 HTML 行) */}
      <div className="mt-1.5 flex flex-wrap gap-4 text-[11px]" style={{ color: INK_2 }}>
        {legend.map((l) => (
          <span key={l.name} className="flex items-center gap-1.5">
            <i
              className="inline-block h-2 w-3 rounded-[2px]"
              style={{ background: l.color }}
            />
            {l.name}
          </span>
        ))}
      </div>
    </ChartCard>
  );
}

interface Seg {
  name: string;
  share: number;
  color: string;
}

/** 年折叠 + 全局着色 + 我方上涨/友商退场判定。 */
function foldRows(rows: ShareStackRow[]): {
  years: number[];
  cols: Seg[][];
  colorOf: (name: string) => string;
  legend: { name: string; color: string }[];
  rising: boolean;
  decliner: { name: string; first: number; last: number } | null;
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
    // 原型:我方段固定置顶(跨年可比),其余按金额降序,「其他」垫底
    const segs: Seg[] = [];
    const ours = top5.find((x) => x.name === OURS);
    if (ours) segs.push({ name: OURS, share: (100 * ours.amt) / tot, color: BLUE });
    for (const x of top5) {
      if (x.name === OURS) continue;
      segs.push({ name: x.name, share: (100 * x.amt) / tot, color: colorOf(x.name) });
    }
    if (rest.length) {
      segs.push({
        name: "其他",
        share: (100 * rest.reduce((s, x) => s + x.amt, 0)) / tot,
        color: OTHER_COLOR,
      });
    }
    return segs;
  });

  // 原始年度份额(不经过 Top5 折叠——掉出 Top5 被折进「其他」不等于份额归零)
  const rawShare = (yi: number, name: string) => {
    const list = byYear.get(years[yi] ?? 0) ?? [];
    const tot = list.reduce((s, x) => s + x.amt, 0) || 1;
    return Math.round((100 * (list.find((x) => x.name === name)?.amt ?? 0)) / tot);
  };

  // 我方份额逐年严格上涨 → 注解(泛化:不看友商名)
  const oursShare = cols.map((segs) => segs.find((s) => s.name === OURS)?.share ?? 0);
  const rising =
    oursShare.length >= 2 && oursShare.every((v, i) => i === 0 || v > (oursShare[i - 1] ?? 0));

  // 首末年都在场的友商里,份额落差最大者为「退场」注解(原型:中机国能 28%→17%)
  let decliner: { name: string; first: number; last: number } | null = null;
  if (years.length >= 2) {
    const last = years.length - 1;
    for (const name of rank.slice(0, RIVAL_PALETTE.length)) {
      const first = rawShare(0, name);
      const end = rawShare(last, name);
      if (first > 0 && end < first && first - end > (decliner?.first ?? 0) - (decliner?.last ?? 0)) {
        decliner = { name, first, last: end };
      }
    }
  }

  // 图例顺序:我方 + 友商全局排名前4 + 其他(原型 6 色封顶)
  const legendNames = [OURS, ...rank.slice(0, RIVAL_PALETTE.length)];
  if (cols.some((c) => c.some((s) => s.name === "其他"))) legendNames.push("其他");
  const legend = legendNames.map((n) => ({
    name: n === OURS ? "我方" : n,
    color: n === "其他" ? OTHER_COLOR : colorOf(n),
  }));

  return { years, cols, colorOf, legend, rising, decliner };
}
