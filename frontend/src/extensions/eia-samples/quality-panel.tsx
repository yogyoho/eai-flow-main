"use client";

// EAI-CUSTOM: 煤矿环评报告样例库 二期（BS3 ④质检面板）——全库聚合卡片 + 逐样例问题清单。
// 质检六项：哈希体检/内容非空/场景枚举/重复标题/隐私扫描/编号体检（pass/warn/fail/unknown 徽章）。

import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  RefreshCw,
  ShieldX,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  QUALITY_CHECK_LABELS,
  QUALITY_RESULT_LABELS,
  SCENARIO_LABELS,
  sampleLibraryApi,
  type QualityReport,
  type QualityResult,
  type QualitySummary,
} from "./sample-library-api";

const RESULT_BADGE_CLASS: Record<QualityResult, string> = {
  pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warn: "bg-amber-50 text-amber-700 border-amber-200",
  fail: "bg-red-50 text-red-700 border-red-200",
  unknown: "bg-muted text-muted-foreground",
};

const RESULT_ICON: Record<QualityResult, typeof CheckCircle2> = {
  pass: CheckCircle2,
  warn: AlertTriangle,
  fail: ShieldX,
  unknown: CircleHelp,
};

function scoreBadgeClass(score: number): string {
  if (score >= 90) return RESULT_BADGE_CLASS.pass;
  if (score >= 70) return RESULT_BADGE_CLASS.warn;
  return RESULT_BADGE_CLASS.fail;
}

export default function QualityPanel({ refreshKey }: { refreshKey: number }) {
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [report, setReport] = useState<QualityReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      setSummary(await sampleLibraryApi.qualitySummary());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载质检汇总失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSummary();
  }, [fetchSummary, refreshKey]);

  const toggleItem = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setReport(null);
      return;
    }
    setExpandedId(id);
    setReport(null);
    setReportLoading(true);
    try {
      setReport(await sampleLibraryApi.sampleQuality(id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载单样例质检报告失败");
    } finally {
      setReportLoading(false);
    }
  };

  if (loading && !summary) {
    return (
      <div className="text-muted-foreground flex items-center justify-center gap-2 py-20 text-sm">
        <RefreshCw className="h-4 w-4 animate-spin" /> 加载质检汇总…
      </div>
    );
  }
  if (!summary) return null;

  const results: QualityResult[] = ["pass", "warn", "fail", "unknown"];

  return (
    <div className="space-y-6">
      {/* 聚合卡片 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div className="border-border rounded-xl border p-4">
          <div className="text-muted-foreground text-xs font-medium">
            样例总数
          </div>
          <div className="text-foreground mt-1 text-2xl font-semibold tabular-nums">
            {summary.total}
          </div>
          <div className="text-muted-foreground mt-1 text-xs">
            检查项 {summary.total * 6} 项
          </div>
        </div>
        {results.map((r) => {
          const Icon = RESULT_ICON[r];
          return (
            <div key={r} className="border-border rounded-xl border p-4">
              <div className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
                <Icon className="h-3.5 w-3.5" />
                {QUALITY_RESULT_LABELS[r]}
              </div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {summary.by_result[r] ?? 0}
              </div>
              <div className="text-muted-foreground mt-1 text-xs">
                逐检查项累计
              </div>
            </div>
          );
        })}
      </div>

      {/* 场景均分 */}
      {Object.keys(summary.by_scenario).length > 0 && (
        <div className="border-border overflow-hidden rounded-xl border">
          <div className="text-muted-foreground bg-muted/50 border-border border-b px-4 py-2 text-xs font-medium">
            分场景均分
          </div>
          <div className="flex flex-wrap gap-4 px-4 py-3">
            {Object.entries(summary.by_scenario).map(([sc, agg]) => (
              <div key={sc} className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground text-xs">
                  {SCENARIO_LABELS[sc] ?? sc}
                </span>
                <span className="text-foreground font-medium tabular-nums">
                  {agg.avg_score}
                </span>
                <span className="text-muted-foreground text-xs">
                  ({agg.samples} 样例)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 逐样例问题清单（最差优先，前 50） */}
      <div className="border-border overflow-hidden rounded-xl border">
        <div className="text-muted-foreground bg-muted/50 border-border flex items-center justify-between border-b px-4 py-2 text-xs font-medium">
          <span>逐样例问题清单（按分数升序，前 {summary.items.length}）</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void fetchSummary()}
            disabled={loading}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", loading && "animate-spin")}
            />
            重新体检
          </Button>
        </div>
        {summary.items.length === 0 ? (
          <p className="text-muted-foreground px-4 py-12 text-center text-sm">
            样例库为空，先登记或导入样例。
          </p>
        ) : (
          <div className="divide-border divide-y">
            {summary.items.map((it) => {
              const isOpen = expandedId === it.sample_id;
              return (
                <div key={it.sample_id}>
                  <button
                    type="button"
                    onClick={() => void toggleItem(it.sample_id)}
                    className="hover:bg-muted/40 flex w-full items-center gap-3 px-4 py-3 text-left"
                  >
                    {isOpen ? (
                      <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
                    ) : (
                      <ChevronRight className="text-muted-foreground h-4 w-4 shrink-0" />
                    )}
                    <Badge
                      variant="outline"
                      className={cn("tabular-nums", scoreBadgeClass(it.score))}
                    >
                      {it.score}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={RESULT_BADGE_CLASS[it.worst_result]}
                    >
                      {QUALITY_RESULT_LABELS[it.worst_result]}
                    </Badge>
                    <span
                      className="text-foreground min-w-0 flex-1 truncate text-sm"
                      title={it.title}
                    >
                      {it.title}
                    </span>
                    <span className="text-muted-foreground hidden shrink-0 text-xs sm:inline">
                      {SCENARIO_LABELS[it.scenario] ?? it.scenario}
                    </span>
                    {it.problems.length > 0 && (
                      <span className="shrink-0 text-xs text-amber-600">
                        {it.problems.length} 项待处理
                      </span>
                    )}
                  </button>
                  {isOpen && (
                    <div className="bg-muted/20 border-border/60 mr-4 mb-3 ml-10 space-y-1.5 rounded-lg border p-3">
                      {reportLoading && !report ? (
                        <p className="text-muted-foreground text-xs">
                          加载六项质检详情…
                        </p>
                      ) : report ? (
                        report.checks.map((c) => {
                          const Icon = RESULT_ICON[c.result];
                          return (
                            <div
                              key={c.check}
                              className="flex items-start gap-2 text-xs"
                            >
                              <Badge
                                variant="outline"
                                className={cn(
                                  "shrink-0",
                                  RESULT_BADGE_CLASS[c.result],
                                )}
                              >
                                <Icon className="mr-0.5 h-3 w-3" />
                                {QUALITY_RESULT_LABELS[c.result]}
                              </Badge>
                              <span className="text-foreground w-16 shrink-0 font-medium">
                                {QUALITY_CHECK_LABELS[c.check] ?? c.check}
                              </span>
                              <span className="text-muted-foreground min-w-0">
                                {c.detail}
                              </span>
                            </div>
                          );
                        })
                      ) : (
                        <p className="text-muted-foreground text-xs">
                          无详情。
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
