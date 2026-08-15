"use client";

import { useEffect, useState } from "react";

import {
  BLUE,
  CARD,
  CARD_BORDER,
  INK,
  INK_2,
  INK_3,
} from "@/extensions/bid-quote/components/chartTheme";
import { useHead2Head } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

/**
 * 图11(新增):遭遇战 — 选定友商与我方在共同投标项目上的直接对垒(原型 block3-competitors 图C):
 * 大数字比分 + 力量对比条 + 分年度成对条。点卡片下钻对阵项目明细。
 */
export function HeadToHeadCard({
  filters,
  competitors,
  onDrill,
}: {
  filters: FilterState;
  competitors: string[];
  onDrill: (d: { title: string; sql: string }) => void;
}) {
  const [selected, setSelected] = useState<string | null>(competitors[0] ?? null);
  // 竞争对手列表刷新后若当前选中项消失,自动回退到第一项
  useEffect(() => {
    if (competitors.length && !competitors.includes(selected ?? "")) {
      setSelected(competitors[0] ?? null);
    }
  }, [competitors, selected]);

  const q = useHead2Head(filters, selected);
  const rows = q.data ?? [];
  const oursTotal = rows.reduce((s, r) => s + Number(r.ours_wins), 0);
  const compTotal = rows.reduce((s, r) => s + Number(r.comp_wins), 0);
  const total = oursTotal + compTotal;
  const oursRate = total > 0 ? (100 * oursTotal) / total : 0;

  const escName = (selected ?? "").replaceAll("'", "''");
  const drillSql = `SELECT project_name, bidder_name, winning_price, won FROM mock_bid WHERE project_name IN (SELECT project_name FROM mock_bid WHERE bidder_name='${escName}' AND bidder_role='competitor') ORDER BY project_name, winning_price`;

  return (
    <div
      className="flex cursor-pointer flex-col rounded-[14px] p-5"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
      onClick={() => selected && onDrill({ title: `遭遇战 · ${selected}`, sql: drillSql })}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[14.5px] font-semibold" style={{ color: INK }}>
            遭遇战
          </h3>
          <p className="mt-0.5 text-xs" style={{ color: INK_3 }}>
            共同投标项目直接对垒 · 点击查看明细
          </p>
        </div>
        <select
          className="rounded-lg px-2.5 py-1.5 text-xs outline-none"
          style={{ border: `1px solid ${CARD_BORDER}`, color: INK_2, background: CARD }}
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value)}
          onClick={(e) => e.stopPropagation()} // 切换对手不触发卡片下钻
        >
          {competitors.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      {competitors.length === 0 ? (
        <p className="py-6 text-center text-xs" style={{ color: INK_3 }}>
          当前过滤下无友商
        </p>
      ) : (
        <>
          {/* 大数字比分(原型 .score) */}
          <div className="flex items-end justify-center gap-6 py-1">
            <div className="text-center">
              <div
                className="text-[44px] leading-none font-[650] [font-variant-numeric:tabular-nums]"
                style={{ color: BLUE }}
              >
                {oursTotal}
              </div>
              <div className="mt-1.5 text-xs" style={{ color: INK_2 }}>
                我方胜
              </div>
            </div>
            <div className="pb-6 text-sm" style={{ color: INK_3 }}>
              vs
            </div>
            <div className="text-center">
              <div
                className="text-[44px] leading-none font-[650] [font-variant-numeric:tabular-nums]"
                style={{ color: INK_3 }}
              >
                {compTotal}
              </div>
              <div className="mt-1.5 text-xs" style={{ color: INK_2 }}>
                {selected ?? "对方"}胜
              </div>
            </div>
          </div>
          {/* 力量对比条 */}
          <div
            className="relative mt-4 h-[14px] overflow-hidden rounded-[7px]"
            style={{ background: "#f0f0ef" }}
          >
            {oursRate > 0 ? (
              <div
                className="flex h-full items-center justify-start pl-2 text-[10px] font-semibold text-white [font-variant-numeric:tabular-nums]"
                style={{ width: `${oursRate}%`, background: BLUE }}
              >
                {oursRate >= 25 ? `${Math.round(oursRate)}%` : ""}
              </div>
            ) : null}
          </div>

          {/* 分年度成对条 */}
          <div className="mt-5 flex items-end justify-center gap-8">
            {rows.map((r) => {
              const max = Math.max(Number(r.ours_wins), Number(r.comp_wins), 1);
              return (
                <div key={r.yr} className="flex flex-col items-center gap-1.5">
                  <div className="flex h-[70px] items-end gap-2">
                    <div
                      className="w-[14px] rounded-t-[3px]"
                      style={{ height: `${(100 * Number(r.ours_wins)) / max}%`, background: BLUE }}
                      title={`${r.yr} 我方 ${r.ours_wins} 胜`}
                    />
                    <div
                      className="w-[14px] rounded-t-[3px]"
                      style={{ height: `${(100 * Number(r.comp_wins)) / max}%`, background: "#e3e5e4" }}
                      title={`${r.yr} ${selected} ${r.comp_wins} 胜`}
                    />
                  </div>
                  <span className="text-[11px] [font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
                    {r.yr}
                  </span>
                </div>
              );
            })}
          </div>

          <p className="mt-4 text-xs" style={{ color: INK_3 }}>
            仅统计双方共同投标的项目。
          </p>
        </>
      )}
    </div>
  );
}
