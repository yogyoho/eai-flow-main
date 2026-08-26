"use client";

import type { ReactNode } from "react";

import { CARD, CARD_BORDER, INK, INK_3 } from "@/extensions/sales-personnel/components/chartTheme";
import { cn } from "@/lib/utils";

interface ChartCardProps {
  title: string;
  /** 标题下说明行(12px 弱色,支持 <b> 强调,传 string 或 ReactNode)。 */
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}

// EAI-CUSTOM: DeepSeek 风白卡(纯白 + 1px 细边 + 14px 圆角,无重阴影无光晕)—— 克隆自
// biz-pipeline/ChartCard,原型即验收标准
export function ChartCard({ title, meta, children, className }: ChartCardProps) {
  return (
    <div
      className={cn("rounded-[14px] p-5", className)}
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <div className="mb-3.5">
        <h3
          className="text-[14.5px] leading-tight font-semibold"
          style={{ color: INK }}
        >
          {title}
        </h3>
        {meta ? (
          <p className="mt-0.5 text-xs leading-normal" style={{ color: INK_3 }}>
            {meta}
          </p>
        ) : null}
      </div>
      {children}
    </div>
  );
}
