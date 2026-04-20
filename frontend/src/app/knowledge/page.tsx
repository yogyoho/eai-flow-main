"use client";

import { motion, AnimatePresence } from "framer-motion";
import DOMPurify from "isomorphic-dompurify";
import {
  Search,
  Plus,
  Database,
  FileText,
  RefreshCw,
  Trash2,
  Edit,
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronDown,
  Copy,
  Edit3,
  ArrowRightToLine,
  Search as SearchIcon,
  X,
  Upload,
  Clock,
  Loader2,
  Settings,
} from "lucide-react";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import { kbApi } from "@/extensions/api";
import type {
  KnowledgeBase,
  Document,
  CreateKnowledgeBaseRequest,
  UpdateKnowledgeBaseRequest,
} from "@/extensions/types";

// ─── helpers ────────────────────────────────────────────────────────────────

function formatDate(dateString: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const KB_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "ragflow", label: "RAGFlow" },
  { value: "pageindex", label: "PageIndex" },
];

function knowledgeBaseTypeLabel(kbType: string | undefined): string {
  if (!kbType) return "RAGFlow";
  return KB_TYPE_OPTIONS.find((o) => o.value === kbType)?.label ?? kbType;
}

// ─── Toast ───────────────────────────────────────────────────────────────────

type ToastType = "success" | "error" | "info";
interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[];
  onRemove: (id: number) => void;
}) {
  return (
    <div className="pointer-events-none fixed right-6 bottom-6 z-[100] flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "pointer-events-auto flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg",
              t.type === "success" &&
                "border-success/20 bg-success/10 text-success",
              t.type === "error" && "border-destructive/20 bg-destructive/10 text-destructive",
              t.type === "info" && "border-primary/20 bg-primary/10 text-primary",
            )}
          >
            {t.type === "success" && (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            )}
            {t.type === "error" && <AlertCircle className="h-4 w-4 shrink-0" />}
            {t.type === "info" && <RefreshCw className="h-4 w-4 shrink-0" />}
            <span>{t.message}</span>
            <button
              onClick={() => onRemove(t.id)}
              className="ml-1 opacity-60 transition-opacity hover:opacity-100"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const show = useCallback((message: string, type: ToastType = "info") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      3500,
    );
  }, []);
  const remove = useCallback(
    (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    [],
  );
  return { toasts, show, remove };
}

// ─── Custom Select component ──────────────────────────────────────────────────

interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

function CustomSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm",
          "border bg-background transition-all duration-150",
          open
            ? "border-primary shadow-sm ring-2 ring-ring/50"
            : "border-input hover:border-input hover:shadow-sm",
        )}
      >
        <span
          className={cn(
            "flex min-w-0 items-center gap-2",
            selected ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {selected?.icon && (
            <span className="shrink-0 text-muted-foreground">{selected.icon}</span>
          )}
          <span className="truncate">{selected?.label ?? "请选择"}</span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-background shadow-lg shadow-black/5"
          >
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors",
                  o.value === value
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-foreground hover:bg-muted",
                )}
              >
                {o.icon && (
                  <span
                    className={cn(
                      "shrink-0",
                      o.value === value ? "text-primary" : "text-muted-foreground",
                    )}
                  >
                    {o.icon}
                  </span>
                )}
                {o.label}
                {o.value === value && (
                  <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0 text-primary" />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Doc status badge ─────────────────────────────────────────────────────────

function DocStatusBadge({ status }: { status: string }) {
  if (status === "success" || status === "done")
    return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (status === "uploading" || status === "processing" || status === "pending")
    return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (status === "failed" || status === "error")
    return <AlertCircle className="h-4 w-4 text-destructive" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

// ─── Upload Modal ─────────────────────────────────────────────────────────────

function UploadModal({
  kbId,
  onClose,
  onUploaded,
  toast,
}: {
  kbId: string;
  onClose: () => void;
  onUploaded: () => void;
  toast: (msg: string, type?: ToastType) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = (newFiles: FileList | null) => {
    if (!newFiles) return;
    setFiles((prev) => [...prev, ...Array.from(newFiles)]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    let success = 0;
    for (const file of files) {
      try {
        await kbApi.uploadDoc(kbId, file);
        success++;
      } catch (e: any) {
        toast(`${file.name} 上传失败: ${e?.message ?? "未知错误"}`, "error");
      }
    }
    setUploading(false);
    if (success > 0) {
      toast(`成功上传 ${success} 个文件`, "success");
      onUploaded();
      onClose();
    }
  };

  return (
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
        className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-lg font-semibold text-foreground">上传文件</h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="space-y-4 p-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors",
              dragOver
                ? "border-primary bg-primary/10"
                : "border-input hover:border-primary/50 hover:bg-muted",
            )}
          >
            <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              拖拽文件到此处，或点击选择
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              支持 PDF、Word、TXT、Markdown 等格式
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />
          </div>
          {files.length > 0 && (
            <div className="max-h-40 space-y-2 overflow-y-auto">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg bg-muted px-3 py-2 text-sm"
                >
                  <span className="flex-1 truncate text-foreground">
                    {f.name}
                  </span>
                  <span className="ml-2 shrink-0 text-muted-foreground">
                    {formatFileSize(f.size)}
                  </span>
                  <button
                    onClick={() =>
                      setFiles((prev) => prev.filter((_, j) => j !== i))
                    }
                    className="ml-2 shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
          <Button
            variant="outline"
            onClick={onClose}
          >
            取消
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!files.length || uploading}
          >
            {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
            上传
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Chunk HTML body (sanitized) ─────────────────────────────────────────────

function chunkRawText(chunk: {
  content?: string;
  content_with_weight?: string;
  [k: string]: unknown;
}): string {
  const c = chunk.content ?? chunk.content_with_weight;
  return c != null ? String(c) : "";
}

/** Heuristic: RAGFlow often stores chunks as HTML fragments (tables, etc.). */
function looksLikeHtmlFragment(s: string): boolean {
  return /<\/?[a-z][\s\S]*?>/i.test(s);
}

function ChunkHtmlBody({ raw }: { raw: string }) {
  const safeHtml = useMemo(() => {
    if (!raw.trim()) return "";
    if (!looksLikeHtmlFragment(raw)) return "";
    return DOMPurify.sanitize(raw, {
      USE_PROFILES: { html: true },
      ADD_ATTR: ["colspan", "rowspan", "align", "valign", "width", "height"],
    });
  }, [raw]);

  if (!raw.trim()) {
    return <p className="text-sm text-muted-foreground">（无文本内容）</p>;
  }

  if (!safeHtml.trim()) {
    return (
      <p className="max-h-[min(50vh,28rem)] overflow-auto rounded-lg bg-background/80 p-3 text-sm break-words whitespace-pre-wrap text-foreground/80">
        {raw}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "chunk-html-body max-h-[min(50vh,28rem)] overflow-auto rounded-lg bg-background/80 p-3 text-sm text-foreground/80",
        "[&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
        "[&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top",
        "[&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1.5 [&_th]:font-medium",
        "[&_tr:nth-child(even)]:bg-muted/80",
        "[&_br]:block [&_p]:my-1",
        "[&_img]:h-auto [&_img]:max-w-full",
      )}
       
      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  );
}

// ─── ChunkModal ───────────────────────────────────────────────────────────────

function ChunkModal({
  kbId,
  doc,
  onClose,
  toast,
}: {
  kbId: string;
  doc: Document;
  onClose: () => void;
  toast: (msg: string, type?: ToastType) => void;
}) {
  const [chunks, setChunks] = useState<
    Array<{ id?: string; content?: string; [k: string]: unknown }>
  >([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await kbApi.listChunks(kbId, doc.id, {
          page: 1,
          size: 200,
        });
        if (!cancelled) {
          setChunks(res.chunks || []);
          setTotal(res.total ?? 0);
        }
      } catch (e: any) {
        if (!cancelled) toast(e?.message ?? "加载分片失败", "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [kbId, doc.id, toast]);

  return (
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
        className="relative flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-foreground">分片数据</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {doc.name} · 共 {total} 个分片
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : chunks.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              {total === 0
                ? "暂无分片数据（文档可能尚未解析完成）"
                : "暂无更多分片"}
            </div>
          ) : (
            <div className="space-y-4">
              {chunks.map((chunk, idx) => (
                <div
                  key={chunk.id ?? idx}
                  className="rounded-xl border border-border bg-muted/50 p-4"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">
                      分片 #{idx + 1}
                    </span>
                    {chunk.id && (
                      <span
                        className="max-w-[280px] truncate font-mono text-xs text-muted-foreground/70"
                        title={String(chunk.id)}
                      >
                        {chunk.id}
                      </span>
                    )}
                  </div>
                  <ChunkHtmlBody raw={chunkRawText(chunk)} />
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}

// ─── KnowledgeBaseDetail ─────────────────────────────────────────────────────

function KnowledgeBaseDetail({
  kb,
  onBack,
  toast,
  onKbUpdated,
}: {
  kb: KnowledgeBase;
  onBack: () => void;
  toast: (msg: string, type?: ToastType) => void;
  onKbUpdated?: (kb: KnowledgeBase) => void;
}) {
  const [activeTab, setActiveTab] = useState<"test" | "config">("test");
  const [isFormatted, setIsFormatted] = useState(false);
  const [query, setQuery] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResult, setChatResult] = useState<{
    answer?: string;
    sources?: any[];
  } | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [fileSearch, setFileSearch] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [showEditKb, setShowEditKb] = useState(false);
  const [showChunksDoc, setShowChunksDoc] = useState<Document | null>(null);
  const [editForm, setEditForm] = useState<UpdateKnowledgeBaseRequest>({
    name: kb.name,
    description: kb.description ?? "",
    kb_type: kb.kb_type ?? "ragflow",
  });
  const [editLoading, setEditLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setEditForm({
      name: kb.name,
      description: kb.description ?? "",
      kb_type: kb.kb_type ?? "ragflow",
    });
  }, [kb.id, kb.name, kb.description, kb.kb_type]);

  // Config tab state
  const [topK, setTopK] = useState(5);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.2);

  const loadDocs = useCallback(async () => {
    try {
      const res = await kbApi.listDocs(kb.id, { limit: 200 });
      setDocs(res.documents);
      return res.documents;
    } catch (e: any) {
      toast(e?.message ?? "加载文档失败", "error");
      return [];
    } finally {
      setDocsLoading(false);
    }
  }, [kb.id, toast]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  // Poll while any doc is in processing state
  useEffect(() => {
    const hasProcessing = docs.some((d) =>
      ["uploading", "processing", "pending"].includes(d.status),
    );
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(loadDocs, 3000);
    } else if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [docs, loadDocs]);

  const handleDeleteDoc = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除该文件吗？")) return;
    try {
      await kbApi.deleteDoc(kb.id, docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      toast("文件已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setChatLoading(true);
    setChatResult(null);
    try {
      const result = await kbApi.chat(kb.id, {
        query,
        top_k: topK,
        similarity_threshold: similarityThreshold,
      });
      setChatResult(result as any);
    } catch (e: any) {
      toast(e?.message ?? "检索失败", "error");
    } finally {
      setChatLoading(false);
    }
  };

  const handleEditSave = async () => {
    setEditLoading(true);
    try {
      const updated = await kbApi.update(kb.id, editForm);
      onKbUpdated?.(updated);
      toast("知识库信息已更新", "success");
      setShowEditKb(false);
    } catch (e: any) {
      toast(e?.message ?? "更新失败", "error");
    } finally {
      setEditLoading(false);
    }
  };

  const filteredDocs = docs.filter((d) =>
    d.name.toLowerCase().includes(fileSearch.toLowerCase()),
  );

  return (
    <div className="flex h-full gap-4 overflow-hidden p-6">
      {/* Left Pane */}
      <div className="flex w-1/2 flex-col gap-4 overflow-hidden">
        {/* Header Card */}
        <div className="shrink-0 rounded-xl border border-border bg-background p-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                onClick={onBack}
              >
                <ChevronLeft className="h-5 w-5" />
              </Button>
              <h2 className="text-lg font-semibold text-foreground">{kb.name}</h2>
              <span className="rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
                ID: {kb.id}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() =>
                  navigator.clipboard
                    .writeText(kb.id)
                    .then(() => toast("ID 已复制", "success"))
                }
                title="复制 ID"
              >
                <Copy className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowEditKb(true)}
                title="编辑"
              >
                <Edit3 className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            {kb.description || "暂无描述"}
          </p>
        </div>

        {/* File List Card */}
        <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-border bg-background">
          <div className="flex shrink-0 items-center justify-between border-b border-border p-4">
            <Button
              variant="ghost"
              onClick={() => setShowUpload(true)}
              className="text-foreground hover:text-primary"
            >
              <Plus className="h-4 w-4" />
              添加文件
            </Button>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Input
                  type="text"
                  placeholder="搜索文件名"
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="w-48 pr-8"
                />
                <Search className="absolute top-1/2 right-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => loadDocs()}
                title="刷新"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon">
                <ArrowRightToLine className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="w-10 px-4 py-3 font-medium">
                    <input
                      type="checkbox"
                    />
                  </th>
                  <th className="px-4 py-3 font-medium">文件名</th>
                  <th className="w-28 px-4 py-3 font-medium">上传时间</th>
                  <th className="w-16 px-4 py-3 font-medium">状态</th>
                  <th className="w-20 px-4 py-3 text-right font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {docsLoading ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-sm text-muted-foreground"
                    >
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                    </td>
                  </tr>
                ) : filteredDocs.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-sm text-muted-foreground"
                    >
                      暂无文件
                    </td>
                  </tr>
                ) : (
                  filteredDocs.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => setShowChunksDoc(doc)}
                      className="group cursor-pointer transition-colors hover:bg-muted/50"
                    >
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          className="w-4 h-4 shrink-0 rounded border-input focus:ring-2 focus:ring-ring/30 focus:ring-offset-0"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-primary text-primary-foreground">
                            <span className="text-[10px] leading-none font-bold">
                              {doc.file_type?.toUpperCase().slice(0, 1) ?? "F"}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <span className="block truncate text-foreground">
                              {doc.name}
                            </span>
                            {doc.file_size > 0 && (
                              <span className="text-[10px] text-muted-foreground">
                                {formatFileSize(doc.file_size)}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <DocStatusBadge status={doc.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(e) => handleDeleteDoc(doc.id, e)}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex shrink-0 items-center justify-end border-t border-border p-3 text-xs text-muted-foreground">
            共 {docs.length} 个文件
          </div>
        </div>
      </div>

      {/* Right Pane */}
      <div className="flex w-1/2 flex-col overflow-hidden rounded-xl border border-border bg-background">
        <div className="flex shrink-0 items-center border-b border-border px-4">
          {(["test", "config"] as const).map((tab) => (
            <button
              key={tab}
              className={cn(
                "border-b-2 px-4 py-3 text-sm font-medium transition-colors",
                activeTab === tab
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "test" ? "检索测试" : "检索配置"}
            </button>
          ))}
        </div>

        <div className="flex flex-1 flex-col gap-4 overflow-auto bg-muted/30 p-4">
          {activeTab === "test" && (
            <>
              <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
                <Textarea
                  className="min-h-[120px] w-full resize-none border-0 p-4 text-sm outline-none"
                  placeholder="输入查询内容..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey))
                      handleSearch();
                  }}
                />
                <div className="flex items-center justify-between border-t border-border bg-muted/50 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
                      格式化
                    </span>
                    <button
                      onClick={() => setIsFormatted(!isFormatted)}
                      className={cn(
                        "relative h-4 w-8 rounded-full transition-colors",
                        isFormatted ? "bg-primary" : "bg-muted-foreground/30",
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                          isFormatted ? "translate-x-4" : "translate-x-0",
                        )}
                      />
                    </button>
                  </div>
                  <Button
                    size="icon"
                    onClick={handleSearch}
                    disabled={chatLoading || !query.trim()}
                    className="rounded-full"
                  >
                    {chatLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <SearchIcon className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              {chatResult && (
                <div className="space-y-3">
                  {chatResult.answer && (
                    <div className="rounded-xl border border-primary/10 bg-primary/5 p-4">
                      <h4 className="mb-2 text-sm font-medium text-foreground">
                        回答
                      </h4>
                      <p className="text-sm whitespace-pre-wrap text-foreground/80">
                        {chatResult.answer}
                      </p>
                    </div>
                  )}
                  {chatResult.sources && chatResult.sources.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium text-foreground">
                        参考来源
                      </h4>
                      <div className="space-y-2">
                        {chatResult.sources.map((src: any, idx: number) => (
                          <div
                            key={idx}
                            className="rounded-lg border border-border bg-background p-3 text-xs"
                          >
                            <div className="mb-1 font-medium text-foreground/80">
                              {src.document_name || `来源 ${idx + 1}`}
                            </div>
                            <p className="line-clamp-3 text-muted-foreground">
                              {src.content}
                            </p>
                            {src.score != null && (
                              <div className="mt-1 text-muted-foreground/70">
                                相似度: {(src.score * 100).toFixed(1)}%
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {activeTab === "config" && (
            <div className="space-y-5">
              <div className="space-y-5 rounded-xl border border-border bg-background p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  检索参数
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    Top K{" "}
                    <span className="font-normal text-muted-foreground">
                      （返回结果数量）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={(e) => setTopK(Number(e.target.value))}
                      className="flex-1 accent-primary"
                    />
                    <span className="w-8 text-center text-sm font-medium text-foreground">
                      {topK}
                    </span>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    相似度阈值{" "}
                    <span className="font-normal text-muted-foreground">
                      （过滤低相关结果）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={similarityThreshold}
                      onChange={(e) =>
                        setSimilarityThreshold(Number(e.target.value))
                      }
                      className="flex-1 accent-primary"
                    />
                    <span className="w-10 text-center text-sm font-medium text-foreground">
                      {similarityThreshold.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-4 rounded-xl border border-border bg-background p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  知识库信息
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    {
                      label: "知识库类型",
                      value: knowledgeBaseTypeLabel(kb.kb_type),
                    },
                    { label: "分块方式", value: kb.chunk_method || "naive" },
                    { label: "访问权限", value: kb.access_type },
                    { label: "嵌入模型", value: kb.embedding_model || "默认" },
                    {
                      label: "创建时间",
                      value: new Date(kb.created_at).toLocaleDateString(
                        "zh-CN",
                      ),
                    },
                  ].map(({ label, value }) => (
                    <div
                      key={label}
                      className="rounded-lg border border-border bg-muted/50 p-3"
                    >
                      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
                      <div className="text-sm font-medium text-foreground">
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {showUpload && (
          <UploadModal
            kbId={kb.id}
            onClose={() => setShowUpload(false)}
            onUploaded={loadDocs}
            toast={toast}
          />
        )}
      </AnimatePresence>

      {/* Chunk Modal */}
      <AnimatePresence>
        {showChunksDoc && (
          <ChunkModal
            kbId={kb.id}
            doc={showChunksDoc}
            onClose={() => setShowChunksDoc(null)}
            toast={toast}
          />
        )}
      </AnimatePresence>

      {/* Edit KB Modal */}
      <AnimatePresence>
        {showEditKb && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setShowEditKb(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <h3 className="text-lg font-semibold text-foreground">
                  编辑知识库
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowEditKb(false)}
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <div className="space-y-5 p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    value={editForm.name ?? ""}
                    onChange={(e) =>
                      setEditForm({ ...editForm, name: e.target.value })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库类型
                  </label>
                  <CustomSelect
                    value={editForm.kb_type ?? "ragflow"}
                    onChange={(v) => setEditForm({ ...editForm, kb_type: v })}
                    options={KB_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                      icon:
                        o.value === "ragflow" ? (
                          <Database className="h-3.5 w-3.5" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        ),
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    描述
                  </label>
                  <Textarea
                    value={editForm.description ?? ""}
                    rows={3}
                    onChange={(e) =>
                      setEditForm({ ...editForm, description: e.target.value })
                    }
                    className="w-full resize-none"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setShowEditKb(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleEditSave}
                  disabled={!editForm.name?.trim() || editLoading}
                >
                  {editLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  保存
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── KnowledgeBaseManagement ─────────────────────────────────────────────────

function KnowledgeBaseManagement() {
  const { toasts, show: toast, remove } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateKnowledgeBaseRequest>({
    name: "",
    description: "",
    access_type: "private",
    kb_type: "ragflow",
  });

  // Edit modal
  const [editKb, setEditKb] = useState<KnowledgeBase | null>(null);
  const [editForm, setEditForm] = useState<UpdateKnowledgeBaseRequest>({});
  const [editLoading, setEditLoading] = useState(false);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await kbApi.list({ limit: 500 });
      setKbs(res.knowledge_bases);
    } catch (e: any) {
      toast(e?.message ?? "加载失败", "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredKBs = kbs.filter((kb) => {
    const matchesSearch =
      kb.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (kb.description ?? "").toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType =
      typeFilter === "all" || (kb.kb_type ?? "ragflow") === typeFilter;
    return matchesSearch && matchesType;
  });

  const handleCreate = async () => {
    if (!createForm.name.trim()) return;
    try {
      const kb = await kbApi.create(createForm);
      setKbs((prev) => [kb, ...prev]);
      setIsCreateOpen(false);
      setCreateForm({
        name: "",
        description: "",
        access_type: "private",
        kb_type: "ragflow",
      });
      toast("知识库创建成功", "success");
    } catch (e: any) {
      toast(e?.message ?? "创建失败", "error");
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除该知识库吗？")) return;
    try {
      await kbApi.delete(id);
      setKbs((prev) => prev.filter((kb) => kb.id !== id));
      toast("知识库已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleSync = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSyncingIds((prev) => new Set(prev).add(id));
    try {
      const status = await kbApi.getStatus(id);
      setKbs((prev) =>
        prev.map((kb) =>
          kb.id === id ? { ...kb, status: status.status } : kb,
        ),
      );
      toast("同步状态已刷新", "success");
    } catch (e: any) {
      toast(e?.message ?? "同步失败", "error");
    } finally {
      setSyncingIds((prev) => {
        const s = new Set(prev);
        s.delete(id);
        return s;
      });
    }
  };

  const openEdit = (kb: KnowledgeBase, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditKb(kb);
    setEditForm({
      name: kb.name,
      description: kb.description ?? "",
      access_type: kb.access_type,
      kb_type: kb.kb_type ?? "ragflow",
    });
  };

  const handleEditSave = async () => {
    if (!editKb) return;
    setEditLoading(true);
    try {
      const updated = await kbApi.update(editKb.id, editForm);
      setKbs((prev) => prev.map((kb) => (kb.id === editKb.id ? updated : kb)));
      setEditKb(null);
      toast("知识库信息已更新", "success");
    } catch (e: any) {
      toast(e?.message ?? "更新失败", "error");
    } finally {
      setEditLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    if (status === "active" || status === "done")
      return (
        <div className="flex items-center gap-1.5 rounded-full border border-success/20 bg-success/10 px-2 py-1 text-xs font-medium text-success">
          <CheckCircle2 className="h-3.5 w-3.5" />
          已就绪
        </div>
      );
    if (status === "syncing" || status === "processing")
      return (
        <div className="flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          同步中
        </div>
      );
    if (status === "error" || status === "failed")
      return (
        <div className="flex items-center gap-1.5 rounded-full border border-destructive/20 bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          同步失败
        </div>
      );
    return (
      <div className="flex items-center gap-1.5 rounded-full border border-border bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
        <Clock className="h-3.5 w-3.5" />
        未同步
      </div>
    );
  };

  if (selectedKb) {
    return (
      <KnowledgeBaseDetail
        kb={selectedKb}
        onBack={() => setSelectedKb(null)}
        toast={toast}
        onKbUpdated={(u) => {
          setSelectedKb(u);
          setKbs((prev) => prev.map((x) => (x.id === u.id ? u : x)));
        }}
      />
    );
  }

  return (
    <main className="flex-1 overflow-y-auto bg-muted/50 p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              知识库管理
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              管理 RAGFlow 知识库，上传文档并监控同步状态。
            </p>
          </div>
          <Button onClick={() => setIsCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            新建知识库
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-col items-center justify-between gap-4 rounded-xl border border-border bg-background p-4 shadow-sm sm:flex-row">
          <div className="relative w-full sm:w-64">
            <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索知识库名称或描述..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-muted pl-9 pr-4"
            />
          </div>
          <div className="w-full sm:w-48">
            <CustomSelect
              value={typeFilter}
              onChange={setTypeFilter}
              options={[
                {
                  value: "all",
                  label: "所有类型",
                  icon: <Search className="h-3.5 w-3.5" />,
                },
                {
                  value: "ragflow",
                  label: "RAGFlow",
                  icon: <Database className="h-3.5 w-3.5" />,
                },
                {
                  value: "pageindex",
                  label: "PageIndex",
                  icon: <FileText className="h-3.5 w-3.5" />,
                },
              ]}
            />
          </div>
        </div>

        {/* Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {filteredKBs.map((kb) => {
                const kbType = kb.kb_type ?? "ragflow";
                const isSyncing = syncingIds.has(kb.id);
                return (
                  <motion.div
                    layout
                    key={kb.id}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.2 }}
                    onClick={() => setSelectedKb(kb)}
                    className="group flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md"
                  >
                    <div className="flex-1 p-5">
                      <div className="mb-4 flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              "flex h-10 w-10 items-center justify-center rounded-lg border",
                              kbType === "ragflow"
                                ? "border-primary/20 bg-primary/10 text-primary"
                                : "border-success/20 bg-success/10 text-success",
                            )}
                          >
                            {kbType === "ragflow" ? (
                              <Database className="h-5 w-5" />
                            ) : (
                              <FileText className="h-5 w-5" />
                            )}
                          </div>
                          <div>
                            <h3 className="line-clamp-1 font-semibold text-foreground">
                              {kb.name}
                            </h3>
                            <span
                              className={cn(
                                "mt-0.5 inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                                kbType === "ragflow"
                                  ? "bg-primary/10 text-primary"
                                  : "bg-success/10 text-success",
                              )}
                            >
                              {knowledgeBaseTypeLabel(kbType)}
                            </span>
                          </div>
                        </div>
                        {getStatusBadge(kb.status)}
                      </div>

                      <p className="mb-4 line-clamp-2 h-10 text-sm text-muted-foreground">
                        {kb.description || "暂无描述"}
                      </p>

                      <div className="grid grid-cols-3 gap-3 border-t border-border py-3">
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            知识库类型
                          </div>
                          <div
                            className="truncate text-sm font-medium text-foreground"
                            title={knowledgeBaseTypeLabel(kbType)}
                          >
                            {knowledgeBaseTypeLabel(kbType)}
                          </div>
                        </div>
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            创建时间
                          </div>
                          <div className="text-sm font-medium text-foreground">
                            {new Date(kb.created_at).toLocaleDateString(
                              "zh-CN",
                            )}
                          </div>
                        </div>
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            分块方式
                          </div>
                          <div className="truncate text-sm font-medium text-foreground">
                            {kb.chunk_method || "naive"}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-border bg-muted/50 px-5 py-3">
                      <div className="text-xs text-muted-foreground">
                        {kb.owner_name || "未知"}
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => handleSync(kb.id, e)}
                          disabled={isSyncing}
                          className="text-muted-foreground hover:bg-primary/10 hover:text-primary"
                          title="同步状态"
                        >
                          <RefreshCw
                            className={cn(
                              "h-4 w-4",
                              isSyncing && "animate-spin",
                            )}
                          />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => openEdit(kb, e)}
                          className="text-muted-foreground hover:bg-muted hover:text-foreground"
                          title="编辑"
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => handleDelete(kb.id, e)}
                          className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          title="删除"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {filteredKBs.length === 0 && (
              <div className="col-span-full rounded-xl border border-dashed border-border bg-background py-12 text-center">
                <Database className="mx-auto mb-3 h-12 w-12 text-muted-foreground/50" />
                <h3 className="text-sm font-medium text-foreground">
                  未找到知识库
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  尝试调整搜索词或筛选条件
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsCreateOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center gap-3 border-b border-border bg-muted/50 px-6 py-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Database className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg leading-tight font-semibold text-foreground">
                    新建知识库
                  </h3>
                  <div className="text-xs text-muted-foreground">
                    创建一个新的文档知识库
                  </div>
                </div>
              </div>
              <div className="space-y-5 p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    value={createForm.name}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, name: e.target.value })
                    }
                    className="w-full"
                    placeholder="例如：产品操作手册"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    访问权限
                  </label>
                  <CustomSelect
                    value={createForm.access_type ?? "private"}
                    onChange={(v) =>
                      setCreateForm({ ...createForm, access_type: v })
                    }
                    options={[
                      {
                        value: "private",
                        label: "私有",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center text-xs">
                            🔒
                          </span>
                        ),
                      },
                      {
                        value: "public",
                        label: "公开",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🌐
                          </span>
                        ),
                      },
                      {
                        value: "dept",
                        label: "部门可见",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🏢
                          </span>
                        ),
                      },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库类型
                  </label>
                  <CustomSelect
                    value={createForm.kb_type ?? "ragflow"}
                    onChange={(v) =>
                      setCreateForm({ ...createForm, kb_type: v })
                    }
                    options={KB_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                      icon:
                        o.value === "ragflow" ? (
                          <Database className="h-3.5 w-3.5" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        ),
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    描述
                  </label>
                  <Textarea
                    value={createForm.description ?? ""}
                    rows={3}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        description: e.target.value,
                      })
                    }
                    className="w-full resize-none"
                    placeholder="简要描述该知识库的用途或包含的内容..."
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!createForm.name.trim()}
                >
                  创建
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Modal */}
      <AnimatePresence>
        {editKb && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setEditKb(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <h3 className="text-lg font-semibold text-foreground">
                  编辑知识库
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setEditKb(null)}
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <div className="space-y-5 p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    value={editForm.name ?? ""}
                    onChange={(e) =>
                      setEditForm({ ...editForm, name: e.target.value })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    访问权限
                  </label>
                  <CustomSelect
                    value={editForm.access_type ?? "private"}
                    onChange={(v) =>
                      setEditForm({ ...editForm, access_type: v })
                    }
                    options={[
                      {
                        value: "private",
                        label: "私有",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center text-xs">
                            🔒
                          </span>
                        ),
                      },
                      {
                        value: "public",
                        label: "公开",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🌐
                          </span>
                        ),
                      },
                      {
                        value: "dept",
                        label: "部门可见",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🏢
                          </span>
                        ),
                      },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库类型
                  </label>
                  <CustomSelect
                    value={editForm.kb_type ?? "ragflow"}
                    onChange={(v) => setEditForm({ ...editForm, kb_type: v })}
                    options={KB_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                      icon:
                        o.value === "ragflow" ? (
                          <Database className="h-3.5 w-3.5" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        ),
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    描述
                  </label>
                  <Textarea
                    value={editForm.description ?? ""}
                    rows={3}
                    onChange={(e) =>
                      setEditForm({ ...editForm, description: e.target.value })
                    }
                    className="w-full resize-none"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setEditKb(null)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleEditSave}
                  disabled={!editForm.name?.trim() || editLoading}
                >
                  {editLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  保存
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <ToastContainer toasts={toasts} onRemove={remove} />
    </main>
  );
}

// ─── Page export ─────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  return (
    <SimpleShellLayout>
      <KnowledgeBaseManagement />
    </SimpleShellLayout>
  );
}
