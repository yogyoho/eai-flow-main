"use client";

/**
 * 任务列表(bid:page:tasks,/bid-review)——Task 12 最小版。
 * 视觉规范:docs/designs/2026-10-29-bid-review-ui-spec.md §3.1(PageHeader + 4×StatCard
 * + 密集表格 + tbl-foot + 骨架/空态/错误态);共享基元直接 import cpa 路径(勿复制第六份)。
 * 新建 = Dialog(模式 SegmentedToggle §1.2 配方内联,Task 17 抽 primitives.tsx 后可替换);
 * 无文件版(文档经对话/MCP 编排),UI 上传 M3 补。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { createTask, listTasks } from "@/extensions/bid-review/api";
import { type TaskOut } from "@/extensions/bid-review/types";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { StatCard } from "@/extensions/contract-price/components/StatCard";
import {
  Pill,
  type PillTone,
} from "@/extensions/contract-price/components/ui/bits";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { cn } from "@/lib/utils";

const COLS = 7;

const MODE_DESC: Record<"quick" | "deep", string> = {
  quick:
    "确定性规则快审(M1 子集),秒级完成;审查文档稍后在对话中上传,由 agent 编排审查。",
  deep: "全量规则深审(含语义逐条审,耗时较长);审查文档稍后在对话中上传,由 agent 编排审查。",
};

/** §2 状态 Pill 映射:running=info / awaiting_confirm=warn / completed=success / failed=error / created,muted=muted。 */
function statusPill(status: string): { tone: PillTone; label: string } {
  switch (status) {
    case "completed":
      return { tone: "success", label: "已完成" };
    case "failed":
      return { tone: "error", label: "失败" };
    case "running":
      return { tone: "info", label: "进行中" };
    case "awaiting_confirm":
      return { tone: "warn", label: "待确认" };
    default:
      return {
        tone: "gray",
        label: status === "created" || status === "pending" ? "已创建" : status,
      };
  }
}

/** §3.1 meter:进度取 progress.pct(worker 契约);completed 恒 100。 */
function progressPct(t: TaskOut): number {
  if (t.status === "completed") return 100;
  const pct = t.progress?.pct;
  return typeof pct === "number" ? Math.min(100, Math.round(pct)) : 0;
}

/** 日期段用连字符 yyyy-MM-dd(用户定案 2026-10-16,zh-CN toLocaleString 是斜杠)。 */
function formatDate(s: string): string {
  const d = new Date(s);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function TasksView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mode, setMode] = useState<"quick" | "deep">("quick");

  const tasksQuery = useQuery({
    queryKey: ["bid-review", "tasks"],
    queryFn: listTasks,
  });

  const createMutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bid-review", "tasks"] });
      setDialogOpen(false);
    },
  });

  const tasks = tasksQuery.data ?? [];
  const runningCount = tasks.filter((t) => t.status === "running").length;
  // 致命未处理/待人工:GET /tasks 行契约尚无任务级问题聚合,Task 17 接 issues 聚合后填实。
  const fatalCount = 0;
  const needHumanCount = 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
      <div className="shrink-0">
        <PageHeader
          title="投标方案审查"
          description="投标文件合规自审 · quick / deep 双模式"
          icon={<ClipboardList />}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void tasksQuery.refetch()}
                disabled={tasksQuery.isFetching}
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4",
                    tasksQuery.isFetching && "animate-spin",
                  )}
                />
                刷新
              </Button>
              <Button size="sm" onClick={() => setDialogOpen(true)}>
                <Plus className="h-4 w-4" />
                新建审查任务
              </Button>
            </>
          }
        />
      </div>

      {/* 指标格 = 4× StatCard(§3.1,非 GateMetricsRow);数据=GET /tasks 聚合 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tasksQuery.isPending ? (
          [0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="border-border bg-card h-[72px] animate-pulse rounded-md border"
            />
          ))
        ) : (
          <>
            <StatCard label="总任务" value={tasks.length} hint="个" />
            <StatCard label="进行中" value={runningCount} />
            <StatCard label="致命未处理" value={fatalCount} tone="warn" />
            <StatCard label="待人工" value={needHumanCount} />
          </>
        )}
      </div>

      {/* 错误态:NoteBar destructive 配方 + 重试 */}
      {tasksQuery.isError ? (
        <div className="bg-destructive/10 text-destructive flex items-center gap-2 rounded-md px-3 py-2 text-xs">
          <span className="flex-1">
            任务列表加载失败:{tasksQuery.error.message}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void tasksQuery.refetch()}
          >
            重试
          </Button>
        </div>
      ) : null}

      {tasksQuery.isPending ? (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  "任务名",
                  "模式",
                  "状态",
                  "进度",
                  "致命数",
                  "更新时间",
                  "操作",
                ].map((h) => (
                  <TableHead key={h} scope="col">
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {[0, 1, 2].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={COLS}>
                    <div className="bg-muted h-6 animate-pulse rounded" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : tasks.length === 0 ? (
        <div className="border-border flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16">
          <p className="text-muted-foreground text-sm">暂无审查任务</p>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            新建审查任务
          </Button>
        </div>
      ) : (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  "任务名",
                  "模式",
                  "状态",
                  "进度",
                  "致命数",
                  "更新时间",
                  "操作",
                ].map((h) => (
                  <TableHead key={h} scope="col">
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((t) => {
                const st = statusPill(t.status);
                const pct = progressPct(t);
                return (
                  <TableRow
                    key={t.id}
                    className="hover:bg-muted/50 cursor-pointer"
                    onClick={() => router.push(`/bid-review/tasks/${t.id}`)}
                  >
                    <TableCell>
                      <span className="font-mono text-xs" title={t.id}>
                        {t.id.slice(0, 8)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Pill tone="gray">{t.mode}</Pill>
                    </TableCell>
                    <TableCell>
                      <Pill tone={st.tone}>{st.label}</Pill>
                    </TableCell>
                    <TableCell>
                      <div className="flex min-w-[96px] items-center gap-2">
                        <div className="bg-muted h-1.5 flex-1 rounded-full">
                          <div
                            className="bg-primary h-full rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-muted-foreground text-xs tabular-nums">
                          {pct}%
                        </span>
                      </div>
                    </TableCell>
                    {/* 任务级致命数聚合 Task 17 接 issues 后填实 */}
                    <TableCell>
                      <span className="tabular-nums">—</span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {formatDate(t.created_at)}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/bid-review/tasks/${t.id}`}
                        className="text-primary text-xs hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        查看工作台
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <div className="text-muted-foreground flex items-center gap-2 px-4 py-2 text-xs">
            共 {tasks.length} 个任务
          </div>
        </div>
      )}

      {/* 新建 = Dialog(§3.1;模式 SegmentedToggle §1.2 配方内联,Task 17 抽 primitives 后替换) */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>新建审查任务</DialogTitle>
            <DialogDescription>
              创建后请将招标文件与投标文件在对话中上传,由 agent
              编排审查;工作台文件上传(M3)就绪后可直接上传。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <span className="text-muted-foreground text-xs font-medium">
              审查模式
            </span>
            <div className="bg-card border-border inline-flex overflow-hidden rounded-md border">
              {(["quick", "deep"] as const).map((m, i) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={mode === m}
                  onClick={() => setMode(m)}
                  className={cn(
                    "text-muted-foreground px-3.5 py-[5px] text-sm",
                    i > 0 && "border-border border-l",
                    mode === m && "bg-primary/10 text-primary font-medium",
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground text-xs">{MODE_DESC[mode]}</p>
          </div>
          {createMutation.isError ? (
            <p className="text-destructive text-xs">
              创建失败:{createMutation.error.message}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              size="sm"
              onClick={() => createMutation.mutate(mode)}
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "创建中…" : "创建任务"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
