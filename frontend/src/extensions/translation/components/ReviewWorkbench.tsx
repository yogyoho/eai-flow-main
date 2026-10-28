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
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  getTaskDraft,
  listReviewQueue,
  saveTaskDraft,
  transitionTask,
  type TaskDraftBlock,
} from "../api";
import type { TltTask } from "../types";

import { PageHeader } from "./PageHeader";

/** 机检轴的用户语标签（文案红线映射表）。 */
const GATE_LABELS: Record<string, string> = {
  numeric: "数字准确性",
  terminology: "术语一致性",
  structure: "格式完整性",
};

/** 源/译数字集合对比（仅作复核视觉提示，最终以后端数值轴为准）。 */
function numericMismatch(source: string, translated: string): boolean {
  const nums = (s: string) => (s.match(/\d+(?:[.,]\d+)*/g) ?? []).sort().join("|");
  const a = nums(source);
  return a !== "" && a !== nums(translated);
}

export function ReviewWorkbench() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["tlt-tasks"] });
    void qc.invalidateQueries({ queryKey: ["tlt-review-queue"] });
  };

  const queueQ = useQuery({
    queryKey: ["tlt-review-queue"],
    queryFn: listReviewQueue,
    refetchInterval: 30_000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("task_id");
  });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [savingDraft, setSavingDraft] = useState(false);

  const queue = queueQ.data ?? [];
  const selected = queue.find((t) => t.id === selectedId) ?? queue[0] ?? null;
  const selectedTaskId = selected?.id;

  useEffect(() => {
    setNote("");
    setEditing(false);
    setEdits({});
  }, [selectedTaskId]);

  const draftQ = useQuery({
    queryKey: ["tlt-draft", selectedTaskId],
    queryFn: () => getTaskDraft(selectedTaskId!),
    enabled: Boolean(selectedTaskId),
  });
  const draftSource = draftQ.data?.source ?? [];
  const draftTranslated = draftQ.data?.translated ?? [];
  const sourceById = new Map(draftSource.map((block) => [block.id, block]));
  const uncertainIds = new Set(
    (draftQ.data?.uncertainty ?? []).map((item) => item.block),
  );
  const comparisonColumns: {
    label: string;
    blocks: TaskDraftBlock[];
    side: "source" | "translated";
  }[] = [
    { label: "源文", blocks: draftSource, side: "source" },
    { label: "译文", blocks: draftTranslated, side: "translated" },
  ];
  const backtranslation = (
    selected?.error_detail as
      | {
          backtranslation?: {
            block: string;
            source: string;
            back: string;
            ratio: number;
            drift: boolean;
          }[];
        }
      | null
      | undefined
  )?.backtranslation;

  const startEditing = () => {
    setEdits(Object.fromEntries(draftTranslated.map((block) => [block.id, block.text])));
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setEdits({});
  };

  const saveDraft = async () => {
    if (!selected || draftTranslated.length === 0) return;
    setSavingDraft(true);
    try {
      const result = await saveTaskDraft(
        selected.id,
        draftTranslated.map((block) => ({
          id: block.id,
          text: edits[block.id] ?? block.text,
        })),
      );
      setEditing(false);
      void qc.invalidateQueries({ queryKey: ["tlt-draft", selectedTaskId] });
      invalidate();
      const failureCount = Object.values(result.gate_failures ?? {}).reduce(
        (count, items) => count + items.length,
        0,
      );
      if (failureCount > 0) {
        toast.warning(`草稿已保存，但仍有 ${failureCount} 项机检问题`);
      } else {
        toast.success("草稿已保存");
      }
    } catch (e) {
      flash(`保存失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingDraft(false);
    }
  };

  const decide = async (t: TltTask, target: "indexed" | "archived") => {
    setBusy(true);
    try {
      await transitionTask(t.id, target, note.trim() || undefined);
      void qc.invalidateQueries({ queryKey: ["tlt-draft"] });
      invalidate();
      setSelectedId(null);
      setNote("");
      if (target === "indexed") toast.success("已通过并交付");
      else toast.success("已驳回归档");
    } catch (e) {
      flash(`操作失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  // flash: sonner 右下角 toast(对齐知识工厂),不再内嵌通知条——列表不位移。
  const flash = (text: string) => {
    toast.error(text);
  };

  /** 复核初始化骨架：左队列列表 + 右裁决详情。 */
  const ReviewSkeleton = () => (
    <div
      className="flex min-h-0 flex-1 gap-3"
      role="status"
      aria-label="复核队列加载中"
    >
      <div className="bg-muted/20 w-60 shrink-0 rounded-lg border p-2">
        <div className="bg-muted-foreground/15 mb-2 h-3 w-24 animate-pulse rounded" />
        {Array.from({ length: 6 }, (_, i) => (
          <div
            key={i}
            className="mb-1 rounded-md border border-transparent p-2"
          >
            <div
              className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
              style={{ width: 140 + (i % 3) * 16 }}
            />
            <div className="bg-muted-foreground/15 mt-1.5 h-3 w-24 animate-pulse rounded" />
          </div>
        ))}
      </div>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border">
        <div className="flex items-center gap-2.5 border-b px-4 py-3">
          <div className="bg-muted-foreground/15 size-5 animate-pulse rounded" />
          <div className="flex-1 space-y-1.5">
            <div className="bg-muted-foreground/15 h-3.5 w-64 animate-pulse rounded" />
            <div className="bg-muted-foreground/15 h-3 w-40 animate-pulse rounded" />
          </div>
        </div>
        <div className="flex-1 space-y-3 px-4 py-3">
          <div className="bg-muted-foreground/15 h-3 w-28 animate-pulse rounded" />
          {Array.from({ length: 2 }, (_, i) => (
            <div
              key={i}
              className="border-border space-y-2 rounded-md border p-2.5"
            >
              <div className="bg-muted-foreground/15 h-3 w-24 animate-pulse rounded" />
              <div className="bg-muted-foreground/15 h-3 w-full animate-pulse rounded" />
              <div className="bg-muted-foreground/15 h-3 w-5/6 animate-pulse rounded" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-3 pb-4">
      <PageHeader
        title="复核工作台"
        description="机检未过任务的逐轴审阅与裁决"
        icon={<ClipboardCheck />}
        actions={
          queueQ.isLoading ? undefined : (
            <span className="rounded-full border border-amber-600/30 bg-amber-600/10 px-2.5 py-0.5 text-xs text-amber-600 tabular-nums">
              待复核 {queue.length}
            </span>
          )
        }
      />

      {queueQ.isLoading ? (
        <ReviewSkeleton />
      ) : queue.length === 0 ? (
        <div className="text-muted-foreground flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-sm">
          <ClipboardCheck className="h-10 w-10" />
          <p>队列已清空——没有待复核的任务。</p>
          <p className="text-xs">机检未过的任务会自动进入此队列。</p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-3">
          {/* 左：队列 */}
          <div className="bg-muted/20 w-60 shrink-0 overflow-auto rounded-lg border p-2">
            <div className="text-muted-foreground mb-1 px-1 text-xs font-medium">
              EXCEEDED 队列
            </div>
            {queue.map((t) => (
              <button
                key={t.id}
                className={cn(
                  "mb-1 w-full rounded-md border p-2 text-left text-xs transition-colors",
                  selected?.id === t.id
                    ? "border-primary bg-accent"
                    : "hover:bg-muted border-transparent",
                )}
                onClick={() => setSelectedId(t.id)}
              >
                <div className="truncate font-mono text-[13px] font-medium">
                  {t.file_name}
                </div>
                <div className="text-muted-foreground mt-0.5 font-mono tabular-nums">
                  {fmtTime(t.updated_at)}
                </div>
              </button>
            ))}
          </div>

          {/* 右：裁决详情 */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border">
            {selected ? (
              <>
                <div className="flex items-center gap-2.5 border-b px-4 py-3">
                  <FileText className="text-muted-foreground h-5 w-5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-[13px] font-semibold">
                      {selected.file_name}
                    </div>
                    <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-1 text-xs tabular-nums">
                      <span className="font-mono">
                        {selected.source_lang?.toUpperCase()} → ZH
                      </span>
                      <span>·</span>
                      <span className="font-mono">
                        {fmtTime(selected.updated_at)}
                      </span>
                      {selected.retry_count > 0 && (
                        <span>· 已重试 {selected.retry_count} 次</span>
                      )}
                    </div>
                  </div>
                  <Button variant="outline" size="sm" asChild>
                    <a
                      href={`/api/extensions/translation/tasks/${selected.id}/deliverable`}
                    >
                      <Download className="mr-1 h-3.5 w-3.5" /> 下载当前译本
                    </a>
                  </Button>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
                  {/* 源文 / 译文逐块对照 */}
                  <section className="mb-3">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <div className="text-muted-foreground text-xs font-semibold tracking-wide">
                        源文 / 译文对照
                      </div>
                      {draftQ.data?.edited_at && (
                        <span className="border-primary/20 bg-primary/10 text-primary rounded border px-1.5 py-0.5 text-[10px]">
                          已人工编辑
                        </span>
                      )}
                      <span className="flex-1" />
                      {!editing ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-6 px-2 text-[11px]"
                          disabled={draftTranslated.length === 0}
                          onClick={startEditing}
                        >
                          编辑译文
                        </Button>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">
                          人工校对中
                        </span>
                      )}
                    </div>
                    {draftQ.isLoading ? (
                      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        加载草稿…
                      </p>
                    ) : draftSource.length === 0 &&
                      draftTranslated.length === 0 ? (
                      <p className="text-muted-foreground text-xs">
                        暂无草稿块（任务可能未进入复核或草稿已清空）
                      </p>
                    ) : (
                      <div className="grid gap-2 xl:grid-cols-2">
                        {comparisonColumns.map(({ label, blocks, side }) => (
                          <div
                            key={label}
                            className="border-border overflow-hidden rounded-md border"
                          >
                            <div className="border-border text-muted-foreground border-b px-2 py-1 text-[11px] font-medium">
                              {label}
                            </div>
                            <div className="max-h-72 divide-y divide-[var(--gray-100)] overflow-y-auto">
                              {blocks.map((block) => {
                                const uncertain = uncertainIds.has(block.id);
                                const mismatch =
                                  side === "translated" &&
                                  numericMismatch(
                                    sourceById.get(block.id)?.text ?? "",
                                    block.text,
                                  );
                                return (
                                  <div
                                    key={`${side}-${block.id}`}
                                    className={cn(
                                      "px-2 py-1.5 text-xs leading-relaxed",
                                      uncertain && "bg-[var(--warn-50)]",
                                    )}
                                  >
                                    <div className="text-muted-foreground text-[10px]">
                                      {block.type} · {block.id}
                                    </div>
                                    {side === "translated" && editing ? (
                                      <Textarea
                                        value={edits[block.id] ?? block.text}
                                        onChange={(e) =>
                                          setEdits((prev) => ({
                                            ...prev,
                                            [block.id]: e.target.value,
                                          }))
                                        }
                                        rows={3}
                                        className="mt-1 min-h-14 text-xs"
                                      />
                                    ) : (
                                      <p
                                        className={cn(
                                          "break-words whitespace-pre-wrap",
                                          mismatch &&
                                            "text-[var(--error-700)] font-medium",
                                        )}
                                      >
                                        {block.text}
                                      </p>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {editing && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="text-muted-foreground mr-auto text-[11px]">
                          保存后重新计算机检；reviewed 档需通过后才能交付。
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          disabled={savingDraft}
                          onClick={cancelEditing}
                        >
                          取消
                        </Button>
                        <Button
                          size="sm"
                          className="h-7 text-xs"
                          disabled={savingDraft}
                          onClick={() => void saveDraft()}
                        >
                          {savingDraft && (
                            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          )}
                          保存草稿
                        </Button>
                      </div>
                    )}
                  </section>
                  <section>
                    <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                      三轴机检失败明细
                    </div>
                    {selected.gate_failures ? (
                      <div className="flex flex-col gap-2">
                        {Object.entries(selected.gate_failures).map(
                          ([axis, violations]) => (
                            <div
                              key={axis}
                              className="border-destructive/30 bg-destructive/5 rounded-md border p-2.5 text-xs"
                            >
                              <div className="text-destructive font-medium">
                                {GATE_LABELS[axis] ?? axis}
                              </div>
                              <ul className="text-muted-foreground mt-1 list-inside list-disc font-mono">
                                {violations.slice(0, 8).map((v, i) => (
                                  <li key={i}>{v}</li>
                                ))}
                              </ul>
                            </div>
                          ),
                        )}
                      </div>
                    ) : (
                      <p className="text-muted-foreground text-sm">
                        （无逐轴明细）
                      </p>
                    )}
                  </section>

                  {/* P2-12 回译诊断：exceeded 前的定向采样结果 */}
                  {backtranslation && backtranslation.length > 0 && (
                    <section className="mt-3">
                      <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                        回译诊断（{backtranslation.length} 块）
                      </div>
                      <div className="flex flex-col gap-1.5">
                        {backtranslation.map((item) => (
                          <div
                            key={item.block}
                            className={cn(
                              "rounded-md border px-2.5 py-2 text-xs",
                              item.drift
                                ? "border-[var(--error-100)] bg-[var(--error-50)]"
                                : "border-border bg-muted/20",
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[11px]">
                                {item.block}
                              </span>
                              <span className="text-muted-foreground text-[11px]">
                                相似度 {(item.ratio * 100).toFixed(0)}%
                              </span>
                              {item.drift && (
                                <span className="text-[var(--error-700)] text-[11px] font-medium">
                                  疑似语义偏移
                                </span>
                              )}
                            </div>
                            <p className="text-muted-foreground mt-1 line-clamp-2">
                              回译：{item.back}
                            </p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* 不确定段 */}
                  {selected.uncertainty && selected.uncertainty.length > 0 && (
                    <section className="mt-3">
                      <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide tabular-nums">
                        LLM 不确定段（{selected.uncertainty.length} 处）
                      </div>
                      <ul className="text-muted-foreground flex flex-col gap-1 font-mono text-xs">
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

                {/* 批注：随裁决写入任务 error_detail.notes */}
                <div className="border-border border-t px-4 py-2.5">
                  <label className="text-muted-foreground mb-1 block text-[11px] font-medium">
                    批注（可选，随裁决留档）
                  </label>
                  <Textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={2}
                    placeholder="例如：数字已人工核对；术语按客户确认译法调整"
                    className="min-h-14 text-xs"
                  />
                </div>

                {/* 裁决操作栏 */}
                <div className="flex flex-wrap gap-2 border-t px-4 py-3">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void decide(selected, "indexed")}
                  >
                    {busy ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="mr-1 h-3.5 w-3.5" />
                    )}
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
                </div>
              </>
            ) : (
              <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
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
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("zh-CN", { hour12: false });
}
