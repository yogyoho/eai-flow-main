"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Loader2, Trash2, Upload, X, ExternalLink, Clock } from "lucide-react";
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
    queryFn: () => scraperApi.listDrafts({ status: statusFilter || undefined, page, page_size: 20 }),
  });

  const { data: detailData } = useQuery({
    queryKey: ["scraper-draft-detail", selectedId],
    queryFn: () => (selectedId ? scraperApi.getDraft(selectedId) : null),
    enabled: !!selectedId,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => scraperApi.deleteDraft(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scraper-drafts"] });
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

  const knowledgeBases = kbData?.knowledge_bases || [];

  const drafts = data?.drafts || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 20);

  function formatDate(iso: string) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  return (
    <div className="flex h-full">
      {/* Draft list */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b shrink-0 bg-card/50">
          <div className="flex items-center gap-1.5">
            {STATUS_TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => { setStatusFilter(t.value); setPage(1); }}
                className={cn(
                  "px-3.5 py-1.5 text-sm rounded-lg transition-all duration-200 font-medium",
                  statusFilter === t.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                {t.label}
              </button>
            ))}
            <span className="ml-2 text-xs text-muted-foreground">共 {total} 条</span>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto p-3 space-y-2">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mb-3 text-primary/60" />
              <p className="text-sm">加载草稿...</p>
            </div>
          ) : drafts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <div className="bg-muted/50 rounded-2xl p-6 mb-4">
                <FileText className="h-12 w-12 text-muted-foreground/30" />
              </div>
              <p className="text-sm font-medium">暂无草稿</p>
              <p className="text-xs text-muted-foreground/70 mt-1">抓取结果可保存为草稿以便后续处理</p>
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
                    "group rounded-xl border px-4 py-3.5 cursor-pointer transition-all duration-200",
                    isSelected
                      ? "border-primary/30 shadow-md bg-primary/[0.02] ring-1 ring-primary/10"
                      : "border-border bg-card shadow-sm hover:shadow-md hover:border-primary/20"
                  )}
                >
                  <div className="flex items-center gap-3">
                    {/* Status indicator */}
                    <div className={cn(
                      "shrink-0 flex items-center justify-center w-8 h-8 rounded-lg",
                      isImported ? "bg-success/10 text-success" : "bg-primary/10 text-primary"
                    )}>
                      {isImported ? <CheckCircle2 className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{draft.title}</p>
                        {isImported ? (
                          <span className="px-1.5 py-0.5 bg-success/10 text-success rounded text-[10px] font-bold uppercase tracking-wider border border-success/20">已导入</span>
                        ) : (
                          <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px] font-bold uppercase tracking-wider border border-primary/20">草稿</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <p className="text-xs text-muted-foreground truncate">{draft.source_url}</p>
                      </div>
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-3 shrink-0">
                      {draft.schema_display_name && (
                        <span className="text-xs text-muted-foreground bg-muted/50 px-2 py-0.5 rounded">{draft.schema_display_name}</span>
                      )}
                      {draft.updated_at && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
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
          <div className="flex items-center justify-center gap-3 px-4 py-3 border-t shrink-0 bg-card/50">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
            >
              上一页
            </button>
            <span className="text-sm text-muted-foreground font-medium tabular-nums">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selectedId && detailData && (
        <div className="w-[420px] border-l flex flex-col overflow-hidden shrink-0 bg-card">
          {/* Header */}
          <div className="px-5 py-4 border-b shrink-0">
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold tracking-tight truncate">{detailData.title}</h3>
                <a
                  href={detailData.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-primary hover:underline mt-1"
                >
                  {detailData.source_url}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <button
                onClick={() => setSelectedId(null)}
                className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0 ml-2"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {/* Meta badges */}
            <div className="flex items-center gap-2 mt-2">
              {detailData.schema_display_name && (
                <span className="px-2 py-0.5 bg-muted/50 text-muted-foreground rounded-lg text-xs">{detailData.schema_display_name}</span>
              )}
              {detailData.tags && detailData.tags.length > 0 && (
                <div className="flex items-center gap-1">
                  {detailData.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="px-1.5 py-0.5 bg-primary/8 text-primary rounded text-[10px] font-medium">#{tag}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Content preview */}
          <div className="flex-1 overflow-auto p-5">
            {detailData.raw_content ? (
              <div className="border rounded-xl p-4 bg-muted/20 shadow-sm">
                <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
                  {detailData.raw_content.slice(0, 5000)}
                </pre>
                {detailData.raw_content.length > 5000 && (
                  <p className="text-xs text-muted-foreground mt-3 text-center">
                    还有 {(detailData.raw_content.length - 5000).toLocaleString()} 字符未显示...
                  </p>
                )}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-8">无内容</div>
            )}
          </div>

          {/* Actions */}
          <div className="px-5 py-4 border-t bg-muted/10 shrink-0">
            <div className="flex gap-2">
              {detailData.status !== "imported" && (
                <>
                  <button
                    onClick={() => { setImportDialogId(selectedId); setSelectedKbId(""); }}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 shadow-sm transition-all"
                  >
                    <Upload className="h-4 w-4" /> 导入知识库
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(selectedId)}
                    disabled={deleteMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2.5 border border-destructive/20 rounded-xl text-sm text-destructive hover:bg-destructive/5 hover:border-destructive/30 transition-colors disabled:opacity-50"
                  >
                    {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    删除
                  </button>
                </>
              )}
              {detailData.status === "imported" && (
                <div className="flex items-center gap-2 text-sm text-success">
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
          <div className="bg-card border rounded-2xl shadow-xl w-[400px] p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">导入到知识库</h3>
              <button onClick={() => setImportDialogId(null)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">选择知识库</label>
              {knowledgeBases.length === 0 ? (
                <p className="text-sm text-muted-foreground py-3 text-center">暂无可用知识库</p>
              ) : (
                <select
                  value={selectedKbId}
                  onChange={(e) => setSelectedKbId(e.target.value)}
                  className="w-full px-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px] outline-none transition-all"
                >
                  <option value="">-- 请选择 --</option>
                  {knowledgeBases.map((kb: { id: string; name: string }) => (
                    <option key={kb.id} value={kb.id}>{kb.name}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => importMutation.mutate({ draftId: importDialogId, kbId: selectedKbId })}
                disabled={!selectedKbId || importMutation.isPending}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 shadow-sm transition-all disabled:opacity-40 disabled:pointer-events-none"
              >
                {importMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                确认导入
              </button>
              <button
                onClick={() => setImportDialogId(null)}
                className="px-4 py-2.5 border rounded-xl text-sm hover:bg-muted transition-colors shadow-sm"
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
