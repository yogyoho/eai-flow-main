"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Braces,
  Eye,
  FileText,
  Layers,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { FormDefinition, FormSchema } from "@/lib/types";
import { fieldCount, initialFormValues, parseFormSchema } from "@/lib/forms";
import { PageBody, PageHeader } from "@/components/page-header";
import { PublishBadge } from "@/components/status-badge";
import { FormBuilderDialog } from "@/components/workflow/form-builder-dialog";
import { FormRenderer } from "@/components/workflow/form-renderer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn, formatNumber, relativeTime } from "@/lib/utils";

const FILTERS = [
  { value: "all", label: "全部" },
  { value: "1", label: "已发布" },
  { value: "0", label: "草稿" },
  { value: "9", label: "已失效" },
];

const PAGE_SIZE = 12;

export default function FormsPage() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editing, setEditing] = useState<FormDefinition | null>(null);
  const [previewTarget, setPreviewTarget] = useState<FormDefinition | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FormDefinition | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(keyword.trim());
      setPage(1);
    }, 280);
    return () => clearTimeout(timer);
  }, [keyword]);

  const listQuery = useQuery({
    queryKey: ["forms", { debounced, filter, page }],
    queryFn: () =>
      api.forms.list({
        page,
        size: PAGE_SIZE,
        formName: debounced || undefined,
        isPublish: filter === "all" ? undefined : Number(filter),
      }),
  });

  const allQuery = useQuery({
    queryKey: ["forms", "all-stats"],
    queryFn: () => api.forms.list({ page: 1, size: 200 }),
    staleTime: 30_000,
  });

  const publishMutation = useMutation({
    mutationFn: (form: FormDefinition) => api.forms.publish(form.id),
    onSuccess: (form) => {
      queryClient.invalidateQueries({ queryKey: ["forms"] });
      queryClient.invalidateQueries({ queryKey: ["designer"] });
      toast.success(`「${form.form_name}」已发布，可用于流程节点`);
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "发布失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: (form: FormDefinition) => api.forms.remove(form.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forms"] });
      toast.success("表单已删除");
      setDeleteTarget(null);
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "删除失败"),
  });

  const allForms = allQuery.data?.items || [];
  const stats = useMemo(
    () => [
      {
        key: "total",
        label: "表单总数",
        value: allForms.length,
        icon: FileText,
        accent: "text-sky-600 bg-sky-50 border-sky-100",
      },
      {
        key: "published",
        label: "已发布",
        value: allForms.filter((form) => form.is_publish === 1).length,
        icon: Layers,
        accent: "text-emerald-600 bg-emerald-50 border-emerald-100",
      },
      {
        key: "draft",
        label: "草稿",
        value: allForms.filter((form) => form.is_publish === 0).length,
        icon: Pencil,
        accent: "text-amber-600 bg-amber-50 border-amber-100",
      },
      {
        key: "fields",
        label: "字段总数",
        value: allForms.reduce((sum, form) => sum + fieldCount(form), 0),
        icon: Braces,
        accent: "text-violet-600 bg-violet-50 border-violet-100",
      },
    ],
    [allForms],
  );

  const total = listQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = listQuery.data?.items ?? [];
  const hasFilter = filter !== "all" || Boolean(debounced);

  const pageLabel = useMemo(() => {
    if (listQuery.isLoading) return "加载中…";
    if (!total) return "共 0 条";
    return `第 ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} 条，共 ${total} 条`;
  }, [listQuery.isLoading, page, total]);

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["forms"] });
  }

  function openCreate() {
    setEditing(null);
    setBuilderOpen(true);
  }

  function openEdit(form: FormDefinition) {
    setEditing(form);
    setBuilderOpen(true);
  }

  return (
    <div className="app-grid-bg min-h-screen">
      <PageBody>
        <PageHeader
          eyebrow="Form Center"
          title="表单中心"
          description="用字段构建器定义业务表单，发布后即可在流程节点中通过 form_path 引用。表单值会作为流程变量参与审批与网关判断。"
          actions={
            <>
              <Button variant="secondary" onClick={refresh}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button onClick={openCreate}>
                <Plus className="h-4 w-4" />
                新建表单
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
                    {allQuery.isLoading ? (
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
          <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center">
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
            <div className="relative sm:ml-auto sm:w-[280px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索表单名称…"
                className="h-9 pl-8"
              />
            </div>
          </div>

          {listQuery.isLoading ? (
            <div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-52 w-full rounded-xl" />
              ))}
            </div>
          ) : listQuery.isError ? (
            <div className="p-4">
              <EmptyState
                title="表单加载失败"
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
                title={hasFilter ? "没有匹配的表单" : "还没有业务表单"}
                description={
                  hasFilter
                    ? "试试清空搜索条件或切换发布状态筛选。"
                    : "创建第一个表单，为流程节点提供结构化的业务字段与变量。"
                }
                icon={<FileText className="h-5 w-5" />}
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
                    <Button size="sm" onClick={openCreate}>
                      <Plus className="h-4 w-4" />
                      新建表单
                    </Button>
                  )
                }
              />
            </div>
          ) : (
            <div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
              {rows.map((form) => (
                <FormCard
                  key={form.id}
                  form={form}
                  onPreview={() => setPreviewTarget(form)}
                  onEdit={() => openEdit(form)}
                  onPublish={() => publishMutation.mutate(form)}
                  onDelete={() => setDeleteTarget(form)}
                  publishing={publishMutation.isPending}
                />
              ))}
            </div>
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

        <p className="mt-4 text-[11px] text-muted-foreground/80">
          表单 schema 结构：{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
            {'{"layout":{"columns":2},"fields":[{"key","label","type","span","required","options"}]}'}
          </code>{" "}
          · 已发布表单会被流程节点以 form_path 引用。
        </p>
      </PageBody>

      <FormBuilderDialog
        open={builderOpen}
        onOpenChange={(open) => {
          setBuilderOpen(open);
          if (!open) setEditing(null);
        }}
        form={editing}
      />

      <FormPreviewDialog
        form={previewTarget}
        onOpenChange={(open) => {
          if (!open) setPreviewTarget(null);
        }}
      />

      <DeleteFormDialog
        form={deleteTarget}
        busy={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
      />
    </div>
  );
}

function FormCard({
  form,
  onPreview,
  onEdit,
  onPublish,
  onDelete,
  publishing,
}: {
  form: FormDefinition;
  onPreview: () => void;
  onEdit: () => void;
  onPublish: () => void;
  onDelete: () => void;
  publishing: boolean;
}) {
  const schema = parseFormSchema(form.form_content);
  const labels = schema.fields.map((field) => field.label || field.key).filter(Boolean);
  const published = form.is_publish === 1;

  return (
    <div className="group flex flex-col overflow-hidden rounded-xl border border-border bg-card transition hover:border-foreground/15 hover:shadow-[0_10px_30px_-24px_rgba(16,24,40,0.4)]">
      <div className="flex items-start gap-3 p-4">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border",
            published
              ? "border-emerald-100 bg-emerald-50 text-emerald-600"
              : form.is_publish === 9
                ? "border-slate-200 bg-slate-100 text-slate-500"
                : "border-amber-100 bg-amber-50 text-amber-600",
          )}
        >
          <FileText className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <p className="min-w-0 flex-1 truncate text-[13.5px] font-semibold">{form.form_name}</p>
            <PublishBadge value={form.is_publish} />
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
            <span className="font-mono">{form.form_code}</span>
            <span className="text-border">/</span>
            <span>v{form.version}</span>
            {form.form_path && (
              <>
                <span className="text-border">/</span>
                <span className="truncate font-mono">{form.form_path}</span>
              </>
            )}
          </p>
        </div>
      </div>

      <div className="flex-1 px-4 pb-3">
        {labels.length ? (
          <div className="flex flex-wrap gap-1.5">
            {labels.slice(0, 5).map((label, index) => (
              <Badge key={`${label}-${index}`} variant="outline" className="font-normal">
                {label}
              </Badge>
            ))}
            {labels.length > 5 && (
              <Badge variant="slate" className="font-normal">
                +{labels.length - 5}
              </Badge>
            )}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground">表单还没有字段</p>
        )}
        <p className="mt-2 text-[10.5px] text-muted-foreground">
          {labels.length} 个字段 · 更新于 {relativeTime(form.update_time)}
        </p>
      </div>

      <div className="flex items-center gap-1 border-t border-border bg-muted/15 px-3 py-2">
        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={onPreview}>
          <Eye className="h-3.5 w-3.5" />
          预览
        </Button>
        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5" />
          编辑
        </Button>
        {!published && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-primary hover:text-primary"
            onClick={onPublish}
            disabled={publishing}
          >
            <Send className="h-3.5 w-3.5" />
            发布
          </Button>
        )}
        <Button
          size="icon-sm"
          variant="ghost"
          className="ml-auto h-7 w-7 text-muted-foreground hover:text-destructive"
          title="删除表单"
          onClick={onDelete}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function FormPreviewDialog({
  form,
  onOpenChange,
}: {
  form: FormDefinition | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const schema = useMemo<FormSchema | null>(() => {
    if (!form?.form_content) return null;
    const parsed = parseFormSchema(form.form_content);
    return parsed.fields.length ? parsed : null;
  }, [form]);

  useEffect(() => {
    setValues(initialFormValues(schema));
  }, [schema]);

  return (
    <Dialog open={Boolean(form)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-2rem)] max-w-[640px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
              <Eye className="h-4 w-4" />
            </span>
            {form?.form_name || "表单预览"}
          </DialogTitle>
          <DialogDescription>
            {form ? (
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-mono">{form.form_code}</span>
                <span className="text-border">/</span>
                <span>v{form.version}</span>
                <PublishBadge value={form.is_publish} />
              </span>
            ) : (
              ""
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-border bg-muted/15 p-4">
          {schema ? (
            <FormRenderer schema={schema} values={values} onChange={setValues} />
          ) : (
            <p className="py-8 text-center text-[12px] text-muted-foreground">
              该表单没有可预览的字段
            </p>
          )}
        </div>

        {form && (
          <details className="rounded-xl border border-border px-3.5 py-3">
            <summary className="cursor-pointer list-none text-[11px] font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
              查看 form_content JSON
            </summary>
            <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-muted/32 p-3 text-[10.5px] leading-relaxed text-muted-foreground">
              {JSON.stringify(parseFormSchema(form.form_content), null, 2)}
            </pre>
          </details>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteFormDialog({
  form,
  busy,
  onOpenChange,
  onConfirm,
}: {
  form: FormDefinition | null;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={Boolean(form)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
              <TriangleAlert className="h-4 w-4" />
            </span>
            删除表单
          </DialogTitle>
          <DialogDescription>
            删除后不可恢复。若表单已被已发布的流程引用，后端会拒绝删除，此时请保留表单或先调整流程。
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg border border-rose-200/70 bg-rose-50/60 px-3.5 py-3 text-[12px] leading-relaxed text-rose-700">
          {form?.form_name} · <span className="font-mono">{form?.form_code}</span> v{form?.version}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            取消
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            确认删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
