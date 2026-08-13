"use client";

// recharts 自定义 tooltip:cyber 浅色玻璃面。
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
