/**
 * 骨架页共用件（EAI-CUSTOM）：页头（条款号 + 衬线标题 + 描述 + 动作区）与基础芯片。
 * 视觉对照 docs/designs/ontostudio-frontend-design.html（青卷版）。
 */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 页头：左侧条款号 chip + 衬线大标题，下方一行描述；右侧动作区。 */
export function PageHeader({
  clause,
  title,
  description,
  actions,
}: {
  clause: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end gap-4">
      <span className="border-primary/25 bg-primary/8 text-primary rounded-md border px-2 py-0.5 font-mono text-[11px]">
        {clause}
      </span>
      <h1 className="font-display text-2xl font-black tracking-wide">{title}</h1>
      {actions ? <div className="ml-auto flex gap-2">{actions}</div> : null}
      <p className="text-muted-foreground w-full text-[13px]">{description}</p>
    </div>
  );
}

/** 状态芯片：语义色走 seal/warning/primary（青卷约定：朱砂只用于合规语义）。 */
export function Chip({
  tone = "gray",
  children,
}: {
  tone?: "gray" | "primary" | "seal" | "warning";
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium whitespace-nowrap",
        tone === "gray" && "border-border text-muted-foreground border",
        tone === "primary" && "bg-primary/10 text-primary",
        tone === "seal" && "bg-seal-wash text-seal",
        tone === "warning" && "bg-warning-wash text-warning",
      )}
    >
      {children}
    </span>
  );
}

/** 卡片容器：卡面 + 细边 + 可选标题行。 */
export function Panel({
  title,
  subtitle,
  actions,
  className,
  children,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "border-border bg-card rounded-lg border shadow-xs",
        className,
      )}
    >
      {title ? (
        <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
          <b className="text-sm font-semibold">{title}</b>
          {subtitle ? (
            <span className="text-muted-foreground text-xs font-normal">
              {subtitle}
            </span>
          ) : null}
          {actions ? <div className="ml-auto">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** 骨架占位水印：标注"示例数据"，防止占位内容被误读为真实数据。 */
export function DemoTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "text-muted-foreground/70 border-border/70 rounded border border-dashed px-1.5 py-px font-mono text-[10px]",
        className,
      )}
    >
      示例数据
    </span>
  );
}
