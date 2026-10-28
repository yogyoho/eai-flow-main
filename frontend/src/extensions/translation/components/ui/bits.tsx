"use client";

/**
 * 翻译工作台轻量展示基元（EAI-CUSTOM, 2026-10-18）。
 * 视觉习语取自 2026-10-12 eia-p2 原型 `.pill` / `.note-bar`：
 * 20px 全圆徽章、12px medium、语义色底 + hairline 边。
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type PillTone =
  | "primary"
  | "success"
  | "warn"
  | "error"
  | "gray"
  | "info";

const pillTones: Record<PillTone, string> = {
  primary: "border-primary/20 bg-primary/10 text-primary",
  // 成功 chip 用 700 阶：900 阶（#135200）视觉近黑，需保持绿色可读。
  success: "border-[var(--success-100)] bg-[var(--success-50)] text-[var(--success-700)]",
  warn: "border-amber-500/25 bg-amber-500/10 text-[var(--warning-900)]",
  error: "border-destructive/25 bg-destructive/10 text-[var(--error-900)]",
  gray: "border-border bg-muted/50 text-muted-foreground",
  info: "border-info/25 bg-info/10 text-[var(--info-900)]",
};

/** 20px 高圆角徽章；语义色六档。 */
export function Pill({
  tone = "gray",
  title,
  className,
  children,
}: {
  tone?: PillTone;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full border px-2 text-xs font-medium whitespace-nowrap",
        pillTones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** 页底 info 说明条（原型 .note-bar）。 */
export function NoteBar({ children }: { children: ReactNode }) {
  return (
    <div className="bg-info/10 text-[var(--info-900)] flex items-start gap-2 rounded-md px-3 py-2 text-xs">
      <svg
        aria-hidden
        className="mt-0.5 h-3.5 w-3.5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4M12 8h.01" />
      </svg>
      <span>{children}</span>
    </div>
  );
}
