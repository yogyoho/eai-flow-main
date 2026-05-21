"use client";

import {
  ArrowLeft, ArrowUp, BookOpen, ChevronDown, ChevronRight, ChevronLeft,
  CheckCircle2, Copy, Download, FileText, File, Image, Lightbulb, Loader2, MoreHorizontal, PenLine, Plus,
  RefreshCw, Scissors, Search, Share2, FolderCheck, Star, Sparkles, Archive,
  Trash2, Wand2, X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useModels } from "@/core/models/hooks";

import { docmgrApi } from "../api";
import type { AIDocument } from "../types";

import TiptapEditor, { type TiptapEditorRef } from "./TiptapEditor";
import { useDocuments } from "./useDocuments";
import FilePreviewModal, { isImageFile, isTextFile, formatFileSize } from "./FilePreviewModal";
import FolderPickerDialog from "./FolderPickerDialog";
import BatchActionBar from "./BatchActionBar";
import ShareDialog from "./ShareDialog";

type AIOperation = "polish" | "expand" | "condense" | "brainstorm";
type View = "list" | "editor";

export default function DocumentManagement({ initialDocId }: { initialDocId?: string }) {
  const [view, setView] = useState<View>(initialDocId ? "editor" : "list");
  const [activeDocId, setActiveDocId] = useState<string | null>(initialDocId ?? null);
  const handleSelectDoc = (doc: AIDocument) => { setActiveDocId(doc.id); setView("editor"); };
  const handleBack = () => { setActiveDocId(null); setView("list"); };
  return (
    <div className="h-full flex overflow-hidden bg-background">
      <AnimatePresence mode="wait">
        {view === "list" ? (
          <motion.div key="list" className="flex-1 flex overflow-hidden"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <DocumentList onSelectDoc={handleSelectDoc} />
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

function DocumentList({ onSelectDoc }: { onSelectDoc: (doc: AIDocument) => void }) {
  const [search, setSearch] = useState("");
  const [showNewModal, setShowNewModal] = useState(false);
  const [activeNav, setActiveNav] = useState<"folder" | "starred" | "shared" | "file_ref" | "file_ref_folder">("folder");
  const [folderOpen, setFolderOpen] = useState(true);
  const [archiveOpen, setArchiveOpen] = useState(true);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<{ x: number; y: number } | null>(null);
  const menuButtonRef = useRef<{ [id: string]: HTMLButtonElement | null }>({});
  const debouncedSearch = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [currentFolder, setCurrentFolder] = useState("默认文件夹");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewDocState, setPreviewDocState] = useState<AIDocument | null>(null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [shareDoc, setShareDoc] = useState<AIDocument | null>(null);
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const { docs, total, loading, page, pageSize, setPage, folders, createDoc, deleteDoc, toggleStar, setFilter, moveToFolder, batchDeleteDocs, renameDoc } =
    useDocuments({ folder: currentFolder });

  const handleSearch = (v: string) => {
    setSearch(v);
    clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(() => setFilter((f) => ({ ...f, q: v || undefined })), 400);
  };

  const totalPages = Math.ceil(total / pageSize);

  const handleNavClick = (nav: typeof activeNav, folder?: string) => {
    setActiveNav(nav);
    setSelectedIds(new Set());
    if (nav === "folder") {
      const nextFolder = folder ?? "默认文件夹";
      setCurrentFolder(nextFolder);
      setFilter({ folder: nextFolder, doc_type: "document", q: search || undefined });
    } else if (nav === "starred") {
      setFilter({ starred: true, q: search || undefined });
    } else if (nav === "shared") {
      setFilter({ shared: true, q: search || undefined });
    } else if (nav === "file_ref") {
      setFilter({ doc_type: "file_ref", q: search || undefined });
    } else if (nav === "file_ref_folder") {
      if (folder) setCurrentFolder(folder);
      setFilter({ doc_type: "file_ref", folder, q: search || undefined });
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

          {/* Folder tree under 我的文档 */}
          <button onClick={() => setFolderOpen((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors">
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />
              <span>子文件夹</span>
            </div>
            {folderOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
          {folderOpen && (
            <div className="pl-4 space-y-0.5">
              {folders.map((f) => (
                <button key={f} onClick={() => handleNavClick("folder", f)}
                  className={cn("w-full text-left px-3 py-1.5 text-sm rounded-lg transition-colors",
                    activeNav === "folder" && currentFolder === f ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
                  {f}
                </button>
              ))}
            </div>
          )}

          <div className="h-px bg-border my-2" />

          {/* AI任务存档 */}
          <div className="text-xs font-medium text-muted-foreground px-3 py-1">AI任务存档</div>
          <button onClick={() => handleNavClick("file_ref")}
            className={cn("w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors",
              activeNav === "file_ref" ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
            <Archive className="w-4 h-4" />全部存档
          </button>
          <button onClick={() => setArchiveOpen((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors">
            <div className="flex items-center gap-2">
              <Archive className="w-3.5 h-3.5" />
              <span>线程文件夹</span>
            </div>
            {archiveOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
          {archiveOpen && (
            <div className="pl-4 space-y-0.5">
              {folders.map((f) => (
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
          <span className="text-xs text-muted-foreground">共 {total} 篇文档</span>
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
          ) : (
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
                      onPreview={() => setPreviewDocState(doc)}
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
              {!isFileRef && (
                <button type="button" onClick={() => { handleCloseMenu(); onSelectDoc(doc); }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                  <PenLine className="w-3 h-3" /> 打开编辑
                </button>
              )}
              {isFileRef && (
                <button type="button" onClick={() => { handleCloseMenu(); setPreviewDocState(doc); }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                  <File className="w-3 h-3" /> 预览
                </button>
              )}
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
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) : "";
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

// ─── File Ref Card ─────────────────────────────────────────────────────────────

function FileRefCard({ doc, isMenuOpen, onOpenMenu, menuButtonRef, onToggleStar, onDelete, onPreview, onShare, selected, onToggleSelect }: {
  doc: AIDocument; isMenuOpen: boolean;
  onOpenMenu: (id: string) => void; menuButtonRef: (el: HTMLButtonElement | null) => void;
  onToggleStar: () => void; onDelete: () => void; onPreview: () => void; onShare?: () => void;
  selected?: boolean; onToggleSelect?: () => void;
}) {
  const isImage = isImageFile(doc.file_mime);
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) : "";
  const fileSize = formatFileSize(doc.file_size);
  const mimeLabel = doc.file_mime?.split("/")[1]?.toUpperCase() || "";

  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.2 }}
      className="bg-background rounded-xl border border-border p-4 cursor-pointer transition-all flex flex-col h-48 group hover:shadow-md hover:border-primary/50 relative"
      onClick={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); onToggleSelect?.(); } else { onPreview(); } }}>
      <div className="flex-1 mb-4 flex items-center justify-center relative overflow-hidden">
        {isImage && doc.file_ref_path ? (
          <img
            src={doc.file_ref_path}
            alt={doc.title || "预览"}
            className="max-w-full max-h-full object-contain rounded-lg"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            {isImage ? <Image className="w-10 h-10 text-muted-foreground/50" /> : <File className="w-10 h-10 text-muted-foreground/50" />}
            {mimeLabel && <span className="text-xs font-medium">{mimeLabel}</span>}
          </div>
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
  const editorRef = useRef<TiptapEditorRef>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const titleRef = useRef(title);
  titleRef.current = title;

  useEffect(() => {
    setLoading(true);
    docmgrApi.get(docId).then((d) => { setDoc(d); setTitle(d.title); setLoading(false); }).catch(() => setLoading(false));
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
            <TiptapEditor
              ref={editorRef}
              initialContent={doc.content ?? ""}
              onChange={scheduleSave}
              placeholder="开始输入内容..."
              className="flex-1"
            />
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
