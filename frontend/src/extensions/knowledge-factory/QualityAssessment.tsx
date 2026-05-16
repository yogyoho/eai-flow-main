"use client";

import { BarChart3, TrendingUp, AlertTriangle, Info, Loader2, AlertCircle, CheckCircle2, Check, ChevronsUpDown, FileText } from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { kfApi } from "@/extensions/api";
import type {
  TemplateListItem,
  QualityAssessmentResult,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

function useColorScheme() {
  const [colorScheme, setColorScheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setColorScheme(isDark ? "dark" : "light");
    const observer = new MutationObserver(() => {
      setColorScheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return colorScheme;
}

const DIMENSION_LABELS: Record<string, string> = {
  completeness: "完整性",
  accuracy: "准确性",
  consistency: "一致性",
  compliance: "合规性",
  freshness: "时效性",
};

const DIMENSION_COLORS: Record<string, string> = {
  completeness: "bg-gradient-to-r from-emerald-500 to-emerald-400",
  accuracy: "bg-gradient-to-r from-blue-500 to-blue-400",
  consistency: "bg-gradient-to-r from-violet-500 to-violet-400",
  compliance: "bg-gradient-to-r from-amber-500 to-amber-400",
  freshness: "bg-gradient-to-r from-pink-500 to-pink-400",
};

function getGradeLabel(grade: string): { label: string; color: string } {
  const grades: Record<string, { label: string; color: string }> = {
    优秀: { label: "优秀", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
    良好: { label: "良好", color: "bg-primary/10 text-primary border-primary/20" },
    一般: { label: "一般", color: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20" },
    较差: { label: "较差", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
    差: { label: "差", color: "bg-red-500/10 text-red-500 border-red-500/20" },
  };
  return grades[grade] ?? { label: grade, color: "bg-muted text-muted-foreground" };
}

export default function QualityAssessment() {
  const colorScheme = useColorScheme();
  const gridColor = colorScheme === "dark" ? "#404040" : "#e4e4e7";
  const axisColor = colorScheme === "dark" ? "#a1a1aa" : "#a1a1aa";
  const radarColor = "#6366f1";

  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [result, setResult] = useState<QualityAssessmentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comboboxOpen, setComboboxOpen] = useState(false);

  const statusLabel = (s: string) =>
    s === "draft" ? "草稿" : s === "published" ? "已发布" : "已废弃";

  const statusColor = (s: string) =>
    s === "draft"
      ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
      : s === "published"
        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";

  const loadTemplates = useCallback(async () => {
    setLoadingTemplates(true);
    try {
      const resp = await kfApi.listTemplates({ limit: 100 });
      setTemplates(resp.templates);
      if (resp.templates.length > 0 && selectedId == null) {
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

  const handleAssess = async () => {
    if (!selectedId) return;
    setAssessing(true);
    setError(null);
    try {
      const data = await kfApi.assessQuality(selectedId);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "质量评估失败");
    } finally {
      setAssessing(false);
    }
  };

  // Compute display data from result
  const selectedTemplate = templates.find((t) => t.id === selectedId);

  const radarData = result
    ? Object.entries(result.dimensions).map(([key, dim]) => ({
        subject: DIMENSION_LABELS[key] ?? key,
        A: dim.score,
        fullMark: 100,
      }))
    : [];

  // Collect all issues from all dimensions
  const allIssues = result
    ? Object.entries(result.dimensions).flatMap(([key, dim]) =>
        (dim.issues || []).map((issue, i) => ({
          id: `${key}-${i}`,
          dimension: DIMENSION_LABELS[key] ?? key,
          title: issue,
          type: dim.score >= 80 ? "info" : "warning",
        }))
      )
    : [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <h2 className="text-lg font-medium flex items-center gap-2 text-foreground tracking-tight">
          <BarChart3 className="w-5 h-5 text-primary" />
          知识质量评估
        </h2>
        <div className="flex gap-2">
          <button
            onClick={handleAssess}
            disabled={!selectedId || assessing}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors shadow-sm font-medium text-sm disabled:opacity-50"
          >
            {assessing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> 评估中...
              </>
            ) : (
              <>
                <TrendingUp className="w-4 h-4" /> {result ? "重新评估" : "开始评估"}
              </>
            )}
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
                            setResult(null);
                            setError(null);
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

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-500/10 p-4 text-red-500 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        {/* No result yet */}
        {!result && !assessing && !error && selectedId && (
          <div className="flex flex-col items-center py-12 text-muted-foreground">
            <BarChart3 className="w-16 h-16 text-muted-foreground/20 mb-4" />
            <p className="text-foreground font-medium mb-1">点击「开始评估」启动 AI 质量评估</p>
            <p className="text-sm">将从完整性、准确性、一致性、合规性、时效性五个维度进行分析</p>
          </div>
        )}

        {/* Assessing */}
        {assessing && (
          <div className="flex flex-col items-center py-12 text-muted-foreground">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-foreground font-medium">AI 正在分析模板质量...</p>
            <p className="text-sm">预计需要 10-30 秒</p>
          </div>
        )}

        {/* Result */}
        {result && !assessing && (
          <>
            {/* Score Cards */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Overall Score */}
              <div className="lg:col-span-1 bg-gradient-to-br from-card to-card/80 p-8 rounded-xl border border-border/50 shadow-sm flex flex-col items-center justify-center text-center space-y-4">
                <h3 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
                  整体评分
                </h3>
                <div className="relative w-48 h-48 flex items-center justify-center">
                  <div className="absolute inset-0 rounded-full border-8 border-muted" />
                  <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 200 200">
                    <circle
                      cx="100" cy="100" r="88"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="8"
                      className={cn(
                        result.overall_score >= 80 ? "text-emerald-500" :
                        result.overall_score >= 60 ? "text-yellow-500" : "text-red-500"
                      )}
                      strokeDasharray={`${(result.overall_score / 100) * 553} 553`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="text-center">
                    <div className={cn(
                      "text-5xl font-black",
                      result.overall_score >= 80 ? "text-emerald-500" :
                      result.overall_score >= 60 ? "text-yellow-500" : "text-red-500"
                    )}>
                      {result.overall_score}
                    </div>
                    <div className="text-sm text-muted-foreground font-bold">/ 100</div>
                  </div>
                </div>
                <div className={cn("border px-4 py-1 rounded-full font-medium text-sm", getGradeLabel(result.quality_grade).color)}>
                  {getGradeLabel(result.quality_grade).label}
                </div>
              </div>

              {/* Dimension Scores */}
              <div className="lg:col-span-2 bg-gradient-to-br from-card to-card/80 p-8 rounded-xl border border-border/50 shadow-sm">
                <div className="flex justify-between items-start mb-6">
                  <h3 className="text-lg font-semibold text-foreground">
                    维度评分
                  </h3>
                  {radarData.length > 0 && (
                    <div className="h-48 w-48">
                      <ResponsiveContainer width="100%" height="100%">
                        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                          <PolarGrid stroke={gridColor} />
                          <PolarAngleAxis
                            dataKey="subject"
                            tick={{ fill: axisColor, fontSize: 10 }}
                          />
                          <PolarRadiusAxis angle={30} domain={[0, 100]} />
                          <Radar
                            name="Score"
                            dataKey="A"
                            stroke={radarColor}
                            fill={radarColor}
                            fillOpacity={0.2}
                          />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
                <div className="space-y-4">
                  {Object.entries(result.dimensions).map(([key, dim]) => (
                    <div key={key} className="space-y-1.5">
                      <div className="flex justify-between text-sm font-medium">
                        <span className="text-foreground">{DIMENSION_LABELS[key] ?? key}</span>
                        <span className={cn(
                          "font-bold",
                          dim.score >= 80 ? "text-emerald-500" :
                          dim.score >= 60 ? "text-yellow-500" : "text-red-500"
                        )}>
                          {dim.score}%
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-1000",
                              DIMENSION_COLORS[key] ?? "bg-muted-foreground"
                            )}
                            style={{ width: `${dim.score}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground whitespace-nowrap min-w-[120px]">
                          {dim.issues.length > 0 ? `${dim.issues.length} 个问题` : "通过"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Suggestions */}
            {result.suggestions && result.suggestions.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-primary" /> 改进建议
                </h3>
                <div className="space-y-3">
                  {result.suggestions.map((suggestion, i) => (
                    <div
                      key={i}
                      className="bg-card p-5 rounded-xl border border-border/50 shadow-sm hover:border-primary/30 hover:shadow-md transition-all flex items-start gap-4 group border-l-[3px] border-l-primary/40"
                    >
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-gradient-to-br from-primary/20 to-primary/5 text-primary shrink-0">
                        <CheckCircle2 className="w-5 h-5" />
                      </div>
                      <div className="flex-1">
                        <p className="text-sm text-foreground">{suggestion}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Issue List */}
            {allIssues.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-500" /> 问题清单
                </h3>
                <div className="space-y-3">
                  {allIssues.map((issue) => (
                    <div
                      key={issue.id}
                      className={cn(
                        "bg-card p-5 rounded-xl border border-border/50 shadow-sm hover:border-primary/30 hover:shadow-md transition-all flex items-start gap-4 border-l-[3px]",
                        issue.type === "warning" ? "border-l-amber-500/60" : "border-l-primary/40"
                      )}
                    >
                      <div
                        className={cn(
                          "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                          issue.type === "warning"
                            ? "bg-gradient-to-br from-amber-500/20 to-amber-500/5 text-amber-500"
                            : "bg-gradient-to-br from-primary/20 to-primary/5 text-primary"
                        )}
                      >
                        {issue.type === "warning" ? (
                          <AlertTriangle className="w-5 h-5" />
                        ) : (
                          <Info className="w-5 h-5" />
                        )}
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground">
                            {issue.dimension}
                          </span>
                        </div>
                        <p className="text-sm text-foreground">{issue.title}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {allIssues.length === 0 && result.suggestions.length === 0 && (
              <div className="flex flex-col items-center py-8 text-muted-foreground">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mb-2" />
                <p className="text-foreground font-medium">模板质量良好，未发现明显问题</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
