"use client";

/**
 * 任务列表(bid:page:tasks,/bid-review)——Task 12 最小版。
 * 视觉规范:docs/designs/2026-10-29-bid-review-ui-spec.md §3.1(PageHeader + 4×StatCard
 * + 密集表格 + tbl-foot + 骨架/空态/错误态);共享基元直接 import cpa 路径(勿复制第六份)。
 * 新建 = Dialog(模式 SegmentedToggle §1.2 配方内联,Task 17 抽 primitives.tsx 后可替换)
 * + 招标/投标文件上传(POST /tasks multipart 是后端唯一文档入口,零材料任务会被后端
 * _enqueue_docs 无条件直推空跑——Task 12 修复轮决定 (b):创建必传文件;M3 工作台
 * 上传 = 补充/重传文档)。
 * 修复轮 2026-10-29(评审 Important:硬编码 fatalCount=0/needHumanCount=0 伪零):
 * 致命未处理/待人工与行级致命数改为逐任务 issues 实测(useBidIssues 同 queryKey/
 * queryFn 缓存空间,useQueries 批量挂起);统计未测全时显示 ———未经测量 ≠ 零,
 * 合规门禁列表首屏伪零会误导用户跳过工作台。回归门:tests/unit/extensions/
 * bid-review-tasks-view.dom.test.tsx。
 */

import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
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
import {
  createTask,
  listTaskIssues,
  listTasks,
} from "@/extensions/bid-review/api";
import { bidReviewKeys } from "@/extensions/bid-review/hooks";
import { type IssueOut, type TaskOut } from "@/extensions/bid-review/types";
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
  quick: "确定性规则快审(M1 子集),上传文件后自动执行,秒级完成。",
  deep: "全量规则深审(含语义逐条审,耗时较长);生成基线后需在工作台人工确认再续跑。",
};

/** 已出问题结果的任务状态——created/parsing/extracting/running 的问题集是半程快照,
 * 拉了也会变,不拉(行内显示 —)。修复轮 2026-10-29:未测量的任务不得以 0 计入统计。 */
const RESULT_STATUSES = new Set(["done", "awaiting_confirm", "failed"]);

/** 致命未处理 = fatal 且未被人工判误报(误报经 Task 16 feedback 落库 verdict=
 * false_positive,已处置不再是「未处理」;工作台 GateMetricsRow 的「致命」计全部
 * fatal,此处口径有意收窄以对齐本页「未处理」标签语义)。 */
function fatalUnhandled(issues: IssueOut[]): number {
  return issues.filter(
    (i) => i.severity === "fatal" && i.verdict !== "false_positive",
  ).length;
}

/** 待人工 = need_human 旗标(误报回写时后端已置 false,天然回落;与工作台同口径)。 */
function countNeedHuman(issues: IssueOut[]): number {
  return issues.filter((i) => i.need_human).length;
}

/** 行级致命数格(§3.1 tabular,>0 error 深档)。问题清单未取到(处理中任务/请求中/
 * 失败)显示 ———未测量不得显示 0(修复轮 2026-10-29 伪零消除)。 */
function FatalCell({
  query,
  gated,
}: {
  query: UseQueryResult<IssueOut[], Error> | undefined;
  gated: boolean;
}) {
  if (gated) {
    return (
      <span
        className="text-muted-foreground tabular-nums"
        title="任务未出结果,暂无统计"
      >
        —
      </span>
    );
  }
  if (!query || query.isPending) {
    return (
      <span
        className="text-muted-foreground tabular-nums"
        title="问题清单加载中"
      >
        —
      </span>
    );
  }
  if (query.isError) {
    return (
      <span
        className="text-muted-foreground tabular-nums"
        title={`问题清单加载失败:${query.error.message}`}
      >
        —
      </span>
    );
  }
  const n = fatalUnhandled(query.data ?? []);
  return (
    <span
      className={cn(
        "tabular-nums",
        n > 0 && "font-medium text-[var(--error-700)]",
      )}
    >
      {n}
    </span>
  );
}

/**
 * §2 状态 Pill 映射(词汇=后端 models.py:30:created|parsing|extracting|awaiting_confirm|
 * running|done|failed;勘误 2026-10-29:终态成功是 done,spec 原文 completed 系笔误):
 * done=success / failed=error / running,parsing,extracting=info / awaiting_confirm=warn /
 * created(pending)=gray(muted 习语);completed 仅作兼容别名(后端只发 done)。
 */
function statusPill(status: string): { tone: PillTone; label: string } {
  switch (status) {
    case "done":
    case "completed":
      return { tone: "success", label: "已完成" };
    case "failed":
      return { tone: "error", label: "失败" };
    case "running":
      return { tone: "info", label: "进行中" };
    case "parsing":
      return { tone: "info", label: "解析中" };
    case "extracting":
      return { tone: "info", label: "基准提取中" };
    case "awaiting_confirm":
      return { tone: "warn", label: "待确认" };
    default:
      return {
        tone: "gray",
        label: status === "created" || status === "pending" ? "已创建" : status,
      };
  }
}

/** §3.1 meter:进度取 progress.pct(worker 契约);done 恒 100(worker done 帧 pct=100,
 * 此处兜底;原 completed 判定不在后端词汇里,是恒死分支——Task 12 修复轮勘误)。 */
function progressPct(t: TaskOut): number {
  if (t.status === "done") return 100;
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
  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [bidFiles, setBidFiles] = useState<File[]>([]);

  const tasksQuery = useQuery({
    queryKey: ["bid-review", "tasks"],
    queryFn: listTasks,
  });

  const createMutation = useMutation({
    mutationFn: (input: {
      mode: "quick" | "deep";
      tender: File[];
      bid: File[];
    }) => createTask(input.mode, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bid-review", "tasks"] });
      setDialogOpen(false);
    },
  });

  /** 打开新建 Dialog:清残留文件与上次错误(创建成功/取消后再开都是干净态)。 */
  const openDialog = () => {
    setTenderFiles([]);
    setBidFiles([]);
    createMutation.reset();
    setDialogOpen(true);
  };

  const tasks = tasksQuery.data ?? [];
  const runningCount = tasks.filter((t) => t.status === "running").length;
  // 逐任务问题统计(修复轮 2026-10-29 填实,原硬编码 0):与 useBidIssues 同 queryKey/
  // queryFn(缓存共享,工作台读同一份),仅对已出结果的任务经 useQueries 批量挂起。
  const statTasks = tasks.filter((t) => RESULT_STATUSES.has(t.status));
  const issuesQueries = useQueries({
    queries: statTasks.map((t) => ({
      queryKey: bidReviewKeys.issues(t.id),
      queryFn: () => listTaskIssues(t.id),
    })),
  });
  const issuesByTask = new Map<string, UseQueryResult<IssueOut[], Error>>();
  statTasks.forEach((t, i) => {
    const q = issuesQueries[i];
    if (q) issuesByTask.set(t.id, q);
  });
  // 聚合卡:全部任务均处已出结果状态且各自问题清单都取到,才给数字;列表加载失败或存在
  // 处理中/未取到的问题清单时显示 ———统计未测全时任何数字(包括部分和、包括 0)都是编造。
  const allMeasured =
    !tasksQuery.isError &&
    tasks.length === statTasks.length &&
    issuesQueries.every((q) => q.isSuccess);
  const fatalCount = allMeasured
    ? issuesQueries.reduce((sum, q) => sum + fatalUnhandled(q.data ?? []), 0)
    : null;
  const needHumanCount = allMeasured
    ? issuesQueries.reduce((sum, q) => sum + countNeedHuman(q.data ?? []), 0)
    : null;

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
              <Button size="sm" onClick={openDialog}>
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
            {/* 未测全时 null → 「—」(修复轮 2026-10-29:伪零即误导合规信号) */}
            <StatCard
              label="致命未处理"
              value={fatalCount ?? "—"}
              tone="warn"
            />
            <StatCard label="待人工" value={needHumanCount ?? "—"} />
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
          <Button size="sm" onClick={openDialog}>
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
                    {/* 行级致命数:逐任务 issues 实测(修复轮 2026-10-29 填实原恒「—」占位) */}
                    <TableCell>
                      <FatalCell
                        query={issuesByTask.get(t.id)}
                        gated={!RESULT_STATUSES.has(t.status)}
                      />
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

      {/* 新建 = Dialog(§3.1;模式 SegmentedToggle §1.2 配方内联,Task 17 抽 primitives 后替换;
          文件上传为必选项——POST /tasks multipart 是后端唯一文档入口,零材料任务会被后端
          无条件直推空跑,Task 12 修复轮决定 (b)) */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>新建审查任务</DialogTitle>
            <DialogDescription>
              上传招标与投标文件后创建;任务创建即自动解析并审查(quick
              秒级完成,deep 生成基线后待工作台人工确认)。
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
          <div className="flex flex-col gap-2">
            <span className="text-muted-foreground text-xs font-medium">
              文档(招标、投标至少各一份)
            </span>
            <label className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-xs">招标文件</span>
              <input
                type="file"
                multiple
                onChange={(e) =>
                  setTenderFiles(Array.from(e.target.files ?? []))
                }
                className="file:border-border file:bg-card file:text-foreground text-xs file:mr-2 file:rounded-md file:border file:px-2 file:py-0.5 file:text-xs"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-xs">投标文件</span>
              <input
                type="file"
                multiple
                onChange={(e) => setBidFiles(Array.from(e.target.files ?? []))}
                className="file:border-border file:bg-card file:text-foreground text-xs file:mr-2 file:rounded-md file:border file:px-2 file:py-0.5 file:text-xs"
              />
            </label>
            {tenderFiles.length + bidFiles.length > 0 ? (
              <p className="text-muted-foreground truncate text-xs">
                已选:
                {[...tenderFiles, ...bidFiles].map((f) => f.name).join("、")}
              </p>
            ) : null}
            <p className="text-muted-foreground text-xs">
              v1 后端将上传文件按 UTF-8 纯文本解码(.txt/.md
              等文本格式最适配;PDF/Word 结构化解析后续版本支持)。
            </p>
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
              onClick={() =>
                createMutation.mutate({
                  mode,
                  tender: tenderFiles,
                  bid: bidFiles,
                })
              }
              disabled={
                createMutation.isPending ||
                tenderFiles.length === 0 ||
                bidFiles.length === 0
              }
            >
              {createMutation.isPending ? "创建中…" : "创建任务"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
