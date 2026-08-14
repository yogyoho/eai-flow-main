"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StatColor = "primary" | "chart2" | "chart3" | "destructive" | "chart5";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  color?: StatColor;
}

// EAI-CUSTOM: 本项目 chart/success/destructive CSS 变量为完整颜色(oklch/hex),非 HSL 通道,
// 故用字面 hex + 8 位 alpha(末2位=透明度:14≈8%/33≈20%),与 spare-parts PartAnalysis 同法。
const HEX: Record<StatColor, { bg: string; border: string; text: string }> = {
  primary: { bg: "#3b82f614", border: "#3b82f633", text: "#3b82f6" },
  chart2: { bg: "#8b5cf614", border: "#8b5cf633", text: "#8b5cf6" },
  chart3: { bg: "#f6bd1614", border: "#f6bd1633", text: "#f6bd16" },
  destructive: { bg: "#f43f5e14", border: "#f43f5e33", text: "#f43f5e" },
  chart5: { bg: "#10b98114", border: "#10b98133", text: "#10b981" },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  color = "primary",
}: StatCardProps) {
  const c = HEX[color];
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl p-4 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] transition-all hover:scale-[1.015]",
      )}
      style={{ background: c.bg, borderColor: c.border, borderWidth: 1 }}
    >
      <span
        className="absolute top-0 right-0 h-2 w-2 rounded-bl-md"
        style={{ background: c.text }}
      />
      <div className="text-muted-foreground/70 flex items-center gap-2">
        <Icon className="h-4 w-4" />
        <p className="text-xs tracking-wide uppercase">{label}</p>
      </div>
      <p
        className="font-cyber text-shadow-glow mt-2 text-3xl font-extrabold tracking-tight"
        style={{ color: c.text }}
      >
        {value}
      </p>
      {hint ? (
        <p className="text-muted-foreground mt-0.5 truncate text-[11px]">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
