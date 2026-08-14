"use client";

import type { ReactNode } from "react";

// recharts 3.x:TooltipProps 不再带 payload/label,用内联结构接口。
interface TechTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string; color?: string }>;
  label?: string | number;
  unit?: string;
}

// dataviz:数值用 text token(次要墨色)+ tabular-nums;色点承载身份,色从不承载文字。
export function TechTooltip({ active, payload, label, unit }: TechTooltipProps): ReactNode {
  if (!active || !payload?.length) return null;
  const suffix = unit ? ` ${unit}` : "";
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      {label !== undefined ? <p className="mb-1.5 font-semibold text-foreground">{label}</p> : null}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <p key={i} className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: p.color }} />
            <span className="text-muted-foreground">{p.name}</span>
            <span className="ml-auto font-semibold tabular-nums text-foreground">
              {p.value}
              {suffix}
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}
