"use client";

import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Check,
  ChevronsUpDown,
  FileText,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

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
  QualityAssessmentResult,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

function useColorScheme() {
  const [colorScheme, setColorScheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setColorScheme(isDark ? "dark" : "light");
    const observer = new MutationObserver(() => {
      setColorScheme(
        document.documentElement.classList.contains("dark") ? "dark" : "light",
      );
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
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
  completeness: "bg-gradient-to-r from-success to-success/70",
  accuracy: "bg-gradient-to-r from-primary to-primary/70",
  consistency: "bg-gradient-to-r from-info to-info/70",
  compliance: "bg-gradient-to-r from-warning to-warning/70",
  freshness: "bg-gradient-to-r from-chart-4 to-chart-4/70",
};

function getGradeLabel(grade: string): { label: string; color: string } {
  const grades: Record<string, { label: string; color: string }> = {
    优秀: {
      label: "优秀",
      color: "bg-success/10 text-success border-success/20",
    },
    良好: {
      label: "良好",
      color: "bg-primary/10 text-primary border-primary/20",
    },
    一般: { label: "一般", color: "bg-info/10 text-info border-info/20" },
    较差: {
      label: "较差",
      color: "bg-warning/10 text-warning border-warning/20",
    },
    差: {
      label: "差",
      color: "bg-destructive/10 text-destructive border-destructive/20",
    },
  };
  return (
    grades[grade] ?? { label: grade, color: "bg-muted text-muted-foreground" }
  );
}

export default function QualityAssessment() {
  const colorScheme = useColorScheme();
  const gridColor =
    colorScheme === "dark" ? "var(--gray-500)" : "var(--gray-200)";
  const axisColor = "var(--gray-400)";
  const radarColor = "var(--primary)";

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
      ? "bg-warning/10 text-warning"
      : s === "published"
        ? "bg-success/10 text-success"
        : "bg-muted text-muted-foreground";

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
          id: `${key}-issue-${i}`,
          dimension: DIMENSION_LABELS[key] ?? key,
          title: issue,
          type: dim.score >= 60 ? "warning" : "error",
        })),
      )
    : [];

  // Collect all strengths from all dimensions
  const allStrengths = result
    ? Object.entries(result.dimensions).flatMap(([key, dim]) =>
        (dim.strengths || []).map((strength, i) => ({
          id: `${key}-strength-${i}`,
          dimension: DIMENSION_LABELS[key] ?? key,
          title: strength,
        })),
      )
    : [];

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border bg-card flex shrink-0 items-center justify-between border-b p-4">
        <h2 className="text-foreground flex items-center gap-2 text-lg font-medium tracking-tight">
          <BarChart3 className="text-primary h-5 w-5" />
          知识质量评估
        </h2>
        <div className="flex gap-2">
          <button
            onClick={handleAssess}
            disabled={!selectedId || assessing}
            className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors disabled:opacity-50"
          >
            {assessing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> 评估中...
              </>
            ) : (
              <>
                <TrendingUp className="h-4 w-4" />{" "}
                {result ? "重新评估" : "开始评估"}
              </>
            )}
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
                  aria-controls="qa-template-combobox-list"
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
                id="qa-template-combobox-list"
                className="w-[var(--radix-popover-trigger-width)] p-0"
                align="start"
              >
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

        {/* Error */}
        {error && (
          <div className="bg-destructive/10 text-destructive flex items-center gap-2 rounded-lg p-4 text-sm">
            <AlertCircle className="h-4 w-4 shrink-0" /> {error}
          </div>
        )}

        {/* No result yet */}
        {!result && !assessing && !error && selectedId && (
          <div className="text-muted-foreground flex flex-col items-center py-12">
            <BarChart3 className="text-muted-foreground/20 mb-4 h-16 w-16" />
            <p className="text-foreground mb-1 font-medium">
              点击「开始评估」启动 AI 质量评估
            </p>
            <p className="text-sm">
              将从完整性、准确性、一致性、合规性、时效性五个维度进行分析
            </p>
          </div>
        )}

        {/* Assessing */}
        {assessing && (
          <div className="text-muted-foreground flex flex-col items-center py-12">
            <Loader2 className="text-primary mb-4 h-12 w-12 animate-spin" />
            <p className="text-foreground font-medium">
              AI 正在分析模板质量...
            </p>
            <p className="text-sm">预计需要 10-30 秒</p>
          </div>
        )}

        {/* Result */}
        {result && !assessing && (
          <>
            {/* Score Cards */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {/* Overall Score */}
              <div className="from-card to-card/80 border-border/50 flex flex-col items-center justify-center space-y-4 rounded-xl border bg-gradient-to-br p-8 text-center shadow-sm lg:col-span-1">
                <h3 className="text-muted-foreground text-sm font-bold tracking-widest uppercase">
                  整体评分
                </h3>
                <div className="relative flex h-48 w-48 items-center justify-center">
                  <div className="border-muted absolute inset-0 rounded-full border-8" />
                  <svg
                    className="absolute inset-0 h-full w-full -rotate-90"
                    viewBox="0 0 200 200"
                  >
                    <circle
                      cx="100"
                      cy="100"
                      r="88"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="8"
                      className={cn(
                        result.overall_score >= 80
                          ? "text-success"
                          : result.overall_score >= 60
                            ? "text-info"
                            : "text-destructive",
                      )}
                      strokeDasharray={`${(result.overall_score / 100) * 553} 553`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="text-center">
                    <div
                      className={cn(
                        "text-5xl font-black",
                        result.overall_score >= 80
                          ? "text-success"
                          : result.overall_score >= 60
                            ? "text-info"
                            : "text-destructive",
                      )}
                    >
                      {result.overall_score}
                    </div>
                    <div className="text-muted-foreground text-sm font-bold">
                      / 100
                    </div>
                  </div>
                </div>
                <div
                  className={cn(
                    "rounded-full border px-4 py-1 text-sm font-medium",
                    getGradeLabel(result.quality_grade).color,
                  )}
                >
                  {getGradeLabel(result.quality_grade).label}
                </div>
              </div>

              {/* Dimension Scores */}
              <div className="from-card to-card/80 border-border/50 rounded-xl border bg-gradient-to-br p-8 shadow-sm lg:col-span-2">
                <h3 className="text-foreground mb-6 text-lg font-semibold">
                  维度评分
                </h3>
                <div className="flex items-center gap-8">
                  {radarData.length > 0 && (
                    <div className="h-64 w-64 shrink-0">
                      <ResponsiveContainer width="100%" height="100%">
                        <RadarChart
                          cx="50%"
                          cy="50%"
                          outerRadius="75%"
                          data={radarData}
                        >
                          <PolarGrid stroke={gridColor} />
                          <PolarAngleAxis
                            dataKey="subject"
                            tick={{ fill: axisColor, fontSize: 12 }}
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
                  <div className="flex-1 space-y-4">
                    {Object.entries(result.dimensions).map(([key, dim]) => (
                      <div key={key} className="space-y-1.5">
                        <div className="flex justify-between text-sm font-medium">
                          <span className="text-foreground">
                            {DIMENSION_LABELS[key] ?? key}
                          </span>
                          <span
                            className={cn(
                              "font-bold",
                              dim.score >= 80
                                ? "text-success"
                                : dim.score >= 60
                                  ? "text-info"
                                  : "text-destructive",
                            )}
                          >
                            {dim.score}%
                          </span>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="bg-muted h-2 flex-1 overflow-hidden rounded-full">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all duration-1000",
                                DIMENSION_COLORS[key] ?? "bg-muted-foreground",
                              )}
                              style={{ width: `${dim.score}%` }}
                            />
                          </div>
                          <span className="text-muted-foreground min-w-[120px] text-xs whitespace-nowrap">
                            {dim.issues && dim.issues.length > 0
                              ? `${dim.issues.length} 个问题`
                              : "通过"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Suggestions */}
            {result.suggestions && result.suggestions.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-foreground flex items-center gap-2 text-lg font-semibold">
                  <CheckCircle2 className="text-primary h-5 w-5" /> 改进建议
                </h3>
                <div className="space-y-3">
                  {result.suggestions.map((suggestion, i) => (
                    <div
                      key={i}
                      className="bg-card border-border/50 hover:border-primary/30 group border-l-primary/40 flex items-start gap-4 rounded-xl border border-l-[3px] p-5 shadow-sm transition-all hover:shadow-md"
                    >
                      <div className="from-primary/20 to-primary/5 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br">
                        <CheckCircle2 className="h-5 w-5" />
                      </div>
                      <div className="flex-1">
                        <p className="text-foreground text-sm">{suggestion}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Strengths */}
            {allStrengths.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-foreground flex items-center gap-2 text-lg font-semibold">
                  <CheckCircle2 className="text-success h-5 w-5" /> 模板亮点
                </h3>
                <div className="space-y-3">
                  {allStrengths.map((s) => (
                    <div
                      key={s.id}
                      className="bg-card border-border/50 hover:border-primary/30 border-l-success/60 flex items-start gap-4 rounded-xl border border-l-[3px] p-5 shadow-sm transition-all hover:shadow-md"
                    >
                      <div className="from-success/20 to-success/5 text-success flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br">
                        <CheckCircle2 className="h-5 w-5" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs">
                            {s.dimension}
                          </span>
                        </div>
                        <p className="text-foreground text-sm">{s.title}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Issue List */}
            {allIssues.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-foreground flex items-center gap-2 text-lg font-semibold">
                  <AlertTriangle className="text-warning h-5 w-5" /> 问题清单
                </h3>
                <div className="space-y-3">
                  {allIssues.map((issue) => (
                    <div
                      key={issue.id}
                      className={cn(
                        "bg-card border-border/50 hover:border-primary/30 flex items-start gap-4 rounded-xl border border-l-[3px] p-5 shadow-sm transition-all hover:shadow-md",
                        issue.type === "error"
                          ? "border-l-destructive/60"
                          : "border-l-warning/60",
                      )}
                    >
                      <div
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                          issue.type === "error"
                            ? "from-destructive/20 to-destructive/5 text-destructive bg-gradient-to-br"
                            : "from-warning/20 to-warning/5 text-warning bg-gradient-to-br",
                        )}
                      >
                        <AlertTriangle className="h-5 w-5" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs">
                            {issue.dimension}
                          </span>
                        </div>
                        <p className="text-foreground text-sm">{issue.title}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {allIssues.length === 0 &&
              allStrengths.length === 0 &&
              result.suggestions.length === 0 && (
                <div className="text-muted-foreground flex flex-col items-center py-8">
                  <CheckCircle2 className="text-success mb-2 h-12 w-12" />
                  <p className="text-foreground font-medium">
                    模板质量良好，未发现明显问题
                  </p>
                </div>
              )}
          </>
        )}
      </div>
    </div>
  );
}
