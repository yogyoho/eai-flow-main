/**
 * 种子数据管理组件
 */

"use client";

import {
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  CircleSlash,
  Database,
  FolderPlus,
  ListOrdered,
  RefreshCw,
  SkipForward,
  Sprout,
  Tag,
} from "lucide-react";
import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

import type { ComplianceRuleImportResponse, ComplianceRuleStatus } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface SeedDataManagerProps {
  status: ComplianceRuleStatus;
  onImport: (forceUpdate: boolean) => Promise<ComplianceRuleImportResponse>;
  onClose: () => void;
}

function StatRow({
  label,
  icon: Icon,
  iconWrapClass,
  iconClass,
  children,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  iconWrapClass: string;
  iconClass: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className={cn("flex size-12 shrink-0 items-center justify-center rounded-xl", iconWrapClass)}>
        <Icon className={cn("size-6", iconClass)} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 whitespace-nowrap text-sm text-muted-foreground">{label}</div>
        {children}
      </div>
    </div>
  );
}

export function SeedDataManager({ status, onImport, onClose }: SeedDataManagerProps) {
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ComplianceRuleImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forceUpdate, setForceUpdate] = useState(false);
  const resultErrorMessages = result?.errorMessages ?? [];

  const handleImport = async () => {
    setImporting(true);
    setError(null);
    setResult(null);

    try {
      const importResult = await onImport(forceUpdate);
      setResult(importResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[min(90vh,800px)] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="seed-manager-title"
      >
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border px-5 py-4">
          <h2 id="seed-manager-title" className="text-lg font-semibold tracking-tight text-foreground">
            种子数据管理
          </h2>
          <Button type="button" variant="ghost" size="icon-sm" className="shrink-0" onClick={onClose}>
            <span className="sr-only">关闭</span>
            <span className="text-xl leading-none text-muted-foreground" aria-hidden>
              ×
            </span>
          </Button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">当前状态</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <StatRow label="种子数据版本" icon={Tag} iconWrapClass="bg-violet-100 dark:bg-violet-950/50" iconClass="text-violet-600 dark:text-violet-400">
                <div className="truncate font-mono text-xl font-bold tabular-nums text-foreground">{status.seedVersion}</div>
              </StatRow>
              <StatRow label="种子规则数" icon={Sprout} iconWrapClass="bg-amber-100 dark:bg-amber-950/50" iconClass="text-amber-600 dark:text-amber-400">
                <div className="text-2xl font-bold tabular-nums text-amber-600">{status.seedTotal}</div>
              </StatRow>
              <StatRow label="数据库规则数" icon={Database} iconWrapClass="bg-slate-100 dark:bg-slate-800" iconClass="text-slate-600 dark:text-slate-300">
                <div className="text-2xl font-bold tabular-nums text-foreground">{status.dbTotal}</div>
              </StatRow>
              <StatRow label="启用规则" icon={BadgeCheck} iconWrapClass="bg-emerald-100 dark:bg-emerald-950/50" iconClass="text-emerald-600 dark:text-emerald-400">
                <div className="text-2xl font-bold tabular-nums text-emerald-600">{status.dbEnabled}</div>
              </StatRow>
              <StatRow label="禁用规则" icon={CircleSlash} iconWrapClass="bg-muted" iconClass="text-muted-foreground">
                <div className="text-2xl font-bold tabular-nums text-muted-foreground">{status.dbDisabled}</div>
              </StatRow>
              <StatRow
                label="状态"
                icon={status.upToDate ? CheckCircle2 : AlertCircle}
                iconWrapClass={status.upToDate ? "bg-emerald-100 dark:bg-emerald-950/50" : "bg-amber-100 dark:bg-amber-950/50"}
                iconClass={status.upToDate ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}
              >
                <div
                  className={cn(
                    "text-base font-semibold leading-snug",
                    status.upToDate ? "text-emerald-600" : "text-amber-600",
                  )}
                >
                  {status.upToDate ? "已是最新" : "需要更新"}
                </div>
              </StatRow>
            </div>
          </section>

          {status.inSeedNotInDb.length > 0 && (
            <section className="rounded-xl border border-amber-200/80 bg-amber-50/80 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
              <h3 className="mb-2 text-sm font-semibold text-foreground">待新增规则 ({status.inSeedNotInDb.length})</h3>
              <div className="flex flex-wrap gap-2">
                {status.inSeedNotInDb.map((ruleId) => (
                  <span
                    key={ruleId}
                    className="rounded-md bg-emerald-100 px-2 py-0.5 font-mono text-xs text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                  >
                    {ruleId}
                  </span>
                ))}
              </div>
            </section>
          )}

          {status.inDbNotInSeed.length > 0 && (
            <section className="rounded-xl border border-red-200/80 bg-red-50/60 p-4 dark:border-red-900/50 dark:bg-red-950/25">
              <h3 className="mb-2 text-sm font-semibold text-foreground">数据库中多余的规则 ({status.inDbNotInSeed.length})</h3>
              <div className="flex flex-wrap gap-2">
                {status.inDbNotInSeed.map((ruleId) => (
                  <span
                    key={ruleId}
                    className="rounded-md bg-red-100 px-2 py-0.5 font-mono text-xs text-red-800 dark:bg-red-950/60 dark:text-red-300"
                  >
                    {ruleId}
                  </span>
                ))}
              </div>
              <p className="mt-3 text-xs text-muted-foreground">这些规则在种子数据文件中不存在，可能是手动创建的。</p>
            </section>
          )}

          {!result && (
            <section className="rounded-xl border border-primary/20 bg-primary/5 p-4">
              <h3 className="mb-3 text-sm font-semibold text-foreground">导入选项</h3>
              <div className="flex items-start gap-2.5">
                <Checkbox
                  id="seed-force-update"
                  checked={forceUpdate}
                  onCheckedChange={(c) => setForceUpdate(c === true)}
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1 space-y-2">
                  <label htmlFor="seed-force-update" className="cursor-pointer text-sm leading-snug text-foreground">
                    强制更新已存在的规则
                  </label>
                  <p className="text-xs text-muted-foreground">勾选后，会用种子数据覆盖数据库中已存在的同名规则。</p>
                </div>
              </div>
            </section>
          )}

          {result && (
            <section className="space-y-4">
              <h3 className="text-sm font-semibold text-foreground">导入结果</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <StatRow label="总数" icon={ListOrdered} iconWrapClass="bg-slate-100 dark:bg-slate-800" iconClass="text-slate-600 dark:text-slate-300">
                  <div className="text-2xl font-bold tabular-nums text-foreground">{result.total}</div>
                </StatRow>
                <StatRow label="新增" icon={FolderPlus} iconWrapClass="bg-emerald-100 dark:bg-emerald-950/50" iconClass="text-emerald-600 dark:text-emerald-400">
                  <div className="text-2xl font-bold tabular-nums text-emerald-600">{result.created}</div>
                </StatRow>
                <StatRow label="更新" icon={RefreshCw} iconWrapClass="bg-blue-100 dark:bg-blue-950/50" iconClass="text-blue-600 dark:text-blue-400">
                  <div className="text-2xl font-bold tabular-nums text-blue-600">{result.updated}</div>
                </StatRow>
                <StatRow label="跳过" icon={SkipForward} iconWrapClass="bg-muted" iconClass="text-muted-foreground">
                  <div className="text-2xl font-bold tabular-nums text-muted-foreground">{result.skipped}</div>
                </StatRow>
                <StatRow label="错误" icon={AlertCircle} iconWrapClass="bg-destructive/10" iconClass="text-destructive">
                  <div className="text-2xl font-bold tabular-nums text-destructive">{result.errors}</div>
                </StatRow>
              </div>

              {resultErrorMessages.length > 0 && (
                <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
                  <h4 className="mb-2 text-sm font-semibold text-destructive">错误信息</h4>
                  <ul className="list-inside list-disc space-y-1 text-xs text-destructive/90">
                    {resultErrorMessages.map((msg, idx) => (
                      <li key={idx}>{msg}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.success && (
                <div className="flex items-center gap-2 rounded-xl border border-emerald-200/80 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200">
                  <CheckCircle2 className="size-5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
                  种子数据导入成功！
                </div>
              )}
            </section>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-border bg-muted/30 px-5 py-4">
          {!result && (
            <Button type="button" onClick={() => void handleImport()} disabled={importing}>
              {importing ? "导入中..." : "导入种子数据"}
            </Button>
          )}
          <Button type="button" variant="outline" onClick={onClose}>
            {result ? "关闭" : "取消"}
          </Button>
        </div>
      </div>
    </div>
  );
}
