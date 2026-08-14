"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/bid-quote/components/ui/table";
import { useDrillDown } from "@/extensions/bid-quote/hooks";
import { type SelfAttribute } from "@/extensions/bid-quote/types";

interface DrillDownModalProps {
  title: string;
  /** 已拼好的参数化只读 SQL(白名单维度,值来自行数据)。null 时关闭。 */
  sql: string | null;
  onClose: () => void;
}

// 通用下钻 modal:标题 + sql → 明细 table。下钻 SQL 走后端 assert_readonly_select 守卫。
// no-base-to-string: 行单元格为 unknown(SQL JSON),收窄后再 String()。
const cellText = (v: unknown) =>
  v === null || v === undefined
    ? ""
    : typeof v === "object"
      ? JSON.stringify(v)
      : String(v as string | number | boolean);

// 二次筛选 chips(仅货物明细行):与货物构成图 selfAttribute 语义一致。
const ATTR_CHIPS: { key: SelfAttribute; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "self_dominant", label: "自产为主" },
  { key: "outsource_dominant", label: "外购为主" },
];

// 货物明细行的自产占比:由 self/outsourced 金额现算 pct(matchesSelfAttribute 只收现成 pct 列)。
// Decimal 列经 JSON 为 string → Number 归一;null/非数值按 0,s+o<=0 时记 0。
const rowSelfPct = (r: Record<string, unknown>): number => {
  const s = Number(r.self_amount ?? 0);
  const o = Number(r.outsourced_amount ?? 0);
  if (!Number.isFinite(s) || !Number.isFinite(o) || s + o <= 0) return 0;
  return (100 * s) / (s + o);
};

// 自产/外购列高亮:表头绿/琥珀浅色,数据列深一档 + font-medium 突出金额。
const headCls = (c: string) =>
  c === "self_amount"
    ? "text-green-500"
    : c === "outsourced_amount"
      ? "text-amber-500"
      : "";
const cellCls = (c: string) =>
  c === "self_amount"
    ? "text-green-600 font-medium"
    : c === "outsourced_amount"
      ? "text-amber-600 font-medium"
      : "";

export function DrillDownModal({ title, sql, onClose }: DrillDownModalProps) {
  const { data, isLoading, error } = useDrillDown(sql);
  const [attr, setAttr] = useState<SelfAttribute>("all");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (sql) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sql, onClose]);

  // 切换下钻目标时重置二次筛选
  useEffect(() => {
    setAttr("all");
  }, [sql]);

  if (!sql) return null;
  const rows = data?.rows ?? [];
  // noUncheckedIndexedAccess: rows[0] 推断为 T|undefined,length 守卫不收窄 → 显式判空。
  const first = rows[0];
  // 货物明细行判定:首行含 self_amount 列(mock_bid_item 投标明细/货物明细)
  const isItemRows = !!first && "self_amount" in first;
  const visibleRows = isItemRows
    ? rows.filter((r) =>
        attr === "all"
          ? true
          : attr === "self_dominant"
            ? rowSelfPct(r) >= 50
            : rowSelfPct(r) < 50,
      )
    : rows;
  // noUncheckedIndexedAccess: rows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const cols = rows.length ? Object.keys(rows[0] ?? {}) : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="border-border bg-background flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-border flex items-center justify-between border-b px-5 py-3">
          <h3 className="font-cyber text-foreground text-sm font-bold">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              加载中…
            </p>
          ) : error ? (
            <p className="text-destructive py-8 text-center text-sm">
              加载失败:{String(error)}
            </p>
          ) : visibleRows.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              无明细数据
            </p>
          ) : (
            <>
              {/* 货物明细二次筛选(自产属性) */}
              {isItemRows && (
                <div
                  role="group"
                  aria-label="货物筛选"
                  className="mb-3 flex gap-2"
                >
                  {ATTR_CHIPS.map((a) => (
                    <button
                      key={a.key}
                      onClick={() => setAttr(a.key)}
                      aria-pressed={attr === a.key}
                      className={
                        "rounded-full border px-3 py-1 text-xs font-medium transition-colors " +
                        (attr === a.key
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:text-foreground")
                      }
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              )}
              <Table>
                <TableHeader>
                  <TableRow>
                    {cols.map((c) => (
                      <TableHead key={c} className={headCls(c)}>
                        {c}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleRows.map((r, i) => (
                    <TableRow key={i} className="cursor-default">
                      {cols.map((c) => (
                        <TableCell key={c} className={cellCls(c)}>
                          {cellText(r[c])}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </div>
        <div className="border-border text-muted-foreground/70 border-t px-5 py-2 text-[11px]">
          共 {data?.row_count ?? 0} 条 · {sql}
        </div>
      </div>
    </div>
  );
}
