/**
 * 骨架页共用件（EAI-CUSTOM）：页头（菜单图标 + 条款号 + 标题 + 描述 + 动作区）与基础芯片。
 * 令牌与组件惯例对齐 EAI 主系统（globals.css Yuxi 暖灰 + #0746ff 蓝）。
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 页头：菜单项图标 + 条款号 chip + 标题，下方一行描述（12px）；右侧动作区。 */
export function PageHeader({
  clause,
  icon: Icon,
  title,
  description,
  actions,
}: {
  clause: string;
  icon?: LucideIcon;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end gap-3">
      {Icon ? <Icon className="text-primary mb-0.5 h-[18px] w-[18px] flex-none" /> : null}
      <span className="border-primary/25 bg-primary/8 text-primary rounded-md border px-2 py-0.5 font-mono text-[11px]">
        {clause}
      </span>
      <h1 className="text-foreground text-lg font-semibold tracking-tight">{title}</h1>
      {actions ? <div className="ml-auto flex gap-2">{actions}</div> : null}
      <p className="text-muted-foreground mt-1 w-full text-xs">{description}</p>
    </div>
  );
}

/** 状态芯片：语义色走 destructive/warning/primary（对齐主系统状态色惯例）。 */
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
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium whitespace-nowrap",
        tone === "gray" && "border-border text-muted-foreground border",
        tone === "primary" && "bg-primary/10 text-primary",
        tone === "danger" && "bg-destructive/10 text-destructive",
        tone === "warning" && "bg-warning/15 text-warning",
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
        "border-border bg-card rounded-xl border shadow-sm",
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
