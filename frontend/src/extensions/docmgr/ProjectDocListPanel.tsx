"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  FileText,
  Grid3X3,
  List,
  Search,
} from "lucide-react";
import React, { useCallback, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { AIDocument } from "../types";

import { formatFileSize } from "./FilePreviewModal";
import { useDocuments } from "./useDocuments";
import { useProjectOutputs, type ProjectDocFile } from "./useProjectOutputs";

// ─── File Type Helpers (rich SVG icon system, matching FileRefCard) ─────────

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

function formatUpdatedAt(dateStr: string | undefined): string {
  if (!dateStr) return "";
  return new Date(dateStr)
    .toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
    .replace(/\//g, "/");
}

// ─── SVG Symbol Paths ────────────────────────────────────────────────────────

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
  const gid = size === "lg" ? `psheen-${fileType}` : `psheen-sm-${fileType}`;
  const cid = size === "lg" ? `pfold-${fileType}` : `pfold-sm-${fileType}`;

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
      </defs>
      <g clipPath={`url(#${cid})`}>
        <rect width="20" height="24" fill={config.primary} />
        <path
          d="M13 1V5.5C13 7.4 14.6 9 16.5 9H20V9L13 1Z"
          fill="rgba(0,0,0,0.12)"
        />
      </g>
      <path
        d="M2 1H13L20 8V22C20 23.1 19.1 24 18 24H2C0.9 24 0 23.1 0 22V3C0 1.9 0.9 1 2 1Z"
        className="stroke-black/8"
        strokeWidth="0.3"
        fill="none"
      />
    </svg>
  );
}

// ─── Component ──────────────────────────────────────────────────────────────

// EAI-CUSTOM (bug-1145 根因④ Surface A): 项目 outputs 文件 → AIDocument 形状。带 project_id +
// source_thread_id + file_ref_path，点击时 onSelectDoc 传给 EditorTab，由其分支路由到
// DocumentEditor（跨用户 readProjectOutput/saveProjectContent 直读/写磁盘）。id 用 proj/ 前缀。
function adaptProjectOutput(pf: ProjectDocFile, projectId: string): AIDocument {
  return {
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
  };
}

interface ProjectDocListPanelProps {
  projectId: string;
  onSelectDoc: (doc: AIDocument) => void;
}

export default function ProjectDocListPanel({
  projectId,
  onSelectDoc,
}: ProjectDocListPanelProps) {
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const { docs, total, loading, page, pageSize, setPage, setFilter } =
    useDocuments({
      project_scope: "project",
      project_id: projectId,
    });

  // EAI-CUSTOM (bug-1145 根因④ Surface A): 聚合项目 outputs 文件系统视图——把 agent 未走
  // present_files（如 bash cp）落盘到 thread outputs/ 的文件也显示出来。已被 present_files
  // 回调同步为 AIDocument 的 file_ref 按线程/rel_path 去重，避免重复显示。
  const projectOutputs = useProjectOutputs(projectId);
  const syncedKeys = useMemo(() => {
    const s = new Set<string>();
    for (const d of docs)
      if (d.source_thread_id && d.file_ref_path)
        s.add(`${d.source_thread_id}/${d.file_ref_path}`);
    return s;
  }, [docs]);
  const extraDocs: AIDocument[] = projectOutputs.files
    .filter((pf) => !syncedKeys.has(`${pf.thread_id}/${pf.rel_path}`))
    .map((pf) => adaptProjectOutput(pf, projectId));
  const displayDocs = [...docs, ...extraDocs];

  const totalPages = Math.ceil(total / pageSize);

  const handleSearch = useCallback(
    (value: string) => {
      setSearch(value);
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        setFilter((f) => ({ ...f, q: value || undefined }));
      }, 400);
    },
    [setFilter],
  );

  return (
    <div className="bg-background flex h-full flex-col">
      {/* Toolbar */}
      <div className="border-border flex h-12 shrink-0 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <div className="relative w-56">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <Input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="搜索项目文档..."
              className="h-8 w-full pr-4 pl-9 text-sm"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="border-border bg-card flex h-7 items-center overflow-hidden rounded border">
            <button
              onClick={() => setViewMode("grid")}
              className={cn(
                "flex h-7 w-7 items-center justify-center transition-colors",
                viewMode === "grid"
                  ? "text-foreground bg-muted"
                  : "text-muted-foreground",
              )}
              title="网格视图"
            >
              <Grid3X3 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={cn(
                "flex h-7 w-7 items-center justify-center transition-colors",
                viewMode === "list"
                  ? "text-foreground bg-muted"
                  : "text-muted-foreground",
              )}
              title="列表视图"
            >
              <List className="h-3.5 w-3.5" />
            </button>
          </div>
          <span className="text-muted-foreground text-xs whitespace-nowrap">
            共 {total} 篇文档
          </span>
        </div>
      </div>

      {/* Content area */}
      <div className="bg-muted/30 flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-muted-foreground flex h-32 items-center justify-center text-sm">
            加载中...
          </div>
        ) : displayDocs.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center text-center">
            <Archive className="text-muted-foreground/30 mb-3 h-10 w-10" />
            <p className="text-muted-foreground text-sm font-medium">
              暂无项目文档
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              项目工作流产出的文件会出现在这里
            </p>
          </div>
        ) : viewMode === "grid" ? (
          <AnimatePresence>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {displayDocs.map((doc) => (
                <ProjectDocCard
                  key={doc.id}
                  doc={doc}
                  onClick={() => onSelectDoc(doc)}
                />
              ))}
            </div>
          </AnimatePresence>
        ) : (
          <div className="bg-background border-border overflow-hidden rounded-lg border shadow-sm">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-border bg-muted/50 border-b">
                  <th className="text-muted-foreground px-4 py-2.5 text-xs font-semibold tracking-wider uppercase">
                    名称
                  </th>
                  <th className="text-muted-foreground px-4 py-2.5 text-xs font-semibold tracking-wider uppercase">
                    类型
                  </th>
                  <th className="text-muted-foreground px-4 py-2.5 text-xs font-semibold tracking-wider uppercase">
                    大小
                  </th>
                  <th className="text-muted-foreground px-4 py-2.5 text-xs font-semibold tracking-wider uppercase">
                    更新时间
                  </th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {displayDocs.map((doc) => {
                  const ft = getFileType(
                    doc.file_mime,
                    doc.title,
                    doc.doc_type,
                  );
                  const cfg = FILE_ICON_CONFIG[ft] ?? FILE_ICON_CONFIG.text!;
                  const fileSize = formatFileSize(doc.file_size);
                  return (
                    <tr
                      key={doc.id}
                      className="hover:bg-muted/50 group cursor-pointer transition-colors"
                      onClick={() => onSelectDoc(doc)}
                    >
                      <td className="px-4 py-3">
                        <div className="flex min-w-0 items-center gap-2.5">
                          <FileTypeIcon
                            mime={doc.file_mime}
                            title={doc.title}
                            docType={doc.doc_type}
                            size="sm"
                          />
                          <span className="text-foreground group-hover:text-primary truncate text-sm font-medium transition-colors">
                            {doc.title || "无标题"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
                          style={{
                            backgroundColor: cfg.primary + "18",
                            color: cfg.primary,
                          }}
                        >
                          {cfg.label}
                        </span>
                      </td>
                      <td className="text-muted-foreground px-4 py-3 text-sm">
                        {fileSize || "—"}
                      </td>
                      <td className="text-muted-foreground px-4 py-3 text-sm">
                        {formatUpdatedAt(doc.updated_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="border-border bg-background flex shrink-0 items-center justify-end gap-2 border-t px-4 py-2.5">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="mr-1 h-4 w-4" />
            上一页
          </Button>
          <span className="text-muted-foreground px-2 text-xs">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            下一页
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Grid Card (matches FileRefCard style from DocumentManagement) ──────────

function ProjectDocCard({
  doc,
  onClick,
}: {
  doc: AIDocument;
  onClick: () => void;
}) {
  const isFileRef = doc.doc_type === "file_ref";
  const fileSize = formatFileSize(doc.file_size);
  const updatedAt = formatUpdatedAt(doc.updated_at);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="bg-background border-border group hover:border-primary/50 flex h-48 cursor-pointer flex-col rounded-xl border p-4 transition-all hover:shadow-md"
      onClick={onClick}
    >
      {/* Icon area */}
      <div className="mb-4 flex flex-1 items-center justify-center overflow-hidden">
        {isFileRef ? (
          <FileTypeIcon
            mime={doc.file_mime}
            title={doc.title}
            docType={doc.doc_type}
            size="lg"
          />
        ) : (
          <div className="bg-primary/10 flex h-14 w-12 items-center justify-center rounded-lg">
            <FileText className="text-primary h-6 w-6" />
          </div>
        )}
      </div>

      {/* Title */}
      <h3 className="text-foreground group-hover:text-primary mb-2 line-clamp-1 text-sm font-medium transition-colors">
        {doc.title || "无标题"}
      </h3>

      {/* Meta */}
      <div className="text-muted-foreground mt-auto flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          {fileSize && <span>{fileSize}</span>}
          {updatedAt && <span>{updatedAt}</span>}
        </div>
      </div>
    </motion.div>
  );
}
