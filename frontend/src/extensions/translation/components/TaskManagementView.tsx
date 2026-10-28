"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  ClipboardCheck,
  Eye,
  FileText,
  ListPlus,
  Loader2,
  MoreHorizontal,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";
import { toast } from "sonner";

import { FileTypeIcon } from "@/components/file-type-icons";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import {
  batchTranslateTasks,
  createBackfillJob,
  deleteTask,
  getTaskStats,
  listKbOptions,
  listTasks,
  transitionTask,
  translateTask,
} from "../api";
import type { TltTask } from "../types";

import { PageHeader } from "./PageHeader";
import { StateBadge } from "./StateBadge";

const PAGE_SIZE = 50;
const POLL_MS = 10_000;

/** 机检轴的用户语标签（文案红线映射表）。 */
const GATE_LABELS: Record<string, string> = {
  numeric: "数字准确性",
  terminology: "术语一致性",
  structure: "格式完整性",
};

function fmtSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("zh-CN", { hour12: false });
}

export function TaskManagementView() {
  const qc = useQueryClient();
  const router = useRouter();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["tlt-tasks"] });
  };

  const [page, setPage] = useState(1);
  const [stateFilter, setStateFilter] = useState("all");
  const [kbFilter, setKbFilter] = useState("all");
  const [langFilter, setLangFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [q, setQ] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [detailId, setDetailId] = useState<string | null>(null);
  const [paneOpen, setPaneOpen] = useState(false);
  const [backfilling, setBackfilling] = useState(false);

  // flash: sonner 右下角 toast(对齐知识工厂),不再内嵌通知条——列表不位移。
  const flash = (kind: "ok" | "err", text: string) =>
    kind === "ok" ? toast.success(text) : toast.error(text);

  const tasksQ = useQuery({
    queryKey: [
      "tlt-tasks",
      "mgmt",
      page,
      stateFilter,
      kbFilter,
      langFilter,
      tierFilter,
      q,
    ],
    queryFn: () =>
      listTasks({
        page,
        page_size: PAGE_SIZE,
        state: stateFilter === "all" ? undefined : stateFilter,
        kb_id: kbFilter === "all" ? undefined : kbFilter,
        source_lang: langFilter === "all" ? undefined : langFilter,
        quality_tier: tierFilter === "all" ? undefined : tierFilter,
        q: q || undefined,
      }),
    refetchInterval: POLL_MS,
  });

  const kbOptionsQ = useQuery({
    queryKey: ["tlt-kb-options"],
    queryFn: listKbOptions,
    staleTime: 5 * 60_000,
  });

  const statsQ = useQuery({
    queryKey: ["tlt-tasks", "stats", kbFilter],
    queryFn: () => getTaskStats(kbFilter === "all" ? undefined : kbFilter),
    refetchInterval: POLL_MS,
  });
  const stats = statsQ.data;

  const tasks = tasksQ.data?.items ?? [];
  const total = tasksQ.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const translatable = tasks.filter(
    (t) => checked.has(t.id) && (t.state === "stored" || t.state === "failed"),
  );

  // 行级缓存：分页翻走后详情栏仍能展示最后已知数据
  const lastSeen = new Map<string, TltTask>();
  for (const t of tasks) lastSeen.set(t.id, t);
  if (detailId && !lastSeen.has(detailId)) {
    // 当前页找不到（翻页/筛选切换）时保留最后快照
    // detail 直接取快照，无需额外状态
  }

  const detail = detailId
    ? (tasks.find((t) => t.id === detailId) ?? null)
    : null;

  const doTranslateChecked = async () => {
    if (!translatable.length) return;
    try {
      const res = await batchTranslateTasks(translatable.map((t) => t.id));
      invalidate();
      setChecked(new Set());
      flash(
        "ok",
        res.queued === translatable.length
          ? `已提交 ${res.queued} 个翻译任务`
          : `已提交 ${res.queued} 个；${res.skipped.length} 个状态已变化被跳过`,
      );
    } catch (e) {
      flash("err", `提交失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** P2 超大回填：按当前知识库筛选创建后台分批任务。 */
  const startBackfill = async () => {
    setBackfilling(true);
    try {
      const job = await createBackfillJob({
        kb_id: kbFilter === "all" ? undefined : kbFilter,
        states: ["stored", "failed"],
        chunk_size: 100,
      });
      invalidate();
      flash(
        "ok",
        `已创建回填任务（${job.total} 个，每批 ${job.chunk_size} 个入队）`,
      );
    } catch (e) {
      flash("err", `回填失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBackfilling(false);
    }
  };

  const doTransition = async (t: TltTask, target: string, okText: string) => {
    try {
      await transitionTask(t.id, target);
      invalidate();
      flash("ok", okText);
    } catch (e) {
      flash("err", `操作失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const doDelete = async (t: TltTask) => {
    if (!window.confirm(`删除「${t.file_name}」？将下线检索索引，交付物文件保留。`))
      return;
    try {
      await deleteTask(t.id);
      invalidate();
      const s = new Set(checked);
      s.delete(t.id);
      setChecked(s);
      if (detailId === t.id) {
        setDetailId(null);
        setPaneOpen(false);
      }
      flash("ok", "已删除并下线检索（交付物留档）");
    } catch (e) {
      flash("err", `删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const openDetail = (t: TltTask) => {
    setDetailId(t.id);
    setPaneOpen(true);
  };

  const opsFor = (t: TltTask) => {
    const ops: { label: string; icon: ReactNode; run: () => void }[] = [];
    if (t.state === "stored" || t.state === "failed") {
      ops.push({
        label: t.state === "failed" ? "重跑翻译" : "翻译",
        icon: <Play className="mr-2 h-4 w-4" />,
        run: () =>
          void translateTask(t.id)
            .then(() => {
              invalidate();
              flash("ok", "已加入翻译队列");
            })
            .catch((e) => flash("err", String(e))),
      });
    }
    if (t.state === "delivered") {
      ops.push({
        label: "预览译本",
        icon: <Eye className="mr-2 h-4 w-4" />,
        run: () => openDetail(t),
      });
    }
    if (t.state === "exceeded") {
      ops.push({
        label: "去复核",
        icon: <ClipboardCheck className="mr-2 h-4 w-4" />,
        run: () => router.push(`/translation/review?task_id=${t.id}`),
      });
    }
    if (["pending", "running", "check_failed", "retrying"].includes(t.state)) {
      ops.push({
        label: "取消任务",
        icon: <Ban className="mr-2 h-4 w-4" />,
        run: () =>
          void doTransition(t, "cancelled", "任务已取消").catch((e) =>
            flash("err", String(e)),
          ),
      });
    }
    ops.push({
      label: "删除文档",
      icon: <Trash2 className="mr-2 h-4 w-4" />,
      run: () => void doDelete(t).catch((e) => flash("err", String(e))),
    });
    return ops;
  };

  /** 任务列表骨架：列形对齐真实表（勾选/文件名/知识库/语言/状态/进度/更新时间/操作）。 */
  const TableSkeleton = () => (
    <div role="status" aria-label="任务列表加载中">
      <table className="w-full text-sm" aria-hidden>
        <thead>
          <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
            <th className="w-8 px-2 py-2" />
            <th className="px-2 py-2">文件名</th>
            <th className="px-2 py-2">知识库</th>
            <th className="px-2 py-2">语言</th>
            <th className="px-2 py-2">状态</th>
            <th className="px-2 py-2">进度</th>
            <th className="px-2 py-2">更新时间</th>
            <th className="w-10 px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }, (_, i) => (
            <tr
              key={i}
              className="border-b border-[var(--gray-100)] last:border-b-0"
            >
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 size-3.5 animate-pulse rounded-sm" />
              </td>
              <td className="px-2 py-2">
                <div className="flex items-center gap-2">
                  <div className="bg-muted-foreground/15 size-5 shrink-0 animate-pulse rounded" />
                  <div
                    className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
                    style={{ width: 140 + (i % 4) * 24 }}
                  />
                </div>
              </td>
              <td className="px-2 py-2">
                <div
                  className="bg-muted-foreground/15 h-3 animate-pulse rounded"
                  style={{ width: 90 + (i % 3) * 20 }}
                />
              </td>
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 h-3 w-12 animate-pulse rounded" />
              </td>
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 h-5 w-16 animate-pulse rounded-full" />
              </td>
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 h-3 w-10 animate-pulse rounded" />
              </td>
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 h-3 w-28 animate-pulse rounded" />
              </td>
              <td className="px-2 py-2">
                <div className="bg-muted-foreground/15 ml-auto size-4 animate-pulse rounded" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-3 pb-4">
      <PageHeader
        title="任务管理"
        description="翻译任务队列与状态跟踪"
        icon={<FileText />}
        actions={
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-[13px]"
                  disabled={backfilling}
                  onClick={() => void startBackfill()}
                >
                  {backfilling ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <ListPlus className="mr-1 h-3 w-3" />
                  )}
                  回填未翻译
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-72">
                按当前知识库筛选，把未翻译和翻译失败的文档分批加入队列，后台按批处理；已交付文件不受影响。
              </TooltipContent>
            </Tooltip>
            {checked.size > 0 && (
              <Button
                size="sm"
                disabled={!translatable.length}
                onClick={doTranslateChecked}
              >
                {tasksQ.isFetching ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Play className="mr-1 h-3 w-3" />
                )}
                翻译 ({translatable.length})
              </Button>
            )}
          </>
        }
      />

      {/* P2-16 头部指标条：按状态聚合（同 owner 口径） */}
      <div className="bg-card border-border flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg border px-4 py-2.5">
        {(
          [
            ["任务总数", stats?.total ?? 0, ""],
            ["已交付", stats?.delivered ?? 0, "text-[var(--success-700)]"],
            ["翻译中", stats?.running ?? 0, "text-[var(--info-700)]"],
            ["待复核", stats?.exceeded ?? 0, "text-[var(--warning-900)]"],
            ["无需翻译", stats?.skipped ?? 0, "text-muted-foreground"],
          ] as const
        ).map(([label, value, tone]) => (
          <div key={label} className="flex items-baseline gap-2">
            <span className="text-muted-foreground text-xs">{label}</span>
            <span
              className={cn(
                "text-foreground text-lg leading-none font-bold tabular-nums",
                tone,
              )}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* 筛选行 */}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={stateFilter}
          onValueChange={(v) => {
            setStateFilter(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {(
              [
                ["stored", "未翻译"],
                ["pending", "排队中"],
                ["running", "翻译中"],
                ["check_failed", "机检未过"],
                ["retrying", "重试中"],
                ["exceeded", "待复核"],
                ["indexed", "入库中"],
                ["delivered", "已交付"],
                ["failed", "失败"],
                ["skipped", "无需翻译"],
              ] as const
            ).map(([v, label]) => (
              <SelectItem key={v} value={v}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={kbFilter}
          onValueChange={(v) => {
            setKbFilter(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="知识库" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部知识库</SelectItem>
            {(kbOptionsQ.data ?? []).map((k) => (
              <SelectItem key={k.id} value={k.id}>
                {k.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={langFilter}
          onValueChange={(v) => {
            setLangFilter(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="语言" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部语言</SelectItem>
            <SelectItem value="en">EN</SelectItem>
            <SelectItem value="fr">FR</SelectItem>
            <SelectItem value="zh">ZH</SelectItem>
            <SelectItem value="mixed">MIXED</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={tierFilter}
          onValueChange={(v) => {
            setTierFilter(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="质量档" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部质量档</SelectItem>
            <SelectItem value="draft">标准版</SelectItem>
            <SelectItem value="reviewed">人工校对版</SelectItem>
          </SelectContent>
        </Select>
        <div className="relative w-64">
          <Search className="text-muted-foreground absolute top-2.5 left-2.5 h-4 w-4" />
          <Input
            placeholder="搜索 文件名 / sha"
            className="pl-8"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <span className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            qc.invalidateQueries({ queryKey: ["tlt-tasks", "mgmt"] })
          }
        >
          <RefreshCw
            className={cn("h-4 w-4", tasksQ.isFetching && "animate-spin")}
          />
        </Button>
      </div>

      {/* master-detail：左表格 + 右详情区（点行展开，X 收起） */}
      <div className="flex min-h-0 flex-1 gap-3">
        {/* 左：表格 + 分页 */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1 overflow-auto rounded-lg border">
            {tasksQ.isLoading ? (
              <TableSkeleton />
            ) : tasks.length === 0 ? (
              <div className="text-muted-foreground p-8 text-center text-sm">
                没有符合条件的任务。在资产库上传 EN/FR 文档后开始翻译。
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                    <th className="w-8 px-2 py-2">
                      <Checkbox
                        checked={
                          tasks.every((t) => checked.has(t.id)) &&
                          tasks.length > 0
                        }
                        onCheckedChange={(v) =>
                          setChecked(
                            v ? new Set(tasks.map((t) => t.id)) : new Set(),
                          )
                        }
                        className="border-muted-foreground/40 hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary h-3.5 w-3.5 rounded-[4px] shadow-none transition-all"
                      />
                    </th>
                    <th className="px-2 py-2">文件名</th>
                    <th className="px-2 py-2">知识库</th>
                    <th className="px-2 py-2">语言</th>
                    <th className="px-2 py-2">状态</th>
                    <th className="px-2 py-2">进度</th>
                    <th className="px-2 py-2">更新时间</th>
                    <th className="w-10 px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr
                      key={t.id}
                      className={cn(
                        "hover:bg-muted/50 cursor-pointer border-b border-[var(--gray-100)] transition-colors last:border-b-0",
                        detailId === t.id && "bg-accent/60",
                      )}
                      onClick={() => openDetail(t)}
                    >
                      <td
                        className="px-2 py-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={checked.has(t.id)}
                          onCheckedChange={(v) => {
                            const s = new Set(checked);
                            if (v) {
                              s.add(t.id);
                            } else {
                              s.delete(t.id);
                            }
                            setChecked(s);
                          }}
                          className="border-muted-foreground/40 hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary h-3.5 w-3.5 rounded-[4px] shadow-none transition-all"
                        />
                      </td>
                      <td className="max-w-64 truncate px-2 py-2">
                        <span className="flex items-center gap-2">
                          <FileTypeIcon
                            name={t.file_name}
                            className="h-5 w-5 shrink-0"
                          />
                          <span className="truncate font-mono text-[13px] font-medium">
                            {t.file_name}
                          </span>
                        </span>
                      </td>
                      <td
                        className={cn(
                          "text-muted-foreground px-2 py-2",
                          t.kb_name &&
                            /^[\x20-\x7E]*$/.test(t.kb_name) &&
                            "font-mono",
                        )}
                      >
                        {t.kb_name ?? "—"}
                      </td>
                      <td className="text-muted-foreground px-2 py-2 font-mono uppercase">
                        {t.source_lang}
                      </td>
                      <td className="px-2 py-2">
                        <StateBadge state={t.state} progress={t.progress} />
                      </td>
                      <td className="px-2 py-2 font-mono tabular-nums">
                        {t.progress}%
                      </td>
                      <td className="text-muted-foreground px-2 py-2 font-mono tabular-nums">
                        {fmtTime(t.updated_at)}
                      </td>
                      <td className="px-2 py-2 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {opsFor(t).map((op) => (
                              <DropdownMenuItem key={op.label} onClick={op.run}>
                                {op.icon} {op.label}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* 分页（初始化骨架期间不显示，避免「共 0 条」误导） */}
          {!tasksQ.isLoading && (
            <div className="flex items-center justify-center gap-3 text-sm">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span className="text-muted-foreground tabular-nums">
                {page} / {totalPages} · 共 {total} 条
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </div>

        {/* 右：详情区（点行展开；X 收起；收起时不占位） */}
        {paneOpen && detail && (
          <aside className="bg-card flex w-[420px] shrink-0 flex-col overflow-hidden rounded-lg border shadow-sm">
            {/* 详情头 */}
            <div className="flex items-start gap-2.5 border-b px-4 py-3">
              <FileTypeIcon
                name={detail.file_name}
                className="mt-0.5 h-5 w-5 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-[13px] font-semibold">
                  {detail.file_name}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <StateBadge state={detail.state} progress={detail.progress} />
                  <span className="text-muted-foreground text-xs tabular-nums">
                    {detail.quality_tier === "reviewed"
                      ? "人工校对版"
                      : "标准版"}{" "}
                    · v{detail.task_version}
                  </span>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => setPaneOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* 详情体 */}
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-3">
              {/* 溯源 */}
              <section>
                <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                  溯源
                </div>
                <div className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-1 text-sm">
                  <span className="text-muted-foreground text-xs">
                    来源文件
                  </span>
                  <span className="truncate font-mono text-xs">
                    {detail.source_uri ?? "—"}
                  </span>
                  <span className="text-muted-foreground text-xs">SHA-256</span>
                  <span className="truncate font-mono text-xs">
                    {detail.doc_sha}
                  </span>
                  <span className="text-muted-foreground text-xs">源语言</span>
                  <span className="font-mono uppercase">
                    {detail.source_lang}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    内容语义
                  </span>
                  <span
                    className={cn(
                      detail.content_tag &&
                        /^[\x20-\x7E]*$/.test(detail.content_tag) &&
                        "font-mono",
                    )}
                  >
                    {detail.content_tag ?? "—"}
                  </span>
                  <span className="text-muted-foreground text-xs">知识库</span>
                  <span
                    className={cn(
                      "truncate",
                      detail.kb_name &&
                        /^[\x20-\x7E]*$/.test(detail.kb_name) &&
                        "font-mono",
                    )}
                  >
                    {detail.kb_name ?? "—"}
                  </span>
                  <span className="text-muted-foreground text-xs">大小</span>
                  <span className="font-mono tabular-nums">
                    {fmtSize(detail.size_bytes)}
                  </span>
                </div>
              </section>

              {/* 三轴机检 */}
              <section>
                <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                  三轴机检
                </div>
                {detail.gate_failures ? (
                  <div className="flex flex-col gap-2">
                    {Object.entries(detail.gate_failures).map(
                      ([axis, violations]) => (
                        <div
                          key={axis}
                          className="border-destructive/30 bg-destructive/5 rounded-md border p-2.5 text-xs"
                        >
                          <div className="text-destructive flex items-center gap-1.5 font-medium">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            {GATE_LABELS[axis] ?? axis} ❌
                          </div>
                          <ul className="text-muted-foreground mt-1 list-inside list-disc font-mono">
                            {violations.slice(0, 6).map((v, i) => (
                              <li key={i}>{v}</li>
                            ))}
                          </ul>
                        </div>
                      ),
                    )}
                  </div>
                ) : (
                  <div className="border-success/30 bg-success/5 text-success flex items-center gap-1.5 rounded-md border p-2.5 text-xs">
                    ✅ 三轴机检全部通过（数字准确性 / 术语一致性 / 格式完整性）
                  </div>
                )}
              </section>

              {/* 不确定段 */}
              {detail.uncertainty && detail.uncertainty.length > 0 && (
                <section>
                  <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                    不确定段（LLM 标记）
                  </div>
                  <ul className="text-muted-foreground flex flex-col gap-1 font-mono text-xs">
                    {detail.uncertainty.map((u, i) => (
                      <li key={i} className="truncate">
                        {u.block}
                        {u.spans?.length ? ` — ${u.spans.join(" · ")}` : ""}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* 交付物 */}
              <section>
                <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                  交付物
                </div>
                {detail.deliverable_uri ? (
                  <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <FileTypeIcon
                        name={`${detail.file_name.replace(/\.[^.]+$/, "")}.md`}
                        className="h-5 w-5 shrink-0"
                      />
                      <span className="truncate font-mono text-[13px]">
                        {detail.file_name.replace(/\.[^.]+$/, "")}.zh.md
                      </span>
                    </span>
                    <Button variant="outline" size="sm" asChild>
                      <a
                        href={`/api/extensions/translation/tasks/${detail.id}/deliverable`}
                      >
                        下载
                      </a>
                    </Button>
                  </div>
                ) : (
                  <div className="text-muted-foreground text-sm">
                    —（翻译交付后生成）
                  </div>
                )}
              </section>

              {/* RAGFlow */}
              <section>
                <div className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-wide">
                  RAGFlow
                </div>
                <div className="font-mono text-xs">
                  {detail.ragflow_zh_doc_id ?? "—"}
                </div>
              </section>

              <div className="text-muted-foreground text-xs tabular-nums">
                任务版本 v{detail.task_version} · 重试 {detail.retry_count}/3 ·
                更新 {fmtTime(detail.updated_at)}
              </div>
            </div>

            {/* 操作栏 */}
            <div className="flex flex-wrap gap-2 border-t px-4 py-3">
              {["stored", "failed"].includes(detail.state) && (
                <Button
                  size="sm"
                  onClick={() =>
                    void doTransition(detail, "pending", "已加入翻译队列")
                  }
                >
                  <Play className="mr-1 h-3.5 w-3.5" /> 翻译
                </Button>
              )}
              {["pending", "running", "check_failed", "retrying"].includes(
                detail.state,
              ) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    void doTransition(detail, "cancelled", "任务已取消")
                  }
                >
                  <Ban className="mr-1 h-3.5 w-3.5" /> 取消任务
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => void doDelete(detail)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除文档
              </Button>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
