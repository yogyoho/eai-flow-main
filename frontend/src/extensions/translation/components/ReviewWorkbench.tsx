"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Check,
  ClipboardCheck,
  Download,
  FileText,
  Loader2,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { listReviewQueue, transitionTask } from "../api";
import type { TltTask } from "../types";

/** 机检轴的用户语标签（文案红线映射表）。 */
const GATE_LABELS: Record<string, string> = {
  numeric: "数字准确性",
  terminology: "术语一致性",
  structure: "格式完整性",
};


export function ReviewWorkbench() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["tlt-tasks"] });
  };

  const queueQ = useQuery({
    queryKey: ["tlt-review-queue"],
    queryFn: listReviewQueue,
    refetchInterval: 30_000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const queue = queueQ.data ?? [];
  const selected = queue.find((t) => t.id === selectedId) ?? queue[0] ?? null;

  const decide = async (t: TltTask, target: "indexed" | "archived") => {
    setBusy(true);
    try {
      await transitionTask(t.id, target);
      invalidate();
      setSelectedId(null);
      flash(target === "indexed" ? "已通过并交付" : "已驳回归档");
    } catch (e) {
      flash(`操作失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const [flashMsg, setFlashMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const flash = (text: string) => {
    setFlashMsg({ kind: "err", text });
    window.setTimeout(() => setFlashMsg(null), 3500);
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* 顶栏 */}
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <ClipboardCheck className="h-5 w-5" /> 复核工作台
        </h1>
        <span className="text-sm text-muted-foreground">
          机检未过任务的逐轴审阅与裁决
        </span>
        <span className="flex-1" />
        <span className="rounded-full border border-amber-600/30 bg-amber-600/10 px-2.5 py-0.5 text-xs text-amber-600">
          待复核 {queue.length}
        </span>
      </div>

      {flashMsg && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {flashMsg.text}
        </div>
      )}

      {queue.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-sm text-muted-foreground">
          <ClipboardCheck className="h-10 w-10" />
          <p>队列已清空——没有待复核的任务。</p>
          <p className="text-xs">机检未过的任务会自动进入此队列。</p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-3">
          {/* 左：队列 */}
          <div className="w-60 shrink-0 overflow-auto rounded-lg border bg-muted/20 p-2">
            <div className="mb-1 px-1 text-xs font-medium text-muted-foreground">
              EXCEEDED 队列
            </div>
            {queue.map((t) => (
              <button
                key={t.id}
                className={cn(
                  "mb-1 w-full rounded-md border p-2 text-left text-xs transition-colors",
                  selected?.id === t.id
                    ? "border-primary bg-accent"
                    : "border-transparent hover:bg-muted",
                )}
                onClick={() => setSelectedId(t.id)}
              >
                <div className="truncate font-medium text-sm">{t.file_name}</div>
                <div className="mt-0.5 text-muted-foreground">{fmtTime(t.updated_at)}</div>
              </button>
            ))}
          </div>

          {/* 右：裁决详情 */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border">
            {selected ? (
              <>
                <div className="flex items-center gap-2.5 border-b px-4 py-3">
                  <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold">{selected.file_name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {selected.source_lang?.toUpperCase()} → ZH · {fmtTime(selected.updated_at)}
                      {selected.retry_count > 0 && ` · 已重试 ${selected.retry_count} 次`}
                    </div>
                  </div>
                  <Button variant="outline" size="sm" asChild>
                    <a href={`/api/extensions/translation/tasks/${selected.id}/deliverable`}>
                      <Download className="mr-1 h-3.5 w-3.5" /> 下载当前译本
                    </a>
                  </Button>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
                  {/* 机检失败明细 */}
                  <section>
                    <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">
                      三轴机检失败明细
                    </div>
                    {selected.gate_failures ? (
                      <div className="flex flex-col gap-2">
                        {Object.entries(selected.gate_failures).map(([axis, violations]) => (
                          <div
                            key={axis}
                            className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
                          >
                            <div className="font-medium text-destructive">
                              {GATE_LABELS[axis] ?? axis}
                            </div>
                            <ul className="mt-1 list-inside list-disc text-muted-foreground">
                              {(violations).slice(0, 8).map((v, i) => (
                                <li key={i}>{v}</li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">（无逐轴明细）</p>
                    )}
                  </section>

                  {/* 不确定段 */}
                  {selected.uncertainty && selected.uncertainty.length > 0 && (
                    <section className="mt-3">
                      <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">
                        LLM 不确定段（{selected.uncertainty.length} 处）
                      </div>
                      <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
                        {selected.uncertainty.map((u, i) => (
                          <li key={i} className="truncate">
                            {u.block}
                            {u.spans?.length ? ` — ${u.spans.join(" · ")}` : ""}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                </div>

                {/* 裁决操作栏 */}
                <div className="flex flex-wrap gap-2 border-t px-4 py-3">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void decide(selected, "indexed")}
                  >
                    {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1 h-3.5 w-3.5" />}
                    通过并交付
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => void decide(selected, "archived")}
                  >
                    <Archive className="mr-1 h-3.5 w-3.5" /> 驳回归档
                  </Button>
                  <span className="flex-1" />
                  <Button variant="ghost" size="sm" asChild>
                    <a href={`/api/extensions/translation/tasks/${selected.id}/deliverable`}>
                      <Download className="mr-1 h-3.5 w-3.5" /> 下载当前译本
                    </a>
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                ← 从队列选择一个任务
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}



function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("zh-CN", { hour12: false });
}
