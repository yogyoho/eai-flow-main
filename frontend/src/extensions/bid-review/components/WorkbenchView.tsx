"use client";

/**
 * 审查工作台(bid:page:workbench)——Task 17,核心视图。
 * 视觉规范:docs/designs/2026-10-29-bid-review-ui-spec.md §3.2(顶条 + GateMetricsRow
 * + SplitPane 左问题列表/右证据面板 + 复核三连 + Sheet w-[600px]);共享基元来自
 * primitives.tsx(四件)与 cpa bits(Pill/NoteBar),勿自创样式。
 * 数据面按 landed 后端契约(Task 10):GET /tasks/{id}、GET /tasks/{id}/issues、
 * POST /issues/{id}/feedback;复核状态后端不落 issue 行(IssueOut 无复核字段)→
 * 本次会话内本地 recorded 映射呈现"确认勾/误报删除线",刷新即失(v1 已记缺口)。
 */

import { ArrowLeft, Check, Download } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { type FeedbackAction, exportReport } from "@/extensions/bid-review/api";
import {
  GateMetricsRow,
  SegmentedToggle,
  SplitPane,
  SplitRow,
  severityPill,
  taskStatusPill,
  verdictPill,
} from "@/extensions/bid-review/components/primitives";
import {
  useBidFeedback,
  useBidIssues,
  useBidTask,
} from "@/extensions/bid-review/hooks";
import { type IssueOut } from "@/extensions/bid-review/types";
import { NoteBar, Pill } from "@/extensions/contract-price/components/ui/bits";
import { cn } from "@/lib/utils";

type LayerFilter = "all" | "L1" | "L3";
type VerdictFilter = "all" | "violation" | "need_human";

const LAYER_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "L1", label: "L1" },
  { value: "L3", label: "L3" },
] as const;

const VERDICT_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "violation", label: "violation" },
  { value: "need_human", label: "need_human" },
] as const;

const MODE_OPTIONS = [
  { value: "quick", label: "quick" },
  { value: "deep", label: "deep" },
] as const;

const SEVERITIES = [
  { value: "fatal", label: "致命" },
  { value: "major", label: "主要" },
  { value: "minor", label: "次要" },
  { value: "info", label: "提示" },
] as const;

/** 证据锚点 chip(spec §3.2 src-chip 习语):doc_id + p.页码;v1 无原文坐标查看器,
 * 点击跳转为已记缺口,chip 仅 title 提示摘录。 */
function EvidenceChip({
  docId,
  page,
  text,
}: {
  docId: string;
  page: number | null;
  text: string;
}) {
  return (
    <span
      title={text}
      className="border-border bg-card text-muted-foreground inline-flex h-[22px] max-w-[240px] items-center gap-1 rounded-full border px-2.5 text-xs"
    >
      <span className="truncate">{docId}</span>
      {page != null ? <span className="shrink-0">· p.{page}</span> : null}
    </span>
  );
}

const isRecord = (x: unknown): x is Record<string, unknown> =>
  typeof x === "object" && x !== null;

/** evidence 条目字段安全取串(no-base-to-string):非串值 JSON 化,缺省回退。 */
function str(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v == null) return fallback;
  return JSON.stringify(v);
}

export function WorkbenchView({ taskId }: { taskId?: string | null }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layerFilter, setLayerFilter] = useState<LayerFilter>("all");
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>("all");
  // 复核状态本地映射:后端 ReviewFeedback 不回写 issue 行(v1 缺口),刷新即失。
  const [reviewed, setReviewed] = useState<Record<string, FeedbackAction>>({});
  const [sheetOpen, setSheetOpen] = useState(false);
  const [newSeverity, setNewSeverity] = useState<string>("major");
  // 报告导出(Task 21):GET report?format=md → Blob 下载(照 docmgr 导出先例);
  // 仅 done 任务可导出——半程审查的条目清单不得冒充完整报告。
  const [exporting, setExporting] = useState(false);

  const handleExportReport = async () => {
    if (!taskId) return;
    setExporting(true);
    try {
      const blob = await exportReport(taskId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bid-review-report-${taskId.slice(0, 8)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "报告导出失败");
    } finally {
      setExporting(false);
    }
  };

  const enabled = Boolean(taskId);
  const taskQuery = useBidTask(enabled ? taskId : null);
  const issuesQuery = useBidIssues(enabled ? taskId : null);
  const feedback = useBidFeedback();
  // 确认门动作在基准确认页(§3.3);工作台仅在基准未确认提示条里给出入口。

  const task = taskQuery.data ?? null;
  const issues = issuesQuery.data ?? [];
  // "基准未确认"唯一可靠信号:deep 任务停在确认门(worker 落 awaiting_confirm);
  // 行级 confirmed 明细后端无 HTTP 读端点(v1 已记缺口)。
  const baselineUnconfirmed = task?.status === "awaiting_confirm";
  // 计划 Task 17 Step 2:确认前 workbench 只读。
  const readOnly = baselineUnconfirmed;

  const filtered = issues.filter(
    (i) =>
      (layerFilter === "all" || i.layer === layerFilter) &&
      (verdictFilter === "all" || i.verdict === verdictFilter),
  );
  const selected: IssueOut | null =
    issues.find((i) => i.id === selectedId) ?? null;
  // evidence: unknown[] → 逐条过滤为 record(isRecord)后经 str() 安全取串。
  const evidence = selected ? selected.evidence.filter(isRecord) : [];

  const fatalCount = issues.filter((i) => i.severity === "fatal").length;
  const majorCount = issues.filter((i) => i.severity === "major").length;
  const minorCount = issues.filter((i) => i.severity === "minor").length;
  const needHumanCount = issues.filter((i) => i.need_human).length;
  const reviewedCount = issues.filter((i) => reviewed[i.id]).length;
  const reviewPct = issues.length
    ? Math.round((reviewedCount / issues.length) * 100)
    : 0;

  // 无选中且列表有数据 → 自动选第一条(过滤后仍优先保持原选中,不在列表则回落)。
  useEffect(() => {
    if (!selectedId && filtered.length > 0) setSelectedId(filtered[0]!.id);
  }, [selectedId, filtered]);

  useEffect(() => {
    if (feedback.isError) {
      toast.error(feedback.error?.message ?? "复核提交失败");
    }
  }, [feedback.isError, feedback.error]);

  const submitFeedback = (
    issue: IssueOut,
    action: FeedbackAction,
    note = "",
  ) => {
    if (!taskId) return;
    feedback.mutate(
      {
        issueId: issue.id,
        taskId,
        action,
        note,
        ...(action === "severity_change" ? { new_severity: newSeverity } : {}),
      },
      {
        onSuccess: () => {
          setReviewed((prev) => ({ ...prev, [issue.id]: action }));
          if (action === "confirm") toast.success("已确认该问题");
          if (action === "false_positive") toast.success("已标记误报");
          if (action === "severity_change") {
            toast.success(`严重度已调整为${newSeverity}`);
            setSheetOpen(false);
          }
        },
      },
    );
  };

  if (!taskId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col p-6">
        <div className="border-border flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16">
          <p className="text-muted-foreground text-sm">
            未指定任务——请从任务列表进入工作台
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/bid-review">
              <ArrowLeft className="h-4 w-4" />
              返回任务列表
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  const st = task ? taskStatusPill(task.status) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
      {/* 顶条:任务名 + 状态 Pill + mode SegmentedToggle(只读)+ 复核进度 meter(§3.2) */}
      <div className="border-border bg-card flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3">
        <Link
          href="/bid-review"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          任务列表
        </Link>
        <span className="font-mono text-lg font-semibold" title={taskId}>
          {taskId.slice(0, 8)}
        </span>
        {st ? <Pill tone={st.tone}>{st.label}</Pill> : null}
        <SegmentedToggle
          options={MODE_OPTIONS}
          value={(task?.mode as "quick" | "deep") ?? "quick"}
          ariaLabel="审查模式(只读)"
          disabled
        />
        <div className="ml-auto flex w-44 items-center gap-2">
          <div className="bg-muted h-1.5 flex-1 rounded-full">
            <div
              className="bg-primary h-full rounded-full"
              style={{ width: `${reviewPct}%` }}
            />
          </div>
          <span className="text-muted-foreground text-xs tabular-nums">
            复核 {reviewedCount}/{issues.length}
          </span>
        </div>
        {/* 报告导出(Task 21):outline 照 ui-spec §3.5 导出按钮形态;仅 done 可导 */}
        <Button
          variant="outline"
          size="sm"
          disabled={exporting || task?.status !== "done"}
          title={
            task && task.status !== "done"
              ? "审查完成后可导出报告"
              : "导出审查报告(.md)"
          }
          onClick={() => void handleExportReport()}
        >
          <Download className="h-3.5 w-3.5" />
          {exporting ? "导出中…" : "导出报告"}
        </Button>
      </div>

      {/* 基准未确认:页顶 NoteBar(warning 深字);确认后状态离开 awaiting_confirm 即移除 */}
      {baselineUnconfirmed ? (
        <div className="flex items-start gap-2 rounded-md border border-[var(--warning-100)] bg-[var(--warning-50)] px-3 py-2 text-xs text-[var(--warning-700)]">
          <span className="flex-1">
            基准未确认——基准错误将批量产生错误结论;确认前工作台只读。
          </span>
          <Link
            href={`/bid-review/baseline?task_id=${taskId}`}
            className="text-primary shrink-0 hover:underline"
          >
            前往基准确认
          </Link>
        </div>
      ) : null}

      {/* 顶条 GateMetricsRow:致命/主要/次要/待人工(§1.3 用法;致命 tone 语义) */}
      <GateMetricsRow
        metrics={[
          {
            label: "致命",
            value: fatalCount,
            tone: fatalCount > 0 ? "error" : "success",
          },
          { label: "主要", value: majorCount },
          { label: "次要", value: minorCount },
          { label: "待人工", value: needHumanCount },
        ]}
      />

      {issuesQuery.isError ? (
        <div className="bg-destructive/10 text-destructive flex items-center gap-2 rounded-md px-3 py-2 text-xs">
          <span className="flex-1">
            问题列表加载失败:{issuesQuery.error.message}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void issuesQuery.refetch()}
          >
            重试
          </Button>
        </div>
      ) : null}

      <SplitPane
        left={
          <div className="flex flex-col gap-2">
            {/* 左列过滤器 SegmentedToggle ×2(§3.2:层级 / 判定) */}
            <div className="flex flex-wrap items-center gap-2">
              <SegmentedToggle
                options={LAYER_OPTIONS}
                value={layerFilter}
                onChange={setLayerFilter}
                ariaLabel="层级过滤"
              />
              <SegmentedToggle
                options={VERDICT_OPTIONS}
                value={verdictFilter}
                onChange={setVerdictFilter}
                ariaLabel="判定过滤"
              />
            </div>
            {/* 左列容器 max-h-[560px] overflow-y-auto(§1.1 原型值) */}
            <div className="border-border bg-card max-h-[560px] overflow-y-auto rounded-lg border">
              {issuesQuery.isPending ? (
                <div className="flex flex-col gap-2 p-3">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="bg-muted h-8 animate-pulse rounded"
                    />
                  ))}
                </div>
              ) : filtered.length === 0 ? (
                <p className="text-muted-foreground px-3 py-8 text-center text-xs">
                  {issues.length === 0
                    ? "暂无问题记录"
                    : "当前过滤条件下无问题"}
                </p>
              ) : (
                filtered.map((i) => {
                  const sp = severityPill(i.severity);
                  const review = reviewed[i.id];
                  return (
                    <SplitRow
                      key={i.id}
                      selected={selected?.id === i.id}
                      onClick={() => setSelectedId(i.id)}
                    >
                      <span className="font-mono text-xs">{i.rule_id}</span>
                      <Pill tone={sp.tone}>{sp.label}</Pill>
                      <span
                        className={cn(
                          "truncate",
                          review === "false_positive" &&
                            "text-muted-foreground line-through",
                        )}
                      >
                        {i.message}
                      </span>
                      {/* 左栏条目只显示复核后状态,不放按钮(§3.2):
                          确认→success 勾,误报→muted 删除线 */}
                      {review === "confirm" ? (
                        <Check className="text-success ml-auto h-3.5 w-3.5 shrink-0" />
                      ) : null}
                      {review === "false_positive" ? (
                        <span className="text-muted-foreground ml-auto shrink-0 text-xs">
                          误报
                        </span>
                      ) : null}
                    </SplitRow>
                  );
                })
              )}
            </div>
          </div>
        }
        right={
          <div className="border-border bg-card flex flex-col gap-3 rounded-lg border p-4">
            {!selected ? (
              <p className="text-muted-foreground py-16 text-center text-sm">
                {issues.length === 0
                  ? "该任务暂无问题记录"
                  : "从左侧选择问题查看证据"}
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{selected.rule_id}</span>
                  {(() => {
                    const sp = severityPill(selected.severity);
                    return <Pill tone={sp.tone}>{sp.label}</Pill>;
                  })()}
                  {(() => {
                    const vp = verdictPill(selected.verdict);
                    return <Pill tone={vp.tone}>{vp.label}</Pill>;
                  })()}
                  {selected.clause_id ? (
                    <Pill tone="gray" title="条款号">
                      {selected.clause_id}
                    </Pill>
                  ) : null}
                </div>
                <p className="text-sm">{selected.message}</p>

                {/* need_human:右栏顶部 NoteBar info(§3.2) */}
                {selected.need_human ? (
                  <NoteBar>证据不足,需人工定位后补锚点</NoteBar>
                ) : null}

                {/* 证据锚点 chips(src-chip 习语)+ 摘录块(border-l-2 primary) */}
                {evidence.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap gap-1.5">
                      {evidence.map((ev, idx) => (
                        <EvidenceChip
                          key={idx}
                          docId={str(ev.doc_id, "未知文档")}
                          page={typeof ev.page === "number" ? ev.page : null}
                          text={str(ev.text)}
                        />
                      ))}
                    </div>
                    {evidence.map((ev, idx) => (
                      <blockquote
                        key={idx}
                        className="border-primary bg-primary/5 rounded-md border-l-2 p-3 text-sm"
                      >
                        <span className="text-muted-foreground mr-2 text-xs">
                          p.{str(ev.page, "-")}
                        </span>
                        <span className="break-words whitespace-pre-wrap">
                          {str(ev.text)}
                        </span>
                      </blockquote>
                    ))}
                  </div>
                ) : null}

                {selected.fix ? (
                  <div className="flex flex-col gap-1">
                    <span className="text-muted-foreground text-xs font-medium">
                      修复建议
                    </span>
                    <p className="text-sm">{selected.fix}</p>
                  </div>
                ) : null}

                {/* 复核三连(§3.2):确认 primary / 误报 outline / 改严重度 outline→Sheet;
                    基准确认前只读(plan Task 17 Step 2) */}
                <div className="border-border flex flex-wrap items-center gap-2 border-t pt-3">
                  <Button
                    size="sm"
                    disabled={
                      readOnly ||
                      reviewed[selected.id] === "confirm" ||
                      feedback.isPending
                    }
                    onClick={() => submitFeedback(selected, "confirm")}
                  >
                    确认
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={readOnly || feedback.isPending}
                    onClick={() => submitFeedback(selected, "false_positive")}
                  >
                    误报
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={readOnly}
                    onClick={() => {
                      setNewSeverity(selected.severity);
                      setSheetOpen(true);
                    }}
                  >
                    改严重度
                  </Button>
                  {readOnly ? (
                    <span className="text-muted-foreground ml-auto text-xs">
                      基准确认前工作台只读
                    </span>
                  ) : null}
                </div>
              </>
            )}
          </div>
        }
      />

      {/* 改严重度 Sheet:w-[600px] sm:max-w-[600px](cpa 裁决);frm-row 习语 label */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="w-[600px] sm:max-w-[600px]">
          <SheetHeader>
            <SheetTitle>调整严重度</SheetTitle>
            <SheetDescription>
              对问题 {selected?.rule_id ?? ""} 重新定级;提交后回流复核记录。
            </SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-2 px-4">
            <span className="text-muted-foreground text-xs font-medium">
              新严重度
            </span>
            <Select value={newSeverity} onValueChange={setNewSeverity}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SEVERITIES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <SheetFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSheetOpen(false)}
            >
              取消
            </Button>
            <Button
              size="sm"
              disabled={feedback.isPending || !selected}
              onClick={() =>
                selected && submitFeedback(selected, "severity_change")
              }
            >
              {feedback.isPending ? "提交中…" : "提交"}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}
