"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Globe,
  Terminal,
  FileText,
  Play,
  CheckCircle2,
  Loader2,
  Save,
  X,
  AlertCircle,
  Settings,
  RefreshCw,
  FolderOpen,
} from "lucide-react";
import React, { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";

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
import { scraperApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

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

interface Draft {
  id: string;
  source_url: string;
  source_title?: string;
  schema_name: string;
  schema_display_name?: string;
  title: string;
  tags: string[];
  status: string;
  created_at: string;
}

interface WebScraperProps {
  onSave?: (title: string, content: string) => void;
  onOpenDraftBox?: () => void;
}

export default function WebScraper({ onSave, onOpenDraftBox }: WebScraperProps) {
  // 状态
  const [url, setUrl] = useState("");
  const [prompt, setPrompt] = useState("提取网页中的所有重要信息，整理成Markdown格式。");
  const [provider, setProvider] = useState("browser_use_local");
  const [schemaName, setSchemaName] = useState<string>("general");

  const [isScraping, setIsScraping] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [schemas, setSchemas] = useState<SchemaOption[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 加载Provider和Schema列表（scraperApi 已自动带 Token）
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [provRes, schemaRes] = await Promise.all([
          scraperApi.listProviders(),
          scraperApi.listSchemas(),
        ]);
        setProviders(provRes.providers || []);
        setSchemas(schemaRes.schemas || []);
      } catch (e) {
        console.error("加载配置失败:", e);
      }
    };
    loadOptions();
  }, []);

  // 自动滚动
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // 清理
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  // 提交任务
  const handleStart = useCallback(async () => {
    if (!url) return;

    // 验证URL
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

    try {
      // 1. 创建任务（scraperApi 自动带 Token，401 时 request() 会跳转登录页）
      const { task_id } = await scraperApi.scrape({
        url,
        prompt,
        provider,
        schema_name: schemaName,
      });
      setTaskId(task_id);

      // 2. 建立SSE连接
      const apiBase = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";
      const eventSource = new EventSource(
        `${apiBase}/api/extensions/web-scraper/stream/${task_id}`
      );
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (e) => {
        try {
          // 后端发送格式: "data: {json}\n\n"，去掉前缀再解析
          const raw = e.data.trim();
          if (!raw) return;
          const jsonStr = raw.replace(/^data:\s*/, "");
          if (!jsonStr) return;
          const data: LogEntry = JSON.parse(jsonStr);
          if (data.type === "heartbeat") return;

          setLogs((prev) => [...prev, data]);

          if (data.type === "result" && data.content) {
            setResult(data.content);
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
  }, [url, prompt, provider, schemaName]);

  // 停止任务
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

  // 重置
  const handleReset = useCallback(() => {
    eventSourceRef.current?.close();
    setUrl("");
    setPrompt("提取网页中的所有重要信息，整理成Markdown格式。");
    setProvider("browser_use_local");
    setSchemaName("general");
    setResult(null);
    setError(null);
    setLogs([]);
    setTaskId(null);
    setIsScraping(false);
  }, []);

  // 保存到草稿箱
  const handleSaveToDraft = useCallback(async () => {
    if (!result) return;

    const selectedSchema = schemas.find((s) => s.name === schemaName);

    try {
      await scraperApi.createDraft({
        source_url: url,
        source_title: url,
        schema_name: schemaName,
        schema_display_name: selectedSchema?.display_name,
        raw_content: result,
        structured_data: undefined,
        title: `爬取-${new URL(url).hostname}-${new Date().toLocaleDateString()}`,
        tags: [],
        category: selectedSchema?.category,
      });

      alert("已保存到草稿箱");
      handleReset();
    } catch (e) {
      console.error("保存草稿失败:", e);
      alert("保存草稿箱失败");
    }
  }, [result, url, schemaName, schemas, handleReset]);

  // 保存回调
  const handleSave = useCallback(() => {
    if (result) {
      const title = url ? `网页抓取 - ${new URL(url).hostname}` : "网页抓取报告";
      onSave?.(title, result);
    }
  }, [result, url, onSave]);

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
        <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
          <Globe className="w-5 h-5 text-primary" />
          AI 网页爬取
        </h2>
        <div className="flex items-center gap-3">
          <p className="text-sm text-muted-foreground">
            基于 Browser Use 的智能数据提取
          </p>
          <button
            onClick={onOpenDraftBox}
            className="px-3 py-1.5 text-sm border rounded-lg hover:bg-muted flex items-center gap-2"
          >
            <FolderOpen className="w-4 h-4" />
            草稿箱
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className={cn(
              "p-2 rounded-lg transition-colors",
              showSettings
                ? "bg-indigo-600 text-white"
                : "hover:bg-muted"
            )}
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden bg-muted/30">
        <div className="flex-1 flex m-6 rounded-2xl bg-card shadow-sm overflow-hidden">
          {/* Left: Config */}
          <div className="w-1/2 border-r flex flex-col">
            <div className="p-6 space-y-4">
              {/* URL */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  目标 URL
                </label>
                <Input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com"
                  disabled={isScraping || !!result}
                  className="w-full bg-background"
                />
              </div>

              {/* Provider + Schema */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label
                    htmlFor="web-scraper-provider"
                    className="text-sm font-medium text-foreground"
                  >
                    Provider
                  </label>
                  <Select
                    value={provider}
                    onValueChange={setProvider}
                    disabled={isScraping || !!result}
                  >
                    <SelectTrigger
                      id="web-scraper-provider"
                      className="w-full bg-background"
                      size="default"
                    >
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
                  <label
                    htmlFor="web-scraper-schema"
                    className="text-sm font-medium text-foreground"
                  >
                    Schema
                  </label>
                  <Select
                    value={schemaName}
                    onValueChange={setSchemaName}
                    disabled={isScraping || !!result}
                  >
                    <SelectTrigger
                      id="web-scraper-schema"
                      className="w-full bg-background"
                      size="default"
                    >
                      <SelectValue placeholder="选择数据 Schema" />
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

              {/* Prompt */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  提取指令
                </label>
                <Textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  disabled={isScraping || !!result}
                  className="min-h-[5.5rem] w-full resize-none bg-background"
                />
              </div>

              {/* 高级设置折叠 */}
              <AnimatePresence>
                {showSettings && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="border-t pt-3 text-sm text-muted-foreground">
                      <p>高级设置（代理、认证等）开发中...</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

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
                      className="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                      开始抓取
                    </button>
                  )
                ) : (
                  <>
                    <button
                      onClick={handleSaveToDraft}
                      className="flex-1 py-2.5 bg-blue-600 text-white rounded-lg flex items-center justify-center gap-2"
                    >
                      <Save className="w-4 h-4" />
                      保存草稿
                    </button>
                    <button
                      onClick={handleSave}
                      className="flex-1 py-2.5 bg-muted rounded-lg flex items-center justify-center gap-2"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      直接使用
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Logs */}
            <div className="flex-1 bg-zinc-900 mx-6 mb-6 rounded-xl p-4 font-mono text-sm overflow-hidden flex flex-col">
              <div className="flex items-center gap-2 mb-3 text-zinc-400 border-b border-zinc-800 pb-2">
                <Terminal className="w-4 h-4" />
                <span>Execution Logs</span>
                {isScraping && (
                  <span className="ml-auto text-xs flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
                    Running
                  </span>
                )}
              </div>
              <div className="flex-1 overflow-y-auto space-y-1 text-emerald-400">
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
                    <AlertCircle className="w-4 h-4" />
                    {error}
                  </div>
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>

          {/* Right: Result */}
          <div className="w-1/2 flex flex-col bg-muted/30">
            <div className="px-6 py-4 border-b bg-card flex items-center justify-between">
              <h3 className="font-medium flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-500" />
                提取结果{" "}
                {selectedSchema && (
                  <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded">
                    {selectedSchema.display_name}
                  </span>
                )}
              </h3>
              {result && (
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveToDraft}
                    className="px-3 py-1.5 text-sm border rounded-lg flex items-center gap-1"
                  >
                    <Save className="w-3 h-3" />
                    存草稿
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {result ? (
                <div className="prose prose-sm max-w-none bg-card p-6 rounded-xl shadow-sm">
                  <ReactMarkdown>{result}</ReactMarkdown>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                  <FileText className="w-12 h-12 mb-3 text-muted-foreground/30" />
                  <p>抓取结果将显示在这里</p>
                  {selectedSchema?.description && (
                    <p className="text-xs mt-2">{selectedSchema.description}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
