"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  MousePointerClick,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  MoreHorizontal,
  PenLine,
  Plus,
  Search,
  FolderCheck,
  Star,
  FolderSync,
  AlertCircle,
  Trash2,
  X,
  Undo2,
  Redo2,
  Maximize,
  Minimize,
  ChevronUp,
  History,
} from "lucide-react";
import dynamic from "next/dynamic";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLicense } from "@/extensions/license/useLicense";
import { cn } from "@/lib/utils";

const CollabEditor = dynamic(
  () => import("../collab/CollabEditor").then((m) => m.CollabEditor),
  {
    ssr: false,
    loading: () => (
      <div className="text-muted-foreground flex flex-1 items-center justify-center">
        加载编辑器...
      </div>
    ),
  },
);
import { docmgrApi, type FolderNode } from "../api";
import type { CollabEditorRef } from "../collab/CollabEditor";
import type { AIDocument } from "../types";

import BatchActionBar from "./BatchActionBar";
import DocAIAgentPanel from "./DocAIAgentPanel";
import { ExportDocxDialog } from "./ExportDocxDialog";
import FilePreviewModal, { formatFileSize } from "./FilePreviewModal";
import FolderPickerDialog from "./FolderPickerDialog";
import PersonalBlockNoteEditor, {
  type PersonalBlockNoteEditorRef,
} from "./PersonalBlockNoteEditor";
import { ProjectFolderTree } from "./ProjectFolderTree";
import { useDocAIThread } from "./useDocAIThread";
import { useDocuments } from "./useDocuments";
import {
  usePersonalOutputs,
  type PersonalDocFile,
  type PersonalThreadOutput,
} from "./usePersonalOutputs";
import { useProjectOutputs, type ProjectDocFile } from "./useProjectOutputs";
import { computeDocStats } from "./utils/docEditorUtils";
import { VersionHistoryDialog } from "./VersionHistoryDialog";

type View = "list" | "editor";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** Windows 风格黄色文件夹图标（资源管理器样式） */
function WindowsFolder({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z"
        fill="#E6A106"
      />
      <path
        d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-17c-1.1 0-2-.9-2-2v-8z"
        fill="#FFC83D"
      />
      <path
        d="M1.5 9.5C1.5 8.4 2.4 7.5 3.5 7.5h17c1.1 0 2 .9 2 2V11H1.5V9.5z"
        fill="#FFD86B"
      />
    </svg>
  );
}

/** 判断是否二进制文件（点击应直接下载而非进编辑器） */
function isBinaryFile(mime: string | undefined | null, name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const textExts = new Set([
    "txt",
    "md",
    "markdown",
    "py",
    "js",
    "mjs",
    "cjs",
    "ts",
    "tsx",
    "jsx",
    "vue",
    "svelte",
    "java",
    "c",
    "cpp",
    "cc",
    "h",
    "hpp",
    "go",
    "rs",
    "rb",
    "php",
    "swift",
    "kt",
    "scala",
    "sh",
    "bash",
    "zsh",
    "fish",
    "sql",
    "html",
    "htm",
    "css",
    "scss",
    "sass",
    "less",
    "json",
    "yaml",
    "yml",
    "xml",
    "svg",
    "toml",
    "ini",
    "conf",
    "cfg",
    "csv",
    "tsv",
    "log",
    "env",
  ]);
  if (mime) {
    if (mime.startsWith("text/")) return false;
    if (
      [
        "application/json",
        "application/javascript",
        "application/xml",
        "application/x-yaml",
        "application/x-sh",
        "application/x-python",
        "image/svg+xml",
      ].includes(mime)
    )
      return false;
  }
  if (!mime || mime === "application/octet-stream") {
    return !textExts.has(ext);
  }
  return true; // image/* · application/pdf · office · zip · ...
}

/** 代码文件扩展名 → 代码块语言（用于编辑器里 ```lang 包裹） */
function getLanguageFromName(name: string): string | null {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    py: "python",
    js: "javascript",
    mjs: "javascript",
    cjs: "javascript",
    ts: "typescript",
    tsx: "tsx",
    jsx: "jsx",
    vue: "vue",
    svelte: "svelte",
    java: "java",
    c: "c",
    cpp: "cpp",
    cc: "cpp",
    h: "c",
    hpp: "cpp",
    go: "go",
    rs: "rust",
    rb: "ruby",
    php: "php",
    swift: "swift",
    kt: "kotlin",
    sh: "bash",
    bash: "bash",
    zsh: "bash",
    sql: "sql",
    html: "html",
    htm: "html",
    css: "css",
    scss: "scss",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    xml: "xml",
    toml: "toml",
  };
  return map[ext] ?? null;
}

/** Windows 风格「打开的」黄色文件夹（展开态） */
function WindowsFolderOpen({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* 后片 */}
      <path
        d="M1.5 6.5C1.5 5.4 2.4 4.5 3.5 4.5h4.7c.6 0 1.2.25 1.62.69L11.06 6.5H18.5c1.1 0 2 .9 2 2V10H3.5C2.4 10 1.5 9.1 1.5 8V6.5z"
        fill="#E6A106"
      />
      {/* 内部（露出浅黄） */}
      <path
        d="M3 10.5h18l-1.2 7.2c-.15.9-.93 1.55-1.84 1.55H4.04c-.91 0-1.69-.65-1.84-1.55L3 10.5z"
        fill="#FFE082"
      />
      {/* 打开的前盖（翻开向右） */}
      <path
        d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.97 0 1.62.99 1.27 1.9l-.7 1.56H3z"
        fill="#FFC83D"
      />
      <path
        d="M3 10.5l2.5-2.8c.38-.42.92-.66 1.48-.66h13.6c.2 0 .38.04.54.11L7.5 10.5H3z"
        fill="#FFD86B"
      />
    </svg>
  );
}

// EAI-CUSTOM: 项目区 outputs 文件系统视图——项目文件 = outputs 直读（跨用户共享），替代旧 file_ref 文件夹树
export type ProjectFileRef = {
  project_id: string;
  thread_id: string;
  rel_path: string;
  title: string;
  member: string;
};

export default function DocumentManagement({
  initialDocId,
}: {
  initialDocId?: string;
}) {
  const [view, setView] = useState<View>(initialDocId ? "editor" : "list");
  const [activeDocId, setActiveDocId] = useState<string | null>(
    initialDocId ?? null,
  );
  const [activePersonalFile, setActivePersonalFile] = useState<{
    thread_id: string;
    rel_path: string;
    title: string;
  } | null>(null);
  const [activeProjectFile, setActiveProjectFile] =
    useState<ProjectFileRef | null>(null);
  // 项目文件夹树导航：folder=个人，file_ref_folder=项目文件夹
  const [activeNav, setActiveNav] = useState<"folder" | "file_ref_folder">(
    "folder",
  );
  const [currentFolder, setCurrentFolder] = useState("默认文件夹");
  const handleSelectDoc = (doc: AIDocument) => {
    // 二进制文件（PDF / Word / Excel / 图片 / 压缩包等）→ 直接下载，不进编辑器
    if (
      doc.source_thread_id &&
      doc.file_ref_path &&
      isBinaryFile(doc.file_mime, doc.title)
    ) {
      void downloadPersonalFile(
        doc.source_thread_id,
        doc.file_ref_path,
        doc.title,
      );
      return;
    }
    // EAI-CUSTOM (bug-1145 根因⑤ 协同诉求): 仅 proj/ 虚拟文件（无 AIDocument 行、bash cp 落盘）
    // 走跨用户单人直读/写磁盘（readProjectOutput/saveProjectContent）——它没有 AIDocument.id，
    // 连不了 Hocuspocus 协同 store（collab-server canAccessDocument 查 ai_documents WHERE id）。
    // 已 present_files 同步成 AIDocument 的 file_ref（有真实 id + project_id）落到下方 docId
    // 分支 → CollabEditor 协同：collab-server loadMarkdownForDoc 首次从磁盘 seed，之后 collab_documents 为真。
    if (
      doc.id.startsWith("proj/") &&
      doc.project_id &&
      doc.source_thread_id &&
      doc.file_ref_path
    ) {
      handleSelectProjectFile({
        project_id: doc.project_id,
        thread_id: doc.source_thread_id,
        rel_path: doc.file_ref_path,
        title: doc.title,
        member: "",
      });
      return;
    }
    // 个人文档（直接映射）：用 thread_id + rel_path 读 artifacts，不走 AIDocument id
    if (doc.source_thread_id && doc.file_ref_path && doc.id.includes("/")) {
      setActivePersonalFile({
        thread_id: doc.source_thread_id,
        rel_path: doc.file_ref_path,
        title: doc.title,
      });
      setActiveDocId(null);
    } else {
      setActiveDocId(doc.id);
      setActivePersonalFile(null);
    }
    setView("editor");
  };
  const handleSelectProjectFile = (f: ProjectFileRef) => {
    setActiveProjectFile(f);
    setActiveDocId(null);
    setActivePersonalFile(null);
    setView("editor");
  };
  const handleBack = () => {
    setActiveDocId(null);
    setActivePersonalFile(null);
    setActiveProjectFile(null);
    setView("list");
  };
  // 二进制文件直接下载（拉取 artifacts blob → 触发浏览器下载）
  const downloadPersonalFile = async (
    threadId: string,
    relPath: string,
    filename: string,
  ) => {
    try {
      const res = await fetch(
        `/api/threads/${threadId}/artifacts/mnt/user-data/outputs/${encodeURIComponent(relPath)}`,
      );
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
    <div className="bg-background relative flex h-full overflow-hidden">
      {/* Always keep DocumentList mounted (CSS-hidden when editing) to preserve sidebar navigation state */}
      <div
        className={cn(
          "flex h-full w-full overflow-hidden",
          view === "editor" && "hidden",
        )}
      >
        <DocumentList
          onSelectDoc={handleSelectDoc}
          activeNav={activeNav}
          onNavChange={setActiveNav}
          currentFolder={currentFolder}
          onFolderChange={setCurrentFolder}
        />
      </div>
      {/* Editor slides in on top when active */}
      {view === "editor" &&
        (activeDocId ?? activePersonalFile ?? activeProjectFile) && (
          <motion.div
            key={
              activeDocId ??
              activePersonalFile?.rel_path ??
              activeProjectFile?.rel_path
            }
            className="absolute inset-0 z-10 flex overflow-hidden"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
          >
            <DocumentEditor
              docId={activeDocId}
              personalFile={activePersonalFile}
              projectFile={activeProjectFile}
              onBack={handleBack}
            />
          </motion.div>
        )}
    </div>
  );
}

// ─── Document List ────────────────────────────────────────────────────────────

function DocumentList({
  onSelectDoc,
  activeNav,
  onNavChange,
  currentFolder,
  onFolderChange,
}: {
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
  const [menuAnchor, setMenuAnchor] = useState<{ x: number; y: number } | null>(
    null,
  );
  const menuButtonRef = useRef<Record<string, HTMLButtonElement | null>>({});
  const debouncedSearch = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewDocState, setPreviewDocState] = useState<AIDocument | null>(
    null,
  );
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [personalOpen, setPersonalOpen] = useState(true);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "starred">("all");
  const [sidebarWidth, setSidebarWidth] = useState(240);
  const sidebarDragRef = useRef<{ startX: number; startWidth: number } | null>(
    null,
  );
  const handleSidebarDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      sidebarDragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
      const onMove = (ev: MouseEvent) => {
        if (!sidebarDragRef.current) return;
        const delta = ev.clientX - sidebarDragRef.current.startX;
        setSidebarWidth(
          Math.max(
            180,
            Math.min(480, sidebarDragRef.current.startWidth + delta),
          ),
        );
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
    },
    [sidebarWidth],
  );
  const {
    docs,
    total,
    loading,
    page,
    pageSize,
    setPage,
    folders,
    folderTree,
    createDoc,
    deleteDoc,
    toggleStar,
    setFilter,
    moveToFolder,
    batchDeleteDocs,
  } = useDocuments({ folder: currentFolder });
  // Personal outputs — direct filesystem view (replaces old personal folder tree)
  const personalOutputs = usePersonalOutputs();

  // EAI-CUSTOM (bug-2231): 首窗非空文件夹不足以撑满容器时没有滚动事件，
  // onScroll 永不触发 → 懒加载死区（提示可见但后续窗口拉不出来）。
  // 数据/加载态变化后容器仍未溢出且 has_more=true 则自动续拉，直到溢出（交给 onScroll）或加载完。
  const personalNavRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = personalNavRef.current;
    if (!el || !personalOpen) return;
    if (
      !personalOutputs.hasMore ||
      personalOutputs.loading ||
      personalOutputs.loadingMore ||
      personalOutputs.threads.length === 0
    )
      return;
    if (el.scrollHeight <= el.clientHeight) void personalOutputs.fetchMore();
    // 成员级依赖即可（整个对象每次渲染都是新建的，进了 deps 会导致 effect 逐渲染重跑）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    personalOpen,
    personalOutputs.hasMore,
    personalOutputs.loading,
    personalOutputs.loadingMore,
    personalOutputs.threads.length,
    personalOutputs.fetchMore,
  ]);

  // Sync filter to match activeNav on mount (preserves nav state when returning from editor)
  const navSynced = useRef(false);
  useEffect(() => {
    if (navSynced.current) return;
    navSynced.current = true;
    if (activeNav === "file_ref_folder")
      setFilter({ project_scope: "project", folder: currentFolder });
    // Default: 全部个人文件，不限定 doc_type（document 与 file_ref 合并显示）
    else setFilter({ project_scope: "personal", folder: currentFolder });
  }, [activeNav, currentFolder, setFilter]);

  const handleSearch = (v: string) => {
    setSearch(v);
    clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(
      () => setFilter((f) => ({ ...f, q: v || undefined })),
      400,
    );
  };

  const handleFilterToggle = (mode: "all" | "starred") => {
    setFilterMode(mode);
    if (mode === "starred") setFilter((f) => ({ ...f, starred: true }));
    else setFilter((f) => ({ ...f, starred: undefined }));
  };

  const totalPages = Math.ceil(total / pageSize);

  const handleNavClick = (
    nav: typeof activeNav,
    folder?: string,
    folderId?: string | null,
  ) => {
    onNavChange(nav);
    setSelectedIds(new Set());
    if (nav === "folder") {
      const nextFolder = folder ?? "默认文件夹";
      onFolderChange(nextFolder);
      // 合并显示全部类型（document + file_ref），不再限定 doc_type
      setFilter({
        project_scope: "personal",
        folder_id: folderId ?? undefined,
        q: search || undefined,
      });
    } else if (nav === "file_ref_folder") {
      if (folder) onFolderChange(folder);
      // EAI-CUSTOM: 只用 folder_id 过滤——doc.folder 字符串是 finalize.py 硬编码的「项目文件夹」，
      // 与文件夹行名不一致，同时传 folder+ folder_id 会被后端 AND 掉导致空列表。
      setFilter({
        project_scope: "project",
        folder_id: folderId ?? undefined,
        q: search || undefined,
      });
    }
  };

  const handleToggleSelect = (id: string) => {
    if (id.startsWith("proj/")) return; // EAI-CUSTOM (bug-1145 根因④): 虚拟 outputs 文件无 AIDocument 行，不可选中/批操作
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
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

  // EAI-CUSTOM (bug-3109 v4 WP-1.4): 多册合并导出——选中文档依序合并单 docx,
  // 册间分页; 后端整单失败语义(任一册解析失败 → 错误指认册名, 不落部分文件)。
  const [mergeExporting, setMergeExporting] = useState(false);
  const handleMergeExport = async () => {
    if (selectedIds.size < 2) {
      alert("合并导出请先勾选至少 2 个文档");
      return;
    }
    setMergeExporting(true);
    try {
      const sections: { filename: string; content: string }[] = [];
      for (const id of selectedIds) {
        const title = docs.find((d) => d.id === id)?.title ?? id;
        const res = await docmgrApi.export(id, "md");
        sections.push({ filename: `${title}.md`, content: await res.text() });
      }
      const blob = await docmgrApi.exportMerged(sections, {
        filename: "合并导出.docx",
        with_toc: true,
        toc_depth: 3,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "合并导出.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "合并导出失败");
    } finally {
      setMergeExporting(false);
    }
  };

  const isFileRefView = activeNav === "file_ref_folder";

  // 选中线程后，主体区显示该线程文件（适配为 DocCard 期望的形状）
  const adaptPersonalFile = (
    file: PersonalDocFile & { user_id?: string; created_at?: string },
    thread: Pick<PersonalThreadOutput, "thread_id" | "display_name">,
  ) => ({
    id: `${thread.thread_id}/${file.rel_path}`,
    title: file.name,
    doc_type: "file_ref" as const,
    file_mime: file.mime,
    file_size: file.size,
    file_ref_path: file.rel_path,
    source_thread_id: thread.thread_id,
    updated_at: file.modified_at,
    user_id: file.user_id ?? "",
    created_at: file.created_at ?? file.modified_at ?? "",
    is_starred: file.starred,
    is_shared: file.shared,
    content: undefined,
    folder: thread.display_name,
    status: "active",
  });
  // EAI-CUSTOM (bug-1145 根因④): 项目 outputs 文件 → DocCard 形状。关键：带 project_id +
  // source_thread_id + file_ref_path，点击时 handleSelectDoc 自动路由到 handleSelectProjectFile
  // → DocumentEditor 跨用户直读/写（readProjectOutput/saveProjectContent）。id 用 proj/ 前缀，
  // 供 star/delete/select 守卫识别这类「无 AIDocument 行」的虚拟文件。
  const adaptProjectOutput = (
    pf: ProjectDocFile,
    projectId: string,
  ): AIDocument => ({
    id: `proj/${projectId}/${pf.thread_id}/${pf.rel_path}`,
    title: pf.name,
    doc_type: "file_ref",
    file_mime: pf.mime,
    file_size: pf.size,
    file_ref_path: pf.rel_path,
    source_thread_id: pf.thread_id,
    project_id: projectId,
    updated_at: pf.modified_at,
    user_id: "",
    created_at: pf.modified_at,
    is_starred: false,
    is_shared: true,
    content: undefined,
    folder: pf.member ?? "",
    status: "active",
  });
  // 从 personalOutputs.threads 派生当前选中线程 —— 单一数据源，
  // 这样 toggleStar 的乐观更新会同时反映到左侧列表和主体区域
  const selectedThread =
    personalOutputs.threads.find((t) => t.thread_id === selectedThreadId) ??
    null;

  // EAI-CUSTOM (bug-1145 根因④): 项目根文件夹视图聚合 outputs 文件系统视图——
  // 把 agent 未走 present_files（如 bash cp）落盘到 thread outputs/ 的文件也显示出来。
  // 仅在选中「项目根文件夹」(parent_id===null) 时聚合；outputs 是扁平全项目视图，无文件夹结构。
  const folderById = useMemo(() => {
    const m = new Map<string, FolderNode>();
    const walk = (nodes: FolderNode[]) => {
      for (const n of nodes) {
        m.set(n.id, n);
        if (n.children?.length) walk(n.children);
      }
    };
    walk(folderTree.folders);
    return m;
  }, [folderTree.folders]);
  const activeProjectRoot =
    isFileRefView && activeFolderId
      ? (folderById.get(activeFolderId) ?? null)
      : null;
  const activeProjectId =
    activeProjectRoot?.parent_id === null ? activeProjectRoot.project_id : null;
  const projectOutputs = useProjectOutputs(activeProjectId);
  // 已被 present_files 回调同步为 AIDocument 的 file_ref 按 线程/rel_path 去重，避免与 outputs 重复显示
  const syncedProjectKeys = useMemo(() => {
    const s = new Set<string>();
    for (const d of docs)
      if (d.source_thread_id && d.file_ref_path)
        s.add(`${d.source_thread_id}/${d.file_ref_path}`);
    return s;
  }, [docs]);
  const projectExtraDocs: AIDocument[] =
    isFileRefView && activeProjectId
      ? projectOutputs.files
          .filter(
            (pf) => !syncedProjectKeys.has(`${pf.thread_id}/${pf.rel_path}`),
          )
          .map((pf) => adaptProjectOutput(pf, activeProjectId))
      : [];

  const displayDocs = selectedThread
    ? selectedThread.files
        .filter((f) => (filterMode === "all" ? true : f.starred))
        .map((f) => adaptPersonalFile(f, selectedThread))
    : [...docs, ...projectExtraDocs];
  const displayTotal = selectedThread
    ? selectedThread.files.length
    : total + projectExtraDocs.length;
  const displayLoading = !selectedThread && loading;

  // 全局搜索：跨所有线程搜文件名 / 线程名
  const isSearching = search.trim().length > 0;
  const searchResults = useMemo(() => {
    if (!isSearching)
      return [] as Array<{
        file: PersonalDocFile;
        thread_id: string;
        thread_name: string;
      }>;
    const q = search.trim().toLowerCase();
    return personalOutputs.threads.flatMap((t) =>
      t.files
        .filter(
          (f) =>
            f.name.toLowerCase().includes(q) ||
            t.display_name.toLowerCase().includes(q),
        )
        .map((f) => ({
          file: f,
          thread_id: t.thread_id,
          thread_name: t.display_name,
        })),
    );
  }, [isSearching, search, personalOutputs.threads]);

  const handlePersonalStar = (docId: string) => {
    if (!selectedThread) return;
    const file = selectedThread.files.find(
      (f) => `${selectedThread.thread_id}/${f.rel_path}` === docId,
    );
    if (file)
      void personalOutputs.toggleStar(
        selectedThread.thread_id,
        file.rel_path,
        file.starred,
      );
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
      const x =
        rect.right + menuW > window.innerWidth ? rect.left - menuW : rect.right;
      setMenuAnchor({ x, y: rect.top });
    }
    setOpenMenuId(id);
  };

  const handleCloseMenu = () => {
    setOpenMenuId(null);
    setMenuAnchor(null);
  };

  useEffect(() => {
    if (!openMenuId) return;
    const handler = () => handleCloseMenu();
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [openMenuId]);

  return (
    <div className="bg-background flex h-full w-full">
      <div
        className="border-border bg-muted/50 relative flex shrink-0 flex-col border-r"
        style={{ width: sidebarWidth }}
      >
        <div className="border-border flex items-center gap-2 border-b p-3.5">
          <div className="shrink-0 rounded-sm border border-blue-200 bg-blue-50 p-1 text-blue-600">
            <FolderCheck className="h-4 w-4" />
          </div>
          <span className="text-foreground text-l font-semibold">文档空间</span>
        </div>
        <nav
          ref={personalNavRef}
          className="flex-1 space-y-1 overflow-y-auto px-2 py-1"
          onScroll={(e) => {
            const el = e.currentTarget;
            if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
              void personalOutputs.fetchMore();
            }
          }}
        >
          {/* 我的文档 — 树形结构 */}
          <div>
            <button
              onClick={() => {
                setPersonalOpen((v) => !v);
                setSelectedThreadId(null);
              }}
              className={cn(
                "flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-sm transition-colors",
                selectedThreadId === null
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <div className="flex items-center gap-2">
                {personalOpen ? (
                  <WindowsFolderOpen className="h-4 w-4" />
                ) : (
                  <WindowsFolder className="h-4 w-4" />
                )}
                <span>我的文档</span>
                <span className="text-muted-foreground/60 text-[10px]">
                  共 {personalOutputs.total} 个
                </span>
              </div>
              {personalOpen ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
            {personalOpen && (
              <div className="ml-2 space-y-0.5">
                {personalOutputs.threads.length === 0 &&
                  !personalOutputs.loading && (
                    <p className="text-muted-foreground px-3 py-1.5 text-xs">
                      暂无输出文件
                    </p>
                  )}
                {personalOutputs.loading && (
                  <p className="text-muted-foreground px-3 py-1.5 text-xs">
                    加载中...
                  </p>
                )}
                {personalOutputs.threads.map((thread) => {
                  const isExpanded = personalOutputs.expandedKeys.has(
                    thread.thread_id,
                  );
                  return (
                    <div key={thread.thread_id}>
                      <button
                        onClick={() => {
                          personalOutputs.toggleExpand(thread.thread_id);
                          setSelectedThreadId(thread.thread_id);
                          setActiveFolderId(null);
                        }}
                        className={cn(
                          "flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs transition-colors",
                          selectedThreadId === thread.thread_id
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                        )}
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          {isExpanded ? (
                            <WindowsFolderOpen className="h-3.5 w-3.5 shrink-0" />
                          ) : (
                            <WindowsFolder className="h-3.5 w-3.5 shrink-0" />
                          )}
                          <span className="truncate">
                            {thread.display_name}
                          </span>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <span className="text-muted-foreground/60 text-[10px]">
                            {thread.files.length} 个文件
                          </span>
                          {isExpanded ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="ml-5 space-y-0.5">
                          {thread.files.map((file) => (
                            <div
                              key={file.rel_path}
                              className="text-muted-foreground hover:bg-muted/50 flex items-center justify-between rounded px-3 py-1 text-xs transition-colors"
                            >
                              <div className="flex min-w-0 items-center gap-1.5">
                                <FileText className="h-3 w-3 shrink-0 opacity-60" />
                                <span className="truncate">{file.name}</span>
                                <span className="text-muted-foreground/50 shrink-0 text-[10px]">
                                  {file.size > 1024
                                    ? `${(file.size / 1024).toFixed(1)} KB`
                                    : `${file.size} B`}
                                </span>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void personalOutputs.toggleStar(
                                    thread.thread_id,
                                    file.rel_path,
                                    file.starred,
                                  );
                                }}
                                className="shrink-0 p-0.5 transition-colors hover:text-amber-400"
                                title={file.starred ? "取消收藏" : "收藏"}
                              >
                                <Star
                                  className={cn(
                                    "h-3 w-3",
                                    file.starred && "text-amber-400",
                                  )}
                                  fill={file.starred ? "currentColor" : "none"}
                                />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {personalOutputs.loadingMore && (
                  <p className="text-muted-foreground flex items-center gap-1.5 px-3 py-1.5 text-xs">
                    <Loader2 className="h-3 w-3 animate-spin" /> 加载更多...
                  </p>
                )}
                {personalOutputs.hasMore && !personalOutputs.loadingMore && (
                  <p className="text-muted-foreground/50 px-3 py-1.5 text-[10px]">
                    ↓ 滚动加载更多
                  </p>
                )}
              </div>
            )}
          </div>
          {canUseProject && ( // 项目文件夹 - 树形结构（权限：后端按项目成员过滤）
            <div className="mt-2 pt-2">
              <button
                onClick={() => setArchiveOpen((v) => !v)}
                className="text-muted-foreground hover:bg-muted flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-sm transition-colors"
              >
                <div className="flex items-center gap-2">
                  <FolderSync className="h-3.5 w-3.5 text-amber-500" />
                  <span>项目文件夹</span>
                </div>
                {archiveOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
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
                  onCreateFolder={async (name, parentId, projectId) => {
                    await folderTree.createFolder(name, parentId, projectId);
                  }}
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
          className="hover:bg-primary/40 active:bg-primary/60 absolute top-0 right-0 z-30 h-full w-1.5 cursor-col-resize transition-colors"
          title="拖动调整宽度"
        />
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="border-border bg-background flex h-14 shrink-0 items-center justify-between border-b px-6">
          <div className="flex items-center gap-3">
            {!isFileRefView && (
              <Button onClick={() => setShowNewModal(true)}>
                <Plus className="h-4 w-4" />
                新建文档
              </Button>
            )}
            <div className="bg-muted/60 flex items-center gap-0.5 rounded-md p-0.5">
              {(["all", "starred"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => handleFilterToggle(mode)}
                  className={cn(
                    "rounded-sm px-2.5 py-1 text-xs font-medium transition-colors",
                    filterMode === mode
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {mode === "all" ? "全部" : "收藏"}
                </button>
              ))}
            </div>
            <div className="relative w-60">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
              <Input
                type="text"
                value={search}
                onChange={(e) => handleSearch(e.target.value)}
                placeholder="搜索文档..."
                className="w-full pr-4 pl-9"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="border-border bg-card flex h-[30px] items-center overflow-hidden rounded-[6px] border">
              <button
                onClick={() => setViewMode("grid-icon")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "grid-icon"
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground",
                )}
                title="图标网格"
              >
                <LayoutGrid className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "flex h-[30px] w-[30px] items-center justify-center transition-colors",
                  viewMode === "list"
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground",
                )}
                title="列表"
              >
                <List className="h-3.5 w-3.5" />
              </button>
            </div>
            <span className="text-muted-foreground text-xs">
              共 {displayTotal} 篇文档
            </span>
          </div>
        </div>
        <div
          className={cn(
            "bg-muted/30 flex-1 p-6",
            displayDocs.length === 0
              ? "flex flex-col items-center justify-center"
              : "overflow-y-auto",
          )}
        >
          {isSearching ? (
            <div className="h-full overflow-y-auto">
              <div className="mx-auto max-w-5xl">
                <div className="mb-5">
                  <h2 className="text-foreground text-lg font-semibold">
                    搜索结果
                  </h2>
                  <p className="text-muted-foreground mt-1 text-sm">
                    关键词 “
                    <span className="text-foreground font-medium">
                      {search.trim()}
                    </span>
                    ” — 找到
                    <span className="text-primary mx-1 font-medium">
                      {searchResults.length}
                    </span>
                    个文件
                  </p>
                </div>
                {searchResults.length === 0 ? (
                  <div className="text-muted-foreground flex flex-col items-center py-20 text-center">
                    <Search className="mb-3 h-12 w-12 opacity-25" />
                    <p className="text-sm">未找到匹配的文件</p>
                    <p className="mt-1 text-xs opacity-70">
                      试试其他关键词，或检查文件名
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                    {searchResults.map(({ file, thread_id, thread_name }) => {
                      const doc = adaptPersonalFile(file, {
                        thread_id,
                        display_name: thread_name,
                      });
                      return (
                        <div
                          key={`${thread_id}/${file.rel_path}`}
                          onClick={() => onSelectDoc(doc)}
                          className="group bg-background border-border hover:border-primary/40 cursor-pointer rounded-xl border p-4 transition-all hover:shadow-md"
                        >
                          <div className="flex items-start gap-3">
                            <div className="shrink-0 rounded-lg bg-blue-50 p-2">
                              <FileText className="h-4 w-4 text-blue-500" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-foreground group-hover:text-primary truncate text-sm font-medium transition-colors">
                                {file.name}
                              </div>
                              <div className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
                                <WindowsFolder className="h-3 w-3 shrink-0" />
                                <span className="truncate">{thread_name}</span>
                              </div>
                              <div className="text-muted-foreground/60 mt-2 text-[10px]">
                                {file.size > 1024
                                  ? `${(file.size / 1024).toFixed(1)} KB`
                                  : `${file.size} B`}
                                {file.starred && (
                                  <span className="ml-2 text-amber-500">
                                    ★ 已收藏
                                  </span>
                                )}
                              </div>
                            </div>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                void personalOutputs.toggleStar(
                                  thread_id,
                                  file.rel_path,
                                  file.starred,
                                );
                              }}
                              className={cn(
                                "shrink-0 rounded p-1 transition-colors",
                                file.starred
                                  ? "text-amber-400"
                                  : "text-muted-foreground/40 hover:text-amber-400",
                              )}
                              title={file.starred ? "取消收藏" : "收藏"}
                            >
                              <Star
                                className="h-3.5 w-3.5"
                                fill={file.starred ? "currentColor" : "none"}
                              />
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
            <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
              加载中...
            </div>
          ) : displayDocs.length === 0 ? (
            <div className="flex max-w-xs flex-col items-center text-center">
              <MousePointerClick className="text-muted-foreground/25 mb-4 h-10 w-10" />
              <p className="text-muted-foreground text-sm font-medium">
                点击左侧文件夹查看文档
              </p>
              <p className="text-muted-foreground/60 mt-1.5 text-xs leading-relaxed">
                {selectedThread
                  ? "该线程暂无输出文件"
                  : isFileRefView
                    ? "选中项目文件夹后，同步的文件会出现在这里"
                    : "在左侧选择一个文件夹，或通过 AI 对话生成新文档"}
              </p>
            </div>
          ) : viewMode === "grid-icon" ? (
            <AnimatePresence>
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {displayDocs.map((doc) => (
                  <DocCard
                    key={doc.id}
                    doc={doc}
                    variant="icon"
                    isMenuOpen={openMenuId === doc.id}
                    onOpenMenu={handleOpenMenu}
                    menuButtonRef={(el) => {
                      menuButtonRef.current[doc.id] = el;
                    }}
                    onSelect={() => onSelectDoc(doc)}
                    onToggleStar={() =>
                      doc.id.startsWith("proj/")
                        ? undefined
                        : selectedThread
                          ? handlePersonalStar(doc.id)
                          : toggleStar(doc.id, doc.is_starred ?? false)
                    }
                    onDelete={async () => {
                      handleCloseMenu();
                      if (doc.id.startsWith("proj/")) return;
                      if (confirm("确认删除该文档？")) await deleteDoc(doc.id);
                    }}
                    onShare={() => {
                      /* intentional no-op */
                    }}
                    selected={selectedIds.has(doc.id)}
                    onToggleSelect={() => handleToggleSelect(doc.id)}
                  />
                ))}
              </div>
            </AnimatePresence>
          ) : (
            <div className="bg-background border-border overflow-hidden rounded-xl border shadow-sm">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-border bg-muted/50 border-b">
                    <th className="text-muted-foreground px-4 py-3 text-xs font-semibold tracking-wider uppercase">
                      名称
                    </th>
                    <th className="text-muted-foreground px-3 py-3 text-xs font-semibold tracking-wider uppercase">
                      类型
                    </th>
                    <th className="text-muted-foreground px-4 py-3 text-xs font-semibold tracking-wider whitespace-nowrap uppercase">
                      大小
                    </th>
                    <th className="text-muted-foreground px-4 py-3 text-xs font-semibold tracking-wider whitespace-nowrap uppercase">
                      更新时间
                    </th>
                    <th className="text-muted-foreground px-4 py-3 text-right text-xs font-semibold tracking-wider uppercase">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-border divide-y">
                  {displayDocs.map((doc) => {
                    const isFileRef = doc.doc_type === "file_ref";
                    const fileSize = formatFileSize(doc.file_size);
                    const updatedAt = doc.updated_at
                      ? new Date(doc.updated_at)
                          .toLocaleString("zh-CN", {
                            year: "numeric",
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: false,
                          })
                          .replace(/\//g, "/")
                      : "";
                    const handleClick = (e: React.MouseEvent) => {
                      if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        handleToggleSelect(doc.id);
                      } else {
                        onSelectDoc(doc);
                      }
                    };
                    return (
                      <tr
                        key={doc.id}
                        className={cn(
                          "hover:bg-muted/50 group cursor-pointer transition-colors",
                          selectedIds.has(doc.id) && "bg-primary/5",
                        )}
                        onClick={handleClick}
                      >
                        <td className="px-4 py-4">
                          <div className="flex min-w-0 items-center gap-3">
                            {selectedIds.has(doc.id) ? (
                              <CheckCircle2 className="text-primary h-4 w-4 shrink-0" />
                            ) : isFileRef ? (
                              <FileTypeIcon
                                mime={doc.file_mime}
                                title={doc.title}
                                docType={doc.doc_type}
                                size="sm"
                              />
                            ) : (
                              <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                            )}
                            <span className="text-foreground group-hover:text-primary truncate font-medium transition-colors">
                              {doc.title != null && doc.title !== ""
                                ? doc.title
                                : "无标题"}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-4">
                          {(() => {
                            const fic =
                              FILE_ICON_CONFIG[
                                getFileType(
                                  doc.file_mime,
                                  doc.title,
                                  doc.doc_type,
                                )
                              ]!;
                            return (
                              <span
                                className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
                                style={{
                                  backgroundColor: fic.primary + "18",
                                  color: fic.primary,
                                }}
                              >
                                {fic.label}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="text-muted-foreground px-4 py-4 text-sm whitespace-nowrap">
                          {fileSize || "—"}
                        </td>
                        <td className="text-muted-foreground px-4 py-4 text-sm whitespace-nowrap">
                          {updatedAt}
                        </td>
                        <td className="px-4 py-4 text-right">
                          <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1.5 transition-colors"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (doc.id.startsWith("proj/")) return;
                                if (selectedThread) {
                                  handlePersonalStar(doc.id);
                                } else {
                                  void toggleStar(
                                    doc.id,
                                    doc.is_starred ?? false,
                                  );
                                }
                              }}
                            >
                              <Star
                                className={cn(
                                  "h-4 w-4",
                                  doc.is_starred && "text-amber-400",
                                )}
                                fill={doc.is_starred ? "currentColor" : "none"}
                              />
                            </button>
                            <button
                              ref={(el) => {
                                menuButtonRef.current[doc.id] = el;
                              }}
                              className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1.5 transition-colors"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenMenu(doc.id);
                              }}
                            >
                              <MoreHorizontal className="h-4 w-4" />
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
          <div className="border-border bg-background flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
            <Button
              variant="outline"
              size="icon"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
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
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
        {openMenuId &&
          menuAnchor &&
          (() => {
            const doc = displayDocs.find((d) => d.id === openMenuId);
            if (!doc) return null;
            const isFileRef = doc.doc_type === "file_ref";
            return (
              <div
                className="bg-background border-border fixed z-[100] w-32 rounded-xl border py-1.5 shadow-xl"
                style={{ left: menuAnchor.x, top: menuAnchor.y + 4 }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    handleCloseMenu();
                    onSelectDoc(doc);
                  }}
                  className="text-foreground hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-xs"
                >
                  <PenLine className="h-3 w-3" /> 打开编辑
                </button>
                <div className="bg-border mx-2 my-1 h-px" />
                {!doc.id.startsWith("proj/") && (
                  <button
                    type="button"
                    onClick={async () => {
                      handleCloseMenu();
                      if (confirm(`确认删除该${isFileRef ? "文件" : "文档"}？`))
                        await deleteDoc(doc.id);
                    }}
                    className="text-destructive hover:bg-destructive/10 flex w-full items-center gap-2 px-3 py-1.5 text-xs"
                  >
                    <Trash2 className="h-3 w-3" /> 删除
                  </button>
                )}
              </div>
            );
          })()}
      </div>
      <AnimatePresence>
        {showNewModal && (
          <NewDocModal
            isOpen={showNewModal}
            onClose={() => setShowNewModal(false)}
            onCreate={handleCreate}
          />
        )}
      </AnimatePresence>
      <FilePreviewModal
        doc={previewDocState}
        open={!!previewDocState}
        onOpenChange={(o) => {
          if (!o) setPreviewDocState(null);
        }}
      />
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
        onMergeExport={handleMergeExport}
        mergeExporting={mergeExporting}
      />
    </div>
  );
}

// ─── Doc Card ─────────────────────────────────────────────────────────────────

function DocCard({
  doc,
  variant = "auto",
  onOpenMenu,
  menuButtonRef,
  onSelect,
  onToggleStar,
  selected,
  onToggleSelect,
}: {
  doc: AIDocument;
  variant?: "auto" | "icon" | "summary";
  isMenuOpen: boolean;
  onOpenMenu: (id: string) => void;
  menuButtonRef: (el: HTMLButtonElement | null) => void;
  onSelect: () => void;
  onToggleStar: () => void;
  onDelete: () => void;
  onShare?: () => void;
  selected?: boolean;
  onToggleSelect?: () => void;
}) {
  const isFileRef = doc.doc_type === "file_ref";
  const rawPreview = (doc.content ?? "").replace(/[#*`>\-_]/g, "").trim();
  const preview = rawPreview.slice(0, 120);
  const showSummary =
    variant === "summary" ? !!preview : variant === "auto" && !!preview;
  const updatedAt = doc.updated_at
    ? new Date(doc.updated_at)
        .toLocaleString("zh-CN", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })
        .replace(/\//g, "/")
    : "";
  const fileSize = isFileRef ? formatFileSize(doc.file_size) : "";

  // For file_ref without content, build a file-info preview line
  const fileInfoLine = isFileRef
    ? [
        getFileType(doc.file_mime, doc.title, doc.doc_type).toUpperCase(),
        fileSize,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="bg-background border-border group hover:border-primary/50 relative flex h-50 cursor-pointer flex-col rounded-xl border p-4 transition-all hover:shadow-md"
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          onToggleSelect?.();
        } else {
          onSelect();
        }
      }}
    >
      <div className="relative mb-4 flex-1 overflow-hidden">
        {showSummary ? (
          <div className="bg-muted/50 border-border relative h-full overflow-hidden rounded-lg border p-4">
            <div className="absolute top-4 bottom-4 left-0 w-1 rounded-r-full bg-purple-200 dark:bg-purple-500/50" />
            <p className="text-muted-foreground line-clamp-4 pl-3 text-sm leading-relaxed">
              {preview}
            </p>
          </div>
        ) : (
          <div className="bg-muted/50 border-border relative flex h-full flex-col items-center justify-center gap-2 overflow-hidden rounded-lg border">
            <FileTypeIcon
              mime={doc.file_mime}
              title={doc.title}
              docType={doc.doc_type}
              size="lg"
            />
            {fileInfoLine && (
              <span className="text-muted-foreground text-xs">
                {fileInfoLine}
              </span>
            )}
          </div>
        )}
      </div>
      <h3 className="text-foreground group-hover:text-primary mb-4 line-clamp-1 text-base font-bold transition-colors">
        {doc.title || "无标题"}
      </h3>
      <div className="text-muted-foreground mt-auto flex items-center justify-between">
        <span className="text-xs">{updatedAt}</span>
        <div className="flex items-center gap-3 text-xs">
          <button
            ref={menuButtonRef}
            className="hover:text-foreground transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onOpenMenu(doc.id);
            }}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          <button
            className={cn(
              "transition-colors",
              doc.is_starred ? "text-amber-400" : "hover:text-foreground",
            )}
            onClick={(e) => {
              e.stopPropagation();
              onToggleStar();
            }}
          >
            <Star
              className="h-4 w-4"
              fill={doc.is_starred ? "currentColor" : "none"}
            />
          </button>
        </div>
      </div>
      {selected && (
        <div className="bg-primary absolute top-2 right-2 flex h-5 w-5 items-center justify-center rounded-full">
          <CheckCircle2 className="text-primary-foreground h-3 w-3" />
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
  markdown: {
    primary: "#0EA5E9",
    secondary: "#FFFFFF",
    label: "MD",
    symbol: "doc",
  },
  python: {
    primary: "#8B5CF6",
    secondary: "#FDE68A",
    label: "PY",
    symbol: "code",
  },
  javascript: {
    primary: "#EAB308",
    secondary: "#1E293B",
    label: "JS",
    dark: true,
    symbol: "code",
  },
  typescript: {
    primary: "#3B82F6",
    secondary: "#FFFFFF",
    label: "TS",
    symbol: "code",
  },
  json: {
    primary: "#F97316",
    secondary: "#FFFFFF",
    label: "JSON",
    symbol: "data",
  },
  html: {
    primary: "#EF4444",
    secondary: "#FFFFFF",
    label: "HTML",
    symbol: "code",
  },
  css: {
    primary: "#06B6D4",
    secondary: "#FFFFFF",
    label: "CSS",
    symbol: "code",
  },
  pdf: {
    primary: "#DC2626",
    secondary: "#FFFFFF",
    label: "PDF",
    symbol: "doc",
  },
  word: {
    primary: "#2563EB",
    secondary: "#FFFFFF",
    label: "DOC",
    symbol: "doc",
  },
  excel: {
    primary: "#16A34A",
    secondary: "#FFFFFF",
    label: "XLS",
    symbol: "data",
  },
  csv: {
    primary: "#65A30D",
    secondary: "#FFFFFF",
    label: "CSV",
    symbol: "data",
  },
  image: {
    primary: "#D946EF",
    secondary: "#FFFFFF",
    label: "IMG",
    symbol: "image",
  },
  text: {
    primary: "#94A3B8",
    secondary: "#FFFFFF",
    label: "TXT",
    symbol: "doc",
  },
  xml: {
    primary: "#EA580C",
    secondary: "#FFFFFF",
    label: "XML",
    symbol: "code",
  },
  yaml: {
    primary: "#EC4899",
    secondary: "#FFFFFF",
    label: "YML",
    symbol: "data",
  },
  shell: {
    primary: "#22C55E",
    secondary: "#FFFFFF",
    label: "SH",
    symbol: "terminal",
  },
};

function getFileType(
  mime: string | undefined | null,
  title: string | undefined | null,
  docType?: string | null,
): string {
  if (!mime && title) {
    const ext = title.split(".").pop()?.toLowerCase() ?? "";
    const extMap: Record<string, string> = {
      md: "markdown",
      py: "python",
      js: "javascript",
      ts: "typescript",
      json: "json",
      html: "html",
      css: "css",
      pdf: "pdf",
      doc: "word",
      docx: "word",
      xls: "excel",
      xlsx: "excel",
      csv: "csv",
      xml: "xml",
      yml: "yaml",
      yaml: "yaml",
      sh: "shell",
      txt: "text",
    };
    return extMap[ext] ?? (docType === "document" ? "markdown" : "text");
  }
  const m = (mime ?? "").toLowerCase();
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
      <rect
        x="8"
        y="11"
        width="24"
        height="2"
        rx="1"
        fill={fill}
        opacity="0.5"
      />
      <rect
        x="8"
        y="16"
        width="18"
        height="2"
        rx="1"
        fill={fill}
        opacity="0.35"
      />
      <rect
        x="8"
        y="21"
        width="12"
        height="2"
        rx="1"
        fill={fill}
        opacity="0.2"
      />
    </g>
  ),
  code: (fill: string) => (
    <g>
      <polyline
        points="10,12 6,17 10,22"
        fill="none"
        stroke={fill}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <polyline
        points="30,12 34,17 30,22"
        fill="none"
        stroke={fill}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <line
        x1="24"
        y1="10"
        x2="16"
        y2="24"
        stroke={fill}
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.4"
      />
    </g>
  ),
  data: (fill: string) => (
    <g>
      <rect
        x="8"
        y="11"
        width="9"
        height="5"
        rx="1"
        fill={fill}
        opacity="0.4"
      />
      <rect
        x="19"
        y="11"
        width="9"
        height="5"
        rx="1"
        fill={fill}
        opacity="0.3"
      />
      <rect
        x="8"
        y="18"
        width="9"
        height="5"
        rx="1"
        fill={fill}
        opacity="0.3"
      />
      <rect
        x="19"
        y="18"
        width="9"
        height="5"
        rx="1"
        fill={fill}
        opacity="0.2"
      />
    </g>
  ),
  image: (fill: string) => (
    <g>
      <circle cx="16" cy="15" r="3.5" fill={fill} opacity="0.45" />
      <polyline
        points="8,26 16,19 21,23 26,18 32,24 32,27 8,27"
        fill={fill}
        opacity="0.3"
      />
    </g>
  ),
  terminal: (fill: string) => (
    <g>
      <polyline
        points="9,13 15,18 9,23"
        fill="none"
        stroke={fill}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <rect
        x="19"
        y="22"
        width="8"
        height="2.5"
        rx="1"
        fill={fill}
        opacity="0.35"
      />
    </g>
  ),
};

function FileTypeIcon({
  mime,
  title,
  docType,
  size = "lg",
}: {
  mime?: string | null;
  title?: string | null;
  docType?: string | null;
  size?: "sm" | "lg";
}) {
  const fileType = getFileType(mime, title, docType);
  const config = FILE_ICON_CONFIG[fileType]!;
  const labelFill = config.dark ? config.secondary : "#fff";
  const symbolFill = config.dark ? config.secondary : "#fff";
  const gid = size === "lg" ? `sheen-${fileType}` : `sheen-sm-${fileType}`;
  const cid = size === "lg" ? `fold-${fileType}` : `fold-sm-${fileType}`;

  if (size === "lg") {
    return (
      <svg className="h-14 w-12" viewBox="0 0 40 48" fill="none">
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
          <path
            d="M26 2V12C26 14.2 27.8 16 30 16H40V16L26 2Z"
            fill="rgba(0,0,0,0.12)"
          />
        </g>
        <path
          d="M4 2H26L40 16V44C40 46.2 38.2 48 36 48H4C1.8 48 0 46.2 0 44V6C0 3.8 1.8 2 4 2Z"
          className="stroke-black/8"
          strokeWidth="0.5"
          fill="none"
        />
        {SymbolPaths[config.symbol](symbolFill)}
        <rect
          x="5"
          y="34"
          width="30"
          height="11"
          rx="3"
          fill="rgba(0,0,0,0.18)"
        />
        <text
          x="20"
          y="43"
          textAnchor="middle"
          fill={labelFill}
          fontSize="10"
          fontWeight="800"
          fontFamily="system-ui, -apple-system, sans-serif"
          letterSpacing="0.5"
        >
          {config.label}
        </text>
      </svg>
    );
  }

  return (
    <svg className="h-6 w-5" viewBox="0 0 20 24" fill="none">
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
        <path
          d="M13 1V6C13 7.1 13.9 8 15 8H20V8L13 1Z"
          fill="rgba(0,0,0,0.12)"
        />
      </g>
      <path
        d="M2 1H13L20 8V22C20 23.1 19.1 24 18 24H2C0.9 24 0 23.1 0 22V3C0 1.9 0.9 1 2 1Z"
        className="stroke-black/8"
        strokeWidth="0.5"
        fill="none"
      />
      <rect
        x="3"
        y="17"
        width="14"
        height="5"
        rx="1.5"
        fill="rgba(0,0,0,0.18)"
      />
      <text
        x="10"
        y="21"
        textAnchor="middle"
        fill={labelFill}
        fontSize="4.5"
        fontWeight="800"
        fontFamily="system-ui, -apple-system, sans-serif"
      >
        {config.label}
      </text>
    </svg>
  );
}

// ─── New Doc Modal ────────────────────────────────────────────────────────────

function NewDocModal({
  isOpen,
  onClose,
  onCreate,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (title: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const handleSubmit = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await onCreate(title.trim());
      setTitle("");
    } finally {
      setSaving(false);
    }
  };
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="bg-background relative w-full max-w-md overflow-hidden rounded-2xl shadow-xl"
          >
            <div className="border-border flex items-center justify-between border-b px-6 py-4">
              <h3 className="text-foreground text-base font-semibold">
                新建文档
              </h3>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="p-6">
              <label className="text-foreground mb-1.5 block text-sm font-medium">
                文档标题 <span className="text-destructive">*</span>
              </label>
              <Input
                autoFocus
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="请输入文档标题"
                className="w-full"
              />
            </div>
            <div className="bg-muted/50 border-border flex items-center justify-end gap-2.5 border-t px-6 py-4">
              <Button variant="outline" onClick={onClose}>
                取消
              </Button>
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
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <Button variant="secondary" size="sm" onClick={() => setOpen((v) => !v)}>
        <Download className="h-3.5 w-3.5" />
        导出
        <ChevronDown
          className={cn(
            "ml-1 h-3 w-3 transition-transform",
            open && "rotate-180",
          )}
        />
      </Button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="bg-background border-border absolute top-full right-0 z-50 mt-1 w-44 rounded-xl border py-1 shadow-xl"
          >
            <button
              type="button"
              onClick={() => {
                onExport("md");
                setOpen(false);
              }}
              className="text-foreground hover:bg-muted flex w-full items-center gap-2.5 px-3 py-2 text-sm transition-colors"
            >
              <FileText className="text-muted-foreground h-4 w-4" />
              <div className="text-left">
                <div className="font-medium">Markdown</div>
                <div className="text-muted-foreground text-xs">.md 格式</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => {
                onExport("docx");
                setOpen(false);
              }}
              className="text-foreground hover:bg-muted flex w-full items-center gap-2.5 px-3 py-2 text-sm transition-colors"
            >
              <FileText className="text-primary h-4 w-4" />
              <div className="text-left">
                <div className="font-medium">Word 文档</div>
                <div className="text-muted-foreground text-xs">.docx 格式</div>
              </div>
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Document Editor ──────────────────────────────────────────────────────────

export function DocumentEditor({
  docId,
  personalFile,
  projectFile,
  onBack,
}: {
  docId: string | null;
  personalFile: { thread_id: string; rel_path: string; title: string } | null;
  projectFile: ProjectFileRef | null;
  onBack: () => void;
}) {
  const [doc, setDoc] = useState<AIDocument | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showAI, setShowAI] = useState(false);
  const [aiPanelKey, setAiPanelKey] = useState(0);
  const [panelWidth, setPanelWidth] = useState(420);
  const resizingRef = useRef(false);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [exportContent, setExportContent] = useState<string | undefined>(
    undefined,
  );
  const [loading, setLoading] = useState(true);
  const editorRef = useRef<PersonalBlockNoteEditorRef | CollabEditorRef>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const titleRef = useRef(title);
  titleRef.current = title;
  // 最近一次待保存的保存逻辑（闭包最新 content），供 unmount flush 用。
  const flushPendingRef = useRef<() => void>(() => {
    /* intentional no-op */
  });
  // EAI-CUSTOM: 项目文件写回乐观锁——读端点返回 mtime，保存时回传；后端比对不一致返 409。
  const projectMtimeRef = useRef<number | null>(null);

  // ── B 组: 字数统计 / 查找替换 / 全屏 ────────────────────────────────
  const [docStats, setDocStats] = useState({ words: 0, chars: 0 });
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [findMatches, setFindMatches] = useState<
    Array<{ blockId: string; blockIndex: number; count: number }>
  >([]);
  const [activeMatch, setActiveMatch] = useState(-1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const editorAreaRef = useRef<HTMLDivElement>(null);

  // ── C10: 版本历史 ────────────────────────────────────────────────────
  const [showVersions, setShowVersions] = useState(false);
  const [editorKey, setEditorKey] = useState(0); // 恢复版本后强制重挂载编辑器重新 seed

  // AI sub-thread persisted at editor level — survives panel close/reopen
  const aiThreadId =
    projectFile?.thread_id ?? personalFile?.thread_id ?? docId ?? "default";
  const { subThreadId, ensureThread, isCreating, resetThread } =
    useDocAIThread(aiThreadId);

  useEffect(() => {
    setLoading(true);
    // EAI-CUSTOM: 项目文档——跨用户直读 outputs（artifacts API 是 owner-scoped，组员走 read_project_output）
    if (projectFile) {
      docmgrApi
        .readProjectOutput(projectFile.project_id, {
          thread_id: projectFile.thread_id,
          rel_path: projectFile.rel_path,
        })
        .then(({ content, mtime }) => {
          projectMtimeRef.current = mtime;
          const lang = getLanguageFromName(projectFile.title);
          const displayContent = lang
            ? "```" + lang + "\n" + content + "\n```"
            : content;
          setDoc({
            id: "project",
            title: projectFile.title,
            content: displayContent,
            doc_type: "file_ref",
          } as AIDocument);
          setTitle(projectFile.title);
          setLoading(false);
        })
        .catch(() => setLoading(false));
      return;
    }
    // 个人文档：直接读线程 outputs/ 文件内容（artifacts API）
    if (personalFile) {
      const artifactPath = `mnt/user-data/outputs/${personalFile.rel_path}`;
      fetch(`/api/threads/${personalFile.thread_id}/artifacts/${artifactPath}`)
        .then((r) => r.text())
        .then((content) => {
          // 代码文件用代码块包裹（在 markdown 编辑器里有语法高亮 + 等宽显示）
          const lang = getLanguageFromName(personalFile.title);
          const displayContent = lang
            ? "```" + lang + "\n" + content + "\n```"
            : content;
          setDoc({
            id: "personal",
            title: personalFile.title,
            content: displayContent,
            doc_type: "file_ref",
          } as AIDocument);
          setTitle(personalFile.title);
          setLoading(false);
        })
        .catch(() => setLoading(false));
      return;
    }
    if (!docId) {
      setLoading(false);
      return;
    }
    docmgrApi
      .get(docId)
      .then(async (d) => {
        // For file_ref documents, load file content via preview API
        if (d.doc_type === "file_ref" && !d.content) {
          try {
            const preview = await docmgrApi.preview(docId);
            if (preview.content) {
              d = { ...d, content: preview.content };
            }
          } catch {
            /* fall through with empty content */
          }
        }
        setDoc(d);
        setTitle(d.title);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [docId, personalFile, projectFile]);

  const scheduleSave = useCallback(
    (content: string) => {
      setSaved(false);
      setSaveError(null);
      setDocStats(computeDocStats(content));
      clearTimeout(saveTimer.current);
      // 具体保存逻辑闭包最新 content；unmount flush 与防抖超时都走它。
      const doSave = async () => {
        setSaving(true);
        try {
          if (projectFile) {
            // EAI-CUSTOM: 项目文件跨用户写回，带 mtime 乐观锁；保存成功后更新 mtime 供下次比对
            let saveContent = content;
            if (getLanguageFromName(projectFile.title)) {
              const m = /^```[^\n]*\n([\s\S]*)\n```\s*$/.exec(content);
              if (m) saveContent = m[1]!;
            }
            const res = await docmgrApi.saveProjectContent(
              projectFile.project_id,
              {
                thread_id: projectFile.thread_id,
                rel_path: projectFile.rel_path,
                content: saveContent,
                if_mtime: projectMtimeRef.current ?? undefined,
              },
            );
            projectMtimeRef.current = res.mtime;
          } else if (personalFile) {
            // 代码文件在编辑器里被 ```lang 包裹，保存时去掉 fence 写回原始内容
            let saveContent = content;
            if (getLanguageFromName(personalFile.title)) {
              const m = /^```[^\n]*\n([\s\S]*)\n```\s*$/.exec(content);
              if (m) saveContent = m[1]!;
            }
            await docmgrApi.savePersonalContent(personalFile.thread_id, {
              rel_path: personalFile.rel_path,
              content: saveContent,
            });
          } else if (docId) {
            await docmgrApi.update(docId, { title: titleRef.current, content });
          }
          setSaved(true);
          setSaveError(null);
          setSavedAt(
            new Date().toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            }),
          );
        } catch (e) {
          // 保存失败不再静默 —— 顶部栏展示错误，用户可继续编辑触发重试
          // 409 = 并发写回冲突（mtime 乐观锁），提示刷新
          const status =
            typeof e === "object" && e !== null && "status" in e
              ? (e as { status?: unknown }).status
              : undefined;
          setSaveError(
            status === 409
              ? "文件已被他人修改，请刷新后重试"
              : getErrorMessage(e, "保存失败，请重试"),
          );
          console.error("[docmgr] save failed:", e);
        } finally {
          setSaving(false);
        }
      };
      flushPendingRef.current = () => {
        void doSave();
      };
      saveTimer.current = setTimeout(() => {
        flushPendingRef.current = () => {
          /* intentional no-op */
        };
        void doSave();
      }, 1500);
    },
    [docId, personalFile, projectFile],
  );

  const handleTitleBlur = async () => {
    if (!doc || title === doc.title || personalFile || projectFile) return;
    if (!docId) return;
    setSaving(true);
    try {
      const content =
        (await editorRef.current?.getMarkdown()) ?? doc.content ?? "";
      await docmgrApi.update(docId, { title, content });
      setSaved(true);
      setSavedAt(
        new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  // 防抖窗口内卸载（关闭编辑器/切档/刷新）时 flush 最近一次待保存内容，避免丢未落盘编辑
  useEffect(() => {
    return () => {
      clearTimeout(saveTimer.current);
      flushPendingRef.current();
      flushPendingRef.current = () => {
        /* intentional no-op */
      };
    };
  }, []);

  // 有未保存内容时，浏览器刷新/关闭给出提示
  useEffect(() => {
    if (saved) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [saved]);

  // 全屏状态跟随 Fullscreen API
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  // 查找: 打开或 query 变化时实时搜索（个人 BlockNote 编辑器）
  const runFind = (target = 0) => {
    const bn =
      editorRef.current as unknown as PersonalBlockNoteEditorRef | null;
    const q = findQuery.trim();
    if (!q || !bn?.findText) {
      setFindMatches([]);
      setActiveMatch(-1);
      return;
    }
    const m = bn.findText(q);
    setFindMatches(m);
    if (!m.length) {
      setActiveMatch(-1);
      return;
    }
    const idx = Math.min(target, m.length - 1);
    setActiveMatch(idx);
    bn.scrollToBlock?.(m[idx]!.blockId);
  };
  useEffect(() => {
    if (findOpen) runFind();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findQuery, findOpen]);

  const goMatch = (delta: number) => {
    if (!findMatches.length) return;
    const bn =
      editorRef.current as unknown as PersonalBlockNoteEditorRef | null;
    const next =
      (activeMatch + delta + findMatches.length) % findMatches.length;
    setActiveMatch(next);
    bn?.scrollToBlock?.(findMatches[next]!.blockId);
  };

  const replaceOne = () => {
    if (activeMatch < 0 || !findMatches.length) return;
    const bn =
      editorRef.current as unknown as PersonalBlockNoteEditorRef | null;
    const q = findQuery.trim();
    if (!q || !bn?.replaceInBlock) return;
    bn.replaceInBlock(findMatches[activeMatch]!.blockId, q, replaceText);
    runFind(activeMatch); // 替换后刷新匹配列表，尽量停留在同一位置
  };

  const replaceAll = () => {
    const bn =
      editorRef.current as unknown as PersonalBlockNoteEditorRef | null;
    const q = findQuery.trim();
    if (!q || !bn?.replaceInBlock) return;
    for (const m of findMatches) bn.replaceInBlock(m.blockId, q, replaceText);
    setFindQuery("");
    setFindOpen(false);
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen?.();
    } else {
      void editorAreaRef.current?.requestFullscreen?.();
    }
  };

  // C10: 版本恢复后，用恢复内容重载编辑器（key 变更触发 PersonalBlockNoteEditor 重新 seed）
  const handleRestored = (content: string) => {
    setDoc((d) => (d ? { ...d, content } : d));
    setEditorKey((k) => k + 1);
    setDocStats(computeDocStats(content));
  };

  const handleExport = async (fmt: "md" | "docx") => {
    if (fmt === "docx") {
      // ponytail: capture live editor markdown so personal/thread files (docId=null)
      // can export via the content-based endpoint.
      setExportContent(
        (await editorRef.current?.getMarkdown()) ?? doc?.content ?? "",
      );
      setShowExportDialog(true);
      return;
    }
    // 个人文档：直接用已读 content 下载
    if (personalFile || !docId) {
      const blob = new Blob([doc?.content ?? ""], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    const res = await docmgrApi.export(docId, fmt);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // 项目文档用 CollabEditor（无 undo/redo/find 能力），个人文档用 PersonalBlockNoteEditor
  const isCollab = !!doc?.project_id;
  if (loading)
    return (
      <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
        加载中...
      </div>
    );

  return (
    <div className="bg-background flex h-full flex-1 flex-col overflow-hidden">
      <div className="bg-background border-border z-20 shrink-0 border-b">
        <div className="flex h-11 items-center justify-between gap-4 px-4">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={onBack}
              className="shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={handleTitleBlur}
              className="min-w-0 flex-1 truncate border-none bg-transparent text-lg font-semibold outline-none"
              placeholder="无标题文档"
            />
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <span className="text-muted-foreground mr-1 text-xs whitespace-nowrap select-none">
              {docStats.words} 字 · {docStats.chars} 字符
            </span>
            <span className="mr-2 flex items-center gap-1.5 text-xs select-none">
              {saveError ? (
                <span
                  className="flex items-center gap-1.5 text-red-600"
                  title={saveError}
                >
                  <AlertCircle className="h-3.5 w-3.5" />
                  {saveError}
                </span>
              ) : saving ? (
                <span className="text-muted-foreground flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  保存中...
                </span>
              ) : savedAt ? (
                <span className="text-muted-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="text-success h-3.5 w-3.5" />
                  已保存于 {savedAt}
                </span>
              ) : null}
            </span>
            <Button
              variant="ghost"
              size="icon"
              disabled={isCollab}
              onClick={() =>
                (
                  editorRef.current as PersonalBlockNoteEditorRef | null
                )?.undo?.()
              }
              title="撤销 (Ctrl+Z)"
            >
              <Undo2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              disabled={isCollab}
              onClick={() =>
                (
                  editorRef.current as PersonalBlockNoteEditorRef | null
                )?.redo?.()
              }
              title="重做 (Ctrl+Y)"
            >
              <Redo2 className="h-4 w-4" />
            </Button>
            {!isCollab && (
              <Button
                variant={findOpen ? "secondary" : "ghost"}
                size="icon"
                onClick={() => setFindOpen((v) => !v)}
                title="查找 / 替换"
              >
                <Search className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleFullscreen}
              title={isFullscreen ? "退出全屏" : "全屏专注"}
            >
              {isFullscreen ? (
                <Minimize className="h-4 w-4" />
              ) : (
                <Maximize className="h-4 w-4" />
              )}
            </Button>
            {!isCollab && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowVersions(true)}
                title="版本历史"
              >
                <History className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant={showAI ? "default" : "ghost"}
              size="sm"
              disabled={!showAI && isCreating}
              onClick={async () => {
                // 先确保线程有效（校验 localStorage 里的 ID 是否失效，失效则重建），再开面板，避免 404
                if (!showAI) await ensureThread();
                setShowAI((v) => !v);
              }}
            >
              {!showAI && isCreating ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : null}
              AI 助手
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={async () => {
                const md = (await editorRef.current?.getMarkdown()) ?? "";
                void navigator.clipboard.writeText(md);
              }}
              title="复制内容"
            >
              <Copy className="h-4 w-4" />
            </Button>
            <ExportMenu onExport={handleExport} />
          </div>
        </div>
      </div>
      {findOpen && (
        <div
          className="border-border bg-muted/20 flex items-center gap-2 border-b px-3 py-1.5 text-xs"
          onKeyDown={(e) => {
            if (e.key === "Escape") setFindOpen(false);
          }}
        >
          <Input
            value={findQuery}
            onChange={(e) => setFindQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                goMatch(1);
              }
            }}
            placeholder="查找"
            className="h-7 w-44 text-xs"
            autoFocus
          />
          <Input
            value={replaceText}
            onChange={(e) => setReplaceText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                replaceOne();
              }
            }}
            placeholder="替换为"
            className="h-7 w-32 text-xs"
          />
          <span className="text-muted-foreground min-w-[3em] shrink-0 text-center">
            {findMatches.length > 0
              ? `${activeMatch + 1}/${findMatches.length}`
              : "无结果"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => goMatch(-1)}
            disabled={!findMatches.length}
            title="上一个 (Shift+Enter)"
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => goMatch(1)}
            disabled={!findMatches.length}
            title="下一个 (Enter)"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={replaceOne}
            disabled={!findMatches.length}
          >
            替换
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={replaceAll}
            disabled={!findMatches.length}
          >
            全部替换
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto h-7 w-7"
            onClick={() => setFindOpen(false)}
            title="关闭 (Esc)"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
      <div className="flex flex-1 overflow-hidden" ref={editorAreaRef}>
        <div className="flex flex-1 flex-col overflow-hidden">
          {doc !== null &&
            (doc.project_id ? (
              <CollabEditor
                ref={editorRef as React.Ref<CollabEditorRef>}
                documentId={docId ?? ""}
                initialContent={doc.content ?? ""}
                projectId={doc.project_id}
                onChange={scheduleSave}
                className="flex-1"
              />
            ) : (
              // EAI-CUSTOM: file_ref 个人文件面无 source_thread_id，回退 personalFile.thread_id，图片三入口才能激活
              <PersonalBlockNoteEditor
                key={editorKey}
                ref={editorRef as React.Ref<PersonalBlockNoteEditorRef>}
                initialContent={doc.content ?? ""}
                onChange={scheduleSave}
                className="flex-1"
                threadId={doc.source_thread_id ?? personalFile?.thread_id ?? undefined}
                hideSideMenu={
                  !!getLanguageFromName(personalFile?.title ?? doc?.title ?? "")
                }
              />
            ))}
        </div>
        <AnimatePresence>
          {showAI &&
            (() => {
              const aiDocTitle = personalFile?.title ?? title ?? "untitled";
              const aiRelPath = personalFile?.rel_path ?? `${aiDocTitle}.md`;
              return (
                <>
                  {/* Resize handle */}
                  <div
                    className="hover:bg-primary/30 active:bg-primary/50 group relative w-1.5 shrink-0 cursor-col-resize transition-colors hover:w-1.5"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      resizingRef.current = true;
                      const startX = e.clientX;
                      const startWidth = panelWidth;
                      const onMove = (ev: MouseEvent) => {
                        const delta = startX - ev.clientX;
                        setPanelWidth(
                          Math.max(280, Math.min(800, startWidth + delta)),
                        );
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
                    <div className="absolute inset-y-0 -right-1 -left-1" />
                  </div>
                  <motion.div
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: panelWidth }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ duration: 0.2 }}
                    className="border-border shrink-0 overflow-hidden border-l"
                  >
                    <DocAIAgentPanel
                      key={aiPanelKey}
                      docTitle={aiDocTitle}
                      docRelPath={aiRelPath}
                      threadId={aiThreadId}
                      editorRef={
                        editorRef as React.RefObject<PersonalBlockNoteEditorRef | null>
                      }
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
      <ExportDocxDialog
        docId={docId}
        docTitle={title}
        content={exportContent}
        open={showExportDialog}
        onOpenChange={setShowExportDialog}
      />
      {!isCollab && (
        <VersionHistoryDialog
          threadId={personalFile?.thread_id ?? docId ?? ""}
          relPath={personalFile?.rel_path ?? `${title}.md`}
          open={showVersions}
          onOpenChange={setShowVersions}
          onRestored={handleRestored}
          getCurrentContent={async () =>
            (await editorRef.current?.getMarkdown()) ?? ""
          }
        />
      )}
    </div>
  );
}
