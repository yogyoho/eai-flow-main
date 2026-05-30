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
      ? "border-green-300 bg-green-50"
      : review.status === "rejected"
        ? "border-red-300 bg-red-50"
        : "border-amber-300 bg-amber-50";

  return (
    <div className={`border rounded-lg p-3 ${statusColor}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {DIMENSION_LABELS[review.dimension || ""] || review.dimension || "未知维度"}
        </span>
        <span className="text-xs text-muted-foreground">
          {review.status === "approved" ? "✓ 通过" : review.status === "rejected" ? "✗ 退回" : "○ 待审核"}
        </span>
      </div>
      {review.comment && <div className="mt-1 text-xs text-muted-foreground">{review.comment}</div>}
    </div>
  );
}
