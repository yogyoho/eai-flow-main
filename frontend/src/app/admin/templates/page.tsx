"use client";

import {
  Search,
  Plus,
  FileText,
  Eye,
  Loader2,
  Globe,
  GlobeLock,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowDefinitionListItem } from "@/extensions/workflow/types";
import { REPORT_TYPE_LABELS } from "@/extensions/project/types";
import type { ReportType } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import Link from "next/link";

const REPORT_TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部类型" },
  ...Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
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

export default function AdminTemplatesPage() {
  const [templates, setTemplates] = useState<WorkflowDefinitionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [reportTypeFilter, setReportTypeFilter] = useState("");
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadTemplates = async () => {
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
  };

  useEffect(() => {
    loadTemplates();
  }, [reportTypeFilter]);

  const filteredTemplates = searchQuery
    ? templates.filter((t) =>
        t.name.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : templates;

  const handleTogglePublish = async (t: WorkflowDefinitionListItem) => {
    setTogglingId(t.id);
    try {
      if (t.isTemplate) {
        await workflowApi.unpublishTemplate(t.id);
        toast.success("已取消发布");
      } else {
        await workflowApi.publishTemplate(t.id);
        toast.success("已发布模板");
      }
      loadTemplates();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (t: WorkflowDefinitionListItem) => {
    if (!confirm(`确定要删除模板"${t.name}"吗？`)) return;
    setDeletingId(t.id);
    try {
      await workflowApi.delete(t.id);
      toast.success("模板已删除");
      loadTemplates();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  };

  if (isLoading) {
    return <PageLoadingOverlay text="加载中" />;
  }

  return (
    <main className="h-full flex flex-col overflow-hidden max-w-[1200px] w-full mx-auto bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border bg-card px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <FileText className="w-4 h-4" />
              <span>模板管理</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">
              工作流模板
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              管理可复用的工作流模板，用于快速创建项目
            </p>
          </div>
          <Link
            href="/projects/new"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            新建模板
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="shrink-0 px-8 py-4 border-b border-border bg-muted/30 flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索模板..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-secondary border-transparent focus:bg-background focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-lg text-sm transition-all outline-none"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {REPORT_TYPE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setReportTypeFilter(f.value)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
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

      {/* Template Grid */}
      <div className="flex-1 overflow-y-auto p-8">
        {filteredTemplates.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                <FileText className="w-8 h-8" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-2">
                {searchQuery || reportTypeFilter ? "没有匹配的模板" : "暂无模板"}
              </h3>
              <p className="text-muted-foreground text-sm mb-6">
                {searchQuery || reportTypeFilter
                  ? "请尝试调整筛选条件"
                  : "创建一个工作流模板，用于快速初始化新项目"}
              </p>
              {!searchQuery && !reportTypeFilter && (
                <Link
                  href="/projects/new"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  新建模板
                </Link>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTemplates.map((t) => (
              <div
                key={t.id}
                className="rounded-xl border border-border bg-card hover:shadow-sm transition-all overflow-hidden"
              >
                {/* Card header */}
                <div className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-foreground truncate">
                          {t.name}
                        </h3>
                        <div className="flex items-center gap-2 mt-1">
                          {t.reportType && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
                              {REPORT_TYPE_LABELS[t.reportType as ReportType] ?? t.reportType}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <span
                      className={cn(
                        "flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0",
                        t.isTemplate
                          ? "bg-green-50 text-green-600 border border-green-200"
                          : "bg-gray-50 text-gray-400 border border-gray-200",
                      )}
                    >
                      {t.isTemplate ? (
                        <>
                          <Globe className="w-3 h-3" />
                          已发布
                        </>
                      ) : (
                        <>
                          <GlobeLock className="w-3 h-3" />
                          草稿
                        </>
                      )}
                    </span>
                  </div>
                </div>

                {/* Card footer */}
                <div className="px-5 py-3 border-t border-border bg-muted/30 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    创建于 {formatDate(t.createdAt)}
                  </span>
                  <div className="flex items-center gap-1">
                    <Link
                      href={`/projects/new?workflowId=${t.id}`}
                      title="基于此模板创建项目"
                      className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </Link>
                    <button
                      type="button"
                      title={t.isTemplate ? "取消发布" : "发布"}
                      disabled={togglingId === t.id}
                      onClick={() => handleTogglePublish(t)}
                      className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors disabled:opacity-50"
                    >
                      {togglingId === t.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : t.isTemplate ? (
                        <GlobeLock className="w-3.5 h-3.5" />
                      ) : (
                        <Globe className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      title="删除"
                      disabled={deletingId === t.id}
                      onClick={() => handleDelete(t)}
                      className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                    >
                      {deletingId === t.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
