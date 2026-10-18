"use client";

import type { ReactElement, ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactElement;
  /** 标题右侧的附加内容（如路径 chip / 面包屑）。 */
  extra?: ReactNode;
  /** 卡片右上角的辅助文案（如语言对 / 范围说明）。 */
  topRight?: ReactNode;
}

/**
 * 翻译工作台页头卡（EAI-CUSTOM, 2026-10-18）。
 *
 * 视觉对齐合同价格分析模块 `extensions/contract-price/components/PageHeader.tsx`
 * （习语源自 2026-10-12 eia-p2 原型 .page-head）：白卡 + 主色细网格底纹
 * + 左实右透渐变遮罩 + 34px 图标容器；token 落本系统语义层。
 */
export function PageHeader({
  title,
  description,
  actions,
  icon,
  extra,
  topRight,
}: PageHeaderProps) {
  return (
    <div className="border-border bg-card relative shrink-0 overflow-hidden rounded-lg border">
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
          <div className="bg-primary/10 text-primary flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-md [&_svg]:h-[18px] [&_svg]:w-[18px]">
            {icon}
          </div>
        ) : null}
        <div className="min-w-0">
          <h1 className="text-foreground text-base leading-snug font-semibold">
            {title}
          </h1>
          {description ? (
            <div className="text-muted-foreground text-xs">{description}</div>
          ) : null}
        </div>
        {extra}
        {topRight ? (
          /* 右上角：辅助文案贴顶，动作其下 */
          <div className="ml-auto flex shrink-0 flex-col items-end gap-1 self-start">
            <div className="text-muted-foreground text-[11px]">
              {topRight}
            </div>
            {actions ? (
              <div className="flex items-center gap-2">{actions}</div>
            ) : null}
          </div>
        ) : actions ? (
          /* 无右上角文案时保持 cpa 的垂直居中动作位 */
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>
    </div>
  );
}
