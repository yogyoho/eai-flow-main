"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 ReviewView — 审「漏脱」只看命中清单
// (规则/档位/位置/哈希),不回看全文。bid-quote 原语体系(SectionCard/FilterBar 风格下拉/ui table)。
import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import {
  ACCENT_SOFT,
  AMBER,
  BLUE,
  GREEN,
  INK,
  INK_2,
  INK_3,
  PAGE_BG,
  RED,
} from "@/extensions/geo-samples/components/chartTheme";
import {
  SelectDropdown,
  type GsbOption,
} from "@/extensions/geo-samples/components/FilterBar";
import { SectionCard } from "@/extensions/geo-samples/components/SectionCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/geo-samples/components/ui/table";
import {
  useGsbDocuments,
  useGsbRedactions,
  useGsbReview,
} from "@/extensions/geo-samples/hooks";

export function ReviewView() {
  const [docId, setDocId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const { data } = useGsbDocuments({ status: "redacted" });
  const { data: reds } = useGsbRedactions(docId);
  const review = useGsbReview();
  const docs = data?.items ?? [];
  const docOptions: GsbOption[] = docs.map((d) => ({
    value: d.id,
    label: `${d.report_id}（${d.file_name}）`,
  }));

  return (
    <div
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold" style={{ color: INK }}>
          脱敏抽审
        </h1>
      </div>

      {/* ① 选择待审样例 */}
      <SectionCard
        badge="①"
        title="选择待审样例"
        sub="仅列出已脱敏（redacted）状态的样例；通过后进 reviewed，驳回退回脱敏"
      >
        <div className="border-border bg-card rounded-xl border p-4">
          <div className="max-w-md">
            <SelectDropdown
              ariaLabel="待审样例"
              value={docId ?? ""}
              allLabel={`选择待审样例（${docs.length}）`}
              options={docOptions}
              onChange={(v) => setDocId(v || null)}
            />
          </div>
          {docs.length === 0 && (
            <p className="mt-2 text-[13px]" style={{ color: INK_3 }}>
              暂无待审样例（先在样例文档库完成脱敏）
            </p>
          )}
        </div>
      </SectionCard>

      {/* ② 命中清单 + 裁决 */}
      <SectionCard
        badge="②"
        title="脱敏命中清单"
        sub="审「漏脱」只看 规则/档位/位置/哈希，不回看全文；琥珀行 = 待审标记（mode=review）"
      >
        {docId ? (
          <>
            <div className="border-border bg-card rounded-xl border p-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>规则</TableHead>
                    <TableHead>档位</TableHead>
                    <TableHead>位置</TableHead>
                    <TableHead>原文哈希（前12）</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(reds?.items ?? []).map((r) => (
                    <TableRow
                      key={r.id}
                      style={
                        r.mode === "review"
                          ? { background: ACCENT_SOFT }
                          : undefined
                      }
                    >
                      <TableCell className="text-[13px]">{r.rule}</TableCell>
                      <TableCell
                        className="text-[13px]"
                        style={{ color: r.mode === "auto" ? INK_2 : AMBER }}
                      >
                        {r.mode === "auto" ? "自动替换" : "待审标记"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {r.start}–{r.end}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {r.original_hash.slice(0, 12)}…
                      </TableCell>
                    </TableRow>
                  ))}
                  {(reds?.items ?? []).length === 0 && (
                    <TableRow>
                      <TableCell
                        colSpan={4}
                        className="text-muted-foreground py-6 text-center text-sm"
                      >
                        无命中记录
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            <div className="space-y-3">
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="审核备注（reject 时必填理由）"
                className="border-border bg-background placeholder:text-muted-foreground/60 focus:border-foreground/40 w-full rounded-md border p-2 text-[14px] outline-none"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() =>
                    review.mutate({
                      id: docId,
                      decision: "approve",
                      note: note || null,
                    })
                  }
                  className="cursor-pointer rounded-md px-3 py-1.5 text-[14px] font-medium text-white"
                  style={{ background: GREEN }}
                >
                  通过（reviewed）
                </button>
                <button
                  type="button"
                  onClick={() =>
                    review.mutate({
                      id: docId,
                      decision: "reject",
                      note: note || "未写理由",
                    })
                  }
                  className="cursor-pointer rounded-md px-3 py-1.5 text-[14px] font-medium text-white"
                  style={{ background: RED }}
                >
                  驳回（退回脱敏）
                </button>
              </div>
            </div>
          </>
        ) : (
          <p className="text-[13px]" style={{ color: INK_3 }}>
            请先在上方选择待审样例
          </p>
        )}
      </SectionCard>
    </div>
  );
}
