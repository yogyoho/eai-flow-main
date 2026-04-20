"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Globe,
  Terminal,
  FileText,
  Play,
  Loader2,
  X,
  AlertCircle,
  ArrowLeft,
  Plus,
  Sparkles,
  Download,
  ChevronUp,
  ChevronDown,
} from "lucide-react";
import React, { useState, useEffect, useRef, useCallback } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { scraperApi, modelsApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { useCreateLaw } from "../hooks/useLawLibrary";
import type { LawType } from "@/extensions/knowledge-factory/types";

// TipTap imports
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "tiptap-markdown";

interface LogEntry {
  type: "log" | "result" | "error" | "heartbeat" | "cancelled";
  level?: "info" | "success" | "error" | "warning";
  message?: string;
  content?: string;
}

interface ProviderOption {
  name: string;
  display_name?: string;
  supports_structured: boolean;
  is_primary: boolean;
}

const PROVIDER_LABELS: Record<string, string> = {
  browser_use_local: "Browser Use local",
  jina: "Jina",
  firecrawl: "Firecrawl",
};

const DEFAULT_PROVIDER_OPTIONS: ProviderOption[] = [
  { name: "browser_use_local", supports_structured: true, is_primary: true },
  { name: "jina", supports_structured: false, is_primary: false },
  { name: "firecrawl", supports_structured: false, is_primary: false },
];

function formatProviderLabel(p: ProviderOption): string {
  const base = p.display_name?.trim() || PROVIDER_LABELS[p.name] || p.name;
  return p.is_primary ? `${base}（推荐）` : `${base}（降级）`;
}

interface SchemaOption {
  name: string;
  display_name: string;
  description: string;
  category: string;
  supports_structured: boolean;
}

interface ModelOption {
  name: string;
  display_name?: string;
  description?: string;
}

interface LawScraperViewProps {
  onBack: () => void;
  onImportSuccess?: () => void;
}

export default function LawScraperView({ onBack, onImportSuccess }: LawScraperViewProps) {
  // Scraping states
  const [url, setUrl] = useState("");
  const [prompt, setPrompt] = useState(
    "提取网页中的法规标准信息，包括：标题、编号、发布部门、生效日期、章节结构和全文内容。"
  );
  const [provider, setProvider] = useState("browser_use_local");
  const [schemaName, setSchemaName] = useState<string>("general");

  const [isScraping, setIsScraping] = useState(false);
  /** 执行日志抽屉：固定在左侧面板底部，向上展开 */
  const [logDrawerExpanded, setLogDrawerExpanded] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExtractingPdf, setIsExtractingPdf] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);

  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [schemas, setSchemas] = useState<SchemaOption[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [llmModel, setLlmModel] = useState<string>("");
  const [loading, setLoading] = useState(false);

  // Import states
  const [showImportForm, setShowImportForm] = useState(false);
  const [importForm, setImportForm] = useState({
    title: "",
    law_number: "",
    law_type: "technical" as LawType,
    department: "",
    effective_date: "",
    keywords: "",
    content: "",
    raw_content: "",
  });

  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const editorContainerRef = useRef<HTMLDivElement>(null);

  const createLawMutation = useCreateLaw();

  // TipTap editor with Markdown support
  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3, 4, 5, 6] },
        }),
        Link.configure({
          openOnClick: false,
          HTMLAttributes: {
            target: "_blank",
            rel: "noopener noreferrer",
          },
        }),
        Placeholder.configure({
          placeholder: "爬取结果将显示在这里，可以直接编辑...",
        }),
        Markdown.configure({
          html: false,
          tightLists: true,
          tightListClass: "tight",
          bulletListMarker: "-",
          linkify: false,
          breaks: false,
          transformPastedText: true,
          transformCopiedText: false,
        }),
      ],
      content: "",
      editorProps: {
        attributes: {
          class: "prose prose-sm max-w-none focus:outline-none min-h-[300px] px-4 py-3",
        },
      },
      immediatelyRender: false,
    },
    []
  );

  // Get markdown content from editor
  const getMarkdownContent = useCallback(() => {
    if (!editor) return "";
    const markdownStorage = editor.storage as { markdown?: { getMarkdown: () => string } };
    return markdownStorage.markdown?.getMarkdown() || "";
  }, [editor]);

  // Update editor content when result changes
  useEffect(() => {
    if (editor && result) {
      editor.commands.setContent(result);
    }
  }, [editor, result]);

  // Handle PDF links in editor
  useEffect(() => {
    if (!editor) return;

    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const link = target.closest("a");
      if (link && link.href?.toLowerCase().includes(".pdf")) {
        event.preventDefault();
        window.open(link.href, "_blank");
      }
    };

    const container = editorContainerRef.current;
    container?.addEventListener("click", handleClick);

    return () => {
      container?.removeEventListener("click", handleClick);
    };
  }, [editor]);

  // Load Provider, Schema, and Model lists
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [provRes, schemaRes, modelRes] = await Promise.all([
          scraperApi.listProviders(),
          scraperApi.listSchemas(),
          modelsApi.list(),
        ]);
        setProviders(provRes.providers || []);
        setSchemas(schemaRes.schemas || []);
        setModels(modelRes.models || []);
        if (modelRes.models && modelRes.models.length > 0) {
          const firstModel = modelRes.models[0];
          if (firstModel?.name) {
            setLlmModel(firstModel.name);
          }
        }

        // Auto-select regulatory schema if available
        const regulatorySchemas = schemaRes.schemas?.filter(
          (s: SchemaOption) => s.category === "法规标准"
        );
        if (regulatorySchemas && regulatorySchemas.length > 0) {
          const firstSchema = regulatorySchemas[0];
          if (firstSchema?.name) {
            setSchemaName(firstSchema.name);
          }
        }
      } catch (e) {
        console.error("加载配置失败:", e);
      }
    };
    loadOptions();
  }, []);

  // Auto scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // Cleanup
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  // Start scraping
  const handleStart = useCallback(async () => {
    if (!url) return;

    try {
      new URL(url);
    } catch {
      setError("请输入有效的URL地址");
      return;
    }

    setLoading(true);
    setIsScraping(true);
    setLogs([]);
    setResult(null);
    setError(null);
    setShowImportForm(false);

    try {
      const { task_id } = await scraperApi.scrape({
        url,
        prompt,
        provider,
        schema_name: schemaName,
        llm_model: llmModel || undefined,
      });
      setTaskId(task_id);

      const apiBase = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";
      const eventSource = new EventSource(
        `${apiBase}/api/extensions/web-scraper/stream/${task_id}`
      );
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (e) => {
        try {
          const raw = e.data.trim();
          if (!raw) return;
          const jsonStr = raw.replace(/^data:\s*/, "");
          if (!jsonStr) return;
          const data: LogEntry = JSON.parse(jsonStr);
          if (data.type === "heartbeat") return;

          setLogs((prev) => [...prev, data]);

          if (data.type === "result" && data.content) {
            setResult(data.content);
            // Auto-populate title from URL
            try {
              const hostname = new URL(url).hostname;
              setImportForm((prev) => ({
                ...prev,
                title: `爬取-${hostname}`,
                content: data.content || "",
                raw_content: data.content || "",
              }));
            } catch {
              // ignore
            }
          }
          if (data.type === "error") {
            setError(data.message || "执行失败");
          }
          if (data.type === "result" || data.type === "error" || data.type === "cancelled") {
            setIsScraping(false);
            eventSource.close();
          }
        } catch (err) {
          console.error("解析SSE失败:", err);
        }
      };

      eventSource.onerror = () => {
        setError("SSE连接断开");
        setIsScraping(false);
        eventSource.close();
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : "发起任务失败");
      setIsScraping(false);
    } finally {
      setLoading(false);
    }
  }, [url, prompt, provider, schemaName, llmModel]);

  // Stop scraping
  const handleStop = useCallback(async () => {
    if (taskId) {
      try {
        await scraperApi.cancel(taskId);
      } catch (e) {
        console.error("取消任务失败:", e);
      }
    }
    eventSourceRef.current?.close();
    setIsScraping(false);
  }, [taskId]);

  // Reset
  const handleReset = useCallback(() => {
    eventSourceRef.current?.close();
    setUrl("");
    setPrompt("提取网页中的法规标准信息，包括：标题、编号、发布部门、生效日期、章节结构和全文内容。");
    setProvider("browser_use_local");
    setSchemaName("general");
    setLlmModel(models.at(0)?.name ?? "");
    setResult(null);
    setError(null);
    setLogs([]);
    setTaskId(null);
    setIsScraping(false);
    setShowImportForm(false);
    if (editor) {
      editor.commands.clearContent();
    }
    setImportForm({
      title: "",
      law_number: "",
      law_type: "technical",
      department: "",
      effective_date: "",
      keywords: "",
      content: "",
      raw_content: "",
    });
  }, [editor, models]);

  // Extract PDF content
  const handleExtractPdf = async () => {
    const markdownContent = getMarkdownContent();
    const pdfMatch = markdownContent.match(/https?:\/\/[^\s"'\n<>]+\.pdf[^\s"'\n<>]*/i);
    if (!pdfMatch) {
      alert("未找到PDF链接，请确认爬取结果中包含PDF下载地址。");
      return;
    }
    setIsExtractingPdf(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";
      const res = await fetch(`${apiBase}/api/extensions/web-scraper/extract-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pdf_url: pdfMatch[0] }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "提取失败");
      }
      const { content } = await res.json();
      if (editor) {
        editor.commands.insertContent(`\n\n---\n\n## PDF全文\n\n${content}`);
      }
    } catch (e) {
      console.error("PDF提取失败:", e);
      alert(`PDF提取失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIsExtractingPdf(false);
    }
  };

  // Import law
  const handleImport = useCallback(async () => {
    if (!importForm.title.trim()) {
      alert("请输入法规标题");
      return;
    }

    const markdownContent = getMarkdownContent();

    try {
      await createLawMutation.mutateAsync({
        title: importForm.title.trim(),
        law_number: importForm.law_number.trim() || undefined,
        law_type: importForm.law_type,
        status: "active",
        department: importForm.department.trim() || undefined,
        effective_date: importForm.effective_date || undefined,
        content: markdownContent || importForm.content || undefined,
        keywords: importForm.keywords
          ? importForm.keywords.split(",").map((k) => k.trim()).filter(Boolean)
          : undefined,
      });

      alert("法规导入成功！");
      onImportSuccess?.();
      handleReset();
    } catch (e) {
      console.error("导入失败:", e);
      alert("导入失败，请重试");
    }
  }, [importForm, createLawMutation, onImportSuccess, handleReset, getMarkdownContent]);

  const selectedSchema = schemas.find((s) => s.name === schemaName);
  const providerOptions =
    providers.length > 0 ? providers : DEFAULT_PROVIDER_OPTIONS;
  const regulatorySchemas = schemas.filter((s) => s.category === "法规标准");
  const generalSchemas = schemas.filter((s) => s.category === "通用");

  const getLogColor = (level?: string) => {
    switch (level) {
      case "success":
        return "text-emerald-400";
      case "error":
        return "text-red-400";
      case "warning":
        return "text-amber-400";
      default:
        return "text-emerald-400";
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            返回列表
          </button>
          <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
            <Globe className="w-5 h-5 text-blue-500" />
            爬取新法规
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          从网页智能提取法规标准内容
        </p>
      </div>

      {/* Content — two independent columns */}
      <div className="flex-1 flex overflow-hidden bg-muted/30 p-6 gap-6">
        {/* ============ Left: Config + Import Form + Logs (fixed width) ============ */}
        <div className="w-[480px] shrink-0 flex flex-col bg-card rounded-2xl border shadow-sm overflow-hidden">
          {/* Config area — scrollable */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {/* URL */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                目标 URL
              </label>
              <Input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.gov.cn/..."
                disabled={isScraping || !!result}
                className="w-full bg-background"
              />
            </div>

            {/* Provider + Schema */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">爬取引擎</label>
                <Select
                  value={provider}
                  onValueChange={setProvider}
                  disabled={isScraping || !!result}
                >
                  <SelectTrigger className="w-full bg-background" size="default">
                    <SelectValue placeholder="选择爬取引擎" />
                  </SelectTrigger>
                  <SelectContent position="popper" className="z-[100]">
                    {providerOptions.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {formatProviderLabel(p)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">数据 Schema</label>
                <Select
                  value={schemaName}
                  onValueChange={setSchemaName}
                  disabled={isScraping || !!result}
                >
                  <SelectTrigger className="w-full bg-background" size="default">
                    <SelectValue placeholder="选择 Schema" />
                  </SelectTrigger>
                  <SelectContent position="popper" className="z-[100] max-h-72">
                    <SelectGroup>
                      <SelectLabel>法规标准类</SelectLabel>
                      {regulatorySchemas.length > 0 ? (
                        regulatorySchemas.map((s) => (
                          <SelectItem key={s.name} value={s.name}>
                            {s.display_name}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="__reg_empty" disabled>
                          暂无
                        </SelectItem>
                      )}
                    </SelectGroup>
                    <SelectSeparator />
                    <SelectGroup>
                      <SelectLabel>通用类</SelectLabel>
                      {generalSchemas.length > 0 ? (
                        generalSchemas.map((s) => (
                          <SelectItem key={s.name} value={s.name}>
                            {s.display_name}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="__gen_empty" disabled>
                          暂无
                        </SelectItem>
                      )}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* LLM Model selector — browser_use_local 需要本地 LLM */}
            {provider === "browser_use_local" && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  LLM 模型
                  {models.length === 0 && (
                    <span className="ml-2 text-xs text-amber-500 font-normal">
                      （系统未配置模型，请联系管理员）
                    </span>
                  )}
                </label>
                <Select
                  value={llmModel}
                  onValueChange={setLlmModel}
                  disabled={isScraping || !!result || models.length === 0}
                >
                  <SelectTrigger className="w-full bg-background" size="default">
                    <SelectValue placeholder="选择 LLM 模型" />
                  </SelectTrigger>
                  <SelectContent position="popper" className="z-[100] max-h-72">
                    {models.length > 0 ? (
                      models.map((m) => (
                        <SelectItem key={m.name} value={m.name}>
                          {m.display_name || m.name}
                          {m.description ? ` — ${m.description}` : ""}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="__no_models" disabled>
                        暂无可用模型
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Prompt */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">提取指令</label>
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                disabled={isScraping || !!result}
                className="min-h-[5.5rem] w-full resize-none bg-background"
              />
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              {!result ? (
                isScraping ? (
                  <button
                    onClick={handleStop}
                    className="flex-1 py-2.5 bg-red-600 text-white rounded-lg flex items-center justify-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    停止
                  </button>
                ) : (
                  <button
                    onClick={handleStart}
                    disabled={!url || loading}
                    className="flex-1 py-2.5 bg-blue-600 text-white rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 hover:bg-blue-700 transition-colors"
                  >
                    {loading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                    开始爬取
                  </button>
                )
              ) : (
                <button
                  onClick={handleReset}
                  className="flex-1 py-2.5 bg-muted rounded-lg flex items-center justify-center gap-2 hover:bg-accent transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  重新爬取
                </button>
              )}
            </div>

            {/* Import Form — slides in below config */}
            <AnimatePresence>
              {showImportForm && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                  className="overflow-hidden"
                >
                  <div className="pt-4 space-y-3 border-t">
                    <h4 className="font-medium flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-indigo-500" />
                      导入信息
                    </h4>
                    <div>
                      <label className="text-xs text-muted-foreground">标题</label>
                      <Input
                        value={importForm.title}
                        onChange={(e) =>
                          setImportForm((p) => ({ ...p, title: e.target.value }))
                        }
                        placeholder="法规标题"
                        className="mt-1 bg-background"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-muted-foreground">标准号</label>
                        <Input
                          value={importForm.law_number}
                          onChange={(e) =>
                            setImportForm((p) => ({ ...p, law_number: e.target.value }))
                          }
                          placeholder="如：GB 12345-2023"
                          className="mt-1 bg-background"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">发布部门</label>
                        <Input
                          value={importForm.department}
                          onChange={(e) =>
                            setImportForm((p) => ({ ...p, department: e.target.value }))
                          }
                          placeholder="如：生态环境部"
                          className="mt-1 bg-background"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-muted-foreground">法规类型</label>
                        <Select
                          value={importForm.law_type}
                          onValueChange={(v) =>
                            setImportForm((p) => ({ ...p, law_type: v as LawType }))
                          }
                        >
                          <SelectTrigger className="mt-1 bg-background">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="law">法律</SelectItem>
                            <SelectItem value="regulation">行政法规</SelectItem>
                            <SelectItem value="rule">部门规章</SelectItem>
                            <SelectItem value="national">国家标准</SelectItem>
                            <SelectItem value="industry">行业标准</SelectItem>
                            <SelectItem value="local">地方标准</SelectItem>
                            <SelectItem value="technical">技术规范</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">生效日期</label>
                        <Input
                          type="date"
                          value={importForm.effective_date}
                          onChange={(e) =>
                            setImportForm((p) => ({ ...p, effective_date: e.target.value }))
                          }
                          className="mt-1 bg-background"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">关键词（逗号分隔）</label>
                      <Input
                        value={importForm.keywords}
                        onChange={(e) =>
                          setImportForm((p) => ({ ...p, keywords: e.target.value }))
                        }
                        placeholder="如：环保, 安全, 化工"
                        className="mt-1 bg-background"
                      />
                    </div>
                    <button
                      onClick={handleImport}
                      disabled={createLawMutation.isPending}
                      className="w-full py-2.5 bg-indigo-600 text-white rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 hover:bg-indigo-700 transition-colors"
                    >
                      {createLawMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Plus className="w-4 h-4" />
                      )}
                      导入到法规库
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Logs — fixed at bottom of left panel, expands upward */}
          <div className="shrink-0 border-t border-zinc-800/30 bg-zinc-900">
            {/* Always-visible header bar */}
            <div
              className="flex items-center gap-2 px-3 py-2.5 text-zinc-400 cursor-pointer select-none"
              onClick={() => setLogDrawerExpanded(!logDrawerExpanded)}
            >
              <Terminal className="h-4 w-4 shrink-0" />
              <span className="text-sm">执行日志</span>
              {logs.length > 0 && (
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                  {logs.length}
                </span>
              )}
              {isScraping && (
                <span className="ml-1 flex items-center gap-1.5 text-xs text-emerald-400/90">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                  运行中
                </span>
              )}
              <div className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setLogDrawerExpanded(!logDrawerExpanded);
                  }}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
                >
                  {logDrawerExpanded ? (
                    <>
                      <ChevronDown className="h-3.5 w-3.5" />
                      收起
                    </>
                  ) : (
                    <>
                      <ChevronUp className="h-3.5 w-3.5" />
                      展开
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Expandable log content — grows upward */}
            <AnimatePresence initial={false}>
              {logDrawerExpanded && (
                <motion.div
                  key="log-content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 320, opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                  className="overflow-hidden"
                >
                  <div className="h-full space-y-1 overflow-y-auto px-3 py-2 font-mono text-sm">
                    {logs.map((log, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className={getLogColor(log.level)}
                      >
                        <span className="text-zinc-600">
                          [{new Date().toLocaleTimeString()}]
                        </span>{" "}
                        {log.message}
                      </motion.div>
                    ))}
                    {error && (
                      <div className="text-red-400 flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 shrink-0" />
                        {error}
                      </div>
                    )}
                    <div ref={logsEndRef} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* ============ Right: Result (flex-1, independent) ============ */}
        <div className="flex-1 min-h-0 flex flex-col bg-card rounded-2xl border shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b shrink-0 flex items-center justify-between">
            <h3 className="font-medium flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-500" />
              爬取结果
              {selectedSchema && (
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                  {selectedSchema.display_name}
                </span>
              )}
            </h3>
            {result && !showImportForm && (
              <>
                {/pdf/i.test(result) && (
                  <button
                    onClick={handleExtractPdf}
                    disabled={isExtractingPdf}
                    className="px-3 py-1.5 text-sm border rounded-lg flex items-center gap-1 hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    {isExtractingPdf ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Download className="w-3 h-3" />
                    )}
                    提取PDF全文
                  </button>
                )}
                <button
                  onClick={() => setShowImportForm(true)}
                  className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg flex items-center gap-1 hover:bg-indigo-700 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  导入法规
                </button>
              </>
            )}
            {showImportForm && (
              <button
                onClick={() => setShowImportForm(false)}
                className="px-3 py-1.5 text-sm border rounded-lg flex items-center gap-1 hover:bg-accent transition-colors"
              >
                <X className="w-3 h-3" />
                取消
              </button>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-hidden p-6">
            {result ? (
              <div
                ref={editorContainerRef}
                className="h-full overflow-y-auto bg-card border rounded-xl"
              >
                <EditorContent
                  editor={editor}
                  className="h-full [&_.tiptap]:h-full [&_.tiptap]:overflow-y-auto [&_.tiptap]:prose prose-sm dark:prose-invert max-w-none [&_.tiptap]:px-4 [&_.tiptap]:py-3 [&_.tiptap]:leading-relaxed [&_.tiptap_p]:my-2 [&_.tiptap_p]:text-sm [&_.tiptap_h1]:text-xl [&_.tiptap_h1]:font-bold [&_.tiptap_h1]:mt-4 [&_.tiptap_h1]:mb-2 [&_.tiptap_h2]:text-lg [&_.tiptap_h2]:font-semibold [&_.tiptap_h2]:mt-3 [&_.tiptap_h2]:mb-2 [&_.tiptap_h3]:text-base [&_.tiptap_h3]:font-medium [&_.tiptap_a]:text-blue-600 [&_.tiptap_a:hover]:underline [&_.tiptap_code]:bg-muted [&_.tiptap_code]:px-1 [&_.tiptap_code]:rounded [&_.tiptap_code]:font-mono [&_.tiptap_pre]:bg-muted [&_.tiptap_pre]:rounded [&_.tiptap_pre]:p-2 [&_.tiptap_ul]:list-disc [&_.tiptap_ul]:pl-6 [&_.tiptap_ol]:list-decimal [&_.tiptap_ol]:pl-6 [&_.tiptap_blockquote]:border-l-4 [&_.tiptap_blockquote]:border-muted-foreground [&_.tiptap_blockquote]:pl-4 [&_.tiptap_blockquote]:italic [&_.tiptap_hr]:border-muted [&_.tiptap_hr]:my-4 [&_.tiptap_table]:border-collapse [&_.tiptap_table]:w-full [&_.tiptap_th]:border [&_.tiptap_th]:border-muted [&_.tiptap_th]:p-2 [&_.tiptap_th]:bg-muted [&_.tiptap_td]:border [&_.tiptap_td]:border-muted [&_.tiptap_td]:p-2"
                />
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                <FileText className="w-12 h-12 mb-3 text-muted-foreground/30" />
                <p>爬取结果将显示在这里</p>
                <p className="text-xs mt-2">输入URL后点击"开始爬取"</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Missing icon component
function RefreshCw({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}
