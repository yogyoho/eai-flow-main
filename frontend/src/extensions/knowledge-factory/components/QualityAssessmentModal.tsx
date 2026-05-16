"use client";

import { useState } from "react";
import { kfApi } from "@/extensions/api";
import type { QualityAssessmentResult } from "@/extensions/knowledge-factory/types";

interface QualityAssessmentModalProps {
  templateId: string;
  templateName: string;
  open: boolean;
  onClose: () => void;
}

const DIMENSION_LABELS: Record<string, string> = {
  completeness: "完整性",
  accuracy: "准确性",
  consistency: "一致性",
  compliance: "合规性",
  freshness: "时效性",
};

const DIMENSION_COLORS: Record<string, string> = {
  completeness: "#3b82f6",
  accuracy: "#10b981",
  consistency: "#8b5cf6",
  compliance: "#f59e0b",
  freshness: "#ec4899",
};

export default function QualityAssessmentModal({
  templateId,
  templateName,
  open,
  onClose,
}: QualityAssessmentModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QualityAssessmentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAssess = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await kfApi.assessQuality(templateId);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "评估失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-emerald-500";
    if (score >= 60) return "text-yellow-500";
    return "text-red-500";
  };

  const getGradeLabel = (grade: string) => {
    const labels: Record<string, string> = {
      优秀: "A",
      良好: "B",
      一般: "C",
      较差: "D",
      差: "E",
      未知: "?",
    };
    return labels[grade] || grade;
  };

  const getGradeColor = (grade: string) => {
    const colors: Record<string, string> = {
      优秀: "bg-emerald-500/10 text-emerald-500",
      良好: "bg-primary/10 text-primary",
      一般: "bg-yellow-500/10 text-yellow-500",
      较差: "bg-amber-500/10 text-amber-500",
      差: "bg-red-500/10 text-red-500",
      未知: "bg-muted text-muted-foreground",
    };
    return colors[grade] || "bg-muted text-muted-foreground";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative w-full max-w-2xl rounded-lg bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold">AI 质量评估</h2>
            <p className="text-sm text-muted-foreground">{templateName}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 hover:bg-accent"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[60vh] overflow-y-auto p-6">
          {!result && !loading && !error && (
            <div className="flex flex-col items-center py-8">
              <div className="mb-4 text-center">
                <svg
                  className="mx-auto h-16 w-16 text-primary"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="mt-4 text-foreground">
                  点击下方按钮启动 AI 质量评估
                </p>
                <p className="mt-1 text-sm text-muted-foreground/60">
                  评估将从完整性、准确性、一致性、合规性、时效性五个维度进行分析
                </p>
              </div>
              <button
                onClick={handleAssess}
                className="rounded-lg bg-primary text-primary-foreground px-6 py-2.5 hover:bg-primary/90"
              >
                开始评估
              </button>
            </div>
          )}

          {loading && (
            <div className="flex flex-col items-center py-8">
              <div className="h-12 w-12 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
              <p className="mt-4 text-foreground">AI 正在分析模板质量...</p>
              <p className="mt-1 text-sm text-muted-foreground/60">预计需要 10-30 秒</p>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center py-8">
              <div className="mb-4 rounded-full bg-red-500/10 p-4">
                <svg className="h-12 w-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <p className="text-red-500">{error}</p>
              <button
                onClick={handleAssess}
                className="mt-4 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 hover:bg-primary/90"
              >
                重试
              </button>
            </div>
          )}

          {result && (
            <div className="space-y-6">
              {/* Overall Score */}
              <div className="flex items-center justify-between rounded-lg bg-gradient-to-r from-primary/10 to-primary/5 p-4">
                <div>
                  <p className="text-sm text-muted-foreground">总体评分</p>
                  <p className={`text-4xl font-bold ${getScoreColor(result.overall_score)}`}>
                    {result.overall_score}
                    <span className="text-lg font-normal text-muted-foreground/60">/100</span>
                  </p>
                </div>
                <div className="text-center">
                  <span
                    className={`inline-block rounded-full px-4 py-2 text-2xl font-bold ${getGradeColor(
                      result.quality_grade
                    )}`}
                  >
                    {getGradeLabel(result.quality_grade)}
                  </span>
                  <p className="mt-1 text-sm text-muted-foreground">{result.quality_grade}</p>
                </div>
              </div>

              {/* Dimension Scores */}
              <div>
                <h3 className="mb-3 text-sm font-medium text-foreground">
                  各维度评分
                </h3>
                <div className="space-y-3">
                  {Object.entries(result.dimensions).map(([key, dim]) => (
                    <div key={key} className="flex items-center gap-4">
                      <div className="w-20 text-sm text-muted-foreground">
                        {DIMENSION_LABELS[key] || key}
                      </div>
                      <div className="flex-1">
                        <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${dim.score}%`,
                              backgroundColor: DIMENSION_COLORS[key] || "#6b7280",
                            }}
                          />
                        </div>
                      </div>
                      <div className={`w-12 text-right text-sm font-medium ${getScoreColor(dim.score)}`}>
                        {dim.score}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Issues */}
              <div>
                <h3 className="mb-3 text-sm font-medium text-foreground">
                  发现的问题
                </h3>
                <div className="space-y-2">
                  {Object.entries(result.dimensions).map(([key, dim]) =>
                    dim.issues && dim.issues.length > 0 ? (
                      <div key={key} className="rounded-lg bg-amber-500/10 p-3">
                        <p className="text-sm font-medium text-amber-500">
                          {DIMENSION_LABELS[key] || key}
                        </p>
                        <ul className="mt-1 list-inside list-disc text-sm text-amber-500/80">
                          {dim.issues.map((issue, i) => (
                            <li key={i}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null
                  )}
                  {Object.values(result.dimensions).every((d) => !d.issues || d.issues.length === 0) && (
                    <p className="text-sm text-muted-foreground">各维度均无明显问题</p>
                  )}
                </div>
              </div>

              {/* Suggestions */}
              {result.suggestions && result.suggestions.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-medium text-foreground">
                    改进建议
                  </h3>
                  <ul className="space-y-2">
                    {result.suggestions.map((s, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 rounded-lg bg-primary/10 p-3 text-sm text-primary"
                      >
                        <svg
                          className="mt-0.5 h-4 w-4 shrink-0 text-primary/60"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                            clipRule="evenodd"
                          />
                        </svg>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Re-assess Button */}
              <div className="flex justify-center pt-2">
                <button
                  onClick={handleAssess}
                  disabled={loading}
                  className="rounded-lg border border-input px-4 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50"
                >
                  重新评估
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-md px-4 py-2 text-foreground hover:bg-accent"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
