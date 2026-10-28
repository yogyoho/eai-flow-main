/**
 * Lightweight table primitives (raw HTML) for the contract-price module.
 *
 * This project has no shadcn `Table` component (admin pages use raw <table>).
 * These provide the same API surface (Table/TableHeader/TableBody/TableRow/
 * TableHead/TableCell) so views stay readable.
 *
 * EAI-CUSTOM: 密度对齐 cpa UI 重构规范 §2-3（2026-10-12 eia-p2 原型 .tbl）——
 * 表头 12px medium 非 uppercase、单元格 px-3 py-2、行 hover muted/50。
 */

import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Table({
  className,
  ...props
}: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-left text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function TableHeader({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  // 表头行下划线用强一档的 border（原型 .tbl th 底 = hairline），行分隔线见 TableRow
  return (
    <thead
      className={cn("[&_tr]:border-border [&_tr]:border-b", className)}
      {...props}
    />
  );
}

export function TableBody({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  );
}

export function TableRow({
  className,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        // 行分隔线：border 70% 透明度——比表头下划线浅一档但清晰可辨
        // （首版 border-muted 太浅在部分显示器上不可见，用户反馈 2026-10-16）
        "border-border/70 hover:bg-muted/50 data-[state=selected]:bg-muted border-b transition-colors",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "text-muted-foreground px-3 py-2.5 text-start align-middle text-xs font-medium",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2 align-middle", className)} {...props} />;
}
