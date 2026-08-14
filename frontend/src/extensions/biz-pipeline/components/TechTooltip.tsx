"use client";

// recharts 3.x:TooltipProps 不再带 payload/label,用内联结构接口。
interface TechTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number | string; color?: string }>;
  label?: string | number;
}

// cyber 浅色玻璃面自定义 tooltip
export function TechTooltip({ active, payload, label }: TechTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-primary/30 bg-card/95 px-3 py-2 font-cyber text-xs text-card-foreground shadow-lg backdrop-blur">
      {label !== undefined ? <p className="mb-1 font-bold text-primary text-shadow-glow">{label}</p> : null}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-bold">{p.value}</span>
        </p>
      ))}
    </div>
  );
}
