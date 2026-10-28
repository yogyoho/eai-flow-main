/**
 * Page shared primitives (EAI-CUSTOM): page header (icon + clause + title + description + actions)
 * and basic chips. Tokens follow docs/designs prototype (indigo / orange / zinc).
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { withAlpha } from "@/explorer/graphTheme";
import { cn } from "@/lib/utils";

/** Page header: dotted-grid card, icon tile, kicker, title, subtitle and right-side actions. */
export function PageHeader({
  clause,
  icon: Icon,
  title,
  description,
  actions,
}: {
  clause?: string;
  icon?: LucideIcon;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="os-page-head">
      {Icon ? (
        <div className="os-ph-icon">
          <Icon />
        </div>
      ) : null}
      <div className="os-ph-main">
        {clause ? <div className="os-ph-kicker">{clause}</div> : null}
        <h1 className="os-ph-title">{title}</h1>
        <p className="os-ph-sub">{description}</p>
      </div>
      {actions ? <div className="os-ph-actions">{actions}</div> : null}
    </div>
  );
}

/** Status chip: semantic tone mapped to the prototype pill palette. */
export function Chip({
  tone = "gray",
  children,
}: {
  tone?: "gray" | "primary" | "danger" | "warning";
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "os-pill whitespace-nowrap",
        tone === "gray" && "os-pill-gray",
        tone === "primary" && "os-pill-main",
        tone === "danger" && "os-pill-err",
        tone === "warning" && "os-pill-warn",
      )}
    >
      {children}
    </span>
  );
}

/** Card container: surface + hairline + optional header row.
 *  tone (EAI-CUSTOM 2026-09-27): colorizes the header icon; header background stays neutral
 *  (prototype convention: color lives in the icon, not in a tinted band). */
export function Panel({
  title,
  subtitle,
  actions,
  tone,
  icon: Icon,
  className,
  children,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  tone?: string;
  icon?: LucideIcon;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("os-card", className)}>
      {title ? (
        <div className="os-card-hd">
          {/* Color is carried by the icon; without an icon fall back to a color dot. */}
          {tone && !Icon ? (
            <span
              className="h-2.5 w-2.5 flex-none rounded-[4px]"
              style={{ background: tone }}
            />
          ) : null}
          {Icon ? (
            <Icon
              className="h-4 w-4 flex-none"
              style={tone ? { color: tone } : undefined}
            />
          ) : null}
          <b>{title}</b>
          {subtitle ? <span className="os-card-sub">{subtitle}</span> : null}
          {actions ? <div className="os-card-right">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Skeleton watermark: marks "sample data" so placeholder content is never mistaken for real data. */
export function DemoTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "text-muted-foreground/70 border-border/70 rounded border border-dashed px-1.5 py-px font-mono text-xs",
        className,
      )}
      style={{ borderColor: withAlpha("#71717a", 0.35) }}
    >
      示例数据
    </span>
  );
}
