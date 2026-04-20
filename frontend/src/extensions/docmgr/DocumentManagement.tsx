"use client";

import {
  ArrowLeft, BookOpen, ChevronDown, ChevronRight, ChevronLeft,
  CheckCircle2, Copy, Download, FileText, Loader2, MoreHorizontal, PenLine, Plus,
  RefreshCw, Scissors, Search, Share2, FolderCheck, Star, Sparkles,
  Trash2, Wand2, X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { docmgrApi } from "../api";
import type { AIDocument } from "../types";

import TiptapEditor, { type TiptapEditorRef } from "./TiptapEditor";
import { useDocuments, type DocumentFilter } from "./useDocuments";

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
  const [filter, setFilter] = useState<DocumentFilter>({ folder: "默认文件夹" });
  const [search, setSearch] = useState("");
  const [showNewModal, setShowNewModal] = useState(false);
  const [activeNav, setActiveNav] = useState<"folder" | "starred" | "shared">("folder");
  const [folderOpen, setFolderOpen] = useState(true);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const debouncedSearch = useRef<ReturnType<typeof setTimeout>>(undefined);

  const handleSearch = (v: string) => {
    setSearch(v);
    clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(() => setFilter((f) => ({ ...f, q: v || undefined })), 400);
  };

  const { docs, total, loading, page, pageSize, setPage, folders, createDoc, deleteDoc, toggleStar } = useDocuments(filter);
  const totalPages = Math.ceil(total / pageSize);

  const handleNavClick = (nav: "folder" | "starred" | "shared", folder?: string) => {
    setActiveNav(nav);
    if (nav === "folder") setFilter({ folder: folder ?? "默认文件夹", q: search || undefined });
    else if (nav === "starred") setFilter({ starred: true, q: search || undefined });
    else setFilter({ shared: true, q: search || undefined });
  };

  const handleCreate = async (title: string) => {
    const doc = await createDoc({ title, content: "", folder: filter.folder ?? "默认文件夹" });
    setShowNewModal(false);
    onSelectDoc(doc);
  };

  useEffect(() => {
    if (!openMenuId) return;
    const handler = () => setOpenMenuId(null);
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
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
          <button onClick={() => setFolderOpen((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-sm text-foreground hover:bg-muted rounded-lg transition-colors">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-muted-foreground" />
              <span className="font-medium">我的文档</span>
            </div>
            {folderOpen ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
          </button>
          {folderOpen && (
            <div className="pl-4 space-y-0.5">
              {folders.map((f) => (
                <button key={f} onClick={() => handleNavClick("folder", f)}
                  className={cn("w-full text-left px-3 py-1.5 text-sm rounded-lg transition-colors",
                    activeNav === "folder" && filter.folder === f ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted")}>
                  {f}
                </button>
              ))}
            </div>
          )}
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
        </nav>
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-14 flex items-center justify-between px-6 border-b border-border shrink-0 bg-background">
          <div className="flex items-center gap-3">
            <Button onClick={() => setShowNewModal(true)}>
              <Plus className="w-4 h-4" />新建文档
            </Button>
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
              <p className="text-sm font-medium text-muted-foreground">暂无文档</p>
              <p className="text-xs text-muted-foreground/70 mt-1">点击「新建文档」开始创作</p>
            </div>
          ) : (
            <AnimatePresence>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {docs.map((doc) => (
                  <DocCard key={doc.id} doc={doc}
                    isMenuOpen={openMenuId === doc.id}
                    onOpenMenu={(id) => setOpenMenuId(id)}
                    onSelect={() => onSelectDoc(doc)}
                    onToggleStar={() => toggleStar(doc.id, doc.is_starred ?? false)}
                    onDelete={async () => { if (confirm("确认删除该文档？")) await deleteDoc(doc.id); }} />
                ))}
              </div>
            </AnimatePresence>
          )}
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
      </div>
      <AnimatePresence>
        {showNewModal && <NewDocModal isOpen={showNewModal} onClose={() => setShowNewModal(false)} onCreate={handleCreate} />}
      </AnimatePresence>
    </div>
  );
}

// ─── Doc Card ─────────────────────────────────────────────────────────────────

function DocCard({ doc, isMenuOpen, onOpenMenu, onSelect, onToggleStar, onDelete }: {
  doc: AIDocument; isMenuOpen: boolean;
  onOpenMenu: (id: string) => void; onSelect: () => void; onToggleStar: () => void; onDelete: () => void;
}) {
  const preview = (doc.content ?? "").replace(/[#*`>\-_]/g, "").trim().slice(0, 120);
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) : "";
  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.2 }}
      className="bg-background rounded-xl border border-border shadow-sm hover:shadow-md cursor-pointer transition-all flex flex-col h-56 group">
      <div onClick={onSelect} className="flex-1 p-4 overflow-hidden relative">
        <div className="absolute left-0 top-4 bottom-4 w-0.5 bg-primary/30 rounded-r-full" />
        <p className="text-xs text-muted-foreground leading-relaxed pl-3 line-clamp-4">{preview || "（空文档）"}</p>
      </div>
      <div className="px-4 py-3 border-t border-border bg-muted/50 rounded-b-xl">
        <h3 onClick={onSelect} className="font-semibold text-foreground text-sm line-clamp-1 mb-2 group-hover:text-primary transition-colors">
          {doc.title || "无标题"}
        </h3>
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">{updatedAt}</span>
          <div className="flex items-center gap-1 relative">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); onOpenMenu(doc.id); }}
            >
              <MoreHorizontal className="w-3.5 h-3.5" />
            </Button>
            {isMenuOpen && (
              <div className="absolute right-0 bottom-7 w-32 bg-background rounded-xl shadow-xl border border-border py-1.5 z-30"
                onClick={(e) => e.stopPropagation()}>
                <button type="button" onClick={onSelect} className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                  <PenLine className="w-3 h-3" /> 打开编辑
                </button>
                <div className="h-px bg-border my-1 mx-2" />
                <button type="button" onClick={onDelete} className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10">
                  <Trash2 className="w-3 h-3" /> 删除
                </button>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              className={cn("h-7 w-7", doc.is_starred ? "text-warning" : "text-muted-foreground hover:text-warning hover:bg-warning/10")}
              onClick={(e) => { e.stopPropagation(); onToggleStar(); }}
            >
              <Star className="w-3.5 h-3.5" fill={doc.is_starred ? "currentColor" : "none"} />
            </Button>
          </div>
        </div>
      </div>
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
              <Sparkles className="w-3.5 h-3.5" />AI 润色
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
            <motion.div initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: 320 }}
              exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.2 }}
              className="border-l border-border overflow-hidden shrink-0">
              <AIEditPanel onClose={() => setShowAI(false)}
                getSelectedText={() => editorRef.current?.getSelectedText() ?? ""}
                onResult={(text) => editorRef.current?.replaceSelection(text)} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── AI Edit Panel ────────────────────────────────────────────────────────────

const AI_OPS: { key: AIOperation; label: string; icon: React.ReactNode; desc: string }[] = [
  { key: "polish",     label: "润色",    icon: <Wand2 className="w-4 h-4" />,       desc: "改善表达，使文字更流畅专业" },
  { key: "expand",     label: "扩写",    icon: <BookOpen className="w-4 h-4" />,    desc: "丰富内容，补充细节和论据" },
  { key: "condense",   label: "缩写",    icon: <Scissors className="w-4 h-4" />,    desc: "精简内容，保留核心要点" },
  { key: "brainstorm", label: "头脑风暴", icon: <RefreshCw className="w-4 h-4" />,   desc: "基于内容生成相关想法" },
];

function AIEditPanel({ onClose, getSelectedText, onResult }: {
  onClose: () => void;
  getSelectedText: () => string;
  onResult: (text: string) => void;
}) {
  const [op, setOp] = useState<AIOperation>("polish");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");

  const handleRun = async () => {
    const text = getSelectedText();
    if (!text.trim()) { setError("请先在编辑器中选中要处理的文字"); return; }
    setRunning(true); setError(""); setResult("");
    try {
      const res = await docmgrApi.aiEdit({ text, operation: op });
      setResult(res.result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI 处理失败");
    } finally { setRunning(false); }
  };

  return (
    <div className="w-80 h-full flex flex-col bg-background">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">AI 助手</span>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="w-4 h-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">操作类型</p>
          {AI_OPS.map(({ key, label, icon, desc }) => (
            <button key={key} type="button" onClick={() => setOp(key)}
              className={cn("w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-all",
                op === key ? "border-primary/20 bg-primary/10" : "border-border hover:border-input hover:bg-muted")}>
              <span className={cn("mt-0.5 shrink-0", op === key ? "text-primary" : "text-muted-foreground")}>{icon}</span>
              <div>
                <p className={cn("text-sm font-medium", op === key ? "text-primary" : "text-foreground")}>{label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
              </div>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">在编辑器中选中文字，然后点击执行</p>
        {error && <div className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</div>}
        {result && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">AI 结果</p>
            <div className="text-sm text-foreground bg-muted border border-border rounded-xl p-3 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
              {result}
            </div>
            <Button onClick={() => { onResult(result); setResult(""); }} className="w-full">
              替换选中内容
            </Button>
          </div>
        )}
      </div>
      <div className="p-4 border-t border-border shrink-0">
        <Button onClick={handleRun} disabled={running} className="w-full">
          {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {running ? "处理中..." : "执行"}
        </Button>
      </div>
    </div>
  );
}
