"use client";

import {
  ChevronLeft,
  ChevronRight,
  History,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  EmptyRow,
  PageHeader,
} from "@/extensions/contract-price/components/PageHeader";
import {
  Pill,
  StatusDot,
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
import { useDeleteRun, useRuns } from "@/extensions/contract-price/hooks";
import type { CpaRun } from "@/extensions/contract-price/types";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 状态徽章+光环圆点走 Pill/StatusDot（cpa UI 重构规范 §2-4 / 原型 .dot-*）
const statusTone: Record<string, PillTone> = {
  completed: "success",
  running: "primary",
  failed: "error",
};
const statusLabel: Record<string, string> = {
  completed: "已完成",
  running: "运行中",
  failed: "失败",
};

/** 历史运行 label 为空（后端 2026-10-16 起才在创建时落名）时的派生名，
 *  命名与后端 _run_label 一致：{解析|聚类}任务_{Unix时间戳秒}。 */
function derivedLabel(run: CpaRun): string {
  const name =
    run.scope?.phase === "cluster" ? "聚类分组任务" : "合同解析任务";
  return `${name}_${Math.floor(new Date(run.started_at).getTime() / 1000)}`;
}

function formatDate(s: string | null): string {
  if (!s) return "—";
  // 用户定案 2026-10-16：日期段用连字符 yyyy-MM-dd（zh-CN toLocaleString 是斜杠）
  const d = new Date(s);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const COL_SPAN = 11;

export function TasksView() {
  const [runStatus, setRunStatus] = useState<
    "all" | "running" | "completed" | "failed"
  >("all");
  // 分页（后端 Page{total} + skip/limit；切筛选回零页）
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const { data, isLoading, isFetching, refetch } = useRuns({
    run_status: runStatus === "all" ? undefined : runStatus,
    skip: page * pageSize,
    limit: pageSize,
  });
  const deleteRun = useDeleteRun();
  const runs = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // clear selection when filter/refetch changes which runs are visible
  useEffect(() => {
    setSelected(new Set());
  }, [runStatus, data]);

  // 尾页删空后回零页（参照 ClustersView clamp 习语）
  useEffect(() => {
    if (page > totalPages - 1) setPage(0);
  }, [page, totalPages]);

  const gotoPage = (p: number) => {
    setPage(p);
    setSelected(new Set());
  };

  const allSelected = useMemo(
    () => runs.length > 0 && runs.every((r) => selected.has(r.id)),
    [runs, selected],
  );

  const toggleAll = useCallback(() => {
    setSelected(allSelected ? new Set() : new Set(runs.map((r) => r.id)));
  }, [runs, allSelected]);

  const toggleOne = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  return (
    <div className="space-y-4 p-6">
      <PageHeader
        title="任务记录"
        description="手动与定时分析任务的运行记录。"
        icon={<History />}
        actions={
          <>
            <Tabs
              value={runStatus}
              onValueChange={(v) => {
                setRunStatus(v as typeof runStatus);
                setPage(0);
              }}
            >
              <TabsList>
                <TabsTrigger value="all">全部</TabsTrigger>
                <TabsTrigger value="running">运行中</TabsTrigger>
                <TabsTrigger value="completed">完成</TabsTrigger>
                <TabsTrigger value="failed">失败</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
              />
              刷新
            </Button>
          </>
        }
      />

      {/* Batch delete bar */}
      {selected.size > 0 ? (
        <div className="border-destructive/30 bg-destructive/5 flex items-center gap-3 rounded-lg border px-4 py-2.5">
          <span className="text-sm font-medium">已选 {selected.size} 项</span>
          <Button
            variant="destructive"
            size="sm"
            disabled={deleteRun.isPending}
            onClick={() => {
              if (!confirm(`确认删除选中的 ${selected.size} 条运行记录？`))
                return;
              Promise.all([...selected].map((id) => deleteRun.mutateAsync(id)))
                .catch((e) => console.error("批量删除失败:", e))
                .finally(() => setSelected(new Set()));
            }}
          >
            <Trash2 className="h-4 w-4" />
            {deleteRun.isPending ? "删除中…" : "批量删除"}
          </Button>
        </div>
      ) : null}

      {/* 列表卡（cpa UI 重构规范 §2-3：表格贴卡边、无内衬留白、失败脚注条贴底） */}
      <div className="bg-card border-border overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-9">
                {/* 首列全选：14px 小尺寸（用户 2026-10-16 反馈默认 16px 偏大） */}
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={toggleAll}
                  className="size-3.5"
                />
              </TableHead>
              <TableHead>任务名称</TableHead>
              <TableHead>开始时间</TableHead>
              <TableHead>触发</TableHead>
              <TableHead>状态</TableHead>
              <TableHead className="text-right">进度</TableHead>
              <TableHead className="text-right">合同</TableHead>
              <TableHead className="text-right">条目</TableHead>
              <TableHead className="text-right">分组</TableHead>
              <TableHead className="text-right">耗时</TableHead>
              {/* 操作：下载(有产物时) + 删除合并一列；无动作不渲染占位符 */}
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              /* 初始化骨架屏（用户 2026-10-16）：10 行脉冲占位，列形对齐真实行；
                  灰条用 muted-foreground/20（比 bg-muted 深一档，用户反馈太浅） */
              Array.from({ length: 10 }, (_, i) => (
                <TableRow key={i} className="hover:bg-transparent">
                  <TableCell>
                    <div className="bg-muted-foreground/15 size-3.5 animate-pulse rounded-sm" />
                  </TableCell>
                  <TableCell>
                    <div className="bg-muted-foreground/15 h-4 w-44 animate-pulse rounded" />
                  </TableCell>
                  <TableCell>
                    <div className="bg-muted-foreground/15 h-3.5 w-28 animate-pulse rounded" />
                  </TableCell>
                  <TableCell>
                    <div className="bg-muted-foreground/15 h-5 w-12 animate-pulse rounded-full" />
                  </TableCell>
                  <TableCell>
                    <div className="bg-muted-foreground/15 h-5 w-16 animate-pulse rounded-full" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-[5px] w-16 animate-pulse rounded-full" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-4 w-8 animate-pulse rounded" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-4 w-8 animate-pulse rounded" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-4 w-8 animate-pulse rounded" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-4 w-10 animate-pulse rounded" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="bg-muted-foreground/15 ml-auto h-4 w-12 animate-pulse rounded" />
                  </TableCell>
                </TableRow>
              ))
            ) : runs.length === 0 ? (
              <EmptyRow colSpan={COL_SPAN}>暂无运行记录。</EmptyRow>
            ) : (
              runs.map((run) => (
                <TableRow
                  key={run.id}
                  className={selected.has(run.id) ? "bg-primary/5" : undefined}
                >
                  <TableCell>
                    <Checkbox
                      checked={selected.has(run.id)}
                      onCheckedChange={() => toggleOne(run.id)}
                      className="size-3.5"
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    {run.label ?? derivedLabel(run)}
                  </TableCell>
                  {/* 开始时间：12px muted + tabular（原型 meta 列习语） */}
                  <TableCell className="text-muted-foreground text-xs whitespace-nowrap tabular-nums">
                    {formatDate(run.started_at)}
                  </TableCell>
                  {/* 触发：chip（定时=info / 手动=gray） */}
                  <TableCell>
                    <Pill
                      tone={run.trigger_type === "scheduled" ? "info" : "gray"}
                    >
                      {run.trigger_type === "scheduled" ? "定时" : "手动"}
                    </Pill>
                  </TableCell>
                  {/* 状态：chip + 光环圆点（原型 .pill + .dot-*） */}
                  <TableCell>
                    <Pill tone={statusTone[run.status] ?? "gray"}>
                      <StatusDot tone={statusTone[run.status] ?? "gray"} />
                      {statusLabel[run.status] ?? run.status}
                    </Pill>
                  </TableCell>
                  {/* 进度：进度条 + 计数（原型 章节口径「来源报告」列 .meter+.num 习语）。
                      凡有 progress 数据即渲染（completed/failed 保留终值）；失败计数或
                      failed 态填充转琥珀（原型 .meter.low 语义）；processing 仅运行中显示。 */}
                  <TableCell className="text-right">
                    {run.progress && run.progress.total > 0 ? (
                      <div className="flex flex-col items-end gap-1.5">
                        <span className="inline-flex items-center gap-2">
                          <span className="bg-muted inline-block h-[5px] w-16 overflow-hidden rounded-full align-middle">
                            <span
                              className={cn(
                                "block h-full rounded-full transition-all",
                                run.progress.failed || run.status === "failed"
                                  ? "bg-amber-500"
                                  : "bg-primary",
                              )}
                              style={{
                                width: `${(run.progress.done / run.progress.total) * 100}%`,
                              }}
                            />
                          </span>
                          <span className="text-xs tabular-nums">
                            {run.progress.done}/{run.progress.total}
                            {run.progress.failed
                              ? `（失败 ${run.progress.failed}）`
                              : ""}
                          </span>
                        </span>
                        {run.status === "running" &&
                        run.progress.processing?.length ? (
                          <span
                            className="text-muted-foreground max-w-[220px] truncate text-xs"
                            title={run.progress.processing.join(", ")}
                          >
                            处理中: {run.progress.processing.join(", ")}
                          </span>
                        ) : null}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  {/* 计数列：mono + tabular（原型 .r .num .mono 数字习语） */}
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {run.docs_processed}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {run.items_extracted}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {run.clusters_formed}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {run.duration_ms != null
                      ? `${(run.duration_ms / 1000).toFixed(1)}s`
                      : "—"}
                  </TableCell>
                  {/* 操作：仅删除（下载按钮用户 2026-10-16 定案去除）；无动作不渲染 "—" 占位 */}
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <Button
                        size="icon"
                        variant="ghost"
                        title="删除"
                        disabled={deleteRun.isPending}
                        onClick={() => {
                          if (!confirm("确认删除此运行记录？")) return;
                          deleteRun.mutate(run.id);
                        }}
                      >
                        <Trash2 className="text-muted-foreground hover:text-destructive h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {runs.some((r) => r.status === "failed" && r.error) ? (
          <div className="border-border text-destructive space-y-1 border-t px-4 py-2.5 text-xs">
            {runs
              .filter((r) => r.status === "failed" && r.error)
              .slice(0, 3)
              .map((r) => (
                <p key={r.id} className="truncate">
                  {formatDate(r.started_at)}: {r.error}
                </p>
              ))}
          </div>
        ) : null}
        {/* 分页脚注（对齐合同解析页 tbl-foot 习语） */}
        <div className="border-border flex items-center justify-between border-t px-4 py-2.5">
          <span className="text-muted-foreground text-xs tabular-nums">
            共 {total} 条
          </span>
          <div className="flex items-center gap-3">
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v));
                setPage(0);
              }}
            >
              <SelectTrigger className="h-7 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 20, 50].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    每页 {n} 条
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7"
                disabled={page <= 0}
                onClick={() => gotoPage(page - 1)}
                aria-label="上一页"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-muted-foreground px-1 text-xs tabular-nums">
                第 {page + 1} / {totalPages} 页
              </span>
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7"
                disabled={page >= totalPages - 1}
                onClick={() => gotoPage(page + 1)}
                aria-label="下一页"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
