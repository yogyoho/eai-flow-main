"use client";

import { Archive, ChevronLeft, ChevronRight, FileText, Grid3X3, List, Search } from "lucide-react";
import React, { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { AIDocument } from "../types";

import { formatFileSize } from "./FilePreviewModal";
import { useDocuments } from "./useDocuments";

// ─── File Type Helpers (lightweight, reused from DocumentManagement) ──────────

interface FileIconConfig {
  primary: string;
  label: string;
}

const FILE_TYPE_CONFIG: Record<string, FileIconConfig> = {
  markdown: { primary: "#0EA5E9", label: "MD" },
  python: { primary: "#8B5CF6", label: "PY" },
  javascript: { primary: "#EAB308", label: "JS" },
  typescript: { primary: "#3B82F6", label: "TS" },
  json: { primary: "#F97316", label: "JSON" },
  html: { primary: "#EF4444", label: "HTML" },
  css: { primary: "#06B6D4", label: "CSS" },
  pdf: { primary: "#DC2626", label: "PDF" },
  word: { primary: "#2563EB", label: "DOC" },
  excel: { primary: "#16A34A", label: "XLS" },
  csv: { primary: "#65A30D", label: "CSV" },
  image: { primary: "#D946EF", label: "IMG" },
  text: { primary: "#94A3B8", label: "TXT" },
  xml: { primary: "#EA580C", label: "XML" },
  yaml: { primary: "#EC4899", label: "YML" },
  shell: { primary: "#22C55E", label: "SH" },
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

function formatUpdatedAt(dateStr: string | undefined): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).replace(/\//g, "/");
}

// ─── Component ──────────────────────────────────────────────────────────────

interface ProjectDocListPanelProps {
  projectId: string;
  projectName: string;
  onSelectDoc: (doc: AIDocument) => void;
}

export default function ProjectDocListPanel({ projectId, projectName, onSelectDoc }: ProjectDocListPanelProps) {
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const { docs, total, loading, page, pageSize, setPage, setFilter } = useDocuments({
    project_scope: "project",
    folder: projectName,
  });

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
    <div className="flex flex-col h-full bg-background">
      {/* Toolbar */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative w-56">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="搜索项目文档..."
              className="w-full pl-9 pr-4 h-8 text-sm"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex h-7 items-center overflow-hidden rounded border border-border bg-card">
            <button
              onClick={() => setViewMode("grid")}
              className={cn(
                "flex h-7 w-7 items-center justify-center transition-colors",
                viewMode === "grid" ? "text-foreground bg-muted" : "text-muted-foreground",
              )}
              title="网格视图"
            >
              <Grid3X3 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={cn(
                "flex h-7 w-7 items-center justify-center transition-colors",
                viewMode === "list" ? "text-foreground bg-muted" : "text-muted-foreground",
              )}
              title="列表视图"
            >
              <List className="h-3.5 w-3.5" />
            </button>
          </div>
          <span className="text-xs text-muted-foreground whitespace-nowrap">共 {total} 篇文档</span>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto p-4 bg-muted/30">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">加载中...</div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-center">
            <Archive className="w-10 h-10 text-muted-foreground/30 mb-3" />
            <p className="text-sm font-medium text-muted-foreground">暂无项目文档</p>
            <p className="text-xs text-muted-foreground/70 mt-1">项目工作流产出的文件会出现在这里</p>
          </div>
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {docs.map((doc) => (
              <ProjectDocCard key={doc.id} doc={doc} onClick={() => onSelectDoc(doc)} />
            ))}
          </div>
        ) : (
          <div className="bg-background border border-border rounded-lg shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="py-2.5 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">名称</th>
                  <th className="py-2.5 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">类型</th>
                  <th className="py-2.5 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">大小</th>
                  <th className="py-2.5 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">更新时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {docs.map((doc) => {
                  const isFileRef = doc.doc_type === "file_ref";
                  const ft = getFileType(doc.file_mime, doc.title);
                  const cfg = FILE_TYPE_CONFIG[ft] ?? FILE_TYPE_CONFIG.text!;
                  return (
                    <tr
                      key={doc.id}
                      className="hover:bg-muted/50 transition-colors cursor-pointer group"
                      onClick={() => onSelectDoc(doc)}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2.5 min-w-0">
                          {isFileRef ? (
                            <FileTypeBadge config={cfg} />
                          ) : (
                            <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                          )}
                          <span className="font-medium text-foreground text-sm truncate group-hover:text-primary transition-colors">
                            {doc.title || "无标题"}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {isFileRef ? (
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold"
                            style={{ backgroundColor: cfg.primary + "18", color: cfg.primary }}
                          >
                            {cfg.label}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-400 text-[11px] font-semibold">
                            DOC
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-sm text-muted-foreground">
                        {isFileRef ? formatFileSize(doc.file_size) : "—"}
                      </td>
                      <td className="py-3 px-4 text-sm text-muted-foreground">
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
        <div className="px-4 py-2.5 border-t border-border flex items-center justify-end gap-2 shrink-0 bg-background">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft className="w-4 h-4 mr-1" />
            上一页
          </Button>
          <span className="text-xs text-muted-foreground px-2">
            {page} / {totalPages}
          </span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            下一页
            <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Grid Card ──────────────────────────────────────────────────────────────

function ProjectDocCard({ doc, onClick }: { doc: AIDocument; onClick: () => void }) {
  const isFileRef = doc.doc_type === "file_ref";
  const ft = getFileType(doc.file_mime, doc.title);
  const cfg = FILE_TYPE_CONFIG[ft] ?? FILE_TYPE_CONFIG.text!;
  const fileSize = isFileRef ? formatFileSize(doc.file_size) : "";
  const updatedAt = formatUpdatedAt(doc.updated_at);

  return (
    <div
      className="bg-background rounded-xl border border-border p-3.5 cursor-pointer transition-all flex flex-col h-44 group hover:shadow-md hover:border-primary/50"
      onClick={onClick}
    >
      {/* Icon area */}
      <div className="flex-1 mb-3 flex items-center justify-center overflow-hidden">
        {isFileRef ? (
          <FileTypeBadge config={cfg} large />
        ) : (
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <FileText className="w-5 h-5 text-primary" />
          </div>
        )}
      </div>

      {/* Title */}
      <h3 className="font-medium text-foreground text-sm line-clamp-1 mb-2 group-hover:text-primary transition-colors">
        {doc.title || "无标题"}
      </h3>

      {/* Meta */}
      <div className="flex items-center justify-between text-muted-foreground text-xs mt-auto">
        <div className="flex items-center gap-2">
          {fileSize && <span>{fileSize}</span>}
        </div>
        {updatedAt && <span>{updatedAt}</span>}
      </div>
    </div>
  );
}

// ─── File Type Badge ────────────────────────────────────────────────────────

function FileTypeBadge({ config, large }: { config: FileIconConfig; large?: boolean }) {
  if (large) {
    return (
      <div
        className="w-14 h-14 rounded-xl flex items-center justify-center text-base font-bold"
        style={{ backgroundColor: config.primary + "18", color: config.primary }}
      >
        {config.label}
      </div>
    );
  }
  return (
    <span
      className="inline-flex items-center justify-center w-5 h-6 rounded-sm text-[8px] font-bold shrink-0"
      style={{ backgroundColor: config.primary + "18", color: config.primary }}
    >
      {config.label}
    </span>
  );
}
