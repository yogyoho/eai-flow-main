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
  FileText,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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
  const [rollbackVersionId, setRollbackVersionId] = useState<string | null>(
    null,
  );
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
      const entries: VersionEntry[] = (data || []).map(
        (v: TemplateVersionResponse, i: number) => ({
          id: v.id,
          version: v.version,
          date: v.published_at
            ? new Date(v.published_at).toLocaleDateString("zh-CN")
            : "",
          author: v.published_by ?? "系统",
          comment: v.changelog ?? `发布版本 ${v.version}`,
          isHead: i === 0,
        }),
      );
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
    if (
      !confirm(
        `确定要回滚到 ${versionLabel} 吗？回滚后模板将变为草稿状态并递增版本号。`,
      )
    )
      return;

    setRollingBack(true);
    setRollbackVersionId(versionId);
    setRollbackMsg(null);
    try {
      const result = await kfApi.rollbackTemplate(
        selectedId,
        versionId,
        `回滚到 ${versionLabel}`,
      );
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
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border bg-card flex shrink-0 items-center justify-between border-b p-4">
        <h2 className="text-foreground flex items-center gap-2 text-lg font-medium tracking-tight">
          <GitBranch className="text-primary h-5 w-5" />
          模板版本管理
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => {
              void loadTemplates();
              void loadVersions();
            }}
            disabled={loadingTemplates || loadingVersions}
            className="border-border text-foreground hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={cn(
                "h-4 w-4",
                (loadingTemplates || loadingVersions) && "animate-spin",
              )}
            />{" "}
            刷新
          </button>
          <button
            onClick={() => setCompareOpen(true)}
            disabled={!selectedId || versions.length < 2}
            className="border-border text-foreground hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50"
          >
            <Layout className="h-4 w-4" /> 版本对比
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="bg-muted/30 flex-1 space-y-6 overflow-y-auto p-6">
        {/* Template Selector */}
        <div className="from-card to-card/80 border-border/50 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
          <label className="text-muted-foreground mb-2 block text-sm font-medium">
            选择模板
          </label>
          {loadingTemplates && !templates.length ? (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> 加载模板列表...
            </div>
          ) : templates.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              暂无模板，请先创建或抽取模板
            </p>
          ) : (
            <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
              <PopoverTrigger asChild>
                <button
                  role="combobox"
                  aria-expanded={comboboxOpen}
                  aria-controls="kf-template-version-combobox-list"
                  className="border-input bg-background hover:bg-accent/50 focus:ring-ring/50 flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors focus:ring-2 focus:ring-offset-1 focus:outline-none"
                >
                  {selectedTemplate ? (
                    <div className="flex min-w-0 items-center gap-2">
                      <FileText className="text-primary h-4 w-4 shrink-0" />
                      <span className="text-foreground truncate font-medium">
                        {selectedTemplate.name}
                      </span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {selectedTemplate.version}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                          statusColor(selectedTemplate.status),
                        )}
                      >
                        {statusLabel(selectedTemplate.status)}
                      </span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">选择模板...</span>
                  )}
                  <ChevronsUpDown className="text-muted-foreground h-4 w-4 shrink-0" />
                </button>
              </PopoverTrigger>
              <PopoverContent
                className="w-[var(--radix-popover-trigger-width)] p-0"
                align="start"
              >
                <Command>
                  <CommandInput placeholder="搜索模板名称..." />
                  <CommandList id="kf-template-version-combobox-list">
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
                          className="flex cursor-pointer items-center gap-2 px-3 py-2.5"
                        >
                          <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="truncate text-sm font-medium">
                                {t.name}
                              </span>
                              <span className="text-muted-foreground shrink-0 text-xs">
                                {t.version}
                              </span>
                            </div>
                            <div className="mt-0.5 flex items-center gap-2">
                              <span className="text-muted-foreground text-xs">
                                {t.domain}
                              </span>
                              <span
                                className={cn(
                                  "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                                  statusColor(t.status),
                                )}
                              >
                                {statusLabel(t.status)}
                              </span>
                            </div>
                          </div>
                          <Check
                            className={cn(
                              "h-4 w-4 shrink-0",
                              selectedId === t.id
                                ? "text-primary"
                                : "opacity-0",
                            )}
                          />
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
          <div
            className={cn(
              "rounded-lg p-3 text-sm",
              rollbackMsg.includes("成功")
                ? "bg-emerald-500/10 text-emerald-500"
                : "bg-red-500/10 text-red-500",
            )}
          >
            {rollbackMsg}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-4 text-sm text-red-500">
            <AlertCircle className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}

        {/* Version History */}
        {selectedId && (
          <div className="from-card to-card/80 border-border/50 overflow-hidden rounded-xl border bg-gradient-to-br shadow-sm">
            <div className="border-border bg-muted/50 flex items-center gap-2 border-b p-4">
              <History className="text-muted-foreground h-5 w-5" />
              <h3 className="text-foreground font-semibold">版本历史</h3>
              {selectedTemplate && (
                <span className="text-muted-foreground ml-2 text-xs">
                  {selectedTemplate.name} · {selectedTemplate.version}
                </span>
              )}
            </div>
            <div className="relative p-6">
              {loadingVersions ? (
                <div className="text-muted-foreground flex items-center justify-center py-8 text-sm">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />{" "}
                  加载版本历史...
                </div>
              ) : versions.length === 0 ? (
                <div className="text-muted-foreground flex flex-col items-center py-8 text-sm">
                  <GitCommit className="text-muted-foreground/30 mb-2 h-10 w-10" />
                  <p>暂无版本记录</p>
                  <p className="mt-1 text-xs">发布模板后会自动创建版本快照</p>
                </div>
              ) : (
                <>
                  <div className="bg-border absolute top-6 bottom-6 left-9 w-0.5" />
                  <div className="space-y-8">
                    {versions.map((item) => (
                      <div key={item.id} className="relative pl-12">
                        <div
                          className={cn(
                            "absolute top-1.5 left-0 z-10 flex h-6 w-6 items-center justify-center rounded-full border-2",
                            item.isHead
                              ? "border-primary bg-primary/10"
                              : "border-muted-foreground bg-card",
                          )}
                        >
                          <GitCommit
                            className={cn(
                              "h-3 w-3",
                              item.isHead
                                ? "text-primary"
                                : "text-muted-foreground",
                            )}
                          />
                        </div>

                        <div
                          className={cn(
                            "bg-card border-border/50 hover:border-primary/30 group rounded-xl border border-l-[3px] p-4 shadow-sm transition-all hover:shadow-md",
                            item.isHead
                              ? "border-l-primary/60"
                              : "border-l-border",
                          )}
                        >
                          <div className="mb-2 flex items-start justify-between">
                            <div className="flex items-center gap-3">
                              <span
                                className={cn(
                                  "font-mono text-sm font-bold",
                                  item.isHead
                                    ? "text-primary"
                                    : "text-foreground",
                                )}
                              >
                                {item.isHead && "(HEAD) "}
                                {item.version}
                              </span>
                              <span className="text-muted-foreground text-xs">
                                {item.date}
                              </span>
                              <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs">
                                {item.author}
                              </span>
                            </div>
                            <div className="flex gap-3 opacity-0 transition-opacity group-hover:opacity-100">
                              <button
                                onClick={() => setCompareOpen(true)}
                                className="text-primary hover:text-primary/70 text-xs font-medium transition-colors hover:underline"
                              >
                                对比
                              </button>
                              {!item.isHead && (
                                <button
                                  onClick={() =>
                                    handleRollback(item.id, item.version)
                                  }
                                  disabled={
                                    rollingBack && rollbackVersionId === item.id
                                  }
                                  className="text-primary hover:text-primary/70 flex items-center gap-1 text-xs font-medium transition-colors hover:underline disabled:opacity-50"
                                >
                                  {rollingBack &&
                                  rollbackVersionId === item.id ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : (
                                    <RotateCcw className="h-3 w-3" />
                                  )}
                                  回滚
                                </button>
                              )}
                            </div>
                          </div>
                          <p className="text-foreground text-sm font-medium">
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
