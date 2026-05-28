"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft, ArrowUp, BookOpen, ChevronDown, ChevronRight, ChevronLeft,
  CheckCircle2, Copy, Download, FileText, LayoutGrid, List, Lightbulb, Loader2, MoreHorizontal, PenLine, Plus,
  RefreshCw, Scissors, Search, Share2, FolderCheck, Star, Sparkles, Archive,
  Trash2, Wand2, X,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useModels } from "@/core/models/hooks";
import { cn } from "@/lib/utils";

import dynamic from "next/dynamic";

const CollabEditor = dynamic(() => import("../collab/CollabEditor").then((m) => m.CollabEditor), {
  ssr: false,
  loading: () => <div className="flex-1 flex items-center justify-center text-muted-foreground">加载编辑器...</div>,
});
import type { CollabEditorRef } from "../collab/CollabEditor";
import { docmgrApi } from "../api";
import type { AIDocument } from "../types";

import BatchActionBar from "./BatchActionBar";
import FilePreviewModal, { isImageFile, isTextFile, formatFileSize } from "./FilePreviewModal";
import FolderPickerDialog from "./FolderPickerDialog";
import ShareDialog from "./ShareDialog";
import TiptapEditor, { type TiptapEditorRef } from "./TiptapEditor";
import { useDocuments } from "./useDocuments";

type AIOperation = "polish" | "expand" | "condense" | "brainstorm";
type View = "list" | "editor";

export default function DocumentManagement({ initialDocId }: { initialDocId?: string }) {
  const [view, setView] = useState<View>(initialDocId ? "editor" : "list");
  const [activeDocId, setActiveDocId] = useState<string | null>(initialDocId ?? null);
  const [activeNav, setActiveNav] = useState<"folder" | "starred" | "shared" | "file_ref" | "file_ref_folder">("folder");
  const [currentFolder, setCurrentFolder] = useState("默认文件夹");
  const handleSelectDoc = (doc: AIDocument) => { setActiveDocId(doc.id); setView("editor"); };
  const handleBack = () => { setActiveDocId(null); setView("list"); };
  return (
    <div className="h-full flex overflow-hidden bg-background">
      <AnimatePresence mode="wait">
        {view === "list" ? (
          <motion.div key="list" className="flex-1 flex overflow-hidden"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <DocumentList onSelectDoc={handleSelectDoc} activeNav={activeNav} onNavChange={setActiveNav} currentFolder={currentFolder} onFolderChange={setCurrentFolder} />
          </motion.div>
        ) : activeDocId ? (
          <motion.div key="editor" className="flex-1 flex overflow-hidden"
            initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            <DocumentEditor docId={activeDocId} onBack={handleBack} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

// ─── Document List ────────────────────────────────────────────────────────────

function DocumentList({ onSelectDoc, activeNav, onNavChange, currentFolder, onFolderChange }: {
  onSelectDoc: (doc: AIDocument) => void;
  activeNav: "folder" | "starred" | "shared" | "file_ref" | "file_ref_folder";
  onNavChange: (nav: "folder" | "starred" | "shared" | "file_ref" | "file_ref_folder") => void;
  currentFolder: string;
  onFolderChange: (folder: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [showNewModal, setShowNewModal] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(true);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<{ x: number; y: number } | null>(null);
  const menuButtonRef = useRef<Record<string, HTMLButtonElement | null>>({});
  const debouncedSearch = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewDocState, setPreviewDocState] = useState<AIDocument | null>(null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [shareDoc, setShareDoc] = useState<AIDocument | null>(null);
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const { docs, total, loading, page, pageSize, setPage, folders, projectFolders, createDoc, deleteDoc, toggleStar, setFilter, moveToFolder, batchDeleteDocs, renameDoc } =
    useDocuments({ folder: currentFolder });

  // Sync filter to match activeNav on mount (preserves nav state when returning from editor)
  const navSynced = useRef(false);
  useEffect(() => {
    if (navSynced.current) return;
    navSynced.current = true;
    if (activeNav === "starred") setFilter({ starred: true });
    else if (activeNav === "shared") setFilter({ shared: true });
    else if (activeNav === "file_ref") setFilter({ doc_type: "file_ref", project_scope: "personal" });
    else if (activeNav === "file_ref_folder") setFilter({ doc_type: "file_ref", project_scope: "project", folder: currentFolder });
    else setFilter({ folder: currentFolder, doc_type: "document" });
  }, [activeNav, currentFolder, setFilter]);

  const handleSearch = (v: string) => {
    setSearch(v);
    clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(() => setFilter((f) => ({ ...f, q: v || undefined })), 400);
  };

  const totalPages = Math.ceil(total / pageSize);

  const handleNavClick = (nav: typeof activeNav, folder?: string) => {
    onNavChange(nav);
    setSelectedIds(new Set());
    if (nav === "folder") {
      const nextFolder = folder ?? "默认文件夹";
      onFolderChange(nextFolder);
      setFilter({ folder: nextFolder, doc_type: "document", q: search || undefined });
    } else if (nav === "starred") {
      setFilter({ starred: true, q: search || undefined });
    } else if (nav === "shared") {
      setFilter({ shared: true, q: search || undefined });
    } else if (nav === "file_ref") {
      setFilter({ doc_type: "file_ref", project_scope: "personal", q: search || undefined });
    } else if (nav === "file_ref_folder") {
      if (folder) onFolderChange(folder);
      setFilter({ doc_type: "file_ref", project_scope: "project", folder, q: search || undefined });
    }
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBatchCancel = () => setSelectedIds(new Set());

  const handleBatchMove = () => setShowFolderPicker(true);

  const handleFolderSelect = async (folder: string) => {
    for (const id of selectedIds) {
      await moveToFolder(id, folder);
    }
    setSelectedIds(new Set());
    setShowFolderPicker(false);
  };

  const handleBatchStar = async () => {
    // Star toggle for batch — toggle star on all selected
    for (const id of selectedIds) {
      const doc = docs.find((d) => d.id === id);
      if (doc) await toggleStar(doc.id, doc.is_starred ?? false);
    }
    setSelectedIds(new Set());
  };

  const handleBatchDelete = async () => {
    if (!confirm(`确认删除选中的 ${selectedIds.size} 个文件？`)) return;
    await batchDeleteDocs(Array.from(selectedIds));
    setSelectedIds(new Set());
  };

  const isFileRefView = activeNav === "file_ref" || activeNav === "file_ref_folder";

  const handleCreate = async (title: string) => {
    const doc = await createDoc({ title, content: "", folder: currentFolder });
    setShowNewModal(false);
    onSelectDoc(doc);
  };

  const handleOpenMenu = (id: string) => {
    const btn = menuButtonRef.current[id];
    if (btn) {
      const rect = btn.getBoundingClientRect();
      setMenuAnchor({ x: rect.right, y: rect.top });
    }
    setOpenMenuId(id);
  };

  const handleCloseMenu = () => { setOpenMenuId(null); setMenuAnchor(null); };

  useEffect(() => {
    if (!openMenuId) return;
    const handler = () => handleCloseMenu();
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [openMenuId]);

  return (
    <div className="flex h-full w-full bg-background">
      <div className="w-60 border-r border-border flex flex-col shrink-0 bg-muted/50">
        <div className="p-4 flex items-center gap-2 border-b border-border">
          <FolderCheck className="w-5 h-5 text-primary" />
          <span className="font-semibold text-foreground text-l">文档空间</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
          {/* 我的文件夹 */}
          <div className="text-xs font-medium text-muted-foreground px-3 py-1">我的文件夹</div>
          <button onClick={() => handleNavClick("folder")}
            className={cn("w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors",
              activeNav === "folder" ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
            <FileText className="w-4 h-4" />我的文档
          </button>
          <button onClick={() => handleNavClick("starred")}
            className={cn("w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors",
              activeNav === "starred" ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
            <Star className="w-4 h-4" />我的收藏
          </button>
          <button onClick={() => handleNavClick("shared")}
            className={cn("w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors",
              activeNav === "shared" ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
            <Share2 className="w-4 h-4" />我的分享
          </button>

          <div className="h-px bg-border my-2" />

          {/* AI任务存档 */}
          <div className="text-xs font-medium text-muted-foreground px-3 py-1">AI任务存档</div>
          <button onClick={() => handleNavClick("file_ref")}
            className={cn("w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors",
              activeNav === "file_ref" ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
            <Archive className="w-4 h-4" />个人文件夹
          </button>
          <button onClick={() => setArchiveOpen((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors">
            <div className="flex items-center gap-2">
              <Archive className="w-3.5 h-3.5" />
              <span>项目文件夹</span>
            </div>
            {archiveOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
          {archiveOpen && (
            <div className="pl-4 space-y-0.5">
              {projectFolders.map((f) => (
                <button key={f} onClick={() => handleNavClick("file_ref_folder", f)}
                  className={cn("w-full text-left px-3 py-1.5 text-sm rounded-lg transition-colors",
                    activeNav === "file_ref_folder" && currentFolder === f ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
                  {f}
                </button>
              ))}
            </div>
          )}
        </nav>
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-14 flex items-center justify-between px-6 border-b border-border shrink-0 bg-background">
          <div className="flex items-center gap-3">
            {!isFileRefView && (
              <Button onClick={() => setShowNewModal(true)}>
                <Plus className="w-4 h-4" />新建文档
              </Button>
            )}
            <div className="relative w-60">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input type="text" value={search} onChange={(e) => handleSearch(e.target.value)} placeholder="搜索文档..."
                className="w-full pl-9 pr-4" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex h-[30px] items-center overflow-hidden rounded-[6px] border border-border bg-card">
              <button
                onClick={() => setViewMode("grid")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "grid" ? "text-foreground" : "text-muted-foreground",
                )}
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "list" ? "text-foreground" : "text-muted-foreground",
                )}
              >
                <List className="h-4 w-4" />
              </button>
            </div>
            <span className="text-xs text-muted-foreground">共 {total} 篇文档</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-muted/30">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">加载中...</div>
          ) : docs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-center">
              <FileText className="w-12 h-12 text-muted-foreground/30 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">{isFileRefView ? "暂无文件" : "暂无文档"}</p>
              <p className="text-xs text-muted-foreground/70 mt-1">{isFileRefView ? "AI任务产出的文件会出现在这里" : "点击「新建文档」开始创作"}</p>
            </div>
          ) : viewMode === "grid" ? (
            <AnimatePresence>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {docs.map((doc) => (
                  doc.doc_type === "file_ref" ? (
                    <FileRefCard key={doc.id} doc={doc}
                      isMenuOpen={openMenuId === doc.id}
                      onOpenMenu={handleOpenMenu}
                      menuButtonRef={(el) => { menuButtonRef.current[doc.id] = el; }}
                      onToggleStar={() => toggleStar(doc.id, doc.is_starred ?? false)}
                      onDelete={async () => { handleCloseMenu(); if (confirm("确认删除该文件？")) await deleteDoc(doc.id); }}
                      onSelect={() => onSelectDoc(doc)}
                      onShare={() => { setShareDoc(doc); setShowShareDialog(true); }}
                      selected={selectedIds.has(doc.id)}
                      onToggleSelect={() => handleToggleSelect(doc.id)} />
                  ) : (
                    <DocCard key={doc.id} doc={doc}
                      isMenuOpen={openMenuId === doc.id}
                      onOpenMenu={handleOpenMenu}
                      menuButtonRef={(el) => { menuButtonRef.current[doc.id] = el; }}
                      onSelect={() => onSelectDoc(doc)}
                      onToggleStar={() => toggleStar(doc.id, doc.is_starred ?? false)}
                      onDelete={async () => { handleCloseMenu(); if (confirm("确认删除该文档？")) await deleteDoc(doc.id); }}
                      onShare={() => { setShareDoc(doc); setShowShareDialog(true); }}
                      selected={selectedIds.has(doc.id)}
                      onToggleSelect={() => handleToggleSelect(doc.id)} />
                  )
                ))}
              </div>
            </AnimatePresence>
          ) : (
            <div className="bg-background border border-border rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">名称</th>
                    <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">类型</th>
                    <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">大小</th>
                    <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">更新时间</th>
                    <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {docs.map((doc) => {
                    const isFileRef = doc.doc_type === "file_ref";
                    const fileSize = isFileRef ? formatFileSize(doc.file_size) : "";
                    const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "/") : "";
                    const handleClick = (e: React.MouseEvent) => {
                      if (e.ctrlKey || e.metaKey) { e.preventDefault(); handleToggleSelect(doc.id); }
                      else { onSelectDoc(doc); }
                    };
                    return (
                      <tr key={doc.id}
                        className={cn("hover:bg-muted/50 transition-colors group cursor-pointer", selectedIds.has(doc.id) && "bg-primary/5")}
                        onClick={handleClick}>
                        <td className="py-4 px-6">
                          <div className="flex items-center gap-3 min-w-0">
                            {selectedIds.has(doc.id) ? (
                              <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
                            ) : isFileRef ? (
                              <FileTypeIcon mime={doc.file_mime} title={doc.title} size="sm" />
                            ) : (
                              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                            )}
                            <span className="font-medium text-foreground truncate group-hover:text-primary transition-colors">
                              {doc.title || "无标题"}
                            </span>
                          </div>
                        </td>
                        <td className="py-4 px-6">
                          {isFileRef ? (() => {
                            const fic = FILE_ICON_CONFIG[getFileType(doc.file_mime, doc.title)]!;
                            return (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                                style={{ backgroundColor: fic.primary + "18", color: fic.primary }}>
                                {fic.label}
                              </span>
                            );
                          })() : (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-400 text-xs font-semibold">
                              DOC
                            </span>
                          )}
                        </td>
                        <td className="py-4 px-6 text-sm text-muted-foreground">
                          {fileSize || "—"}
                        </td>
                        <td className="py-4 px-6 text-sm text-muted-foreground">{updatedAt}</td>
                        <td className="py-4 px-6 text-right">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                              onClick={(e) => { e.stopPropagation(); toggleStar(doc.id, doc.is_starred ?? false); }}>
                              <Star className={cn("w-4 h-4", doc.is_starred && "text-amber-400")} fill={doc.is_starred ? "currentColor" : "none"} />
                            </button>
                            <button ref={(el) => { menuButtonRef.current[doc.id] = el; }}
                              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                              onClick={(e) => { e.stopPropagation(); handleOpenMenu(doc.id); }}>
                              <MoreHorizontal className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {openMenuId && menuAnchor && (() => {
          const doc = docs.find((d) => d.id === openMenuId);
          if (!doc) return null;
          const isFileRef = doc.doc_type === "file_ref";
          return (
            <div
              className="fixed w-32 bg-background rounded-xl shadow-xl border border-border py-1.5 z-[100]"
              style={{ left: menuAnchor.x, top: menuAnchor.y + 4 }}
              onClick={(e) => e.stopPropagation()}
            >
              <button type="button" onClick={() => { handleCloseMenu(); onSelectDoc(doc); }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                <PenLine className="w-3 h-3" /> 打开编辑
              </button>
              <button type="button" onClick={() => { handleCloseMenu(); setShareDoc(doc); setShowShareDialog(true); }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                <Share2 className="w-3 h-3" /> 分享
              </button>
              <div className="h-px bg-border my-1 mx-2" />
              <button type="button" onClick={async () => { handleCloseMenu(); if (confirm(`确认删除该${isFileRef ? "文件" : "文档"}？`)) await deleteDoc(doc.id); }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10">
                <Trash2 className="w-3 h-3" /> 删除
              </button>
            </div>
          );
        })()}
      </div>
      {totalPages > 1 && (
        <div className="px-6 py-3 border-t border-border flex items-center justify-end gap-2 shrink-0 bg-background">
          <Button
            variant="outline"
            size="icon"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <Button
              key={p}
              variant={p === page ? "default" : "outline"}
              size="icon"
              onClick={() => setPage(p)}
            >
              {p}
            </Button>
          ))}
          <Button
            variant="outline"
            size="icon"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
      <AnimatePresence>
        {showNewModal && <NewDocModal isOpen={showNewModal} onClose={() => setShowNewModal(false)} onCreate={handleCreate} />}
      </AnimatePresence>
      <FilePreviewModal doc={previewDocState} open={!!previewDocState} onOpenChange={(o) => { if (!o) setPreviewDocState(null); }} />
      <ShareDialog doc={shareDoc} open={showShareDialog} onOpenChange={setShowShareDialog} />
      <FolderPickerDialog
        folders={folders}
        open={showFolderPicker}
        onOpenChange={setShowFolderPicker}
        onSelect={handleFolderSelect}
      />
      <BatchActionBar
        selectedCount={selectedIds.size}
        onMove={handleBatchMove}
        onStar={handleBatchStar}
        onDelete={handleBatchDelete}
        onCancel={handleBatchCancel}
      />
    </div>
  );
}

// ─── Doc Card ─────────────────────────────────────────────────────────────────

function DocCard({ doc, isMenuOpen, onOpenMenu, menuButtonRef, onSelect, onToggleStar, onDelete, onShare, selected, onToggleSelect }: {
  doc: AIDocument; isMenuOpen: boolean;
  onOpenMenu: (id: string) => void; menuButtonRef: (el: HTMLButtonElement | null) => void;
  onSelect: () => void; onToggleStar: () => void; onDelete: () => void; onShare?: () => void;
  selected?: boolean; onToggleSelect?: () => void;
}) {
  const preview = (doc.content ?? "").replace(/[#*`>\-_]/g, "").trim().slice(0, 120);
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "/") : "";
  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.2 }}
      className="bg-background rounded-xl border border-border p-4 cursor-pointer transition-all flex flex-col h-64 group hover:shadow-md hover:border-primary/50"
      onClick={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); onToggleSelect?.(); } else { onSelect(); } }}>
      <div className="flex-1 mb-4 relative overflow-hidden">
        <div className="bg-muted/50 rounded-lg p-4 h-full border border-border relative overflow-hidden">
          <div className="absolute left-0 top-4 bottom-4 w-1 bg-purple-200 dark:bg-purple-500/50 rounded-r-full" />
          <p className="text-sm text-muted-foreground leading-relaxed pl-3 line-clamp-4">{preview || "（空文档）"}</p>
        </div>
      </div>
      <h3 className="font-bold text-foreground text-base line-clamp-1 mb-4 group-hover:text-primary transition-colors">
        {doc.title || "无标题"}
      </h3>
      <div className="flex items-center justify-between text-muted-foreground mt-auto">
        <span className="text-xs">{updatedAt}</span>
        <div className="flex items-center gap-3 text-xs">
          <button ref={menuButtonRef} className="hover:text-foreground transition-colors" onClick={(e) => { e.stopPropagation(); onOpenMenu(doc.id); }}>
            <MoreHorizontal className="w-4 h-4" />
          </button>
          <button className={cn("transition-colors", doc.is_starred ? "text-amber-400" : "hover:text-foreground")} onClick={(e) => { e.stopPropagation(); onToggleStar(); }}>
            <Star className="w-4 h-4" fill={doc.is_starred ? "currentColor" : "none"} />
          </button>
        </div>
      </div>
      {selected && (
        <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
          <CheckCircle2 className="w-3 h-3 text-primary-foreground" />
        </div>
      )}
    </motion.div>
  );
}

// ─── File Type Icon System ─────────────────────────────────────────────────

interface FileIconConfig {
  primary: string;
  secondary: string;
  label: string;
  dark?: boolean;
  symbol: "doc" | "code" | "data" | "image" | "terminal";
}

const FILE_ICON_CONFIG: Record<string, FileIconConfig> = {
  markdown:   { primary: "#0EA5E9", secondary: "#FFFFFF", label: "MD",  symbol: "doc" },
  python:     { primary: "#8B5CF6", secondary: "#FDE68A", label: "PY",  symbol: "code" },
  javascript: { primary: "#EAB308", secondary: "#1E293B", label: "JS",  dark: true, symbol: "code" },
  typescript: { primary: "#3B82F6", secondary: "#FFFFFF", label: "TS",  symbol: "code" },
  json:       { primary: "#F97316", secondary: "#FFFFFF", label: "JSON", symbol: "data" },
  html:       { primary: "#EF4444", secondary: "#FFFFFF", label: "HTML", symbol: "code" },
  css:        { primary: "#06B6D4", secondary: "#FFFFFF", label: "CSS",  symbol: "code" },
  pdf:        { primary: "#DC2626", secondary: "#FFFFFF", label: "PDF",  symbol: "doc" },
  word:       { primary: "#2563EB", secondary: "#FFFFFF", label: "DOC",  symbol: "doc" },
  excel:      { primary: "#16A34A", secondary: "#FFFFFF", label: "XLS",  symbol: "data" },
  csv:        { primary: "#65A30D", secondary: "#FFFFFF", label: "CSV",  symbol: "data" },
  image:      { primary: "#D946EF", secondary: "#FFFFFF", label: "IMG",  symbol: "image" },
  text:       { primary: "#94A3B8", secondary: "#FFFFFF", label: "TXT",  symbol: "doc" },
  xml:        { primary: "#EA580C", secondary: "#FFFFFF", label: "XML",  symbol: "code" },
  yaml:       { primary: "#EC4899", secondary: "#FFFFFF", label: "YML",  symbol: "data" },
  shell:      { primary: "#22C55E", secondary: "#FFFFFF", label: "SH",   symbol: "terminal" },
};

function getFileType(mime: string | undefined | null, title: string | undefined | null): string {
  if (!mime && title) {
    const ext = title.split(".").pop()?.toLowerCase() || "";
    const extMap: Record<string, string> = {
      md: "markdown", py: "python", js: "javascript", ts: "typescript",
      json: "json", html: "html", css: "css", pdf: "pdf",
      doc: "word", docx: "word", xls: "excel", xlsx: "excel",
      csv: "csv", xml: "xml", yml: "yaml", yaml: "yaml", sh: "shell", txt: "text",
    };
    return extMap[ext] || "text";
  }
  const m = (mime || "").toLowerCase();
  if (m.includes("markdown") || m.includes("x-markdown")) return "markdown";
  if (m.includes("python")) return "python";
  if (m.includes("javascript")) return "javascript";
  if (m.includes("typescript")) return "typescript";
  if (m.includes("json")) return "json";
  if (m.includes("html")) return "html";
  if (m.includes("css")) return "css";
  if (m.includes("pdf")) return "pdf";
  if (m.includes("word") || m.includes("document")) return "word";
  if (m.includes("excel") || m.includes("spreadsheet")) return "excel";
  if (m.includes("csv")) return "csv";
  if (m.includes("image")) return "image";
  if (m.includes("xml")) return "xml";
  if (m.includes("yaml")) return "yaml";
  if (m.includes("shell") || m.includes("bash")) return "shell";
  if (m.includes("text/plain")) return "text";
  return "text";
}

const SymbolPaths = {
  doc: (fill: string) => (
    <g>
      <rect x="8" y="11" width="24" height="2" rx="1" fill={fill} opacity="0.5" />
      <rect x="8" y="16" width="18" height="2" rx="1" fill={fill} opacity="0.35" />
      <rect x="8" y="21" width="12" height="2" rx="1" fill={fill} opacity="0.2" />
    </g>
  ),
  code: (fill: string) => (
    <g>
      <polyline points="10,12 6,17 10,22" fill="none" stroke={fill} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
      <polyline points="30,12 34,17 30,22" fill="none" stroke={fill} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
      <line x1="24" y1="10" x2="16" y2="24" stroke={fill} strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
    </g>
  ),
  data: (fill: string) => (
    <g>
      <rect x="8" y="11" width="9" height="5" rx="1" fill={fill} opacity="0.4" />
      <rect x="19" y="11" width="9" height="5" rx="1" fill={fill} opacity="0.3" />
      <rect x="8" y="18" width="9" height="5" rx="1" fill={fill} opacity="0.3" />
      <rect x="19" y="18" width="9" height="5" rx="1" fill={fill} opacity="0.2" />
    </g>
  ),
  image: (fill: string) => (
    <g>
      <circle cx="16" cy="15" r="3.5" fill={fill} opacity="0.45" />
      <polyline points="8,26 16,19 21,23 26,18 32,24 32,27 8,27" fill={fill} opacity="0.3" />
    </g>
  ),
  terminal: (fill: string) => (
    <g>
      <polyline points="9,13 15,18 9,23" fill="none" stroke={fill} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
      <rect x="19" y="22" width="8" height="2.5" rx="1" fill={fill} opacity="0.35" />
    </g>
  ),
};

function FileTypeIcon({ mime, title, size = "lg" }: { mime?: string | null; title?: string | null; size?: "sm" | "lg" }) {
  const fileType = getFileType(mime, title);
  const config = FILE_ICON_CONFIG[fileType]!;
  const labelFill = config.dark ? config.secondary : "#fff";
  const symbolFill = config.dark ? config.secondary : "#fff";
  const gid = size === "lg" ? `sheen-${fileType}` : `sheen-sm-${fileType}`;
  const cid = size === "lg" ? `fold-${fileType}` : `fold-sm-${fileType}`;

  if (size === "lg") {
    return (
      <svg className="w-12 h-14" viewBox="0 0 40 48" fill="none">
        <defs>
          <clipPath id={cid}>
            <path d="M4 2H26L40 16V44C40 46.2 38.2 48 36 48H4C1.8 48 0 46.2 0 44V6C0 3.8 1.8 2 4 2Z" />
          </clipPath>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="white" stopOpacity="0.28" />
            <stop offset="50%" stopColor="white" stopOpacity="0.06" />
            <stop offset="100%" stopColor="black" stopOpacity="0.06" />
          </linearGradient>
        </defs>
        <g clipPath={`url(#${cid})`}>
          <rect width="40" height="48" fill={config.primary} />
          <rect width="40" height="48" fill={`url(#${gid})`} />
          <path d="M26 2V12C26 14.2 27.8 16 30 16H40V16L26 2Z" fill="rgba(0,0,0,0.12)" />
        </g>
        <path d="M4 2H26L40 16V44C40 46.2 38.2 48 36 48H4C1.8 48 0 46.2 0 44V6C0 3.8 1.8 2 4 2Z"
          className="stroke-black/8" strokeWidth="0.5" fill="none" />
        {SymbolPaths[config.symbol](symbolFill)}
        <rect x="5" y="34" width="30" height="11" rx="3" fill="rgba(0,0,0,0.18)" />
        <text x="20" y="43" textAnchor="middle" fill={labelFill} fontSize="10" fontWeight="800" fontFamily="system-ui, -apple-system, sans-serif" letterSpacing="0.5">{config.label}</text>
      </svg>
    );
  }

  return (
    <svg className="w-5 h-6" viewBox="0 0 20 24" fill="none">
      <defs>
        <clipPath id={cid}>
          <path d="M2 1H13L20 8V22C20 23.1 19.1 24 18 24H2C0.9 24 0 23.1 0 22V3C0 1.9 0.9 1 2 1Z" />
        </clipPath>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="white" stopOpacity="0.25" />
          <stop offset="100%" stopColor="black" stopOpacity="0.05" />
        </linearGradient>
      </defs>
      <g clipPath={`url(#${cid})`}>
        <rect width="20" height="24" fill={config.primary} />
        <rect width="20" height="24" fill={`url(#${gid})`} />
        <path d="M13 1V6C13 7.1 13.9 8 15 8H20V8L13 1Z" fill="rgba(0,0,0,0.12)" />
      </g>
      <path d="M2 1H13L20 8V22C20 23.1 19.1 24 18 24H2C0.9 24 0 23.1 0 22V3C0 1.9 0.9 1 2 1Z"
        className="stroke-black/8" strokeWidth="0.5" fill="none" />
      <rect x="3" y="17" width="14" height="5" rx="1.5" fill="rgba(0,0,0,0.18)" />
      <text x="10" y="21" textAnchor="middle" fill={labelFill} fontSize="4.5" fontWeight="800" fontFamily="system-ui, -apple-system, sans-serif">{config.label}</text>
    </svg>
  );
}

// ─── File Ref Card ─────────────────────────────────────────────────────────────

function FileRefCard({ doc, isMenuOpen, onOpenMenu, menuButtonRef, onToggleStar, onDelete, onSelect, onShare, selected, onToggleSelect }: {
  doc: AIDocument; isMenuOpen: boolean;
  onOpenMenu: (id: string) => void; menuButtonRef: (el: HTMLButtonElement | null) => void;
  onToggleStar: () => void; onDelete: () => void; onSelect: () => void; onShare?: () => void;
  selected?: boolean; onToggleSelect?: () => void;
}) {
  const isImage = isImageFile(doc.file_mime);
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "/") : "";
  const fileSize = formatFileSize(doc.file_size);

  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.2 }}
      className="bg-background rounded-xl border border-border p-4 cursor-pointer transition-all flex flex-col h-48 group hover:shadow-md hover:border-primary/50 relative"
      onClick={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); onToggleSelect?.(); } else { onSelect(); } }}>
      <div className="flex-1 mb-4 flex items-center justify-center relative overflow-hidden">
        {isImage && doc.file_ref_path ? (
          <img
            src={doc.file_ref_path}
            alt={doc.title || "预览"}
            className="max-w-full max-h-full object-contain rounded-lg"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : (
          <FileTypeIcon mime={doc.file_mime} title={doc.title} size="lg" />
        )}
      </div>
      <h3 className="font-medium text-foreground text-sm line-clamp-1 mb-2 group-hover:text-primary transition-colors">
        {doc.title || "无标题"}
      </h3>
      <div className="flex items-center justify-between text-muted-foreground mt-auto">
        <div className="flex items-center gap-2 text-xs">
          {fileSize && <span>{fileSize}</span>}
          {updatedAt && <span>{updatedAt}</span>}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <button ref={menuButtonRef} className="hover:text-foreground transition-colors" onClick={(e) => { e.stopPropagation(); onOpenMenu(doc.id); }}>
            <MoreHorizontal className="w-4 h-4" />
          </button>
          <button className={cn("transition-colors", doc.is_starred ? "text-amber-400" : "hover:text-foreground")} onClick={(e) => { e.stopPropagation(); onToggleStar(); }}>
            <Star className="w-4 h-4" fill={doc.is_starred ? "currentColor" : "none"} />
          </button>
        </div>
      </div>
      {selected && (
        <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
          <CheckCircle2 className="w-3 h-3 text-primary-foreground" />
        </div>
      )}
    </motion.div>
  );
}

// ─── New Doc Modal ────────────────────────────────────────────────────────────

function NewDocModal({ isOpen, onClose, onCreate }: {
  isOpen: boolean; onClose: () => void; onCreate: (title: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const handleSubmit = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try { await onCreate(title.trim()); setTitle(""); } finally { setSaving(false); }
  };
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
          <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative bg-background rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <h3 className="text-base font-semibold text-foreground">新建文档</h3>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="p-6">
              <label className="block text-sm font-medium text-foreground mb-1.5">文档标题 <span className="text-destructive">*</span></label>
              <Input autoFocus type="text" value={title} onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()} placeholder="请输入文档标题"
                className="w-full" />
            </div>
            <div className="px-6 py-4 bg-muted/50 border-t border-border flex items-center justify-end gap-2.5">
              <Button variant="outline" onClick={onClose}>取消</Button>
              <Button onClick={handleSubmit} disabled={!title.trim() || saving}>
                {saving ? "创建中..." : "创建"}
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

// ─── Export Menu ──────────────────────────────────────────────────────────────

function ExportMenu({ onExport }: { onExport: (fmt: "md" | "docx") => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen((v) => !v)}
      >
        <Download className="w-3.5 h-3.5" />导出
        <ChevronDown className={cn("w-3 h-3 transition-transform ml-1", open && "rotate-180")} />
      </Button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full mt-1 w-44 bg-background rounded-xl shadow-xl border border-border py-1 z-50"
          >
            <button
              type="button"
              onClick={() => { onExport("md"); setOpen(false); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              <FileText className="w-4 h-4 text-muted-foreground" />
              <div className="text-left">
                <div className="font-medium">Markdown</div>
                <div className="text-xs text-muted-foreground">.md 格式</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => { onExport("docx"); setOpen(false); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              <FileText className="w-4 h-4 text-primary" />
              <div className="text-left">
                <div className="font-medium">Word 文档</div>
                <div className="text-xs text-muted-foreground">.docx 格式</div>
              </div>
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Document Editor ──────────────────────────────────────────────────────────

function DocumentEditor({ docId, onBack }: { docId: string; onBack: () => void }) {
  const [doc, setDoc] = useState<AIDocument | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [showAI, setShowAI] = useState(false);
  const [loading, setLoading] = useState(true);
  const editorRef = useRef<TiptapEditorRef | CollabEditorRef>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const titleRef = useRef(title);
  titleRef.current = title;

  useEffect(() => {
    setLoading(true);
    docmgrApi.get(docId).then(async (d) => {
      // For file_ref documents, load file content via preview API
      if (d.doc_type === "file_ref" && !d.content) {
        try {
          const preview = await docmgrApi.preview(docId);
          if (preview.content) {
            d = { ...d, content: preview.content };
          }
        } catch { /* fall through with empty content */ }
      }
      setDoc(d);
      setTitle(d.title);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [docId]);

  const scheduleSave = useCallback((content: string) => {
    setSaved(false);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      setSaving(true);
      try { await docmgrApi.update(docId, { title: titleRef.current, content }); setSaved(true); setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })); }
      finally { setSaving(false); }
    }, 1500);
  }, [docId]);

  const handleTitleBlur = async () => {
    if (!doc || title === doc.title) return;
    setSaving(true);
    try {
      const content = editorRef.current?.getMarkdown() ?? doc.content ?? "";
      await docmgrApi.update(docId, { title, content });
      setSaved(true);
      setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
    } finally { setSaving(false); }
  };

  const handleExport = async (fmt: "md" | "docx") => {
    const res = await docmgrApi.export(docId, fmt);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${title}.${fmt}`; a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">加载中...</div>;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background">
      <div className="shrink-0 bg-background border-b border-border z-20">
        <div className="h-11 flex items-center justify-between px-4 gap-4">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={onBack}
              className="shrink-0"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={handleTitleBlur}
              className="text-lg font-semibold bg-transparent border-none outline-none min-w-0 flex-1 truncate"
              placeholder="无标题文档"
            />
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground mr-2 select-none">
              {saving ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" />保存中...</>
              ) : savedAt ? (
                <><CheckCircle2 className="w-3.5 h-3.5 text-success" />已保存于 {savedAt}</>
              ) : null}
            </span>
            <Button
              variant={showAI ? "default" : "ghost"}
              size="sm"
              onClick={() => setShowAI((v) => !v)}
            >
              AI 润色
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => { const md = editorRef.current?.getMarkdown() ?? ""; navigator.clipboard.writeText(md); }}
              title="复制内容"
            >
              <Copy className="w-4 h-4" />
            </Button>
            <ExportMenu onExport={handleExport} />
          </div>
        </div>
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          {doc !== null && (
            doc.project_id ? (
              <CollabEditor
                ref={editorRef as React.Ref<CollabEditorRef>}
                documentId={docId}
                initialContent={doc.content ?? ""}
                onChange={scheduleSave}
                className="flex-1"
              />
            ) : (
              <TiptapEditor
                ref={editorRef as React.Ref<TiptapEditorRef>}
                initialContent={doc.content ?? ""}
                onChange={scheduleSave}
                placeholder="开始输入内容..."
                className="flex-1"
              />
            )
          )}
        </div>
        <AnimatePresence>
          {showAI && (
            <motion.div initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: 360 }}
              exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.2 }}
              className="border-l border-border overflow-hidden shrink-0">
              <AIEditPanel onClose={() => setShowAI(false)}
                getSelectedText={() => editorRef.current?.getSelectedText() ?? ""}
                getFullText={() => editorRef.current?.getMarkdown() ?? ""}
                onResult={(text) => editorRef.current?.replaceSelection(text)} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── AI Edit Panel ────────────────────────────────────────────────────────────

const AI_OPS: { key: AIOperation; label: string; icon: React.ReactNode }[] = [
  { key: "polish",     label: "润色",    icon: <Wand2 className="w-3 h-3" /> },
  { key: "expand",     label: "扩写",    icon: <BookOpen className="w-3 h-3" /> },
  { key: "condense",   label: "缩写",    icon: <Scissors className="w-3 h-3" /> },
  { key: "brainstorm", label: "头脑风暴", icon: <Lightbulb className="w-3 h-3" /> },
];

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  operation?: AIOperation;
}

const SUGGESTED_PROMPTS = [
  "请阅读全文并总结要点",
  "帮我优化文档结构",
];

function AIEditPanel({ onClose, getSelectedText, getFullText, onResult }: {
  onClose: () => void;
  getSelectedText: () => string;
  getFullText: () => string;
  onResult: (text: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [activeOp, setActiveOp] = useState<AIOperation>("polish");
  const [modelName, setModelName] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [hasSelection, setHasSelection] = useState(false);
  const { models } = useModels();
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const modelMenuRef = useRef<HTMLDivElement>(null);

  const selectedModelLabel = modelName
    ? models.find((m) => m.name === modelName)?.display_name ?? modelName
    : "默认模型";

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  };

  const resetInputHeight = () => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }
  };

  const autoResizeInput = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  useEffect(() => {
    if (!modelMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node)) setModelMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelMenuOpen]);

  useEffect(() => {
    const handler = () => setHasSelection(!!getSelectedText().trim());
    document.addEventListener("selectionchange", handler);
    return () => document.removeEventListener("selectionchange", handler);
  }, [getSelectedText]);

  const sendMessage = async (text: string, operation?: AIOperation, displayContent?: string) => {
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: displayContent ?? text, operation };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    resetInputHeight();
    setRunning(true);
    scrollToBottom();

    try {
      const res = await docmgrApi.aiEdit({ text, operation: operation ?? activeOp, model_name: modelName ?? undefined });
      const assistantMsg: ChatMessage = { id: crypto.randomUUID(), role: "assistant", content: res.result };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(), role: "assistant",
        content: `⚠️ ${e instanceof Error ? e.message : "AI 处理失败"}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setRunning(false);
      scrollToBottom();
    }
  };

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || running) return;
    const selected = getSelectedText();
    const text = selected.trim() ? `${trimmed}\n\n【选中文字】：\n${selected}` : trimmed;
    void sendMessage(text, activeOp);
  };

  const handleQuickAction = (op: AIOperation) => {
    if (!hasSelection) return;
    setActiveOp(op);
    const selected = getSelectedText();
    if (selected.trim()) {
      void sendMessage(selected, op);
    } else {
      inputRef.current?.focus();
    }
  };

  const handleSuggestedPrompt = (prompt: string) => {
    const fullText = getFullText();
    const selected = getSelectedText();
    const apiText = `${prompt}\n\n${selected.trim() ? `【选中文字】：\n${selected}` : `【文档全文】：\n${fullText}`}`;
    void sendMessage(apiText, activeOp, prompt);
  };

  const handleCopy = async (content: string) => {
    await navigator.clipboard.writeText(content);
  };

  const handleReplace = (content: string) => {
    onResult(content);
  };

  const handleNewChat = () => {
    setMessages([]);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="w-[360px] h-full flex flex-col bg-background">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">AI 助手</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewChat} title="新对话">
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Quick action pills */}
      <div className="px-4 py-2 border-b border-border/60 flex gap-1.5 flex-wrap shrink-0">
        {AI_OPS.map(({ key, label, icon }) => {
          const disabled = !hasSelection;
          return (
            <button
              key={key}
              type="button"
              disabled={disabled}
              onClick={() => handleQuickAction(key)}
              className={cn(
                "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[13px] font-medium transition-all",
                disabled
                  ? "opacity-40 cursor-not-allowed border border-border text-muted-foreground"
                  : activeOp === key
                    ? "bg-primary text-primary-foreground"
                    : "border border-border text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {icon}{label}
            </button>
          );
        })}
      </div>

      {/* Message area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center h-full px-6 text-center">
            <div className="text-3xl mb-3 opacity-40">💬</div>
            <div className="text-sm font-medium text-foreground mb-1">AI 文档助手</div>
            <div className="text-[13px] text-muted-foreground leading-relaxed mb-4">
              在编辑器中选中文字，选择操作后发送<br />或在下方直接输入自定义指令
            </div>
            <div className="w-full space-y-2">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleSuggestedPrompt(prompt)}
                  className="w-full text-left px-3 py-2 border border-border rounded-lg text-[13px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Conversation */
          <div className="p-4 space-y-4">
            {messages.map((msg) => (
              msg.role === "user" ? (
                /* User message */
                <div key={msg.id} className="flex justify-end">
                  <div className="bg-primary text-primary-foreground px-3 py-2 rounded-2xl rounded-br-sm max-w-[85%] text-xs leading-relaxed">
                    {msg.operation && (
                      <div className="text-[10px] opacity-70 mb-1">{AI_OPS.find((o) => o.key === msg.operation)?.label}</div>
                    )}
                    {msg.content}
                  </div>
                </div>
              ) : (
                /* Assistant message */
                <div key={msg.id}>
                  <div className="bg-muted border border-border rounded-2xl rounded-bl-sm px-3 py-2.5 text-xs leading-relaxed text-foreground prose prose-xs prose-neutral max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_strong]:text-foreground [&_code]:text-primary [&_pre]:bg-background [&_pre]:rounded-lg [&_pre]:p-2 [&_blockquote]:border-primary [&_blockquote]:pl-2.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  {!msg.content.startsWith("⚠️") && (
                    <div className="mt-1.5 flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleReplace(msg.content)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-primary/30 text-primary text-[11px] hover:bg-primary/10 transition-colors"
                      >
                        <Wand2 className="w-3 h-3" />替换
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopy(msg.content)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors"
                      >
                        <Copy className="w-3 h-3" />复制
                      </button>
                    </div>
                  )}
                </div>
              )
            ))}
            {running && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>思考中...</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom input bar */}
      <div className="px-3 py-3 shrink-0">
        <div className="bg-muted/30 border border-gray-200 rounded-2xl px-3 py-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => { setInput(e.target.value); autoResizeInput(); }}
            onKeyDown={handleKeyDown}
            placeholder="输入指令或直接发送..."
            rows={1}
            className="w-full border-none outline-none bg-transparent text-[13px] text-foreground min-w-0 placeholder:text-gray-400 resize-none leading-relaxed max-h-[120px]"
          />
          <div className="flex items-center justify-between mt-1.5">
            {models.length > 0 ? (
              <div ref={modelMenuRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setModelMenuOpen((v) => !v)}
                  className="flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground transition-colors rounded-md px-1.5 py-0.5 hover:bg-muted"
                >
                  <span className="max-w-[72px] truncate">{selectedModelLabel}</span>
                  <ChevronDown className={cn("w-2.5 h-2.5 transition-transform", modelMenuOpen && "rotate-180")} />
                </button>
                <AnimatePresence>
                  {modelMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      transition={{ duration: 0.12 }}
                      className="absolute bottom-full left-0 mb-2 w-40 bg-background rounded-xl shadow-lg border border-border py-1 z-50"
                    >
                      <button
                        type="button"
                        onClick={() => { setModelName(null); setModelMenuOpen(false); }}
                        className={cn("w-full flex items-center gap-2 px-3 py-1.5 text-[13px] transition-colors",
                          !modelName ? "text-primary bg-primary/10" : "text-muted-foreground hover:bg-muted hover:text-foreground")}
                      >
                        <span>默认模型</span>
                      </button>
                      {models.map((m) => (
                        <button
                          key={m.name}
                          type="button"
                          onClick={() => { setModelName(m.name); setModelMenuOpen(false); }}
                          className={cn("w-full flex items-center gap-2 px-3 py-1.5 text-[13px] transition-colors",
                            modelName === m.name ? "text-primary bg-primary/10" : "text-muted-foreground hover:bg-muted hover:text-foreground")}
                        >
                          <span className="truncate">{m.display_name || m.name}</span>
                          {modelName === m.name && <CheckCircle2 className="w-3 h-3 ml-auto" />}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : <div />}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={running || !input.trim()}
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors",
                input.trim() && !running
                  ? "bg-primary text-primary-foreground hover:opacity-90"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowUp className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
