"use client";

import type { PhaseReview } from "./types";

interface DimensionReviewCardProps {
  review: PhaseReview;
}

const DIMENSION_LABELS: Record<string, string> = {
  technical: "技术准确性",
  compliance: "法规合规性",
  language: "语言表述",
  completeness: "内容完整性",
  format: "格式规范",
};

export function DimensionReviewCard({ review }: DimensionReviewCardProps) {
  const statusColor =
    review.status === "approved"
      ? "border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/40"
      : review.status === "rejected"
        ? "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40"
        : "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40";

  return (
    <div className={`rounded-lg border p-3 ${statusColor}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {/* truthiness fallback preserved: empty-string dimension renders "未知维度", not blank */}
          {DIMENSION_LABELS[review.dimension ?? ""] ??
            (review.dimension != null && review.dimension !== ""
              ? review.dimension
              : "未知维度")}
        </span>
        <span className="text-muted-foreground text-xs">
          {review.status === "approved"
            ? "✓ 通过"
            : review.status === "rejected"
              ? "✗ 退回"
              : "○ 待审核"}
        </span>
      </div>
      {review.comment && (
        <div className="text-muted-foreground mt-1 text-xs">
          {review.comment}
        </div>
      )}
    </div>
  );
}
