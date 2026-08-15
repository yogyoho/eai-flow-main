"use client";

import { CARD, INK, INK_2 } from "@/extensions/bid-quote/components/chartTheme";

// recharts 自定义 tooltip:DeepSeek 风白卡(无光晕无玻璃)。
// recharts 3.x 的 TooltipProps 泛型不再直出 payload/label,这里用结构化内联接口
// (content 接受任意 ReactElement 并在运行期克隆注入 active/payload/label)。
interface TooltipEntry {
  name?: string | number;
  value?: string | number;
  color?: string;
}
interface TechTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
}

export function TechTooltip({ active, payload, label }: TechTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-[10px] px-3 py-2 text-xs shadow-[0_4px_16px_rgba(0,0,0,0.08)]"
      style={{ background: CARD, border: "1px solid rgba(0,0,0,0.08)" }}
    >
      {label !== undefined ? (
        <p className="mb-1 text-[12px] font-semibold" style={{ color: INK }}>
          {label}
        </p>
      ) : null}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-[3px]"
            style={{ background: p.color }}
          />
          <span style={{ color: INK_2 }}>{p.name}:</span>
          <span
            className="font-semibold [font-variant-numeric:tabular-nums]"
            style={{ color: INK }}
          >
            {p.value}
          </span>
        </p>
      ))}
    </div>
  );
}
