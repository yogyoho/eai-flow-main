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
} from "@/extensions/sales-personnel/components/chartTheme";

interface StatCardProps {
  label: string;
  value: string | number;
  /** 注脚行(12px 弱色;达标/警示用绿/红 b 强调)。 */
  delta?: ReactNode;
}

/** DeepSeek 风 KPI 白卡(克隆自 biz-pipeline/StatCard):label 次级色 → 主数字 26px/650 → 注脚弱色行。 */
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

/** KPI 注脚强调片段:正=绿 / 负=红,600 字重(供 delta 行组装)。 */
export function Emph({ value, neg = false }: { value: string; neg?: boolean }) {
  return (
    <b className="font-semibold" style={{ color: neg ? RED : GREEN }}>
      {value}
    </b>
  );
}
