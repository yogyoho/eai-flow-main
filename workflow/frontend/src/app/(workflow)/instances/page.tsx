"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  CircleDashed,
  ClipboardList,
  GitBranch,
  Inbox,
  Layers,
  PlayCircle,
  RefreshCw,
  Search,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useUserDirectory } from "@/lib/directory";
import type { InstanceWire } from "@/lib/types";
import { PageBody, PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { StartInstanceDialog } from "@/components/workflow/start-instance-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, formatNumber, formatDate, initials, relativeTime } from "@/lib/utils";

const FILTERS = [
  { value: "all", label: "全部" },
  { value: "0", label: "待提交" },
  { value: "1", label: "审批中" },
  { value: "9", label: "已退回" },
  { value: "8", label: "已完成" },
  { value: "4", label: "已终止" },
];

const PAGE_SIZE = 12;

const NODE_COLOR: Record<number, string> = {
  0: "border-emerald-100 bg-emerald-50 text-emerald-600",
  1: "border-sky-100 bg-sky-50 text-sky-600",
  2: "border-rose-100 bg-rose-50 text-rose-600",
  3: "border-amber-100 bg-amber-50 text-amber-600",
  4: "border-cyan-100 bg-cyan-50 text-cyan-600",
  5: "border-violet-100 bg-violet-50 text-violet-600",
};

export default function InstancesPage() {
  const queryClient = useQueryClient();
  const directory = useUserDirectory();
  const { user } = useSession();
  const [keyword, setKeyword] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filter, setFilter] = useState("all");
  const [definitionId, setDefinitionId] = useState("all");
  const [page, setPage] = useState(1);
  const [startOpen, setStartOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(keyword.trim());
      setPage(1);
    }, 280);
    return () => clearTimeout(timer);
  }, [keyword]);

  const instancesQuery = useQuery({
    queryKey: ["instances", { debounced, filter, definitionId, page }],
    queryFn: () =>
      api.instances.list({
        page,
        size: PAGE_SIZE,
        businessId: debounced || undefined,
        flowStatus: filter === "all" ? undefined : filter,
        definitionId: definitionId === "all" ? undefined : Number(definitionId),
      }),
  });

  const statsQuery = useQuery({
    queryKey: ["meta", "stats"],
    queryFn: api.meta.stats,
  });

  const definitionsQuery = useQuery({
    queryKey: ["definitions", "filter-options"],
    queryFn: () => api.definitions.list({ page: 1, size: 200 }),
    staleTime: 60_000,
  });

  const total = instancesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = instancesQuery.data?.items ?? [];
  const hasFilter = filter !== "all" || Boolean(debounced) || definitionId !== "all";

  const stats = useMemo(
    () => [
      {
        key: "instances",
        label: "累计实例",
        value: statsQuery.data?.instances ?? 0,
        icon: GitBranch,
        accent: "text-violet-600 bg-violet-50 border-violet-100",
      },
      {
        key: "running",
        label: "运行中",
        value: statsQuery.data?.running ?? 0,
        icon: Activity,
        accent: "text-amber-600 bg-amber-50 border-amber-100",
      },
      {
        key: "tasks",
        label: "待办任务",
        value: statsQuery.data?.tasks ?? 0,
        icon: ClipboardList,
        accent: "text-rose-600 bg-rose-50 border-rose-100",
      },
      {
        key: "published",
        label: "可发起流程",
        value: statsQuery.data?.published ?? 0,
        icon: Layers,
        accent: "text-emerald-600 bg-emerald-50 border-emerald-100",
      },
    ],
    [statsQuery.data],
  );

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["instances"] });
    queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
  }

  const pageLabel = useMemo(() => {
    if (instancesQuery.isLoading) return "加载中…";
    if (!total) return "共 0 条";
    return `第 ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} 条，共 ${total} 条`;
  }, [instancesQuery.isLoading, page, total]);

  return (
    <div className="app-grid-bg min-h-screen">
      <PageBody>
        <PageHeader
          eyebrow="Runtime Center"
          title="流程实例"
          description="追踪每一次发起的流程运行：当前节点、审批状态、表单快照与完整流转时间线。"
          actions={
            <>
              <Button variant="secondary" onClick={refresh}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button onClick={() => setStartOpen(true)}>
                <PlayCircle className="h-4 w-4" />
                发起流程
              </Button>
            </>
          }
        />

        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {stats.map((card) => {
            const Icon = card.icon;
            return (
              <div
                key={card.key}
                className="rounded-xl border border-border bg-card p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[11px] font-medium text-muted-foreground">{card.label}</p>
                    {statsQuery.isLoading ? (
                      <Skeleton className="mt-2 h-7 w-12" />
                    ) : (
                      <p className="mt-1 text-[24px] font-semibold leading-none tracking-tight tabular-nums">
                        {formatNumber(card.value)}
                      </p>
                    )}
                  </div>
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-lg border",
                      card.accent,
                    )}
                  >
                    <Icon className="h-4 w-4" strokeWidth={2} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <div className="flex flex-col gap-3 border-b border-border p-4 xl:flex-row xl:items-center">
            <Tabs
              value={filter}
              onValueChange={(value) => {
                setFilter(value);
                setPage(1);
              }}
            >
              <TabsList>
                {FILTERS.map((item) => (
                  <TabsTrigger key={item.value} value={item.value}>
                    {item.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
              <div className="sm:w-[220px]">
                <Select
                  value={definitionId}
                  onValueChange={(value) => {
                    setDefinitionId(value);
                    setPage(1);
                  }}
                  placeholder="全部流程"
                  options={[
                    { value: "all", label: "全部流程" },
                    ...(definitionsQuery.data?.items || []).map((definition) => ({
                      value: String(definition.id),
                      label: definition.flow_name,
                    })),
                  ]}
                  className="h-9"
                />
              </div>
              <div className="relative sm:w-[260px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="搜索业务编号…"
                  className="h-9 pl-8"
                />
              </div>
            </div>
          </div>

          {instancesQuery.isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex items-center gap-4">
                  <Skeleton className="h-9 w-9 rounded-lg" />
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="ml-auto h-4 w-24" />
                </div>
              ))}
            </div>
          ) : instancesQuery.isError ? (
            <div className="p-4">
              <EmptyState
                title="实例加载失败"
                description="请确认工作流后端已启动（默认 http://127.0.0.1:8020），然后点击刷新重试。"
                action={
                  <Button variant="secondary" size="sm" onClick={refresh}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    重试
                  </Button>
                }
              />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={hasFilter ? "没有匹配的实例" : "还没有流程实例"}
                description={
                  hasFilter
                    ? "试试清空业务编号搜索、切换状态或流程筛选。"
                    : "发起第一个流程，审批通过后这里会沉淀完整的运行记录与流程图。"
                }
                icon={<Inbox className="h-5 w-5" />}
                action={
                  hasFilter ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setKeyword("");
                        setFilter("all");
                        setDefinitionId("all");
                      }}
                    >
                      清空筛选
                    </Button>
                  ) : (
                    <Button size="sm" onClick={() => setStartOpen(true)}>
                      <PlayCircle className="h-4 w-4" />
                      发起流程
                    </Button>
                  )
                }
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">流程 / 业务编号</TableHead>
                  <TableHead>发起人</TableHead>
                  <TableHead>当前节点</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>发起时间</TableHead>
                  <TableHead className="pr-5 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((instance) => (
                  <InstanceRow
                    key={instance.id}
                    instance={instance}
                    creator={directory.name(instance.create_by)}
                  />
                ))}
              </TableBody>
            </Table>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
            <p className="text-[11px] text-muted-foreground">{pageLabel}</p>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-7"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                上一页
              </Button>
              <span className="min-w-12 text-center text-[11px] tabular-nums text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        </div>

        <p className="mt-4 flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
          <span className="h-1 w-1 rounded-full bg-emerald-500" />
          当前身份 {user.name} · 实例按发起时间倒序 · 点击任意实例查看流程图与审批时间线
        </p>
      </PageBody>

      <StartInstanceDialog open={startOpen} onOpenChange={setStartOpen} />
    </div>
  );
}

function InstanceRow({ instance, creator }: { instance: InstanceWire; creator: string }) {
  const active = !["4", "5", "6", "8"].includes(instance.flow_status);
  return (
    <TableRow>
      <TableCell className="pl-5">
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
              NODE_COLOR[instance.node_type] || NODE_COLOR[1],
            )}
          >
            {active ? <CircleDashed className="h-4 w-4" /> : <GitBranch className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <Link
              href={`/instances/${instance.id}`}
              className="group flex items-center gap-1 text-[13.5px] font-medium hover:text-primary"
            >
              <span className="truncate">{instance.flow_name || "流程实例"}</span>
              <ArrowUpRight className="h-3 w-3 opacity-0 transition group-hover:opacity-100" />
            </Link>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="font-mono">{instance.business_id || `INSTANCE-${instance.id}`}</span>
              <span className="text-border">/</span>
              <span>#{instance.id}</span>
            </div>
          </div>
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[9px] font-medium text-muted-foreground">
            {initials(creator)}
          </span>
          <span className="text-[12px] text-foreground">{creator}</span>
        </div>
      </TableCell>
      <TableCell>
        <div className="flex flex-col gap-1">
          <span className="text-[12px] text-foreground">
            {instance.node_name || instance.node_code || "—"}
          </span>
          <Badge variant="outline" className="w-fit font-mono text-[10px]">
            {instance.node_code || "—"}
          </Badge>
        </div>
      </TableCell>
      <TableCell>
        <StatusBadge
          tone={instance.flow_status_tone}
          label={instance.flow_status_label || instance.flow_status}
        />
      </TableCell>
      <TableCell>
        <div className="text-[12px] text-foreground">{relativeTime(instance.create_time)}</div>
        <div className="text-[10.5px] text-muted-foreground">
          {formatDate(instance.create_time)}
        </div>
      </TableCell>
      <TableCell className="pr-5">
        <div className="flex items-center justify-end">
          <Button asChild size="sm" variant="secondary" className="h-8">
            <Link href={`/instances/${instance.id}`}>
              查看详情
              <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
