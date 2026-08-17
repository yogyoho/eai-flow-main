"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  Upload,
  X,
  ExternalLink,
  Clock,
} from "lucide-react";
import React, { useState } from "react";

import { scraperApi, kbApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { useScraperContext } from "./ScraperContext";

const STATUS_TABS = [
  { value: "", label: "全部" },
  { value: "draft", label: "草稿" },
  { value: "imported", label: "已导入" },
];

export default function ScraperDraftBox() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importDialogId, setImportDialogId] = useState<string | null>(null);
  const [selectedKbId, setSelectedKbId] = useState<string>("");
  const { draftRefreshTrigger, triggerDraftRefresh } = useScraperContext();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["scraper-drafts", statusFilter, page, draftRefreshTrigger],
    queryFn: () =>
      scraperApi.listDrafts({
        status: statusFilter || undefined,
        page,
        page_size: 20,
      }),
  });

  const { data: detailData } = useQuery({
    queryKey: ["scraper-draft-detail", selectedId],
    queryFn: () => (selectedId ? scraperApi.getDraft(selectedId) : null),
    enabled: !!selectedId,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => scraperApi.deleteDraft(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scraper-drafts"] });
      if (selectedId) setSelectedId(null);
    },
  });

  const { data: kbData } = useQuery({
    queryKey: ["knowledge-bases-for-import"],
    queryFn: () => kbApi.list(),
    enabled: !!importDialogId,
  });

  const importMutation = useMutation({
    mutationFn: ({ draftId, kbId }: { draftId: string; kbId: string }) =>
      scraperApi.importDraft(draftId, { knowledge_base_id: kbId }),
    onSuccess: () => {
      triggerDraftRefresh();
      setImportDialogId(null);
      setSelectedKbId("");
    },
  });

  const knowledgeBases = kbData?.knowledge_bases ?? [];

  const drafts = data?.drafts ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  function formatDate(iso: string) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="flex h-full">
      {/* Draft list */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="bg-card/50 flex shrink-0 items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-1.5">
            {STATUS_TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => {
                  setStatusFilter(t.value);
                  setPage(1);
                }}
                className={cn(
                  "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
                  statusFilter === t.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {t.label}
              </button>
            ))}
            <span className="text-muted-foreground ml-2 text-xs">
              共 {total} 条
            </span>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 space-y-2 overflow-auto p-3">
          {isLoading ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-24">
              <Loader2 className="text-primary/60 mb-3 h-6 w-6 animate-spin" />
              <p className="text-sm">加载草稿...</p>
            </div>
          ) : drafts.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-24">
              <div className="bg-muted/50 mb-4 rounded-2xl p-6">
                <FileText className="text-muted-foreground/30 h-12 w-12" />
              </div>
              <p className="text-sm font-medium">暂无草稿</p>
              <p className="text-muted-foreground/70 mt-1 text-xs">
                抓取结果可保存为草稿以便后续处理
              </p>
            </div>
          ) : (
            drafts.map((draft) => {
              const isSelected = selectedId === String(draft.id);
              const isImported = draft.status === "imported";
              return (
                <div
                  key={String(draft.id)}
                  onClick={() => setSelectedId(String(draft.id))}
                  className={cn(
                    "group cursor-pointer rounded-xl border px-4 py-3.5 transition-all duration-200",
                    isSelected
                      ? "border-primary/30 bg-primary/[0.02] ring-primary/10 shadow-md ring-1"
                      : "border-border bg-card hover:border-primary/20 shadow-sm hover:shadow-md",
                  )}
                >
                  <div className="flex items-center gap-3">
                    {/* Status indicator */}
                    <div
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                        isImported
                          ? "bg-success/10 text-success"
                          : "bg-primary/10 text-primary",
                      )}
                    >
                      {isImported ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <FileText className="h-4 w-4" />
                      )}
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="group-hover:text-primary truncate text-sm font-medium transition-colors">
                          {draft.title}
                        </p>
                        {isImported ? (
                          <span className="bg-success/10 text-success border-success/20 rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase">
                            已导入
                          </span>
                        ) : (
                          <span className="bg-primary/10 text-primary border-primary/20 rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase">
                            草稿
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <p className="text-muted-foreground truncate text-xs">
                          {draft.source_url}
                        </p>
                      </div>
                    </div>

                    {/* Meta */}
                    <div className="flex shrink-0 items-center gap-3">
                      {draft.schema_display_name && (
                        <span className="text-muted-foreground bg-muted/50 rounded px-2 py-0.5 text-xs">
                          {draft.schema_display_name}
                        </span>
                      )}
                      {draft.updated_at && (
                        <span className="text-muted-foreground flex items-center gap-1 text-xs">
                          <Clock className="h-3 w-3" />
                          {formatDate(draft.updated_at)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="bg-card/50 flex shrink-0 items-center justify-center gap-3 border-t px-4 py-3">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="bg-card hover:bg-muted rounded-lg border px-4 py-1.5 text-sm shadow-sm transition-colors disabled:pointer-events-none disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-muted-foreground text-sm font-medium tabular-nums">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="bg-card hover:bg-muted rounded-lg border px-4 py-1.5 text-sm shadow-sm transition-colors disabled:pointer-events-none disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selectedId && detailData && (
        <div className="bg-card flex w-[420px] shrink-0 flex-col overflow-hidden border-l">
          {/* Header */}
          <div className="shrink-0 border-b px-5 py-4">
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-sm font-semibold tracking-tight">
                  {detailData.title}
                </h3>
                <a
                  href={detailData.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary mt-1 flex items-center gap-1 text-xs hover:underline"
                >
                  {detailData.source_url}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <button
                onClick={() => setSelectedId(null)}
                className="hover:bg-muted text-muted-foreground hover:text-foreground ml-2 shrink-0 rounded-lg p-1.5 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {/* Meta badges */}
            <div className="mt-2 flex items-center gap-2">
              {detailData.schema_display_name && (
                <span className="bg-muted/50 text-muted-foreground rounded-lg px-2 py-0.5 text-xs">
                  {detailData.schema_display_name}
                </span>
              )}
              {detailData.tags && detailData.tags.length > 0 && (
                <div className="flex items-center gap-1">
                  {detailData.tags.slice(0, 3).map((tag) => (
                    <span
                      key={tag}
                      className="bg-primary/8 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Content preview */}
          <div className="flex-1 overflow-auto p-5">
            {detailData.raw_content ? (
              <div className="bg-muted/20 rounded-xl border p-4 shadow-sm">
                <pre className="font-sans text-sm leading-relaxed whitespace-pre-wrap">
                  {detailData.raw_content.slice(0, 5000)}
                </pre>
                {detailData.raw_content.length > 5000 && (
                  <p className="text-muted-foreground mt-3 text-center text-xs">
                    还有{" "}
                    {(detailData.raw_content.length - 5000).toLocaleString()}{" "}
                    字符未显示...
                  </p>
                )}
              </div>
            ) : (
              <div className="text-muted-foreground py-8 text-center text-sm">
                无内容
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="bg-muted/10 shrink-0 border-t px-5 py-4">
            <div className="flex gap-2">
              {detailData.status !== "imported" && (
                <>
                  <button
                    onClick={() => {
                      setImportDialogId(selectedId);
                      setSelectedKbId("");
                    }}
                    className="bg-primary text-primary-foreground hover:bg-primary/90 flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium shadow-sm transition-all"
                  >
                    <Upload className="h-4 w-4" /> 导入知识库
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(selectedId)}
                    disabled={deleteMutation.isPending}
                    className="border-destructive/20 text-destructive hover:bg-destructive/5 hover:border-destructive/30 flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm transition-colors disabled:opacity-50"
                  >
                    {deleteMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    删除
                  </button>
                </>
              )}
              {detailData.status === "imported" && (
                <div className="text-success flex items-center gap-2 text-sm">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>已导入知识库</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Import dialog overlay */}
      {importDialogId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card w-[400px] space-y-4 rounded-2xl border p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">导入到知识库</h3>
              <button
                onClick={() => setImportDialogId(null)}
                className="hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg p-1.5 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1.5">
              <label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                选择知识库
              </label>
              {knowledgeBases.length === 0 ? (
                <p className="text-muted-foreground py-3 text-center text-sm">
                  暂无可用知识库
                </p>
              ) : (
                <select
                  value={selectedKbId}
                  onChange={(e) => setSelectedKbId(e.target.value)}
                  className="bg-background focus-visible:border-primary focus-visible:ring-primary/20 w-full rounded-xl border px-3 py-2.5 text-sm shadow-sm transition-all outline-none focus-visible:ring-[3px]"
                >
                  <option value="">-- 请选择 --</option>
                  {knowledgeBases.map((kb: { id: string; name: string }) => (
                    <option key={kb.id} value={kb.id}>
                      {kb.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={() =>
                  importMutation.mutate({
                    draftId: importDialogId,
                    kbId: selectedKbId,
                  })
                }
                disabled={!selectedKbId || importMutation.isPending}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium shadow-sm transition-all disabled:pointer-events-none disabled:opacity-40"
              >
                {importMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                确认导入
              </button>
              <button
                onClick={() => setImportDialogId(null)}
                className="hover:bg-muted rounded-xl border px-4 py-2.5 text-sm shadow-sm transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
