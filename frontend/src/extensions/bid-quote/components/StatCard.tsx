"use client";

import type { ReactNode } from "react";

import {
  CARD,
  CARD_BORDER,
  GREEN,
  INK,
  INK_2,
  INK_3,
  RED,
} from "@/extensions/bid-quote/components/chartTheme";

interface StatCardProps {
  label: string;
  value: string | number;
  /** 注脚行(原型 .delta:12px 弱色;delta 主数字靠字重,涨跌用绿/红 b 强调)。 */
  delta?: ReactNode;
}

/**
 * DeepSeek 风 KPI 白卡:label 次级色 → 主数字 26px/650/tabular(不靠颜色靠字重)
 * → 注脚弱色行。2026-08-15 仪表盘重构:替换原彩色五卡。
 */
export function StatCard({ label, value, delta }: StatCardProps) {
  return (
    <div
      className="rounded-[14px] px-5 py-[18px]"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <p className="text-[12.5px]" style={{ color: INK_2 }}>
        {label}
      </p>
      <p
        className="mt-2 text-[26px] leading-none font-[650] tracking-[-0.5px] [font-variant-numeric:tabular-nums]"
        style={{ color: INK }}
      >
        {value}
      </p>
      {delta ? (
        <p
          className="mt-1.5 text-xs [font-variant-numeric:tabular-nums]"
          style={{ color: INK_3 }}
        >
          {delta}
        </p>
      ) : null}
    </div>
  );
}

/** KPI 注脚涨跌片段:正=绿 / 负=红,650 字重(供 DashboardView 组装 delta 行)。 */
export function Delta({
  pt,
  suffix = "pt",
}: {
  pt: number | null;
  suffix?: string;
}) {
  if (pt === null || !Number.isFinite(pt)) return null;
  const up = pt >= 0;
  return (
    <b className="font-semibold" style={{ color: up ? GREEN : RED }}>
      {up ? "+" : "−"}
      {Math.abs(pt).toFixed(1)}
      {suffix}
    </b>
  );
}
