"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Trash2,
  Edit2,
  Upload,
  Search,
  RefreshCw,
  Tag,
  Calendar,
  ExternalLink,
  X,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { scraperApi } from "@/extensions/api";
import { kbApi } from "@/extensions/api";
import type { ScrapDraft, ScrapDraftDetail } from "@/extensions/api";
import { cn } from "@/lib/utils";

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
}

interface DraftBoxProps {
  onClose?: () => void;
  onEdit?: (draft: ScrapDraft) => void;
}

export { type DraftBoxProps };
export default function DraftBox({ onClose, onEdit }: DraftBoxProps) {
  const [drafts, setDrafts] = useState<ScrapDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<ScrapDraftDetail | null>(
    null,
  );
  const [showPreview, setShowPreview] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);

  // 加载草稿列表（scraperApi 已自动带 Token）
  const loadDrafts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await scraperApi.listDrafts({
        status: statusFilter ?? undefined,
        page_size: 50,
      });
      setDrafts(data.drafts || []);
    } catch (e) {
      console.error("加载草稿失败:", e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadDrafts();
  }, [loadDrafts]);

  // 删除草稿
  const handleDelete = async (draftId: string) => {
    if (!confirm("确定要删除这个草稿吗？")) return;
    try {
      await scraperApi.deleteDraft(draftId);
      setDrafts((prev) => prev.filter((d) => d.id !== draftId));
    } catch (e) {
      console.error("删除失败:", e);
    }
  };

  // 预览草稿（列表项点击：仅显示摘要，不含 raw_content）
  const handlePreview = async (draft: ScrapDraft) => {
    try {
      const data = await scraperApi.getDraft(draft.id);
      setSelectedDraft(data);
      setShowPreview(true);
    } catch (e) {
      console.error("预览失败:", e);
    }
  };

  // 打开导入模态框（知识库列表走 kbApi；draft 仅作上下文信息，不含 raw_content）
  const handleOpenImport = async (draft: ScrapDraft) => {
    try {
      const data = await kbApi.list();
      setKnowledgeBases(data.knowledge_bases || []);
      setSelectedDraft({ ...draft, raw_content: "" } as ScrapDraftDetail);
      setShowImportModal(true);
    } catch (e) {
      console.error("加载知识库失败:", e);
    }
  };

  // 导入到知识库
  const handleImport = async (kbId: string) => {
    if (!selectedDraft) return;
    try {
      await scraperApi.importDraft(selectedDraft.id, {
        knowledge_base_id: kbId,
        auto_parse: true,
      });
      toast.success("已成功导入到知识库！");
      setShowImportModal(false);
      setSelectedDraft(null);
      void loadDrafts();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "导入失败");
    }
  };

  // 过滤草稿
  const filteredDrafts = drafts.filter((draft) => {
    const matchSearch =
      !searchTerm ||
      draft.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (draft.source_title?.toLowerCase().includes(searchTerm.toLowerCase()) ??
        false) ||
      draft.tags.some((tag) =>
        tag.toLowerCase().includes(searchTerm.toLowerCase()),
      );

    const matchStatus = !statusFilter || draft.status === statusFilter;

    return matchSearch && matchStatus;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "draft":
        return "bg-amber-500/10 text-amber-500";
      case "imported":
        return "bg-emerald-500/10 text-emerald-500";
      case "deleted":
        return "bg-muted text-muted-foreground";
      default:
        return "bg-muted text-muted-foreground";
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case "draft":
        return "草稿";
      case "imported":
        return "已导入";
      case "deleted":
        return "已删除";
      default:
        return status;
    }
  };

  return (
    <>
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="bg-background border-b p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-foreground flex items-center gap-2 text-lg font-semibold">
              <FileText className="h-5 w-5" />
              草稿箱 ({filteredDrafts.length})
            </h2>
            <div className="flex gap-2">
              <button
                onClick={loadDrafts}
                className="hover:bg-accent rounded-lg p-2"
                title="刷新"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
              {onClose && (
                <button
                  onClick={onClose}
                  className="hover:bg-accent rounded-lg p-2"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>

          {/* 搜索和筛选 */}
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
              <input
                type="text"
                placeholder="搜索草稿..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="border-border bg-background w-full rounded-lg border py-2 pr-4 pl-10"
              />
            </div>
            <select
              value={statusFilter ?? ""}
              onChange={(e) => setStatusFilter(e.target.value || null)}
              className="border-border bg-background rounded-lg border px-3 py-2"
            >
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="imported">已导入</option>
              <option value="deleted">已删除</option>
            </select>
          </div>
        </div>

        {/* 草稿列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <RefreshCw className="text-muted-foreground h-6 w-6 animate-spin" />
            </div>
          ) : filteredDrafts.length === 0 ? (
            <div className="text-muted-foreground flex h-full flex-col items-center justify-center">
              <FileText className="text-muted-foreground/30 mb-3 h-12 w-12" />
              <p>暂无草稿</p>
              <p className="text-sm">爬取网页后将自动保存到草稿箱</p>
            </div>
          ) : (
            <div className="divide-y">
              {filteredDrafts.map((draft) => (
                <motion.div
                  key={draft.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="hover:bg-accent group cursor-pointer p-4"
                  onClick={() => handlePreview(draft)}
                >
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <h3 className="truncate font-medium">{draft.title}</h3>
                        <span
                          className={cn(
                            "shrink-0 rounded-full px-2 py-0.5 text-xs",
                            getStatusBadge(draft.status),
                          )}
                        >
                          {getStatusText(draft.status)}
                        </span>
                      </div>

                      <div className="text-muted-foreground mb-2 flex items-center gap-3 text-sm">
                        <span className="flex items-center gap-1">
                          <Tag className="h-3 w-3" />
                          {draft.schema_display_name ?? draft.schema_name}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {new Date(draft.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      {draft.source_url && (
                        <a
                          href={draft.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-primary flex items-center gap-1 text-sm hover:underline"
                        >
                          <ExternalLink className="h-3 w-3" />
                          {draft.source_title ?? draft.source_url}
                        </a>
                      )}

                      {draft.tags.length > 0 && (
                        <div className="mt-2 flex gap-1">
                          {draft.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs"
                            >
                              {tag}
                            </span>
                          ))}
                          {draft.tags.length > 3 && (
                            <span className="text-muted-foreground/60 text-xs">
                              +{draft.tags.length - 3}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      {draft.status === "draft" && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onEdit?.(draft);
                            }}
                            className="hover:bg-accent rounded-lg p-2"
                            title="编辑"
                          >
                            <Edit2 className="h-4 w-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleOpenImport(draft);
                            }}
                            className="hover:bg-accent text-primary rounded-lg p-2"
                            title="导入知识库"
                          >
                            <Upload className="h-4 w-4" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDelete(draft.id);
                        }}
                        className="rounded-lg p-2 text-red-500 hover:bg-red-500/10"
                        title="删除"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 预览模态框 */}
      <AnimatePresence>
        {showPreview && selectedDraft && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-8"
            onClick={() => setShowPreview(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-background flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b p-6">
                <div>
                  <h2 className="text-foreground text-xl font-semibold">
                    {selectedDraft.title}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {selectedDraft.schema_display_name} •{" "}
                    {new Date(selectedDraft.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  {selectedDraft.status === "draft" && (
                    <button
                      onClick={() => {
                        setShowPreview(false);
                        void handleOpenImport(selectedDraft);
                      }}
                      className="bg-primary text-primary-foreground flex items-center gap-2 rounded-lg px-4 py-2"
                    >
                      <Upload className="h-4 w-4" /> 存入知识库
                    </button>
                  )}
                  <button
                    onClick={() => setShowPreview(false)}
                    className="hover:bg-accent text-muted-foreground hover:text-foreground rounded-lg p-2 transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown>
                    {selectedDraft.raw_content || selectedDraft.title}
                  </ReactMarkdown>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 导入模态框 */}
      <AnimatePresence>
        {showImportModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={() => setShowImportModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-background w-full max-w-md rounded-2xl p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="mb-4 text-xl font-semibold">选择目标知识库</h2>

              {knowledgeBases.length === 0 ? (
                <div className="text-muted-foreground py-8 text-center">
                  暂无可用知识库，请先创建知识库
                </div>
              ) : (
                <div className="max-h-96 space-y-2 overflow-y-auto">
                  {knowledgeBases.map((kb) => (
                    <button
                      key={kb.id}
                      onClick={() => handleImport(kb.id)}
                      className="border-border hover:bg-accent w-full rounded-lg border p-4 text-left"
                    >
                      <div className="text-foreground font-medium">
                        {kb.name}
                      </div>
                      {kb.description && (
                        <div className="text-muted-foreground text-sm">
                          {kb.description}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}

              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => setShowImportModal(false)}
                  className="border-border hover:bg-accent text-foreground rounded-lg border px-4 py-2"
                >
                  取消
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
