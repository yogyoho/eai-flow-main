"use client";

import type { ReactNode } from "react";

import { CARD, CARD_BORDER, INK, INK_3 } from "@/extensions/bid-quote/components/chartTheme";
import { cn } from "@/lib/utils";


interface ChartCardProps {
  title: string;
  /** 标题下说明行(原型 .meta:12px 弱色,支持 <b> 强调,传 string 或 ReactNode)。 */
  meta?: ReactNode;
  /** 标题行右侧操作区,放每图筛选 Popover 等控件。 */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

// EAI-CUSTOM: DeepSeek 风白卡(纯白 + 1px 细边 + 14px 圆角,无重阴影无光晕) —— 原型即验收标准
export function ChartCard({
  title,
  meta,
  action,
  children,
  className,
}: ChartCardProps) {
  return (
    <div
      className={cn("rounded-[14px] p-5", className)}
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <div className="mb-3.5">
        <div className="flex items-center justify-between gap-2">
          <h3
            className="text-[14.5px] leading-tight font-semibold"
            style={{ color: INK }}
          >
            {title}
          </h3>
          {action}
        </div>
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
