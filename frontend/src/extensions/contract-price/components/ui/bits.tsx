"use client";

/**
 * cpa 模块轻量展示基元（cpa UI 重构规范 §2-4/§2-6）。
 * EAI-CUSTOM: 视觉习语取自 2026-10-12 eia-p2 原型（.pill / .note-bar），
 * token 落本系统语义层 + EAI 状态色；warning 500 不作文字色，warn 档用 amber-600。
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
  success: "border-success/30 bg-success/10 text-success",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  error: "border-destructive/30 bg-destructive/10 text-destructive",
  gray: "border-border bg-muted/40 text-muted-foreground",
  info: "border-info/30 bg-info/10 text-info",
};

/** 圆角全圆徽章：20px 高、12px medium，六档语义色。 */
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
        "inline-flex h-5 items-center gap-1 rounded-sm border px-2 text-xs font-medium whitespace-nowrap",
        pillTones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** 页底 info 说明条（只读边界 / 机制提示等）。 */
export function NoteBar({ children }: { children: ReactNode }) {
  return (
    <div className="bg-info/10 text-info flex items-start gap-2 rounded-md px-3 py-2 text-xs">
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

const dotTone: Record<PillTone, string> = {
  primary: "bg-primary ring-primary/15",
  success: "bg-success ring-success/15",
  warn: "bg-amber-500 ring-amber-500/15",
  error: "bg-destructive ring-destructive/15",
  gray: "bg-muted-foreground/60 ring-muted-foreground/15",
  info: "bg-info ring-info/15",
};

/** 状态圆点：6px 实心 + 3px 同色光环（原型 .dot-* 习语，光环=ring 3px 同色 15%）。 */
export function StatusDot({ tone = "gray" }: { tone?: PillTone }) {
  return (
    <span
      aria-hidden
      className={cn("size-1.5 shrink-0 rounded-full ring-[3px]", dotTone[tone])}
    />
  );
}
