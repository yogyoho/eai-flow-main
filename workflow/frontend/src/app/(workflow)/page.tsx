"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowUpRight,
  Download,
  Ellipsis,
  PauseCircle,
  Plus,
  Search,
  Upload,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Definition } from "@/lib/types";
import { PageBody, PageHeader } from "@/components/page-header";
import { PublishBadge } from "@/components/status-badge";
import { StatCards } from "@/components/workflow/stat-cards";
import { CreateDefinitionDialog } from "@/components/workflow/create-definition-dialog";
import { ImportDefinitionDialog } from "@/components/workflow/import-definition-dialog";
import { DefinitionActionsDialog } from "@/components/workflow/definition-actions-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import { cn, formatDate, relativeTime } from "@/lib/utils";

const FILTERS = [
  { value: "all", label: "全部" },
  { value: "1", label: "已发布" },
  { value: "0", label: "未发布" },
  { value: "9", label: "已失效" },
];

const PAGE_SIZE = 10;

export default function WorkflowDefinitionsPage() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [actionTarget, setActionTarget] = useState<Definition | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(keyword.trim());
      setPage(1);
    }, 280);
    return () => clearTimeout(timer);
  }, [keyword]);

  const query = useQuery({
    queryKey: ["definitions", { debounced, filter, page }],
    queryFn: () =>
      api.definitions.list({
        page,
        size: PAGE_SIZE,
        flowName: debounced || undefined,
        isPublish: filter === "all" ? undefined : Number(filter),
      }),
    placeholderData: keepPreviousData,
  });

  const publishMutation = useMutation({
    mutationFn: ({ definition, publish }: { definition: Definition; publish: boolean }) =>
      publish
        ? api.definitions.publish(definition.id)
        : api.definitions.unpublish(definition.id),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["definitions"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success(variables.publish ? "流程已发布" : "已取消发布");
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "操作失败"),
  });

  const exportMutation = useMutation({
    mutationFn: (definition: Definition) => api.definitions.exportJson(definition.id),
    onSuccess: (payload, definition) => {
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${definition.flow_code}-v${definition.version}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success("已导出 JSON");
    },
    onError: (error: unknown) => toast.error(error instanceof ApiError ? error.message : "导出失败"),
  });

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = query.data?.items ?? [];
  const hasFilter = filter !== "all" || Boolean(debounced);

  const pageLabel = useMemo(() => {
    if (query.isLoading) return "加载中…";
    if (!total) return "共 0 条";
    return `第 ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} 条，共 ${total} 条`;
  }, [page, query.isLoading, total]);

  return (
    <div className="app-grid-bg min-h-screen">
      <PageBody>
        <PageHeader
          eyebrow="Workflow Studio"
          title="流程定义"
          description="集中管理流程模型、版本与发布状态。使用经典画布设计节点与跳转，保存后即可发起运行。"
          actions={
            <>
              <Button variant="secondary" onClick={() => setImportOpen(true)}>
                <Upload className="h-4 w-4" />
                导入
              </Button>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                新建流程
              </Button>
            </>
          }
        />

        <div className="mt-6">
          <StatCards />
        </div>

        <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center">
            <Tabs value={filter} onValueChange={(value) => { setFilter(value); setPage(1); }}>
              <TabsList>
                {FILTERS.map((item) => (
                  <TabsTrigger key={item.value} value={item.value}>
                    {item.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <div className="relative sm:ml-auto sm:w-[280px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索流程名称…"
                className="h-9 pl-8"
              />
            </div>
          </div>

          {query.isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex items-center gap-4">
                  <Skeleton className="h-9 w-9 rounded-lg" />
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="ml-auto h-4 w-24" />
                </div>
              ))}
            </div>
          ) : rows.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={hasFilter ? "没有匹配的流程" : "还没有流程定义"}
                description={
                  hasFilter
                    ? "试试清空搜索条件或切换发布状态筛选。"
                    : "从新建流程开始：填写基础信息后进入设计器，画好节点即可发布。"
                }
                action={
                  hasFilter ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setKeyword("");
                        setFilter("all");
                      }}
                    >
                      清空筛选
                    </Button>
                  ) : (
                    <Button size="sm" onClick={() => setCreateOpen(true)}>
                      <Plus className="h-4 w-4" />
                      新建流程
                    </Button>
                  )
                }
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">流程</TableHead>
                  <TableHead>版本</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">实例</TableHead>
                  <TableHead>更新时间</TableHead>
                  <TableHead className="pr-5 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((definition) => {
                  const published = definition.is_publish === 1;
                  const suspended = definition.activity_status === 0;
                  return (
                    <TableRow key={definition.id}>
                      <TableCell className="pl-5">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-sky-100 bg-sky-50 text-sky-600">
                            <Workflow className="h-4 w-4" />
                          </span>
                          <div className="min-w-0">
                            <Link
                              href={`/design/${definition.id}`}
                              className="group flex items-center gap-1 text-[13.5px] font-medium text-foreground hover:text-primary"
                            >
                              <span className="truncate">{definition.flow_name}</span>
                              <ArrowUpRight className="h-3 w-3 opacity-0 transition group-hover:opacity-100" />
                            </Link>
                            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                              <span className="font-mono">{definition.flow_code}</span>
                              {definition.category && (
                                <>
                                  <span className="text-border">/</span>
                                  <span>{definition.category}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-[12px] text-muted-foreground">
                          v{definition.version}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <PublishBadge value={definition.is_publish} />
                          {suspended && (
                            <Badge variant="warning" className="gap-1">
                              <PauseCircle className="h-3 w-3" />
                              挂起
                            </Badge>
                          )}
                          {published && !suspended && (
                            <span className="flex items-center gap-1 text-[10px] text-emerald-600">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              可发起
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="text-[13px] tabular-nums text-foreground">
                          {definition.instance_count ?? 0}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="text-[12px] text-foreground">
                          {relativeTime(definition.update_time)}
                        </div>
                        <div className="text-[10.5px] text-muted-foreground">
                          {formatDate(definition.update_time)}
                        </div>
                      </TableCell>
                      <TableCell className="pr-5">
                        <div className="flex items-center justify-end gap-1">
                          <Button asChild size="sm" variant="secondary" className="h-8">
                            <Link href={`/design/${definition.id}`}>设计</Link>
                          </Button>
                          <Button
                            size="sm"
                            variant={published ? "ghost" : "outline"}
                            className={cn(
                              "h-8",
                              published && "text-muted-foreground hover:text-foreground",
                            )}
                            disabled={publishMutation.isPending}
                            onClick={() => publishMutation.mutate({ definition, publish: !published })}
                          >
                            {published ? "取消发布" : "发布"}
                          </Button>
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            title="导出 JSON"
                            onClick={() => exportMutation.mutate(definition)}
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            title="更多操作"
                            onClick={() => setActionTarget(definition)}
                          >
                            <Ellipsis className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
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
          后端契约：/api/workflow · 生产使用 EAI Cookie 鉴权 · 本地演示可在左下角切换身份
        </p>
      </PageBody>

      <CreateDefinitionDialog open={createOpen} onOpenChange={setCreateOpen} />
      <ImportDefinitionDialog open={importOpen} onOpenChange={setImportOpen} />
      <DefinitionActionsDialog
        definition={actionTarget}
        open={Boolean(actionTarget)}
        onOpenChange={(open) => {
          if (!open) setActionTarget(null);
        }}
      />
    </div>
  );
}
