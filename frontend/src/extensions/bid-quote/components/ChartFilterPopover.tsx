"use client";

import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import type { ChartFilter, SelfAttribute } from "@/extensions/bid-quote/types";

interface Props {
  chart: ChartFilter;
  onChange: (c: ChartFilter) => void;
  /** 启用的维度子集。 */
  enable: { selfAttribute?: boolean; goodsName?: string[] };
}

// 每图高级筛选 popover(折叠态跟随全局,展开叠加收紧)。selfAttribute 不进 SQL(前端 filter/渲染)。
export function ChartFilterPopover({ chart, onChange, enable }: Props) {
  const [open, setOpen] = useState(false);
  const setAttr = (a: SelfAttribute) =>
    onChange({ ...chart, selfAttribute: a });
  const toggleGoods = (g: string) => {
    const cur = chart.goodsName ?? [];
    onChange({
      ...chart,
      goodsName: cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g],
    });
  };
  // "all" 仍算已选(按钮高亮跟随),故用显式布尔而非 ?? 语义
  const active = !!chart.selfAttribute || (chart.goodsName?.length ?? 0) > 0;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        className={
          "flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors " +
          (active
            ? "border-primary text-primary"
            : "border-border text-muted-foreground hover:text-foreground")
        }
      >
        <SlidersHorizontal className="h-3 w-3" />
        筛选
      </button>
      {open && (
        <div className="border-border bg-popover absolute top-7 right-0 z-20 w-48 rounded-lg border p-2 shadow-xl">
          {enable.selfAttribute && (
            <div className="mb-2" role="group" aria-label="自产属性">
              <div className="text-muted-foreground mb-1 text-[11px]">
                自产属性
              </div>
              {(
                [
                  "all",
                  "self_dominant",
                  "outsource_dominant",
                ] as SelfAttribute[]
              ).map((a) => (
                <button
                  key={a}
                  aria-pressed={(chart.selfAttribute ?? "all") === a}
                  onClick={() => setAttr(a)}
                  className={
                    "mr-1 rounded px-1.5 py-0.5 text-[11px] " +
                    ((chart.selfAttribute ?? "all") === a
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground")
                  }
                >
                  {a === "all"
                    ? "全部"
                    : a === "self_dominant"
                      ? "自产为主"
                      : "外购为主"}
                </button>
              ))}
            </div>
          )}
          {enable.goodsName && enable.goodsName.length > 0 && (
            <div role="group" aria-label="货物">
              <div className="text-muted-foreground mb-1 text-[11px]">货物</div>
              <div className="flex max-h-32 flex-wrap gap-1 overflow-auto">
                {enable.goodsName.map((g) => (
                  <button
                    key={g}
                    aria-pressed={(chart.goodsName ?? []).includes(g)}
                    onClick={() => toggleGoods(g)}
                    className={
                      "rounded border px-1.5 py-0.5 text-[11px] " +
                      ((chart.goodsName ?? []).includes(g)
                        ? "border-primary text-primary"
                        : "border-border text-muted-foreground")
                    }
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
