"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/sales-personnel/components/ui/table";
import { useDrillDown } from "@/extensions/sales-personnel/hooks";

interface DrillDownModalProps {
  title: string;
  /** 已拼好的参数化只读 SQL(白名单维度,值来自行数据)。null 时关闭。 */
  sql: string | null;
  onClose: () => void;
}

// 通用下钻 modal:标题 + sql → 明细 table。下钻 SQL 走后端 assert_readonly_select 守卫。
// no-base-to-string: 行单元格为 unknown(SQL JSON),收窄后再 String()。
const cellText = (v: unknown) =>
  v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v as string | number | boolean);

export function DrillDownModal({ title, sql, onClose }: DrillDownModalProps) {
  const { data, isLoading, error } = useDrillDown(sql);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (sql) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sql, onClose]);

  if (!sql) return null;
  const rows = data?.rows ?? [];
  // noUncheckedIndexedAccess: rows[0] 推断为 T|undefined,length 守卫不收窄 → ?? {} 兜底。
  const cols = rows.length ? Object.keys(rows[0] ?? {}) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-cyber text-sm font-bold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
          ) : error ? (
            <p className="py-8 text-center text-sm text-destructive">加载失败:{String(error)}</p>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">无明细数据</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {cols.map((c) => (
                    <TableHead key={c}>{c}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i} className="cursor-default">
                    {cols.map((c) => (
                      <TableCell key={c}>{cellText(r[c])}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <div className="border-t border-border px-5 py-2 text-[11px] text-muted-foreground/70">
          共 {data?.row_count ?? 0} 条 · {sql}
        </div>
      </div>
    </div>
  );
}
