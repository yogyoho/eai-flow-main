"use client";

import type { ReactNode } from "react";

import {
  CARD,
  CARD_BORDER,
  INK,
  INK_2,
  INK_3,
} from "@/extensions/geo-samples/components/chartTheme";

interface StatCardProps {
  label: string;
  value: string | number;
  /** 注脚行(12px 弱色)。 */
  delta?: ReactNode;
}

/**
 * KPI 白卡:label 次级色 → 主数字 26px/650/tabular(不靠颜色靠字重)→ 注脚弱色行。
 * forked from bid-quote/components/StatCard.tsx(EAI-CUSTOM: geo-sample-bank Phase 1 复制模式)。
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
