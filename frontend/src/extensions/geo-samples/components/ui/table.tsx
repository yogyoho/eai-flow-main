/**
 * Lightweight table primitives(raw HTML)—— geo-samples 模块用。
 * forked from bid-quote/components/ui/table.tsx(EAI-CUSTOM: geo-sample-bank Phase 1,
 * 复制模式,同 bid-quote→contract-price 惯例);去掉 cursor-pointer——本模块行不可点击。
 * 本项目无 shadcn Table,沿用同款 API(Table/TableHeader/TableBody/TableRow/TableHead/TableCell)。
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
  return <thead className={cn("[&_tr]:border-b", className)} {...props} />;
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
        "border-border hover:bg-muted/50 border-b transition-colors",
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
        "text-muted-foreground h-10 px-2 text-start align-middle text-xs font-medium tracking-wider uppercase",
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
  return <td className={cn("p-2 align-middle", className)} {...props} />;
}
