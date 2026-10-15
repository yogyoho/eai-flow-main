"use client";

import type { ReactElement, ReactNode } from "react";

import {
  TableCell,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  icon?: ReactElement;
  /** 标题右侧的附加内容（如路径 chip+面包屑）。 */
  extra?: ReactNode;
}

export function PageHeader({
  title,
  description,
  actions,
  icon,
  extra,
}: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        {icon && (
          <div className="border-primary/20 bg-primary/10 text-primary shrink-0 rounded-sm border p-1">
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-foreground text-2xl font-bold">{title}</h1>
          {description ? (
            <p className="text-muted-foreground text-sm">{description}</p>
          ) : null}
        </div>
        {extra}
      </div>
      {actions ? (
        <div className="flex items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

export function EmptyRow({
  colSpan,
  children,
}: {
  colSpan: number;
  children: ReactNode;
}) {
  return (
    <TableRow>
      <TableCell
        colSpan={colSpan}
        className="text-muted-foreground py-6 text-center text-sm"
      >
        {children}
      </TableCell>
    </TableRow>
  );
}
