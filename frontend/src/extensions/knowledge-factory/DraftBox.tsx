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
  const [selectedDraft, setSelectedDraft] = useState<ScrapDraftDetail | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);

  // 加载草稿列表（scraperApi 已自动带 Token）
  const loadDrafts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await scraperApi.listDrafts({
        status: statusFilter || undefined,
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
    loadDrafts();
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
      alert("已成功导入到知识库！");
      setShowImportModal(false);
      setSelectedDraft(null);
      loadDrafts();
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入失败");
    }
  };

  // 过滤草稿
  const filteredDrafts = drafts.filter((draft) => {
    const matchSearch =
      !searchTerm ||
      draft.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      draft.source_title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      draft.tags.some((tag) => tag.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchStatus = !statusFilter || draft.status === statusFilter;

    return matchSearch && matchStatus;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "draft":
        return "bg-amber-100 text-amber-800";
      case "imported":
        return "bg-green-100 text-green-800";
      case "deleted":
        return "bg-gray-100 text-gray-500";
      default:
        return "bg-gray-100 text-gray-600";
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
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="p-4 border-b bg-white">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <FileText className="w-5 h-5" />
              草稿箱 ({filteredDrafts.length})
            </h2>
            <div className="flex gap-2">
              <button
                onClick={loadDrafts}
                className="p-2 hover:bg-gray-100 rounded-lg"
                title="刷新"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
              {onClose && (
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-gray-100 rounded-lg"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* 搜索和筛选 */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="搜索草稿..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border rounded-lg"
              />
            </div>
            <select
              value={statusFilter || ""}
              onChange={(e) => setStatusFilter(e.target.value || null)}
              className="px-3 py-2 border rounded-lg"
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
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : filteredDrafts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <FileText className="w-12 h-12 mb-3 text-gray-300" />
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
                  className="p-4 hover:bg-gray-50 cursor-pointer group"
                  onClick={() => handlePreview(draft)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium truncate">{draft.title}</h3>
                        <span
                          className={cn(
                            "px-2 py-0.5 text-xs rounded-full shrink-0",
                            getStatusBadge(draft.status)
                          )}
                        >
                          {getStatusText(draft.status)}
                        </span>
                      </div>

                      <div className="flex items-center gap-3 text-sm text-gray-500 mb-2">
                        <span className="flex items-center gap-1">
                          <Tag className="w-3 h-3" />
                          {draft.schema_display_name || draft.schema_name}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(draft.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      {draft.source_url && (
                        <a
                          href={draft.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-sm text-blue-600 hover:underline flex items-center gap-1"
                        >
                          <ExternalLink className="w-3 h-3" />
                          {draft.source_title || draft.source_url}
                        </a>
                      )}

                      {draft.tags.length > 0 && (
                        <div className="flex gap-1 mt-2">
                          {draft.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                            >
                              {tag}
                            </span>
                          ))}
                          {draft.tags.length > 3 && (
                            <span className="text-gray-400 text-xs">
                              +{draft.tags.length - 3}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {draft.status === "draft" && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onEdit?.(draft);
                            }}
                            className="p-2 hover:bg-gray-200 rounded-lg"
                            title="编辑"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleOpenImport(draft);
                            }}
                            className="p-2 hover:bg-gray-200 rounded-lg text-blue-600"
                            title="导入知识库"
                          >
                            <Upload className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(draft.id);
                        }}
                        className="p-2 hover:bg-red-100 rounded-lg text-red-600"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
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
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-8"
            onClick={() => setShowPreview(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-white rounded-2xl max-w-4xl w-full max-h-full overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold">{selectedDraft.title}</h2>
                  <p className="text-sm text-gray-500">
                    {selectedDraft.schema_display_name} •{" "}
                    {new Date(selectedDraft.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  {selectedDraft.status === "draft" && (
                    <button
                      onClick={() => {
                        setShowPreview(false);
                        handleOpenImport(selectedDraft);
                      }}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg flex items-center gap-2"
                    >
                      <Upload className="w-4 h-4" /> 存入知识库
                    </button>
                  )}
                  <button
                    onClick={() => setShowPreview(false)}
                    className="px-4 py-2 border rounded-lg"
                  >
                    关闭
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
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={() => setShowImportModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-white rounded-2xl w-full max-w-md p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-semibold mb-4">选择目标知识库</h2>

              {knowledgeBases.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  暂无可用知识库，请先创建知识库
                </div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {knowledgeBases.map((kb) => (
                    <button
                      key={kb.id}
                      onClick={() => handleImport(kb.id)}
                      className="w-full p-4 border rounded-lg hover:bg-gray-50 text-left"
                    >
                      <div className="font-medium">{kb.name}</div>
                      {kb.description && (
                        <div className="text-sm text-gray-500">{kb.description}</div>
                      )}
                    </button>
                  ))}
                </div>
              )}

              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 border rounded-lg"
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
