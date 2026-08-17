"use client";

import {
  Search,
  Plus,
  FileText,
  Loader2,
  Globe,
  GlobeLock,
  Trash2,
  Pencil,
  Send,
  CheckCircle2,
  Clock,
  XCircle,
  Undo2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
// EAI-CUSTOM (F4): 以 /me 的 is_admin 判超管（替代 role_name 显示名）
import { usePermission } from "@/core/permissions";
import { REPORT_TYPE_LABELS } from "@/extensions/project/types";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowDefinitionListItem } from "@/extensions/workflow/types";
import { cn } from "@/lib/utils";

const REPORT_TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部类型" },
  ...Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({
    value,
    label,
  })),
];

function formatDate(s: string | null): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return s;
  }
}

const STATUS_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; color: string }
> = {
  draft: {
    label: "草稿",
    icon: GlobeLock,
    color: "bg-gray-50 text-gray-400 border-gray-200",
  },
  pending_approval: {
    label: "待审批",
    icon: Clock,
    color: "bg-amber-50 text-amber-600 border-amber-200",
  },
  published: {
    label: "已发布",
    icon: Globe,
    color: "bg-green-50 text-green-600 border-green-200",
  },
  rejected: {
    label: "已拒绝",
    icon: XCircle,
    color: "bg-red-50 text-red-600 border-red-200",
  },
};

export default function AdminTemplatesPage() {
  const { is_admin: isSuperAdmin } = usePermission();
  const [templates, setTemplates] = useState<WorkflowDefinitionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [reportTypeFilter, setReportTypeFilter] = useState("");
  const [actioningId, setActioningId] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await workflowApi.list({
        isTemplate: true,
        reportType: reportTypeFilter || undefined,
      });
      setTemplates(res.items);
    } catch (err) {
      console.error(err);
      toast.error("加载模板列表失败");
    } finally {
      setIsLoading(false);
    }
  }, [reportTypeFilter]);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const filteredTemplates = searchQuery
    ? templates.filter((t) =>
        t.name.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : templates;

  const handlePublish = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.publishTemplate(t.id);
      toast.success("模板已发布");
      void loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发布失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleUnpublish = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.update(t.id, { templateStatus: "draft" });
      toast.success("已撤回发布");
      void loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleSubmitApproval = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.submitApproval(t.id);
      toast.success("已提交审批");
      void loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleWithdrawApproval = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.withdrawApproval(t.id);
      toast.success("已撤回审批");
      void loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "撤回失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleDelete = async (t: WorkflowDefinitionListItem) => {
    if (!confirm(`确定要删除模板"${t.name}"吗？`)) return;
    setActioningId(t.id);
    try {
      await workflowApi.delete(t.id);
      toast.success("模板已删除");
      void loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setActioningId(null);
    }
  };

  if (isLoading) return <PageLoadingOverlay text="加载中" />;

  return (
    <main className="bg-background mx-auto flex h-full w-full max-w-[1200px] flex-col overflow-hidden">
      <div className="border-border bg-card shrink-0 border-b px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground text-2xl font-bold tracking-tight">
              工作流编排
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              管理、编辑和发布可复用的工作流模板
            </p>
          </div>
          <Link
            href="/workflow-admin/new"
            className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
          >
            <Plus className="h-4 w-4" />
            新建模板
          </Link>
        </div>
      </div>

      <div className="border-border bg-muted/30 flex shrink-0 items-center gap-4 border-b px-8 py-4">
        <div className="relative max-w-sm flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <input
            type="text"
            placeholder="搜索模板..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-secondary focus:bg-background focus:border-primary focus:ring-primary/20 w-full rounded-lg border-transparent py-2 pr-4 pl-9 text-sm transition-all outline-none focus:ring-2"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {REPORT_TYPE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setReportTypeFilter(f.value)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                reportTypeFilter === f.value
                  ? "bg-primary text-white"
                  : "bg-secondary text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {filteredTemplates.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <div className="bg-muted text-muted-foreground mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                <FileText className="h-8 w-8" />
              </div>
              <h3 className="text-foreground mb-2 text-base font-medium">
                {searchQuery || reportTypeFilter
                  ? "没有匹配的模板"
                  : "暂无模板"}
              </h3>
              <p className="text-muted-foreground mb-6 text-sm">
                {searchQuery || reportTypeFilter
                  ? "请尝试调整筛选条件"
                  : "创建一个工作流模板，用于快速初始化新项目"}
              </p>
              {!searchQuery && !reportTypeFilter && (
                <Link
                  href="/workflow-admin/new"
                  className="bg-primary hover:bg-primary/90 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
                >
                  <Plus className="h-4 w-4" />
                  新建模板
                </Link>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredTemplates.map((t) => {
              const status = t.templateStatus ?? "draft";
              const sc = STATUS_CONFIG[status] ?? STATUS_CONFIG.draft!;
              const StatusIcon = sc.icon;
              return (
                <div
                  key={t.id}
                  className="border-border bg-card overflow-hidden rounded-xl border transition-all hover:shadow-sm"
                >
                  <div className="p-5">
                    <div className="mb-3 flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                          <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-foreground truncate text-sm font-semibold">
                            {t.name}
                          </h3>
                          <div className="mt-1 flex items-center gap-2">
                            {t.reportType && (
                              <span className="bg-secondary text-muted-foreground rounded px-1.5 py-0.5 text-xs">
                                {REPORT_TYPE_LABELS[t.reportType] ??
                                  t.reportType}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <span
                        className={cn(
                          "flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                          sc.color,
                        )}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {sc.label}
                      </span>
                    </div>
                    {t.description && (
                      <p className="text-muted-foreground mt-2 line-clamp-2 text-xs">
                        {t.description}
                      </p>
                    )}
                  </div>
                  <div className="border-border bg-muted/30 flex items-center justify-between border-t px-5 py-3">
                    <span className="text-muted-foreground text-xs">
                      {formatDate(t.createdAt)}
                    </span>
                    <div className="flex items-center gap-1">
                      <Link
                        href={`/workflow-admin/${t.id}`}
                        title="编辑模板"
                        className="text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md p-1.5 transition-colors"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Link>
                      {status === "draft" && isSuperAdmin && (
                        <button
                          type="button"
                          title="直接发布"
                          disabled={actioningId === t.id}
                          onClick={() => handlePublish(t)}
                          className="text-muted-foreground rounded-md p-1.5 transition-colors hover:bg-green-50 hover:text-green-600 disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      {status === "draft" && !isSuperAdmin && (
                        <button
                          type="button"
                          title="提交审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleSubmitApproval(t)}
                          className="text-muted-foreground rounded-md p-1.5 transition-colors hover:bg-amber-50 hover:text-amber-600 disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Send className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      {status === "pending_approval" && (
                        <button
                          type="button"
                          title="撤回审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleWithdrawApproval(t)}
                          className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1.5 transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Undo2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      {status === "published" && (
                        <button
                          type="button"
                          title="撤回发布"
                          disabled={actioningId === t.id}
                          onClick={() => handleUnpublish(t)}
                          className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1.5 transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Undo2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      {status === "rejected" && isSuperAdmin && (
                        <button
                          type="button"
                          title="直接发布"
                          disabled={actioningId === t.id}
                          onClick={() => handlePublish(t)}
                          className="text-muted-foreground rounded-md p-1.5 transition-colors hover:bg-green-50 hover:text-green-600 disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      {status === "rejected" && !isSuperAdmin && (
                        <button
                          type="button"
                          title="重新提交审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleSubmitApproval(t)}
                          className="text-muted-foreground rounded-md p-1.5 transition-colors hover:bg-amber-50 hover:text-amber-600 disabled:opacity-50"
                        >
                          {actioningId === t.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Send className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                      <button
                        type="button"
                        title="删除"
                        disabled={actioningId === t.id}
                        onClick={() => handleDelete(t)}
                        className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md p-1.5 transition-colors disabled:opacity-50"
                      >
                        {actioningId === t.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
