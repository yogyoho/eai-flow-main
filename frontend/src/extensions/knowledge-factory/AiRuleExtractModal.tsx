"use client";

import {
  Upload,
  Sparkles,
  Loader2,
  CheckCircle2,
  X,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
} from "lucide-react";
import React, { useState, useCallback, useRef } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  extractRulesFromDocument,
  batchCreateRules,
  mapExtractedToCreate,
  type ExtractedRule,
} from "@/extensions/knowledge-factory/aiRuleExtractApi";
import type { ComplianceRuleCreate, RuleDictionaries } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

type Phase = "upload" | "extracting" | "preview" | "importing";

interface AiRuleExtractModalProps {
  onClose: () => void;
  onImported: () => void;
  dictionaries: RuleDictionaries;
}

export default function AiRuleExtractModal({
  onClose,
  onImported,
  dictionaries,
}: AiRuleExtractModalProps) {
  const [phase, setPhase] = useState<Phase>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [industry, setIndustry] = useState("");
  const [reportType, setReportType] = useState("");
  const [extractedRules, setExtractedRules] = useState<ComplianceRuleCreate[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (f: File) => {
    const ext = f.name.split(".").pop()?.toLowerCase();
    const allowed = ["pdf", "doc", "docx", "txt", "md"];
    if (!ext || !allowed.includes(ext)) {
      setError("不支持的文件格式，支持: pdf, doc, docx, txt, md");
      return;
    }
    setFile(f);
    setError(null);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFileSelect(f);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleExtract = async () => {
    if (!file) return;
    setPhase("extracting");
    setError(null);
    try {
      const result = await extractRulesFromDocument(
        file,
        industry || undefined,
        reportType ? [reportType] : undefined,
      );
      const mapped = (result.rules || []).map(mapExtractedToCreate);
      setExtractedRules(mapped);
      setSelectedIds(new Set(mapped.map((r) => r.ruleId)));
      setPhase("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "规则提取失败");
      setPhase("upload");
    }
  };

  const toggleSelect = (ruleId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === extractedRules.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(extractedRules.map((r) => r.ruleId)));
    }
  };

  const updateRule = (ruleId: string, updates: Partial<ComplianceRuleCreate>) => {
    setExtractedRules((prev) =>
      prev.map((r) => (r.ruleId === ruleId ? { ...r, ...updates } : r)),
    );
  };

  const handleImport = async () => {
    const selected = extractedRules.filter((r) => selectedIds.has(r.ruleId));
    if (selected.length === 0) return;

    setPhase("importing");
    setError(null);
    try {
      const result = await batchCreateRules(selected);
      setImportResult({ created: result.created, skipped: result.skipped, errors: result.errors });
      if (result.errors.length === 0) {
        onImported();
        onClose();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "批量导入失败");
      setPhase("preview");
    }
  };

  const severityColor = (s: string) => {
    if (s === "critical") return "text-destructive";
    if (s === "warning") return "text-amber-500";
    return "text-blue-500";
  };

  const severityBg = (s: string) => {
    if (s === "critical") return "bg-gradient-to-r from-destructive/20 to-destructive/5 border-l-destructive/60";
    if (s === "warning") return "bg-gradient-to-r from-amber-500/20 to-amber-500/5 border-l-amber-500/60";
    return "bg-gradient-to-r from-blue-500/20 to-blue-500/5 border-l-blue-500/60";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-[800px] flex-col rounded-2xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">AI 智能提取合规规则</h2>
              <p className="text-xs text-muted-foreground">上传法规文档，AI 自动分析并提取可校验的合规要求</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-4 text-sm text-red-500">
              <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
            </div>
          )}

          {/* Phase: Upload */}
          {phase === "upload" && (
            <>
              <div
                className={cn(
                  "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors",
                  isDragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/40",
                )}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className={cn("mb-4 h-12 w-12", isDragging ? "text-primary" : "text-muted-foreground/40")} />
                <p className="mb-1 font-medium text-foreground">
                  {file ? file.name : "拖拽文件到此处或点击上传"}
                </p>
                <p className="text-xs text-muted-foreground">支持 PDF、Word、TXT、Markdown 格式，最大 20MB</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.doc,.docx,.txt,.md"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFileSelect(f);
                  }}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground">行业（可选）</label>
                  <AdminSelect
                    value={industry || "all"}
                    onChange={(v) => setIndustry(v === "all" ? "" : v)}
                    options={[
                      { value: "all", label: "不限行业" },
                      ...dictionaries.industries.map((d) => ({ value: d.value, label: d.label })),
                    ]}
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground">报告类型（可选）</label>
                  <AdminSelect
                    value={reportType || "all"}
                    onChange={(v) => setReportType(v === "all" ? "" : v)}
                    options={[
                      { value: "all", label: "不限报告类型" },
                      ...dictionaries.reportTypes.map((d) => ({ value: d.value, label: d.label })),
                    ]}
                    className="w-full"
                  />
                </div>
              </div>
            </>
          )}

          {/* Phase: Extracting */}
          {phase === "extracting" && (
            <div className="flex flex-col items-center py-16 text-muted-foreground">
              <Loader2 className="mb-4 h-12 w-12 animate-spin text-primary" />
              <p className="mb-1 font-medium text-foreground">AI 正在分析文档，提取合规规则...</p>
              <p className="text-sm">预计需要 15-45 秒</p>
            </div>
          )}

          {/* Phase: Preview / Importing */}
          {(phase === "preview" || phase === "importing") && (
            <>
              {extractedRules.length === 0 ? (
                <div className="flex flex-col items-center py-12 text-muted-foreground">
                  <AlertTriangle className="mb-4 h-12 w-12 text-amber-500/40" />
                  <p className="mb-1 font-medium text-foreground">未提取到可校验的合规规则</p>
                  <p className="text-sm">该文档可能不包含可自动校验的合规要求</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      提取到 <span className="font-bold text-foreground">{extractedRules.length}</span> 条规则
                    </div>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === extractedRules.length}
                        onChange={toggleSelectAll}
                        className="h-4 w-4"
                      />
                      <span className="text-muted-foreground">全选</span>
                    </label>
                  </div>

                  <div className="space-y-3">
                    {extractedRules.map((rule) => {
                      const isSelected = selectedIds.has(rule.ruleId);
                      const isEditing = editingId === rule.ruleId;

                      return (
                        <div
                          key={rule.ruleId}
                          className={cn(
                            "overflow-hidden rounded-xl border border-border/50 shadow-sm transition-all border-l-[3px]",
                            severityBg(rule.severity),
                            !isSelected && "opacity-50",
                          )}
                        >
                          <div className="flex items-start gap-3 p-4">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelect(rule.ruleId)}
                              className="mt-1 h-4 w-4 shrink-0"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="mb-1 flex items-center gap-2">
                                <span className="font-mono text-xs font-bold text-muted-foreground">{rule.ruleId}</span>
                                <span className="font-medium text-sm text-foreground">{rule.name}</span>
                                <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", severityColor(rule.severity), "bg-muted")}>
                                  {rule.severity}
                                </span>
                                <span className="rounded bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                                  {rule.type}
                                </span>
                              </div>
                              <p className="line-clamp-2 text-sm text-muted-foreground">{rule.description}</p>

                              {rule.sourceSections && rule.sourceSections.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1">
                                  {rule.sourceSections.map((s, i) => (
                                    <span key={i} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                      {s}
                                    </span>
                                  ))}
                                </div>
                              )}

                              {isEditing && (
                                <div className="mt-3 space-y-3 rounded-lg border border-border bg-background p-4">
                                  <div>
                                    <label className="mb-1 block text-xs font-medium text-muted-foreground">规则名称</label>
                                    <input
                                      type="text"
                                      value={rule.name}
                                      onChange={(e) => updateRule(rule.ruleId, { name: e.target.value })}
                                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                                    />
                                  </div>
                                  <div className="grid grid-cols-2 gap-3">
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-muted-foreground">严重级别</label>
                                      <AdminSelect
                                        value={rule.severity}
                                        onChange={(v) => updateRule(rule.ruleId, { severity: v })}
                                        options={[
                                          { value: "critical", label: "Critical" },
                                          { value: "warning", label: "Warning" },
                                          { value: "info", label: "Info" },
                                        ]}
                                        className="w-full"
                                      />
                                    </div>
                                    <div>
                                      <label className="mb-1 block text-xs font-medium text-muted-foreground">规则类型</label>
                                      <AdminSelect
                                        value={rule.type}
                                        onChange={(v) => updateRule(rule.ruleId, { type: v })}
                                        options={[
                                          { value: "data_validation", label: "数据校验" },
                                          { value: "text_pattern", label: "文本匹配" },
                                          { value: "field_presence", label: "字段存在性" },
                                          { value: "cross_reference", label: "交叉引用" },
                                          { value: "value_range", label: "值范围" },
                                          { value: "keyword_check", label: "关键词检查" },
                                        ]}
                                        className="w-full"
                                      />
                                    </div>
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs font-medium text-muted-foreground">描述</label>
                                    <textarea
                                      value={rule.description ?? ""}
                                      onChange={(e) => updateRule(rule.ruleId, { description: e.target.value })}
                                      rows={2}
                                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                                    />
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs font-medium text-muted-foreground">错误提示</label>
                                    <input
                                      type="text"
                                      value={rule.errorMessage ?? ""}
                                      onChange={(e) => updateRule(rule.ruleId, { errorMessage: e.target.value })}
                                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                                    />
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs font-medium text-muted-foreground">修复建议</label>
                                    <input
                                      type="text"
                                      value={rule.autoFixSuggestion ?? ""}
                                      onChange={(e) => updateRule(rule.ruleId, { autoFixSuggestion: e.target.value })}
                                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                                    />
                                  </div>
                                </div>
                              )}
                            </div>

                            <button
                              onClick={() => setEditingId(isEditing ? null : rule.ruleId)}
                              className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                            >
                              {isEditing ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-between border-t border-border p-5">
          <div className="text-sm text-muted-foreground">
            {phase === "preview" && extractedRules.length > 0 && (
              <>已选 {selectedIds.size} / {extractedRules.length} 条</>
            )}
            {phase === "importing" && (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> 正在导入...
              </span>
            )}
            {importResult && (
              <span className="flex items-center gap-1 text-emerald-500">
                <CheckCircle2 className="h-4 w-4" /> 成功导入 {importResult.created} 条
                {importResult.skipped > 0 && `，跳过 ${importResult.skipped} 条重复`}
              </span>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              {phase === "preview" ? "取消" : "关闭"}
            </button>

            {phase === "upload" && (
              <button
                onClick={handleExtract}
                disabled={!file}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-5 py-2 text-sm font-medium text-white shadow-sm transition-all hover:shadow-md disabled:opacity-50"
              >
                <Sparkles className="h-4 w-4" /> 开始提取
              </button>
            )}

            {phase === "preview" && extractedRules.length > 0 && (
              <button
                onClick={handleImport}
                disabled={selectedIds.size === 0}
                className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                导入所选规则
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
