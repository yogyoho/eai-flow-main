"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { DrillDownModal } from "@/extensions/biz-pipeline/components/DrillDownModal";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/biz-pipeline/components/ui/table";
import { useBidList, useContractRecon, useMonthlyBids } from "@/extensions/biz-pipeline/hooks";
import type { BidRow, MonthlyRow, ReconRow } from "@/extensions/biz-pipeline/types";

type TabKey = "bidlist" | "recon" | "monthly";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bidlist", label: "投标明细" },
  { key: "recon", label: "合同开票对账" },
  { key: "monthly", label: "月度投标节奏" },
];

// 清洗:单引号转义防 SQL 注入(值来自 DB 行数据,非用户自由输入),仅用于 SQL 拼接。
// no-base-to-string: v 为 unknown,需显式收窄后再 String()(对象走 JSON)。
const esc = (v: unknown) => {
  const s =
    v === null || v === undefined
      ? ""
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v as string | number | boolean);
  return s.replace(/'/g, "''");
};

export function QueryView() {
  const [tab, setTab] = useState<TabKey>("bidlist");
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(null);

  const bidQ = useBidList();
  const reconQ = useContractRecon();
  const monthlyQ = useMonthlyBids();

  const bidRows = bidQ.data ?? [];
  const reconRows = reconQ.data ?? [];
  const monthlyRows = monthlyQ.data ?? [];
  // 明细列动态(取首行列名);罐装视图列固定。
  // noUncheckedIndexedAccess: bidRows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const bidCols = bidRows.length ? Object.keys(bidRows[0] ?? {}) : [];

  const onRowDrill = (key: TabKey, row: BidRow | ReconRow | MonthlyRow) => {
    // 白名单维度:仅 contract_no / ym;值经 esc 转义后拼入只读 SELECT。
    if (key === "bidlist") {
      // 投标明细:仅中标行(contract_no 非空)可下钻到该合同开票明细;落标行禁用。
      const cn = (row as BidRow).contract_no;
      if (!cn) return;
      const v = esc(cn);
      setDrill({
        title: `合同开票明细 · ${v}`,
        sql: `SELECT invoice_id, invoice_date, amount, tax_amount, total_amount, status FROM mock_invoice WHERE contract_no='${v}' ORDER BY invoice_date`,
      });
    } else if (key === "recon") {
      const v = esc((row as ReconRow).contract_no);
      setDrill({
        title: `合同开票明细 · ${v}`,
        sql: `SELECT invoice_id, invoice_date, amount, tax_amount, total_amount, status FROM mock_invoice WHERE contract_no='${v}' ORDER BY invoice_date`,
      });
    } else {
      const v = esc((row as MonthlyRow).ym);
      setDrill({
        title: `月份投标明细 · ${v}`,
        sql: `SELECT bid_id, project_name, customer, bid_date, our_bid_amount, status, competitor_name FROM mock_pipeline_bid WHERE to_char(bid_date,'YYYY-MM')='${v}' ORDER BY bid_date`,
      });
    }
  };

  const loading = useMemo(
    () => (tab === "bidlist" ? bidQ.isLoading : tab === "recon" ? reconQ.isLoading : monthlyQ.isLoading),
    [tab, bidQ.isLoading, reconQ.isLoading, monthlyQ.isLoading],
  );

  const toWan = (v: unknown) => {
    const n = v === null || v === undefined ? null : Number(v);
    return n === null || Number.isNaN(n) ? "—" : `${(n / 10000).toFixed(1)}万`;
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">数据查询</h1>
      </div>

      {/* 视图 tab(pill) */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors " +
              (tab === t.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 当前视图表(点行下钻) */}
      <div className="rounded-xl border border-border bg-card p-4">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
        ) : tab === "bidlist" ? (
          <Table>
            <TableHeader>
              <TableRow>
                {bidCols.map((c) => (
                  <TableHead key={c}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {bidRows.map((r, i) => {
                const cn = r.contract_no;
                return (
                  <TableRow
                    key={i}
                    onClick={() => onRowDrill("bidlist", r)}
                    className={cn ? "cursor-pointer" : "cursor-default opacity-70"}
                  >
                    {bidCols.map((c) => (
                      // 显示用 String(原始值);r[c] 为 primitive(BidRow 类型),不触发 no-base-to-string
                      <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : tab === "recon" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>合同号</TableHead>
                <TableHead>合同名称</TableHead>
                <TableHead>客户</TableHead>
                <TableHead>合同额</TableHead>
                <TableHead>已开票</TableHead>
                <TableHead>待开票</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reconRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("recon", r)}>
                  <TableCell>{r.contract_no}</TableCell>
                  <TableCell>{r.contract_name}</TableCell>
                  <TableCell>{r.customer}</TableCell>
                  <TableCell>{toWan(r.amount)}</TableCell>
                  <TableCell>{toWan(r.invoiced)}</TableCell>
                  <TableCell className={Number(r.uninvoiced) > 0 ? "font-bold text-destructive" : ""}>
                    {toWan(r.uninvoiced)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>月份</TableHead>
                <TableHead>投标数</TableHead>
                <TableHead>中标数</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {monthlyRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("monthly", r)}>
                  <TableCell>{r.ym}</TableCell>
                  <TableCell>{r.bids}</TableCell>
                  <TableCell>{r.won}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DrillDownModal title={drill?.title ?? ""} sql={drill?.sql ?? null} onClose={() => setDrill(null)} />
    </div>
  );
}
