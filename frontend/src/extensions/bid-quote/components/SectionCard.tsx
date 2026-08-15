"use client";

import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import {
  ACCENT_SOFT,
  BLUE,
  INK,
  INK_2,
  INK_3,
} from "@/extensions/bid-quote/components/chartTheme";
import { cn } from "@/lib/utils";


interface SectionCardProps {
  /** 区块序号徽标(①/②/③,原型 .section-badge)。 */
  badge: string;
  /** 区块标题 = 使用者的问题(如"我们赢在哪、输在哪?")。 */
  title: string;
  /** 标题下副行(原型 .section-sub)。 */
  sub?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * 三问框架可折叠区块:标题即问题(原型 block1~3 的 .section-title 结构),
 * 默认展开,点标题行折叠/展开。
 */
export function SectionCard({
  badge,
  title,
  sub,
  defaultOpen = true,
  children,
}: SectionCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="space-y-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 pt-1 text-left"
      >
        <span
          className="mt-0.5 rounded-md px-2 py-0.5 text-xs font-semibold"
          style={{ background: ACCENT_SOFT, color: BLUE }}
        >
          {badge}
        </span>
        <span>
          <span
            className="block text-[17px] leading-snug font-semibold"
            style={{ color: INK }}
          >
            {title}
          </span>
          {sub ? (
            <span className="block text-[13px]" style={{ color: INK_2 }}>
              {sub}
            </span>
          ) : null}
        </span>
        <ChevronDown
          className={cn(
            "mt-1.5 ml-auto h-4 w-4 shrink-0 transition-transform",
            open && "rotate-180",
          )}
          style={{ color: INK_3 }}
        />
      </button>
      {open ? <div className="space-y-4">{children}</div> : null}
    </section>
  );
}
