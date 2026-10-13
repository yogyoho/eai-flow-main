"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Eye,
  FileText,
  Loader2,
  MoreHorizontal,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { type ReactNode, useState } from "react";

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
import { cn } from "@/lib/utils";

import {
  deleteTask,
  listKbOptions,
  listTasks,
  transitionTask,
  translateTask,
} from "../api";
import type { TltTask } from "../types";

import { FileIcon } from "./FileIcon";
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
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("zh-CN", { hour12: false });
}

export function TaskManagementView() {
  const qc = useQueryClient();
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
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const flash = (kind: "ok" | "err", text: string) => {
    setNotice({ kind, text });
    window.setTimeout(() => setNotice(null), 3500);
  };

  const tasksQ = useQuery({
    queryKey: ["tlt-tasks", "mgmt", page, stateFilter, kbFilter, langFilter, tierFilter, q],
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
      for (const t of translatable) await translateTask(t.id);
      invalidate();
      setChecked(new Set());
      flash("ok", `已提交 ${translatable.length} 个翻译任务`);
    } catch (e) {
      flash("err", `提交失败：${e instanceof Error ? e.message : String(e)}`);
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
      flash("ok", "已移出资产库（可恢复）");
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
      label: "移出资产库",
      icon: <Trash2 className="mr-2 h-4 w-4" />,
      run: () =>
        void doDelete(t).catch((e) => flash("err", String(e))),
    });
    return ops;
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* 顶栏 */}
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <FileText className="h-5 w-5" /> 任务管理
        </h1>
        <span className="text-sm text-muted-foreground">翻译任务队列与状态跟踪</span>
        <span className="flex-1" />
        {checked.size > 0 && (
          <Button size="sm" disabled={!translatable.length} onClick={doTranslateChecked}>
            {tasksQ.isFetching ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="mr-1 h-3.5 w-3.5" />
            )}
            翻译 ({translatable.length})
          </Button>
        )}
      </div>

      {notice && (
        <div
          className={cn(
            "rounded-md border px-3 py-2 text-sm",
            notice.kind === "ok"
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          {notice.text}
        </div>
      )}

      {/* 筛选行 */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={stateFilter} onValueChange={(v) => { setStateFilter(v); setPage(1); }}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {([
              ["stored", "未翻译"],
              ["pending", "排队中"],
              ["running", "翻译中"],
              ["check_failed", "机检未过"],
              ["retrying", "重试中"],
              ["exceeded", "待复核"],
              ["indexed", "入库中"],
              ["delivered", "已交付"],
              ["failed", "失败"],
            ] as const).map(([v, label]) => (
              <SelectItem key={v} value={v}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={kbFilter} onValueChange={(v) => { setKbFilter(v); setPage(1); }}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="知识库" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部知识库</SelectItem>
            {(kbOptionsQ.data ?? []).map((k) => (
              <SelectItem key={k.id} value={k.id}>{k.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={langFilter} onValueChange={(v) => { setLangFilter(v); setPage(1); }}>
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
        <Select value={tierFilter} onValueChange={(v) => { setTierFilter(v); setPage(1); }}>
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
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
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
          onClick={() => qc.invalidateQueries({ queryKey: ["tlt-tasks", "mgmt"] })}
        >
          <RefreshCw className={cn("h-4 w-4", tasksQ.isFetching && "animate-spin")} />
        </Button>
      </div>

      {/* master-detail：左表格 + 右详情区（点行展开，X 收起） */}
      <div className="flex min-h-0 flex-1 gap-3">
        {/* 左：表格 + 分页 */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1 overflow-auto rounded-lg border">
            {tasksQ.isLoading ? (
              <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
              </div>
            ) : tasks.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                没有符合条件的任务。在资产库上传 EN/FR 文档后开始翻译。
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                    <th className="w-8 px-2 py-2">
                      <Checkbox
                        checked={tasks.every((t) => checked.has(t.id)) && tasks.length > 0}
                        onCheckedChange={(v) =>
                          setChecked(v ? new Set(tasks.map((t) => t.id)) : new Set())
                        }
                        className="h-3.5 w-3.5 rounded-[4px] border-muted-foreground/40 shadow-none transition-all hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary"
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
                        "cursor-pointer border-b last:border-b-0 transition-colors hover:bg-muted/50",
                        detailId === t.id && "bg-accent/60",
                      )}
                      onClick={() => openDetail(t)}
                    >
                      <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
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
                          className="h-3.5 w-3.5 rounded-[4px] border-muted-foreground/40 shadow-none transition-all hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary"
                        />
                      </td>
                      <td className="max-w-64 truncate px-2 py-2">
                        <span className="flex items-center gap-2">
                          <FileIcon name={t.file_name} />
                          <span className="truncate font-medium">{t.file_name}</span>
                        </span>
                      </td>
                      <td className="px-2 py-2 text-muted-foreground">{t.kb_name ?? "—"}</td>
                      <td className="px-2 py-2 uppercase text-muted-foreground">{t.source_lang}</td>
                      <td className="px-2 py-2"><StateBadge state={t.state} progress={t.progress} /></td>
                      <td className="px-2 py-2 tabular-nums">{t.progress}%</td>
                      <td className="px-2 py-2 text-muted-foreground">{fmtTime(t.updated_at)}</td>
                      <td className="px-2 py-2 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={(e) => e.stopPropagation()}>
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

          {/* 分页 */}
          <div className="flex items-center justify-center gap-3 text-sm">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              上一页
            </Button>
            <span className="text-muted-foreground">
              {page} / {totalPages} · 共 {total} 条
            </span>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              下一页
            </Button>
          </div>
        </div>

        {/* 右：详情区（点行展开；X 收起；收起时不占位） */}
        {paneOpen && detail && (
          <aside className="flex w-[420px] shrink-0 flex-col overflow-hidden rounded-lg border bg-card shadow-sm">
            {/* 详情头 */}
            <div className="flex items-start gap-2.5 border-b px-4 py-3">
              <FileIcon name={detail.file_name} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold">{detail.file_name}</div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <StateBadge state={detail.state} progress={detail.progress} />
                  <span className="text-xs text-muted-foreground">
                    {detail.quality_tier === "reviewed" ? "人工校对版" : "标准版"} · v{detail.task_version}
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
                <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">溯源</div>
                <div className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-1 text-sm">
                  <span className="text-xs text-muted-foreground">来源文件</span>
                  <span className="truncate">{detail.source_uri ?? "—"}</span>
                  <span className="text-xs text-muted-foreground">SHA-256</span>
                  <span className="truncate font-mono text-xs">{detail.doc_sha}</span>
                  <span className="text-xs text-muted-foreground">源语言</span>
                  <span className="uppercase">{detail.source_lang}</span>
                  <span className="text-xs text-muted-foreground">内容语义</span>
                  <span>{detail.content_tag ?? "—"}</span>
                  <span className="text-xs text-muted-foreground">知识库</span>
                  <span className="truncate">{detail.kb_name ?? "—"}</span>
                  <span className="text-xs text-muted-foreground">大小</span>
                  <span>{fmtSize(detail.size_bytes)}</span>
                </div>
              </section>

              {/* 三轴机检 */}
              <section>
                <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">三轴机检</div>
                {detail.gate_failures ? (
                  <div className="flex flex-col gap-2">
                    {Object.entries(detail.gate_failures).map(([axis, violations]) => (
                      <div
                        key={axis}
                        className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
                      >
                        <div className="flex items-center gap-1.5 font-medium text-destructive">
                          <ShieldAlert className="h-3.5 w-3.5" />
                          {GATE_LABELS[axis] ?? axis} ❌
                        </div>
                        <ul className="mt-1 list-inside list-disc text-muted-foreground">
                          {(violations).slice(0, 6).map((v, i) => (
                            <li key={i}>{v}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 rounded-md border border-success/30 bg-success/5 p-2.5 text-xs text-success">
                    ✅ 三轴机检全部通过（数字准确性 / 术语一致性 / 格式完整性）
                  </div>
                )}
              </section>

              {/* 不确定段 */}
              {detail.uncertainty && detail.uncertainty.length > 0 && (
                <section>
                  <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">
                    不确定段（LLM 标记）
                  </div>
                  <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
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
                <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">交付物</div>
                {detail.deliverable_uri ? (
                  <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <FileIcon name={`${detail.file_name.replace(/\.[^.]+$/, "")}.md`} />
                      <span className="truncate">
                        {detail.file_name.replace(/\.[^.]+$/, "")}.zh.md
                      </span>
                    </span>
                    <Button variant="outline" size="sm" asChild>
                      <a href={`/api/extensions/translation/tasks/${detail.id}/deliverable`}>下载</a>
                    </Button>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">—（翻译交付后生成）</div>
                )}
              </section>

              {/* RAGFlow */}
              <section>
                <div className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground">RAGFlow</div>
                <div className="font-mono text-xs">{detail.ragflow_zh_doc_id ?? "—"}</div>
              </section>

              <div className="text-xs text-muted-foreground">
                任务版本 v{detail.task_version} · 重试 {detail.retry_count}/3 · 更新{" "}
                {fmtTime(detail.updated_at)}
              </div>
            </div>

            {/* 操作栏 */}
            <div className="flex flex-wrap gap-2 border-t px-4 py-3">
              {["stored", "failed"].includes(detail.state) && (
                <Button
                  size="sm"
                  onClick={() => void doTransition(detail, "pending", "已加入翻译队列")}
                >
                  <Play className="mr-1 h-3.5 w-3.5" /> 翻译
                </Button>
              )}
              {["pending", "running", "check_failed", "retrying"].includes(detail.state) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void doTransition(detail, "cancelled", "任务已取消")}
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
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 移出资产库
              </Button>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
