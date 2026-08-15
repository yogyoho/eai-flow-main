"use client";

import { useMemo } from "react";

import {
  ACCENT_SOFT,
  BLUE,
  CARD,
  CARD_BORDER,
  GREEN,
  INK,
  INK_2,
  INK_3,
  RED,
} from "@/extensions/bid-quote/components/chartTheme";
import {
  useCompetitorGoods,
  useCompetitorProfile,
} from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

interface CompetitorProfileTableProps {
  filters: FilterState;
  /** 点行下钻(与项目报价对比图同 DrillDownModal 通道)。 */
  onDrill: (d: { title: string; sql: string }) => void;
}

/**
 * 图10(新增):友商画像 — 表+条混合(原型 block3-competitors 图A):
 * 每行一家友商:中标率横条(灰竖标=市场均值)/ 平均溢价(负=低价抢标型,绿色)/
 * 优势领域 chips(中标行货物金额 Top2)/ 同期项目数。点行下钻对阵明细。
 */
export function CompetitorProfileTable({
  filters,
  onDrill,
}: CompetitorProfileTableProps) {
  const q = useCompetitorProfile(filters);
  const goodsQ = useCompetitorGoods(filters);

  const rows = q.data ?? [];
  // 市场均值线 = 全部友商合计 中标数/投标数
  const totBid = rows.reduce((s, r) => s + r.bids, 0);
  const totWin = rows.reduce((s, r) => s + r.wins, 0);
  const meanRate = totBid > 0 ? (100 * totWin) / totBid : 0;

  // 优势领域:按友商取货物金额 Top2
  const chips = useMemo(() => {
    const m = new Map<string, { goods: string; amt: number }[]>();
    for (const g of goodsQ.data ?? []) {
      const list = m.get(g.bidder_name) ?? [];
      list.push({ goods: g.goods_name, amt: Number(g.amt ?? 0) });
      m.set(g.bidder_name, list);
    }
    const top = new Map<string, string[]>();
    for (const [name, list] of m) {
      top.set(
        name,
        [...list]
          .sort((a, b) => b.amt - a.amt)
          .slice(0, 2)
          .map((x) => x.goods),
      );
    }
    return top;
  }, [goodsQ.data]);

  return (
    <div
      className="rounded-[14px] p-5"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <div className="mb-3.5">
        <h3 className="text-[14.5px] font-semibold" style={{ color: INK }}>
          友商画像
        </h3>
        <p className="mt-0.5 text-xs" style={{ color: INK_3 }}>
          点击行 → 该友商与我们的<b style={{ color: INK_2 }}>遭遇战详情</b> · 竖标
          = 市场均值 {meanRate.toFixed(0)}%
        </p>
      </div>
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            {["友商", "中标率", "平均溢价", "优势领域", "同期项目"].map((h) => (
              <th
                key={h}
                className="border-b px-2.5 py-1.5 text-left text-[11.5px] font-normal"
                style={{ borderColor: "#f0f0ef", color: INK_3 }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const rate = r.win_rate === null ? 0 : Number(r.win_rate);
            const prem = r.avg_premium_pct === null ? null : Number(r.avg_premium_pct);
            return (
              <tr
                key={r.bidder_name}
                className="cursor-pointer transition-colors hover:bg-[#f7f8f8]"
                onClick={() => onDrill({
                  title: `对阵明细 · ${r.bidder_name}`,
                  // 该友商参与的项目的全部投标行(含我方)——与遭遇战口径一致
                  sql: `SELECT project_name, bidder_name, winning_price, won FROM mock_bid WHERE project_name IN (SELECT project_name FROM mock_bid WHERE bidder_name='${r.bidder_name.replaceAll("'", "''")}' AND bidder_role='competitor') ORDER BY project_name, winning_price`,
                })}
              >
                <td
                  className="border-b px-2.5 py-2 font-semibold"
                  style={{ borderColor: "#f0f0ef", color: INK }}
                >
                  {r.bidder_name}
                </td>
                <td className="border-b px-2.5 py-2" style={{ borderColor: "#f0f0ef" }}>
                  {/* 中标率横条 + 市场均值竖标(原型 .ratebar) */}
                  <div
                    className="relative h-[9px] w-[120px] rounded-[5px]"
                    style={{ background: "#f0f0ef" }}
                    title={`中标率 ${rate}% vs 均值 ${meanRate.toFixed(0)}% · ${r.wins}/${r.bids}`}
                  >
                    <i
                      className="absolute top-0 bottom-0 left-0 rounded-[5px]"
                      style={{ width: `${Math.min(rate, 100)}%`, background: BLUE }}
                    />
                    <em
                      className="absolute -top-0.5 h-[13px] w-[2px] not-italic"
                      style={{
                        left: `${Math.min(meanRate, 100)}%`,
                        background: INK_3,
                      }}
                    />
                  </div>
                </td>
                <td
                  className="border-b px-2.5 py-2 font-semibold [font-variant-numeric:tabular-nums]"
                  style={{
                    borderColor: "#f0f0ef",
                    color: prem === null ? INK_3 : prem < 0 ? GREEN : RED,
                  }}
                >
                  {prem === null
                    ? "—"
                    : `${prem < 0 ? "−" : "+"}${Math.abs(prem).toFixed(1)}%`}
                </td>
                <td className="border-b px-2.5 py-2" style={{ borderColor: "#f0f0ef" }}>
                  {(chips.get(r.bidder_name) ?? []).map((g) => (
                    <span
                      key={g}
                      className="mr-1 rounded-[5px] px-[7px] py-0.5 text-[11px]"
                      style={{ background: ACCENT_SOFT, color: BLUE }}
                    >
                      {g}
                    </span>
                  ))}
                </td>
                <td
                  className="border-b px-2.5 py-2 font-semibold [font-variant-numeric:tabular-nums]"
                  style={{ borderColor: "#f0f0ef", color: INK }}
                >
                  {r.projects}
                </td>
              </tr>
            );
          })}
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                className="px-2.5 py-6 text-center text-xs"
                style={{ color: INK_3 }}
              >
                {q.isLoading ? "加载中…" : "当前过滤下无友商数据"}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
      <p className="mt-3 text-xs" style={{ color: INK_3 }}>
        平均溢价 = 该友商报价相对中标价的均值(负 = 惯于低价抢标)。
      </p>
    </div>
  );
}
