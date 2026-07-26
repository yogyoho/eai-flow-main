"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft, ArrowUp, BookOpen, ChevronDown, ChevronRight, ChevronLeft, MousePointerClick,
  CheckCircle2, Copy, Download, FileText, LayoutGrid, List, Loader2, MoreHorizontal, PenLine, Plus,
  RefreshCw, Scissors, Search, FolderCheck, Star, Sparkles, Archive,
  Trash2, Wand2, X,
} from "lucide-react";
import dynamic from "next/dynamic";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useModels } from "@/core/models/hooks";
import { cn } from "@/lib/utils";


const CollabEditor = dynamic(() => import("../collab/CollabEditor").then((m) => m.CollabEditor), {
  ssr: false,
  loading: () => <div className="flex-1 flex items-center justify-center text-muted-foreground">加载编辑器...</div>,
});
import { docmgrApi } from "../api";
import type { CollabEditorRef } from "../collab/CollabEditor";
import type { AIDocument } from "../types";

import BatchActionBar from "./BatchActionBar";
import { ExportDocxDialog } from "./ExportDocxDialog";
import FilePreviewModal, { isImageFile, isTextFile, formatFileSize } from "./FilePreviewModal";
import FolderPickerDialog from "./FolderPickerDialog";
import { ProjectFolderTree } from "./ProjectFolderTree";
import ShareDialog from "./ShareDialog";
// ShareDialog retained for potential future use; share UI entry points removed below.
import DocAIAgentPanel from "./DocAIAgentPanel";
import PersonalBlockNoteEditor, { type PersonalBlockNoteEditorRef } from "./PersonalBlockNoteEditor";
import { useDocAIThread } from "./useDocAIThread";
import { useDocuments } from "./useDocuments";
import { usePersonalOutputs } from "./usePersonalOutputs";
import { useLicense } from "@/extensions/license/useLicense";

type AIOperation = "polish" | "expand" | "condense" | "chat";
type View = "list" | "editor";

/** Windows 风格黄色文件夹图标（资源管理器样式） */
function WindowsFolder({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z" fill="#E6A106" />
      <path d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-17c-1.1 0-2-.9-2-2v-8z" fill="#FFC83D" />
      <path d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2V11H1.5V9.5z" fill="#FFD86B" />
    </svg>
  );
}

/** 判断是否二进制文件（点击应直接下载而非进编辑器） */
function isBinaryFile(mime: string | undefined | null, name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  const textExts = new Set([
    "txt","md","markdown","py","js","mjs","cjs","ts","tsx","jsx","vue","svelte",
    "java","c","cpp","cc","h","hpp","go","rs","rb","php","swift","kt","scala",
    "sh","bash","zsh","fish","sql","html","htm","css","scss","sass","less",
    "json","yaml","yml","xml","svg","toml","ini","conf","cfg","csv","tsv","log","env",
  ]);
  if (mime) {
    if (mime.startsWith("text/")) return false;
    if (["application/json", "application/javascript", "application/xml",
         "application/x-yaml", "application/x-sh", "application/x-python",
         "image/svg+xml"].includes(mime)) return false;
  }
  if (!mime || mime === "application/octet-stream") {
    return !textExts.has(ext);
  }
  return true; // image/* · application/pdf · office · zip · ...
}

/** 代码文件扩展名 → 代码块语言（用于编辑器里 ```lang 包裹） */
function getLanguageFromName(name: string): string | null {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    py: "python", js: "javascript", mjs: "javascript", cjs: "javascript",
    ts: "typescript", tsx: "tsx", jsx: "jsx", vue: "vue", svelte: "svelte",
    java: "java", c: "c", cpp: "cpp", cc: "cpp", h: "c", hpp: "cpp",
    go: "go", rs: "rust", rb: "ruby", php: "php", swift: "swift", kt: "kotlin",
    sh: "bash", bash: "bash", zsh: "bash", sql: "sql",
    html: "html", htm: "html", css: "css", scss: "scss",
    json: "json", yaml: "yaml", yml: "yaml", xml: "xml", toml: "toml",
  };
  return map[ext] || null;
}

/** Windows 风格「打开的」黄色文件夹（展开态） */
function WindowsFolderOpen({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* 后片 */}
      <path d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z" fill="#E6A106" />
      {/* 内部（露出浅黄） */}
      <path d="M3 10.5h18l-1.2 7.2c-.15.9-.93 1.55-1.84 1.55H4.04c-.91 0-1.69-.65-1.84-1.55L3 10.5z" fill="#FFE082" />
      {/* 打开的前盖（翻开向右） */}
      <path d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.97 0 1.62.99 1.27 1.9l-.7 1.56H3z" fill="#FFC83D" />
      <path d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.2 0 .38.04.54.11L7.5 10.5H3z" fill="#FFD86B" />
    </svg>
  );
}

export default function DocumentManagement({ initialDocId }: { initialDocId?: string }) {
  const [view, setView] = useState<View>(initialDocId ? "editor" : "list");
  const [activeDocId, setActiveDocId] = useState<string | null>(initialDocId ?? null);
  const [activePersonalFile, setActivePersonalFile] = useState<{ thread_id: string; rel_path: string; title: string } | null>(null);
  const [activeNav, setActiveNav] = useState<"folder" | "file_ref_folder">("folder");
  const [currentFolder, setCurrentFolder] = useState("默认文件夹");
  const handleSelectDoc = (doc: AIDocument) => {
    // 二进制文件（PDF / Word / Excel / 图片 / 压缩包等）→ 直接下载，不进编辑器
    if (doc.source_thread_id && doc.file_ref_path && isBinaryFile(doc.file_mime, doc.title)) {
      downloadPersonalFile(doc.source_thread_id, doc.file_ref_path, doc.title);
      return;
    }
    // 个人文档（直接映射）：用 thread_id + rel_path 读 artifacts，不走 AIDocument id
    if (doc.source_thread_id && doc.file_ref_path && doc.id.includes("/")) {
      setActivePersonalFile({ thread_id: doc.source_thread_id, rel_path: doc.file_ref_path, title: doc.title });
      setActiveDocId(null);
    } else {
      setActiveDocId(doc.id);
      setActivePersonalFile(null);
    }
    setView("editor");
  };
  const handleBack = () => { setActiveDocId(null); setActivePersonalFile(null); setView("list"); };
  // 二进制文件直接下载（拉取 artifacts blob → 触发浏览器下载）
  const downloadPersonalFile = async (threadId: string, relPath: string, filename: string) => {
    try {
      const res = await fetch(`/api/threads/${threadId}/artifacts/mnt/user-data/outputs/${encodeURIComponent(relPath)}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("download failed", e);
    }
  };
  return (
    <div className="h-full flex overflow-hidden bg-background relative">
      {/* Always keep DocumentList mounted (CSS-hidden when editing) to preserve sidebar navigation state */}
      <div className={cn("h-full w-full flex overflow-hidden", view === "editor" && "hidden")}>
        <DocumentList onSelectDoc={handleSelectDoc} activeNav={activeNav} onNavChange={setActiveNav} currentFolder={currentFolder} onFolderChange={setCurrentFolder} />
      </div>
      {/* Editor slides in on top when active */}
      {view === "editor" && (activeDocId || activePersonalFile) && (
        <motion.div key={activeDocId || activePersonalFile?.rel_path} className="absolute inset-0 z-10 flex overflow-hidden"
          initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2 }}>
          <DocumentEditor docId={activeDocId} personalFile={activePersonalFile} onBack={handleBack} />
        </motion.div>
      )}
    </div>
  );
}

// ─── Document List ────────────────────────────────────────────────────────────

function DocumentList({ onSelectDoc, activeNav, onNavChange, currentFolder, onFolderChange, view = "list" }: {
  onSelectDoc: (doc: AIDocument) => void;
  activeNav: "folder" | "file_ref_folder";
  onNavChange: (nav: "folder" | "file_ref_folder") => void;
  currentFolder: string;
  onFolderChange: (folder: string) => void;
  view?: View;
}) {
  const [search, setSearch] = useState("");
  const [showNewModal, setShowNewModal] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(true);
  // 项目文件夹是 project 许可的子能力；未授权则隐藏整段（含 CollabEditor 入口）
  const { hasModule, isLoading: licenseLoading } = useLicense();
  const canUseProject = licenseLoading || hasModule("project");
  const [viewMode, setViewMode] = useState<"grid-icon" | "list">("grid-icon");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<{ x: number; y: number } | null>(null);
  const menuButtonRef = useRef<Record<string, HTMLButtonElement | null>>({});
  const debouncedSearch = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewDocState, setPreviewDocState] = useState<AIDocument | null>(null);
  // 分享功能已下线（保留 ShareDialog 组件以备后续）
  const showShareDialog = false;
  const shareDoc: AIDocument | null = null;
  const setShowShareDialog = (_: boolean) => {};
  const setShareDoc = (_: AIDocument | null) => {};
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [personalOpen, setPersonalOpen] = useState(true);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "starred">("all");
  const [sidebarWidth, setSidebarWidth] = useState(240);
  const sidebarDragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const handleSidebarDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    sidebarDragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
    const onMove = (ev: MouseEvent) => {
      if (!sidebarDragRef.current) return;
      const delta = ev.clientX - sidebarDragRef.current.startX;
      setSidebarWidth(Math.max(180, Math.min(480, sidebarDragRef.current.startWidth + delta)));
    };
    const onUp = () => {
      sidebarDragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [sidebarWidth]);
  const { docs, total, loading, page, pageSize, setPage, folders, projectFolders, createDoc, deleteDoc, toggleStar, setFilter, moveToFolder, batchDeleteDocs, renameDoc, folderTree } =
    useDocuments({ folder: currentFolder });
  // Personal outputs — direct filesystem view (replaces old personal folder tree)
  const personalOutputs = usePersonalOutputs();

  // Sync filter to match activeNav on mount (preserves nav state when returning from editor)
  const navSynced = useRef(false);
  useEffect(() => {
    if (navSynced.current) return;
    navSynced.current = true;
    if (activeNav === "file_ref_folder") setFilter({ project_scope: "project", folder: currentFolder });
    // Default: 全部个人文件，不限定 doc_type（document 与 file_ref 合并显示）
    else setFilter({ project_scope: "personal", folder: currentFolder });
  }, [activeNav, currentFolder, setFilter]);

  const handleSearch = (v: string) => {
    setSearch(v);
    clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(() => setFilter((f) => ({ ...f, q: v || undefined })), 400);
  };

  const handleFilterToggle = (mode: "all" | "starred") => {
    setFilterMode(mode);
    if (mode === "starred") setFilter((f) => ({ ...f, starred: true }));
    else setFilter((f) => ({ ...f, starred: undefined }));
  };

  const totalPages = Math.ceil(total / pageSize);

  const handleNavClick = (nav: typeof activeNav, folder?: string, folderId?: string | null) => {
    onNavChange(nav);
    setSelectedIds(new Set());
    if (nav === "folder") {
      const nextFolder = folder ?? "默认文件夹";
      onFolderChange(nextFolder);
      // 合并显示全部类型（document + file_ref），不再限定 doc_type
      setFilter({ project_scope: "personal", folder_id: folderId || undefined, q: search || undefined });
    } else if (nav === "file_ref_folder") {
      if (folder) onFolderChange(folder);
      setFilter({ project_scope: "project", folder, folder_id: folderId || undefined, q: search || undefined });
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

  const isFileRefView = activeNav === "file_ref_folder";

  // 选中线程后，主体区显示该线程文件（适配为 DocCard 期望的形状）
  const adaptPersonalFile = (file: any, thread: any) => ({
    id: `${thread.thread_id}/${file.rel_path}`,
    title: file.name,
    doc_type: "file_ref" as const,
    file_mime: file.mime,
    file_size: file.size,
    file_ref_path: file.rel_path,
    source_thread_id: thread.thread_id,
    updated_at: file.modified_at,
    is_starred: file.starred,
    is_shared: file.shared,
    content: null,
    folder: thread.display_name,
    status: "active",
  });
  // 从 personalOutputs.threads 派生当前选中线程 —— 单一数据源，
  // 这样 toggleStar 的乐观更新会同时反映到左侧列表和主体区域
  const selectedThread = personalOutputs.threads.find((t) => t.thread_id === selectedThreadId) || null;
  const displayDocs = selectedThread
    ? selectedThread.files
        .filter((f: any) => (filterMode === "all" ? true : f.starred))
        .map((f: any) => adaptPersonalFile(f, selectedThread))
    : docs;
  const displayTotal = selectedThread ? selectedThread.files.length : total;
  const displayLoading = !selectedThread && loading;

  // 全局搜索：跨所有线程搜文件名 / 线程名
  const isSearching = search.trim().length > 0;
  const searchResults = useMemo(() => {
    if (!isSearching) return [] as Array<{ file: any; thread_id: string; thread_name: string }>;
    const q = search.trim().toLowerCase();
    return personalOutputs.threads.flatMap(t =>
      t.files
        .filter(f => f.name.toLowerCase().includes(q) || t.display_name.toLowerCase().includes(q))
        .map(f => ({ file: f, thread_id: t.thread_id, thread_name: t.display_name })),
    );
  }, [isSearching, search, personalOutputs.threads]);

  const handlePersonalStar = (docId: string) => {
    if (!selectedThread) return;
    const file = selectedThread.files.find((f: any) => `${selectedThread.thread_id}/${f.rel_path}` === docId);
    if (file) personalOutputs.toggleStar(selectedThread.thread_id, file.rel_path, file.starred);
  };

  const handleCreate = async (title: string) => {
    const doc = await createDoc({ title, content: "", folder: currentFolder });
    setShowNewModal(false);
    onSelectDoc(doc);
  };

  const handleOpenMenu = (id: string) => {
    const btn = menuButtonRef.current[id];
    if (btn) {
      const rect = btn.getBoundingClientRect();
      const menuW = 128; // w-32
      const x = rect.right + menuW > window.innerWidth ? rect.left - menuW : rect.right;
      setMenuAnchor({ x, y: rect.top });
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
      <div className="border-r border-border flex flex-col shrink-0 bg-muted/50 relative" style={{ width: sidebarWidth }}>
        <div className="p-3.5 flex items-center gap-2 border-b border-border">
          <div className="p-1 border rounded-sm bg-blue-50 border-blue-200 text-blue-600 shrink-0">
            <FolderCheck className="w-4 h-4" />
          </div>
          <span className="font-semibold text-foreground text-l">文档空间</span>
        </div>
        <nav
          className="flex-1 overflow-y-auto px-2 py-1 space-y-1"
          onScroll={(e) => {
            const el = e.currentTarget;
            if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
              personalOutputs.fetchMore();
            }
          }}
        >
          {/* 我的文档 — 树形结构 */}
          <div>
            <button
              onClick={() => { setPersonalOpen((v) => !v); setSelectedThreadId(null); }}
              className={cn(
                "flex w-full items-center justify-between px-3 py-1.5 text-sm rounded-lg transition-colors",
                selectedThreadId === null
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <div className="flex items-center gap-2">
                {personalOpen
                  ? <WindowsFolderOpen className="w-4 h-4" />
                  : <WindowsFolder className="w-4 h-4" />}
                <span>我的文档</span>
                <span className="text-[10px] text-muted-foreground/60">共 {personalOutputs.total} 个</span>
              </div>
              {personalOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
            {personalOpen && (
              <div className="ml-2 space-y-0.5">
                {personalOutputs.threads.length === 0 && !personalOutputs.loading && (
                  <p className="text-xs text-muted-foreground px-3 py-1.5">暂无输出文件</p>
                )}
                {personalOutputs.loading && (
                  <p className="text-xs text-muted-foreground px-3 py-1.5">加载中...</p>
                )}
                {personalOutputs.threads.map((thread) => {
                  const isExpanded = personalOutputs.expandedKeys.has(thread.thread_id);
                  return (
                    <div key={thread.thread_id}>
                      <button
                        onClick={() => { personalOutputs.toggleExpand(thread.thread_id); setSelectedThreadId(thread.thread_id); setActiveFolderId(null); }}
                        className={cn(
                          "flex w-full items-center justify-between px-3 py-1.5 text-xs rounded-lg transition-colors",
                          selectedThreadId === thread.thread_id
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {isExpanded
                            ? <WindowsFolderOpen className="w-3.5 h-3.5 shrink-0" />
                            : <WindowsFolder className="w-3.5 h-3.5 shrink-0" />}
                          <span className="truncate">{thread.display_name}</span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[10px] text-muted-foreground/60">{thread.files.length} 个文件</span>
                          {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="ml-5 space-y-0.5">
                          {thread.files.map((file) => (
                            <div
                              key={file.rel_path}
                              className="flex items-center justify-between px-3 py-1 text-xs text-muted-foreground hover:bg-muted/50 rounded transition-colors"
                            >
                              <div className="flex items-center gap-1.5 min-w-0">
                                <FileText className="w-3 h-3 shrink-0 opacity-60" />
                                <span className="truncate">{file.name}</span>
                                <span className="text-[10px] text-muted-foreground/50 shrink-0">
                                  {file.size > 1024 ? `${(file.size / 1024).toFixed(1)} KB` : `${file.size} B`}
                                </span>
                              </div>
                              <button
                                onClick={(e) => { e.stopPropagation(); personalOutputs.toggleStar(thread.thread_id, file.rel_path, file.starred); }}
                                className="shrink-0 p-0.5 hover:text-amber-400 transition-colors"
                                title={file.starred ? "取消收藏" : "收藏"}
                              >
                                <Star className={cn("w-3 h-3", file.starred && "text-amber-400")} fill={file.starred ? "currentColor" : "none"} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {personalOutputs.loadingMore && (
                  <p className="text-xs text-muted-foreground px-3 py-1.5 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" /> 加载更多...
                  </p>
                )}
                {personalOutputs.hasMore && !personalOutputs.loadingMore && (
                  <p className="text-[10px] text-muted-foreground/50 px-3 py-1.5">↓ 滚动加载更多</p>
                )}
              </div>
            )}
          </div>
          {canUseProject && ( // 项目文件夹 - 树形结构
          <div className="pt-2 mt-2">
            <button
              onClick={() => setArchiveOpen((v) => !v)}
              className="flex w-full items-center justify-between px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
            >
              <div className="flex items-center gap-2">
                <Archive className="w-3.5 h-3.5" />
                <span>项目文件夹</span>
              </div>
              {archiveOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
            {archiveOpen && (
              <ProjectFolderTree
                folders={folderTree.folders}
                expandedKeys={folderTree.expandedKeys}
                onToggleExpand={folderTree.toggleExpand}
                onSelectFolder={(folderId, folderName) => {
                  setActiveFolderId(folderId);
                  handleNavClick("file_ref_folder", folderName, folderId);
                }}
                onCreateFolder={async (name, parentId, projectId) => { await folderTree.createFolder(name, parentId, projectId) }}
                onRenameFolder={folderTree.renameFolder}
                onDeleteFolder={folderTree.deleteFolder}
                activeFolderId={activeFolderId}
              />
            )}
          </div>
          )}
        </nav>
        <div
          onMouseDown={handleSidebarDragStart}
          className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-primary/40 active:bg-primary/60 transition-colors z-30"
          title="拖动调整宽度"
        />
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-14 flex items-center justify-between px-6 border-b border-border shrink-0 bg-background">
          <div className="flex items-center gap-3">
            {!isFileRefView && (
              <Button onClick={() => setShowNewModal(true)}>
                <Plus className="w-4 h-4" />新建文档
              </Button>
            )}
            <div className="flex items-center gap-0.5 bg-muted/60 rounded-md p-0.5">
              {(["all", "starred"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => handleFilterToggle(mode)}
                  className={cn(
                    "px-2.5 py-1 text-xs rounded-sm font-medium transition-colors",
                    filterMode === mode ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {mode === "all" ? "全部" : "收藏"}
                </button>
              ))}
            </div>
            <div className="relative w-60">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input type="text" value={search} onChange={(e) => handleSearch(e.target.value)} placeholder="搜索文档..."
                className="w-full pl-9 pr-4" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex h-[30px] items-center overflow-hidden rounded-[6px] border border-border bg-card">
              <button
                onClick={() => setViewMode("grid-icon")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "grid-icon" ? "text-foreground bg-muted" : "text-muted-foreground",
                )}
                title="图标网格"
              >
                <LayoutGrid className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "list" ? "text-foreground bg-muted" : "text-muted-foreground",
                )}
                title="列表"
              >
                <List className="h-3.5 w-3.5" />
              </button>
            </div>
            <span className="text-xs text-muted-foreground">共 {displayTotal} 篇文档</span>
          </div>
        </div>
        <div className={cn(
          "flex-1 p-6 bg-muted/30",
          displayDocs.length === 0 ? "flex flex-col items-center justify-center" : "overflow-y-auto"
        )}>
          {isSearching ? (
            <div className="overflow-y-auto h-full">
              <div className="max-w-5xl mx-auto">
                <div className="mb-5">
                  <h2 className="text-lg font-semibold text-foreground">搜索结果</h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    关键词 “<span className="text-foreground font-medium">{search.trim()}</span>” — 找到
                    <span className="text-primary font-medium mx-1">{searchResults.length}</span>个文件
                  </p>
                </div>
                {searchResults.length === 0 ? (
                  <div className="flex flex-col items-center text-center py-20 text-muted-foreground">
                    <Search className="w-12 h-12 mb-3 opacity-25" />
                    <p className="text-sm">未找到匹配的文件</p>
                    <p className="text-xs mt-1 opacity-70">试试其他关键词，或检查文件名</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {searchResults.map(({ file, thread_id, thread_name }) => {
                      const doc = adaptPersonalFile(file, { thread_id, display_name: thread_name });
                      return (
                        <div
                          key={`${thread_id}/${file.rel_path}`}
                          onClick={() => onSelectDoc(doc)}
                          className="group bg-background border border-border rounded-xl p-4 hover:border-primary/40 hover:shadow-md transition-all cursor-pointer"
                        >
                          <div className="flex items-start gap-3">
                            <div className="p-2 rounded-lg bg-blue-50 shrink-0">
                              <FileText className="w-4 h-4 text-blue-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-sm text-foreground truncate group-hover:text-primary transition-colors">
                                {file.name}
                              </div>
                              <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                                <WindowsFolder className="w-3 h-3 shrink-0" />
                                <span className="truncate">{thread_name}</span>
                              </div>
                              <div className="text-[10px] text-muted-foreground/60 mt-2">
                                {file.size > 1024 ? `${(file.size / 1024).toFixed(1)} KB` : `${file.size} B`}
                                {file.starred && <span className="ml-2 text-amber-500">★ 已收藏</span>}
                              </div>
                            </div>
                            <button
                              onClick={(e) => { e.stopPropagation(); personalOutputs.toggleStar(thread_id, file.rel_path, file.starred); }}
                              className={cn("p-1 rounded transition-colors shrink-0", file.starred ? "text-amber-400" : "text-muted-foreground/40 hover:text-amber-400")}
                              title={file.starred ? "取消收藏" : "收藏"}
                            >
                              <Star className="w-3.5 h-3.5" fill={file.starred ? "currentColor" : "none"} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : displayLoading ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">加载中...</div>
          ) : displayDocs.length === 0 ? (
            <div className="flex flex-col items-center text-center max-w-xs">
              <MousePointerClick className="w-10 h-10 text-muted-foreground/25 mb-4" />
              <p className="text-sm font-medium text-muted-foreground">点击左侧文件夹查看文档</p>
              <p className="text-xs text-muted-foreground/60 mt-1.5 leading-relaxed">{selectedThread ? "该线程暂无输出文件" : isFileRefView ? "选中项目文件夹后，同步的文件会出现在这里" : "在左侧选择一个文件夹，或通过 AI 对话生成新文档"}</p>
            </div>
          ) : viewMode === "grid-icon" ? (
            <AnimatePresence>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {displayDocs.map((doc) => (
                    <DocCard key={doc.id} doc={doc}
                      variant="icon"
                      isMenuOpen={openMenuId === doc.id}
                      onOpenMenu={handleOpenMenu}
                      menuButtonRef={(el) => { menuButtonRef.current[doc.id] = el; }}
                      onSelect={() => onSelectDoc(doc)}
                      onToggleStar={() => selectedThread ? handlePersonalStar(doc.id) : toggleStar(doc.id, doc.is_starred ?? false)}
                      onDelete={async () => { handleCloseMenu(); if (confirm("确认删除该文档？")) await deleteDoc(doc.id); }}
                      onShare={() => {}}
                      selected={selectedIds.has(doc.id)}
                      onToggleSelect={() => handleToggleSelect(doc.id)} />
                ))}
              </div>
            </AnimatePresence>
          ) : (
            <div className="bg-background border border-border rounded-xl shadow-sm overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">名称</th>
                    <th className="py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">类型</th>
                    <th className="py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">大小</th>
                    <th className="py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">更新时间</th>
                    <th className="py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {displayDocs.map((doc) => {
                    const isFileRef = doc.doc_type === "file_ref";
                    const fileSize = formatFileSize(doc.file_size);
                    const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "/") : "";
                    const handleClick = (e: React.MouseEvent) => {
                      if (e.ctrlKey || e.metaKey) { e.preventDefault(); handleToggleSelect(doc.id); }
                      else { onSelectDoc(doc); }
                    };
                    return (
                      <tr key={doc.id}
                        className={cn("hover:bg-muted/50 transition-colors group cursor-pointer", selectedIds.has(doc.id) && "bg-primary/5")}
                        onClick={handleClick}>
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-3 min-w-0">
                            {selectedIds.has(doc.id) ? (
                              <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
                            ) : isFileRef ? (
                              <FileTypeIcon mime={doc.file_mime} title={doc.title} docType={doc.doc_type} size="sm" />
                            ) : (
                              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                            )}
                            <span className="font-medium text-foreground truncate group-hover:text-primary transition-colors">
                              {doc.title || "无标题"}
                            </span>
                          </div>
                        </td>
                        <td className="py-4 px-3">
                          {(() => {
                            const fic = FILE_ICON_CONFIG[getFileType(doc.file_mime, doc.title, doc.doc_type)]!;
                            return (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                                style={{ backgroundColor: fic.primary + "18", color: fic.primary }}>
                                {fic.label}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="py-4 px-4 text-sm text-muted-foreground whitespace-nowrap">
                          {fileSize || "—"}
                        </td>
                        <td className="py-4 px-4 text-sm text-muted-foreground whitespace-nowrap">{updatedAt}</td>
                        <td className="py-4 px-4 text-right">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                              onClick={(e) => { e.stopPropagation(); selectedThread ? handlePersonalStar(doc.id) : toggleStar(doc.id, doc.is_starred ?? false); }}>
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
        {openMenuId && menuAnchor && (() => {
          const doc = displayDocs.find((d) => d.id === openMenuId);
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
              <div className="h-px bg-border my-1 mx-2" />
              <button type="button" onClick={async () => { handleCloseMenu(); if (confirm(`确认删除该${isFileRef ? "文件" : "文档"}？`)) await deleteDoc(doc.id); }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10">
                <Trash2 className="w-3 h-3" /> 删除
              </button>
            </div>
          );
        })()}
      </div>
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

function DocCard({ doc, variant = "auto", isMenuOpen, onOpenMenu, menuButtonRef, onSelect, onToggleStar, onDelete, onShare, selected, onToggleSelect }: {
  doc: AIDocument; variant?: "auto" | "icon" | "summary"; isMenuOpen: boolean;
  onOpenMenu: (id: string) => void; menuButtonRef: (el: HTMLButtonElement | null) => void;
  onSelect: () => void; onToggleStar: () => void; onDelete: () => void; onShare?: () => void;
  selected?: boolean; onToggleSelect?: () => void;
}) {
  const isFileRef = doc.doc_type === "file_ref";
  const rawPreview = (doc.content ?? "").replace(/[#*`>\-_]/g, "").trim();
  const preview = rawPreview.slice(0, 120);
  const showSummary = variant === "summary" ? !!preview : (variant === "auto" && !!preview);
  const updatedAt = doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "/") : "";
  const fileSize = isFileRef ? formatFileSize(doc.file_size) : "";

  // For file_ref without content, build a file-info preview line
  const fileInfoLine = isFileRef
    ? [getFileType(doc.file_mime, doc.title, doc.doc_type).toUpperCase(), fileSize].filter(Boolean).join(" · ")
    : "";

  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.2 }}
      className="bg-background rounded-xl border border-border p-4 cursor-pointer transition-all flex flex-col h-64 group hover:shadow-md hover:border-primary/50 relative"
      onClick={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); onToggleSelect?.(); } else { onSelect(); } }}>
      <div className="flex-1 mb-4 relative overflow-hidden">
        {showSummary ? (
          <div className="bg-muted/50 rounded-lg p-4 h-full border border-border relative overflow-hidden">
            <div className="absolute left-0 top-4 bottom-4 w-1 bg-purple-200 dark:bg-purple-500/50 rounded-r-full" />
            <p className="text-sm text-muted-foreground leading-relaxed pl-3 line-clamp-4">{preview}</p>
          </div>
        ) : (
          <div className="bg-muted/50 rounded-lg h-full border border-border relative overflow-hidden flex flex-col items-center justify-center gap-2">
            <FileTypeIcon mime={doc.file_mime} title={doc.title} docType={doc.doc_type} size="lg" />
            {fileInfoLine && <span className="text-xs text-muted-foreground">{fileInfoLine}</span>}
          </div>
        )}
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

function getFileType(mime: string | undefined | null, title: string | undefined | null, docType?: string | null): string {
  if (!mime && title) {
    const ext = title.split(".").pop()?.toLowerCase() || "";
    const extMap: Record<string, string> = {
      md: "markdown", py: "python", js: "javascript", ts: "typescript",
      json: "json", html: "html", css: "css", pdf: "pdf",
      doc: "word", docx: "word", xls: "excel", xlsx: "excel",
      csv: "csv", xml: "xml", yml: "yaml", yaml: "yaml", sh: "shell", txt: "text",
    };
    return extMap[ext] || (docType === "document" ? "markdown" : "text");
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
  return docType === "document" ? "markdown" : "text";
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

function FileTypeIcon({ mime, title, docType, size = "lg" }: { mime?: string | null; title?: string | null; docType?: string | null; size?: "sm" | "lg" }) {
  const fileType = getFileType(mime, title, docType);
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
          <FileTypeIcon mime={doc.file_mime} title={doc.title} docType={doc.doc_type} size="lg" />
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

function DocumentEditor({ docId, personalFile, onBack }: { docId: string | null; personalFile: { thread_id: string; rel_path: string; title: string } | null; onBack: () => void }) {
  const [doc, setDoc] = useState<AIDocument | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [showAI, setShowAI] = useState(false);
  const [aiPanelKey, setAiPanelKey] = useState(0);
  const [panelWidth, setPanelWidth] = useState(420);
  const resizingRef = useRef(false);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [exportContent, setExportContent] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const editorRef = useRef<PersonalBlockNoteEditorRef | CollabEditorRef>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const titleRef = useRef(title);
  titleRef.current = title;

  // AI sub-thread persisted at editor level — survives panel close/reopen
  const aiThreadId = personalFile?.thread_id ?? docId ?? "default";
  const { subThreadId, ensureThread, isCreating, resetThread } = useDocAIThread(aiThreadId);

  useEffect(() => {
    setLoading(true);
    // 个人文档：直接读线程 outputs/ 文件内容（artifacts API）
    if (personalFile) {
      const artifactPath = `mnt/user-data/outputs/${personalFile.rel_path}`;
      fetch(`/api/threads/${personalFile.thread_id}/artifacts/${artifactPath}`)
        .then((r) => r.text())
        .then((content) => {
          // 代码文件用代码块包裹（在 markdown 编辑器里有语法高亮 + 等宽显示）
          const lang = getLanguageFromName(personalFile.title);
          const displayContent = lang ? "```" + lang + "\n" + content + "\n```" : content;
          setDoc({ id: "personal", title: personalFile.title, content: displayContent, doc_type: "file_ref" } as AIDocument);
          setTitle(personalFile.title);
          setLoading(false);
        })
        .catch(() => setLoading(false));
      return;
    }
    if (!docId) { setLoading(false); return; }
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
  }, [docId, personalFile]);

  const scheduleSave = useCallback((content: string) => {
    setSaved(false);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      setSaving(true);
      try {
        if (personalFile) {
          // 代码文件在编辑器里被 ```lang 包裹，保存时去掉 fence 写回原始内容
          let saveContent = content;
          if (getLanguageFromName(personalFile.title)) {
            const m = content.match(/^```[^\n]*\n([\s\S]*)\n```\s*$/);
            if (m) saveContent = m[1];
          }
          await docmgrApi.savePersonalContent(personalFile.thread_id, { rel_path: personalFile.rel_path, content: saveContent });
        } else if (docId) {
          await docmgrApi.update(docId, { title: titleRef.current, content });
        }
        setSaved(true);
        setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
      } finally { setSaving(false); }
    }, 1500);
  }, [docId, personalFile]);

  const handleTitleBlur = async () => {
    if (!doc || title === doc.title || personalFile) return;
    if (!docId) return;
    setSaving(true);
    try {
      const content = (await editorRef.current?.getMarkdown()) ?? doc.content ?? "";
      await docmgrApi.update(docId, { title, content });
      setSaved(true);
      setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
    } finally { setSaving(false); }
  };

  const handleExport = async (fmt: "md" | "docx") => {
    if (fmt === "docx") {
      // ponytail: capture live editor markdown so personal/thread files (docId=null)
      // can export via the content-based endpoint.
      setExportContent((await editorRef.current?.getMarkdown()) ?? doc?.content ?? "");
      setShowExportDialog(true);
      return;
    }
    // 个人文档：直接用已读 content 下载
    if (personalFile || !docId) {
      const blob = new Blob([doc?.content ?? ""], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${title}.${fmt}`; a.click();
      URL.revokeObjectURL(url);
      return;
    }
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
              AI 助手
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={async () => { const md = (await editorRef.current?.getMarkdown()) ?? ""; navigator.clipboard.writeText(md); }}
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
                projectId={doc.project_id}
                onChange={scheduleSave}
                className="flex-1"
              />
            ) : (
              <PersonalBlockNoteEditor
                ref={editorRef as React.Ref<PersonalBlockNoteEditorRef>}
                initialContent={doc.content ?? ""}
                onChange={scheduleSave}
                className="flex-1"
                hideSideMenu={!!getLanguageFromName(personalFile?.title ?? doc?.title ?? "")}
              />
            )
          )}
        </div>
        <AnimatePresence>
          {showAI && (() => {
            const aiDocTitle = personalFile?.title ?? title ?? "untitled";
            const aiRelPath = personalFile?.rel_path ?? `${aiDocTitle}.md`;
            return (
            <>
            {/* Resize handle */}
            <div
              className="w-1.5 hover:w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors shrink-0 relative group"
              onMouseDown={(e) => {
                e.preventDefault();
                resizingRef.current = true;
                const startX = e.clientX;
                const startWidth = panelWidth;
                const onMove = (ev: MouseEvent) => {
                  const delta = startX - ev.clientX;
                  setPanelWidth(Math.max(280, Math.min(800, startWidth + delta)));
                };
                const onUp = () => {
                  resizingRef.current = false;
                  document.removeEventListener("mousemove", onMove);
                  document.removeEventListener("mouseup", onUp);
                  document.body.style.cursor = "";
                  document.body.style.userSelect = "";
                };
                document.body.style.cursor = "col-resize";
                document.body.style.userSelect = "none";
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
              }}
            >
              <div className="absolute inset-y-0 -left-1 -right-1" />
            </div>
            <motion.div initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: panelWidth }}
              exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.2 }}
              className="border-l border-border overflow-hidden shrink-0">
              <DocAIAgentPanel
                key={aiPanelKey}
                docTitle={aiDocTitle}
                docRelPath={aiRelPath}
                threadId={aiThreadId}
                editorRef={editorRef as React.RefObject<PersonalBlockNoteEditorRef | null>}
                onClose={() => setShowAI(false)}
                subThreadId={subThreadId}
                ensureThread={ensureThread}
                isCreating={isCreating}
                resetThread={resetThread}
                onClearHistory={() => setAiPanelKey((k) => k + 1)}
              />
            </motion.div>
            </>
            );
          })()}
        </AnimatePresence>
      </div>
      <ExportDocxDialog docId={docId} docTitle={title} content={exportContent} open={showExportDialog} onOpenChange={setShowExportDialog} />
    </div>
  );
}

// ─── AI Edit Panel ────────────────────────────────────────────────────────────

const AI_OPS: { key: AIOperation; label: string; icon: React.ReactNode }[] = [
  { key: "polish",     label: "润色",    icon: <Wand2 className="w-3 h-3" /> },
  { key: "expand",     label: "扩写",    icon: <BookOpen className="w-3 h-3" /> },
  { key: "condense",   label: "缩写",    icon: <Scissors className="w-3 h-3" /> },
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

function AIEditPanel({ docKey, onClose, getSelectedText, getFullText, getCursorParagraph, onResult, onInsert, onHighlightSelection, onClearHighlight }: {
  docKey: string;
  onClose: () => void;
  getSelectedText: () => string;
  getFullText: () => string;
  getCursorParagraph: () => string;
  onResult: (text: string) => void;
  onInsert: (text: string) => void;
  onHighlightSelection: () => void;
  onClearHighlight: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // 对话持久化缓存：按 docKey 缓存最近 50 条消息
  const chatCache = useRef<Map<string, ChatMessage[]>>(new Map());
  const prevDocKey = useRef<string>(docKey);

  // 切换文档时保存/恢复对话
  if (prevDocKey.current !== docKey) {
    // 保存当前对话
    if (messages.length > 0) {
      chatCache.current.set(prevDocKey.current, messages.slice(-50));
    }
    // 恢复目标文档对话（或空数组）
    setMessages(chatCache.current.get(docKey) ?? []);
    prevDocKey.current = docKey;
  }

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
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

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
    const capturedDocKey = docKey;
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: displayContent ?? text, operation };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    resetInputHeight();
    setRunning(true);
    scrollToBottom();

    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", content: "" };
    setMessages((prev) => [...prev, assistantMsg]);

    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      await docmgrApi.aiEditStream(
        { text, operation: operation ?? activeOp, model_name: modelName ?? undefined },
        (token) => {
          if (capturedDocKey !== docKey) return;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m)),
          );
          scrollToBottom();
        },
        abortController.signal,
      );
    } catch (e) {
      if (capturedDocKey !== docKey) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `⚠️ ${e instanceof Error ? e.message : "AI 处理失败"}` }
            : m,
        ),
      );
    } finally {
      if (abortRef.current === abortController) abortRef.current = null;
      setRunning(false);
      scrollToBottom();
    }
  };

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || running) return;
    const selected = getSelectedText();
    if (selected.trim()) onHighlightSelection(); else onClearHighlight();
    const text = selected.trim() ? `${trimmed}\n\n【选中文字】：\n${selected}` : trimmed;
    void sendMessage(text, "chat");
  };

  const handleQuickAction = (op: AIOperation) => {
    if (running) return;
    setActiveOp(op);
    const selected = getSelectedText();
    if (selected.trim()) {
      onHighlightSelection();
      void sendMessage(selected, op);
    } else {
      onClearHighlight();
      // 无选中时：作用于光标所在段落（无则退回全文）
      const actionText = getCursorParagraph() || getFullText();
      if (!actionText.trim()) return;
      void sendMessage(actionText, op);
    }
  };

  const handleSuggestedPrompt = (prompt: string) => {
    const selected = getSelectedText();
    if (selected.trim()) onHighlightSelection(); else onClearHighlight();
    const fullText = getFullText();
    const apiText = selected.trim()
      ? `${prompt}\n\n【选中文字】：\n${selected}`
      : `${prompt}\n\n【文档全文】：\n${fullText}`;
    void sendMessage(apiText, "chat", prompt);
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
      <div className="px-4 py-2 border-b border-border/60 shrink-0">
        <div className="flex gap-1.5 flex-wrap">
          {AI_OPS.map(({ key, label, icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => handleQuickAction(key)}
              className={cn(
                "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[13px] font-medium transition-all border",
                activeOp === key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {icon}{label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {hasSelection ? "将对选中文字执行操作" : "将对全文执行操作（可选中文字后精确操作）"}
        </p>
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
                  <div className="bg-blue-50 border border-blue-200 text-slate-800 px-3 py-2 rounded-2xl rounded-br-sm max-w-[85%] text-xs leading-relaxed">
                    {msg.operation && msg.operation !== "chat" && (
                      <div className="text-[10px] opacity-70 mb-1">{AI_OPS.find((o) => o.key === msg.operation)?.label}</div>
                    )}
                    {msg.content}
                  </div>
                </div>
              ) : (
                /* Assistant message */
                <div key={msg.id}>
                  <div className="bg-muted border border-border rounded-2xl rounded-bl-sm px-3 py-2.5 text-xs leading-relaxed text-foreground prose prose-xs prose-neutral max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_strong]:text-foreground [&_code]:text-primary [&_pre]:bg-background [&_pre]:rounded-lg [&_pre]:p-2 [&_blockquote]:border-primary [&_blockquote]:pl-2.5">
                    {msg.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-muted-foreground/70 italic">
                        <Loader2 className="w-3 h-3 animate-spin" />正在思考...
                      </span>
                    )}
                  </div>
                  {msg.content.trim() && !msg.content.startsWith("⚠️") && (
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
                        onClick={() => onInsert(msg.content)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors"
                      >
                        <Plus className="w-3 h-3" />插入
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
            onFocus={() => { if (getSelectedText().trim()) onHighlightSelection(); else onClearHighlight(); }}
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
