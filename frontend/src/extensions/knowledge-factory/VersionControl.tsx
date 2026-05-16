"use client";

import {
  GitBranch,
  History,
  GitCommit,
  RotateCcw,
  Layout,
  Loader2,
  RefreshCw,
  AlertCircle,
  Check,
  ChevronsUpDown,
  Search,
  FileText,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";

import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { kfApi } from "@/extensions/api";
import type {
  TemplateListItem,
  TemplateVersionResponse,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import VersionCompareModal from "./components/VersionCompareModal";

interface VersionEntry {
  id: string;
  version: string;
  date: string;
  author: string;
  comment: string;
  isHead: boolean;
}

export default function VersionControl() {
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Rollback
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackVersionId, setRollbackVersionId] = useState<string | null>(null);
  const [rollbackMsg, setRollbackMsg] = useState<string | null>(null);

  // Compare
  const [compareOpen, setCompareOpen] = useState(false);

  // Combobox open state
  const [comboboxOpen, setComboboxOpen] = useState(false);

  const statusLabel = (s: string) =>
    s === "draft" ? "草稿" : s === "published" ? "已发布" : "已废弃";

  const statusColor = (s: string) =>
    s === "draft"
      ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
      : s === "published"
        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";

  // Load templates on mount
  const loadTemplates = useCallback(async () => {
    setLoadingTemplates(true);
    setError(null);
    try {
      const resp = await kfApi.listTemplates({ limit: 100 });
      setTemplates(resp.templates);
      if (resp.templates.length > 0 && !selectedId) {
        setSelectedId(resp.templates[0]!.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载模板列表失败");
    } finally {
      setLoadingTemplates(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  // Load versions when template is selected
  const loadVersions = useCallback(async () => {
    if (!selectedId) return;
    setLoadingVersions(true);
    setError(null);
    try {
      const data = await kfApi.getTemplateVersions(selectedId);
      const entries: VersionEntry[] = (data || []).map((v: TemplateVersionResponse, i: number) => ({
        id: v.id,
        version: v.version,
        date: v.published_at ? new Date(v.published_at).toLocaleDateString("zh-CN") : "",
        author: v.published_by ?? "系统",
        comment: v.changelog ?? `发布版本 ${v.version}`,
        isHead: i === 0,
      }));
      setVersions(entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载版本历史失败");
    } finally {
      setLoadingVersions(false);
    }
  }, [selectedId]);

  useEffect(() => {
    if (selectedId) void loadVersions();
  }, [selectedId, loadVersions]);

  // Rollback handler
  const handleRollback = async (versionId: string, versionLabel: string) => {
    if (!selectedId) return;
    if (!confirm(`确定要回滚到 ${versionLabel} 吗？回滚后模板将变为草稿状态并递增版本号。`)) return;

    setRollingBack(true);
    setRollbackVersionId(versionId);
    setRollbackMsg(null);
    try {
      const result = await kfApi.rollbackTemplate(selectedId, versionId, `回滚到 ${versionLabel}`);
      setRollbackMsg(result.message);
      await loadVersions();
    } catch (e) {
      setRollbackMsg(e instanceof Error ? e.message : "回滚失败");
    } finally {
      setRollingBack(false);
      setRollbackVersionId(null);
    }
  };

  const selectedTemplate = templates.find((t) => t.id === selectedId);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <h2 className="text-lg font-medium flex items-center gap-2 text-foreground tracking-tight">
          <GitBranch className="w-5 h-5 text-primary" />
          模板版本管理
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => { void loadTemplates(); void loadVersions(); }}
            disabled={loadingTemplates || loadingVersions}
            className="flex items-center gap-2 px-3 py-2 border border-border text-foreground rounded-lg hover:bg-accent transition-colors text-sm disabled:opacity-50"
          >
            <RefreshCw className={cn("w-4 h-4", (loadingTemplates || loadingVersions) && "animate-spin")} /> 刷新
          </button>
          <button
            onClick={() => setCompareOpen(true)}
            disabled={!selectedId || versions.length < 2}
            className="flex items-center gap-2 px-3 py-2 border border-border text-foreground rounded-lg hover:bg-accent transition-colors text-sm disabled:opacity-50"
          >
            <Layout className="w-4 h-4" /> 版本对比
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-muted/30">
        {/* Template Selector */}
        <div className="bg-gradient-to-br from-card to-card/80 rounded-xl border border-border/50 shadow-sm p-4">
          <label className="block text-sm font-medium text-muted-foreground mb-2">选择模板</label>
          {loadingTemplates && !templates.length ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Loader2 className="w-4 h-4 animate-spin" /> 加载模板列表...
            </div>
          ) : templates.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无模板，请先创建或抽取模板</p>
          ) : (
            <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
              <PopoverTrigger asChild>
                <button
                  role="combobox"
                  aria-expanded={comboboxOpen}
                  className="w-full flex items-center justify-between gap-2 rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-left hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-ring/50 focus:ring-offset-1 transition-colors"
                >
                  {selectedTemplate ? (
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-4 h-4 text-primary shrink-0" />
                      <span className="truncate font-medium text-foreground">{selectedTemplate.name}</span>
                      <span className="text-xs text-muted-foreground shrink-0">{selectedTemplate.version}</span>
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0", statusColor(selectedTemplate.status))}>
                        {statusLabel(selectedTemplate.status)}
                      </span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">选择模板...</span>
                  )}
                  <ChevronsUpDown className="w-4 h-4 shrink-0 text-muted-foreground" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
                <Command>
                  <CommandInput placeholder="搜索模板名称..." />
                  <CommandList>
                    <CommandEmpty>未找到匹配的模板</CommandEmpty>
                    <CommandGroup>
                      {templates.map((t) => (
                        <CommandItem
                          key={t.id}
                          value={t.name}
                          onSelect={() => {
                            setSelectedId(t.id);
                            setComboboxOpen(false);
                          }}
                          className="flex items-center gap-2 px-3 py-2.5 cursor-pointer"
                        >
                          <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm truncate">{t.name}</span>
                              <span className="text-xs text-muted-foreground shrink-0">{t.version}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-xs text-muted-foreground">{t.domain}</span>
                              <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium", statusColor(t.status))}>
                                {statusLabel(t.status)}
                              </span>
                            </div>
                          </div>
                          <Check className={cn("w-4 h-4 shrink-0", selectedId === t.id ? "text-primary" : "opacity-0")} />
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}
        </div>

        {/* Rollback message */}
        {rollbackMsg && (
          <div className={cn(
            "rounded-lg p-3 text-sm",
            rollbackMsg.includes("成功") ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"
          )}>
            {rollbackMsg}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-500/10 p-4 text-red-500 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        {/* Version History */}
        {selectedId && (
          <div className="bg-gradient-to-br from-card to-card/80 rounded-xl border border-border/50 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-muted/50 flex items-center gap-2">
              <History className="w-5 h-5 text-muted-foreground" />
              <h3 className="font-semibold text-foreground">版本历史</h3>
              {selectedTemplate && (
                <span className="text-xs text-muted-foreground ml-2">
                  {selectedTemplate.name} · {selectedTemplate.version}
                </span>
              )}
            </div>
            <div className="p-6 relative">
              {loadingVersions ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" /> 加载版本历史...
                </div>
              ) : versions.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-muted-foreground text-sm">
                  <GitCommit className="w-10 h-10 text-muted-foreground/30 mb-2" />
                  <p>暂无版本记录</p>
                  <p className="text-xs mt-1">发布模板后会自动创建版本快照</p>
                </div>
              ) : (
                <>
                  <div className="absolute left-9 top-6 bottom-6 w-0.5 bg-border" />
                  <div className="space-y-8">
                    {versions.map((item) => (
                      <div key={item.id} className="relative pl-12">
                        <div
                          className={cn(
                            "absolute left-0 top-1.5 w-6 h-6 rounded-full border-2 z-10 flex items-center justify-center",
                            item.isHead
                              ? "border-primary bg-primary/10"
                              : "border-muted-foreground bg-card"
                          )}
                        >
                          <GitCommit
                            className={cn(
                              "w-3 h-3",
                              item.isHead ? "text-primary" : "text-muted-foreground"
                            )}
                          />
                        </div>

                        <div className={cn(
                            "bg-card p-4 rounded-xl border border-border/50 shadow-sm hover:border-primary/30 hover:shadow-md transition-all group border-l-[3px]",
                            item.isHead ? "border-l-primary/60" : "border-l-border"
                          )}>
                          <div className="flex justify-between items-start mb-2">
                            <div className="flex items-center gap-3">
                              <span
                                className={cn(
                                  "font-mono font-bold text-sm",
                                  item.isHead ? "text-primary" : "text-foreground"
                                )}
                              >
                                {item.isHead && "(HEAD) "}
                                {item.version}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {item.date}
                              </span>
                              <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground">
                                {item.author}
                              </span>
                            </div>
                            <div className="flex gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={() => setCompareOpen(true)}
                                className="text-primary text-xs font-medium hover:text-primary/70 hover:underline transition-colors"
                              >
                                对比
                              </button>
                              {!item.isHead && (
                                <button
                                  onClick={() => handleRollback(item.id, item.version)}
                                  disabled={rollingBack && rollbackVersionId === item.id}
                                  className="text-primary text-xs font-medium hover:text-primary/70 hover:underline flex items-center gap-1 transition-colors disabled:opacity-50"
                                >
                                  {rollingBack && rollbackVersionId === item.id ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                  ) : (
                                    <RotateCcw className="w-3 h-3" />
                                  )}
                                  回滚
                                </button>
                              )}
                            </div>
                          </div>
                          <p className="text-sm text-foreground font-medium">
                            {item.comment}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Compare Modal */}
      {selectedId && (
        <VersionCompareModal
          templateId={selectedId}
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </div>
  );
}
