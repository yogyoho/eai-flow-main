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

/**
 * 页头卡（cpa UI 重构规范 §2-1，docs/designs/2026-10-16-cpa-ui-restyle-spec.md）。
 * EAI-CUSTOM: 视觉习语取自 2026-10-12 eia-p2 原型 .page-head —— 白卡 + 主色细网格
 * 底纹 + 左实右透渐变遮罩 + 34px 图标容器；token 落本系统语义层（primary/card）。
 */
export function PageHeader({
  title,
  description,
  actions,
  icon,
  extra,
}: PageHeaderProps) {
  return (
    <div className="border-border bg-card relative overflow-hidden rounded-lg border">
      {/* 细网格底纹：1px 主色线条 / 26px 网格，8% 透明度压底 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          opacity: 0.08,
          backgroundImage:
            "linear-gradient(to right, var(--color-primary) 1px, transparent 1px), linear-gradient(to bottom, var(--color-primary) 1px, transparent 1px)",
          backgroundSize: "26px 26px, 26px 26px",
          backgroundPosition: "8px 8px, 8px 8px",
        }}
      />
      {/* 左实右透渐变：保证标题可读，点阵只在右端透出 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-r from-card from-55% to-transparent"
      />
      <div className="relative flex flex-wrap items-center gap-3 px-[18px] py-3">
        {icon ? (
          /* 图标容器统一 34px / 18px 线框（lucide 尺寸由父级归一，调用点无需传 h-6） */
          <div className="bg-primary/10 text-primary flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-md [&_svg]:h-[18px] [&_svg]:w-[18px]">
            {icon}
          </div>
        ) : null}
        <div className="min-w-0">
          <h1 className="text-foreground text-base leading-snug font-semibold">
            {title}
          </h1>
          {description ? (
            <p className="text-muted-foreground text-xs">{description}</p>
          ) : null}
        </div>
        {extra}
        {actions ? (
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>
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
