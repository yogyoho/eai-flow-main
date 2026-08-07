"use client";

import {
  FileOutput,
  FileText,
  History,
  LayoutGrid,
  Loader2,
  Plus,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

import { outputApi } from "./api";
import { LayoutTemplateCard } from "./components/LayoutTemplateCard";
import { LayoutTemplateEditor } from "./components/LayoutTemplateEditor";
import { OutputConfigPanel } from "./components/OutputConfigPanel";
import { OutputProgress } from "./components/OutputProgress";
import type {
  GenerateOutputRequest,
  GenerateOutputResult,
  LayoutTemplate,
} from "./types";

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
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<LayoutTemplate | null>(
    null,
  );
  // L1: list responses carry only a lightweight cover_master (no xml/images);
  // the editor needs the full template, so fetch detail on edit-open.
  const [editingPendingId, setEditingPendingId] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await outputApi.listTemplates();
      setTemplates(data);
    } catch (err) {
      if ((err as Error & { status?: number })?.status === 404) {
        setTemplates([]);
      } else {
        setError(err instanceof Error ? err.message : "加载模板失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const handleCreateSave = useCallback(
    async (
      data: Omit<
        LayoutTemplate,
        "id" | "isBuiltin" | "createdAt" | "updatedAt"
      >,
    ) => {
      await outputApi.createTemplate(data);
      toast.success("模板已创建");
      setShowEditor(false);
      void loadTemplates();
    },
    [loadTemplates],
  );

  const handleEditTemplate = useCallback(
    async (t: LayoutTemplate) => {
      if (editingPendingId) {
        toast.info("正在加载模板，请稍候");
        return; // one detail fetch at a time
      }
      setEditingPendingId(t.id);
      try {
        // bound the fetch so a hung request can't leave editingPendingId stuck
        let timer: ReturnType<typeof setTimeout> | undefined;
        const full = await Promise.race([
          outputApi.getTemplate(t.id),
          new Promise<never>((_, reject) => {
            timer = setTimeout(
              () => reject(new Error("加载模板详情超时")),
              15000,
            );
          }),
        ]).finally(() => clearTimeout(timer));
        setEditingTemplate(full);
      } catch (err) {
        // do NOT open the editor with the stripped list template — saving it
        // would send cover_master missing required xml (422).
        toast.error(err instanceof Error ? err.message : "加载模板详情失败");
      } finally {
        setEditingPendingId(null);
      }
    },
    [editingPendingId],
  );

  const handleEditSave = useCallback(
    async (
      data: Omit<
        LayoutTemplate,
        "id" | "isBuiltin" | "createdAt" | "updatedAt"
      >,
    ) => {
      if (!editingTemplate) return;
      await outputApi.updateTemplate(editingTemplate.id, data);
      toast.success("模板已更新");
      setEditingTemplate(null);
      void loadTemplates();
    },
    [editingTemplate, loadTemplates],
  );

  if (loading) {
    return (
      <div className="text-muted-foreground flex flex-col items-center justify-center py-16">
        <Loader2 className="mb-4 h-8 w-8 animate-spin" />
        <span>加载模板中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-destructive flex flex-col items-center justify-center py-16">
        <span className="mb-2 text-lg">加载失败</span>
        <span className="text-muted-foreground mb-4 text-sm">{error}</span>
        <button
          type="button"
          className="bg-destructive hover:bg-destructive/90 rounded-lg px-4 py-2 text-sm text-white"
          onClick={() => void loadTemplates()}
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-muted-foreground text-sm">
          共 {templates.length} 个模板
        </span>
        <button
          type="button"
          onClick={() => setShowEditor(true)}
          disabled={editingPendingId !== null}
          className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors disabled:cursor-wait disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          新建模板
        </button>
      </div>

      {templates.length === 0 ? (
        <div className="text-muted-foreground flex flex-col items-center justify-center py-16">
          <FileText className="mb-4 h-12 w-12" />
          <span className="mb-2 text-lg">暂无排版模板</span>
          <span className="text-sm">
            点击上方「新建模板」创建第一个排版模板
          </span>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => (
            <LayoutTemplateCard
              key={template.id}
              template={template}
              onEdit={(t) => void handleEditTemplate(t)}
              editingPending={editingPendingId === template.id}
              onRefresh={loadTemplates}
            />
          ))}
        </div>
      )}

      {showEditor && (
        <LayoutTemplateEditor
          template={null}
          onSave={handleCreateSave}
          onCancel={() => setShowEditor(false)}
        />
      )}
      {editingTemplate && (
        <LayoutTemplateEditor
          template={editingTemplate}
          onSave={handleEditSave}
          onCancel={() => setEditingTemplate(null)}
        />
      )}
    </>
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
      pollingRef.current = setInterval(() => {
        void outputApi
          .getTaskStatus(taskId)
          .then((status) => {
            setResult(status);
            if (status.status === "completed" || status.status === "failed") {
              stopPolling();
            }
          })
          .catch(() => stopPolling());
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
      } catch {
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
      <OutputProgress result={result} polling={polling} onRetry={handleRetry} />
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
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await outputApi.listHistory();
      setItems(data);
    } catch (err: unknown) {
      if (
        err instanceof Error &&
        (err as Error & { status: number }).status === 404
      ) {
        setItems([]);
      } else {
        setError(err instanceof Error ? err.message : "加载历史记录失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  if (loading) {
    return (
      <div className="text-muted-foreground flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-destructive flex flex-col items-center justify-center py-16">
        <span className="mb-2 text-lg">加载失败</span>
        <span className="text-muted-foreground mb-4 text-sm">{error}</span>
        <button
          type="button"
          className="bg-destructive hover:bg-destructive/90 rounded-lg px-4 py-2 text-sm text-white"
          onClick={() => void loadHistory()}
        >
          重试
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-muted-foreground flex flex-col items-center justify-center py-16">
        <History className="mb-4 h-12 w-12" />
        <span className="mb-2 text-lg">暂无输出历史</span>
        <span className="text-sm">生成报告后将在此处显示历史记录</span>
      </div>
    );
  }

  return (
    <div className="border-border bg-card overflow-hidden rounded-xl border shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-border bg-muted/50 text-muted-foreground border-b text-left text-xs font-medium">
            <th className="px-4 py-3">项目</th>
            <th className="px-4 py-3">格式</th>
            <th className="px-4 py-3">状态</th>
            <th className="px-4 py-3">文件名</th>
            <th className="px-4 py-3">时间</th>
            <th className="px-4 py-3">操作</th>
          </tr>
        </thead>
        <tbody className="divide-border divide-y">
          {items.map((item) => (
            <tr key={item.taskId} className="hover:bg-muted/30">
              <td className="text-foreground px-4 py-3">{item.projectId}</td>
              <td className="text-foreground px-4 py-3">{item.format}</td>
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
                  {item.status === "completed"
                    ? "已完成"
                    : item.status === "failed"
                      ? "失败"
                      : "进行中"}
                </span>
              </td>
              <td className="text-muted-foreground px-4 py-3">
                {item.fileName ?? "-"}
              </td>
              <td className="text-muted-foreground px-4 py-3">
                {item.createdAt}
              </td>
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
    <div className="bg-muted flex h-full flex-col">
      {/* Tab Header */}
      <header className="bg-background border-border flex h-15 shrink-0 items-center border-b px-6">
        <div className="mr-3 shrink-0 rounded-sm border border-emerald-200 bg-emerald-50 p-1 text-emerald-600">
          <FileOutput className="h-4 w-4" />
        </div>
        <span className="text-foreground mr-8 text-lg font-bold tracking-tight">
          报告输出
        </span>
        <nav className="text-muted-foreground flex h-full items-center gap-6 text-sm font-medium">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const href = `/output?tab=${id}`;
            const isActive = currentTab === id;
            return (
              <Link
                key={id}
                href={href}
                className={cn(
                  "flex h-full items-center gap-2 border-b-2 py-5 transition-colors",
                  isActive
                    ? "text-primary border-primary"
                    : "hover:text-foreground border-transparent",
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
      <div className="bg-background flex-1 overflow-y-auto p-6">
        {currentTab === "templates" && <TemplatesTab />}
        {currentTab === "generate" && <GenerateTab />}
        {currentTab === "history" && <HistoryTab />}
      </div>
    </div>
  );
}
