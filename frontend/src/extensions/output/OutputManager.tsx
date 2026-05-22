"use client";

import { FileText, History, LayoutGrid, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { outputApi } from "./api";
import { LayoutTemplateCard } from "./components/LayoutTemplateCard";
import { OutputConfigPanel } from "./components/OutputConfigPanel";
import { OutputProgress } from "./components/OutputProgress";
import type { GenerateOutputRequest, GenerateOutputResult, LayoutTemplate } from "./types";

type TabId = "templates" | "generate" | "history";

const NAV_ITEMS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "templates", label: "排版模板", icon: LayoutGrid },
  { id: "generate", label: "生成输出", icon: FileText },
  { id: "history", label: "历史记录", icon: History },
];

function TemplatesTab() {
  const [templates, setTemplates] = useState<LayoutTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await outputApi.listTemplates();
      setTemplates(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模板失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mb-4 h-8 w-8 animate-spin" />
        <span>加载模板中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-destructive">
        <span className="mb-2 text-lg">加载失败</span>
        <span className="mb-4 text-sm text-muted-foreground">{error}</span>
        <button
          type="button"
          className="rounded-lg bg-destructive px-4 py-2 text-sm text-white hover:bg-destructive/90"
          onClick={() => void loadTemplates()}
        >
          重试
        </button>
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <FileText className="mb-4 h-12 w-12" />
        <span className="mb-2 text-lg">暂无排版模板</span>
        <span className="text-sm">请先在知识工厂中创建排版模板</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {templates.map((template) => (
        <LayoutTemplateCard key={template.id} template={template} />
      ))}
    </div>
  );
}

function GenerateTab() {
  const [templates, setTemplates] = useState<LayoutTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [result, setResult] = useState<GenerateOutputResult | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    outputApi
      .listTemplates()
      .then(setTemplates)
      .catch(() => {
        // Templates are optional for the config panel
      });
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setPolling(false);
  }, []);

  const startPolling = useCallback(
    (taskId: string) => {
      setPolling(true);
      pollingRef.current = setInterval(async () => {
        try {
          const status = await outputApi.getTaskStatus(taskId);
          setResult(status);
          if (status.status === "completed" || status.status === "failed") {
            stopPolling();
          }
        } catch {
          stopPolling();
        }
      }, 3000);
    },
    [stopPolling],
  );

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const handleGenerate = useCallback(
    async (req: GenerateOutputRequest) => {
      setLoading(true);
      setResult(null);
      try {
        const res = await outputApi.generate(req);
        setResult(res);
        if (res.status === "queued" || res.status === "processing") {
          startPolling(res.taskId);
        }
      } catch (err) {
        setResult({
          taskId: "",
          status: "failed",
        });
      } finally {
        setLoading(false);
      }
    },
    [startPolling],
  );

  const handleRetry = useCallback(() => {
    setResult(null);
  }, []);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <OutputConfigPanel
        templates={templates}
        onGenerate={handleGenerate}
        loading={loading}
      />
      <OutputProgress
        result={result}
        polling={polling}
        onRetry={handleRetry}
      />
    </div>
  );
}

interface HistoryItem {
  taskId: string;
  projectId: string;
  format: string;
  status: GenerateOutputResult["status"];
  fileName?: string;
  downloadUrl?: string;
  createdAt: string;
}

function HistoryTab() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Placeholder — will connect to real API when available
    setLoading(false);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <History className="mb-4 h-12 w-12" />
        <span className="mb-2 text-lg">暂无生成记录</span>
        <span className="text-sm">生成报告后将在此处显示历史记录</span>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50 text-left text-xs font-medium text-muted-foreground">
            <th className="px-4 py-3">项目</th>
            <th className="px-4 py-3">格式</th>
            <th className="px-4 py-3">状态</th>
            <th className="px-4 py-3">文件名</th>
            <th className="px-4 py-3">时间</th>
            <th className="px-4 py-3">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((item) => (
            <tr key={item.taskId} className="hover:bg-muted/30">
              <td className="px-4 py-3 text-foreground">{item.projectId}</td>
              <td className="px-4 py-3 text-foreground">{item.format}</td>
              <td className="px-4 py-3">
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                    item.status === "completed"
                      ? "bg-success/10 text-success"
                      : item.status === "failed"
                        ? "bg-destructive/10 text-destructive"
                        : "bg-primary/10 text-primary",
                  )}
                >
                  {item.status === "completed" ? "已完成" : item.status === "failed" ? "失败" : "进行中"}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{item.fileName ?? "-"}</td>
              <td className="px-4 py-3 text-muted-foreground">{item.createdAt}</td>
              <td className="px-4 py-3">
                {item.downloadUrl && (
                  <a
                    href={item.downloadUrl}
                    download={item.fileName}
                    className="text-primary hover:underline"
                  >
                    下载
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OutputManager() {
  const params = useSearchParams();
  const currentTab = (params.get("tab") ?? "templates") as TabId;

  return (
    <div className="flex flex-col h-full bg-muted">
      {/* Tab Header */}
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <span className="font-bold text-lg tracking-tight text-foreground mr-8">
          报告输出
        </span>
        <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const href = `/output?tab=${id}`;
            const isActive = currentTab === id;
            return (
              <Link
                key={id}
                href={href}
                className={cn(
                  "flex items-center gap-2 h-full transition-colors py-5 border-b-2",
                  isActive
                    ? "text-primary border-primary"
                    : "border-transparent hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 bg-background">
        {currentTab === "templates" && <TemplatesTab />}
        {currentTab === "generate" && <GenerateTab />}
        {currentTab === "history" && <HistoryTab />}
      </div>
    </div>
  );
}
