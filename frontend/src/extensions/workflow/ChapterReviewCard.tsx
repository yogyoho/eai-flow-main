"use client";

import { useState } from "react";

import { workflowApi } from "./api";
import type { PhaseReview } from "./types";

interface ChapterReviewCardProps {
  review: PhaseReview;
  onAction: () => void;
}

export function ChapterReviewCard({
  review,
  onAction,
}: ChapterReviewCardProps) {
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleAction = async (action: "approved" | "rejected") => {
    setSubmitting(true);
    try {
      await workflowApi.submitReviewAction(review.projectId, review.id, {
        action,
        comment: comment || null,
      });
      onAction();
    } finally {
      setSubmitting(false);
    }
  };

  const statusColor =
    review.status === "approved"
      ? "bg-green-100 text-green-700"
      : review.status === "rejected"
        ? "bg-red-100 text-red-700"
        : "bg-amber-100 text-amber-700";

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">
          {review.reviewType === "chapter"
            ? `章节审核`
            : `维度: ${review.dimension ?? ""}`}
        </div>
        <span className={`rounded px-2 py-0.5 text-xs ${statusColor}`}>
          {review.status === "approved"
            ? "已通过"
            : review.status === "rejected"
              ? "已退回"
              : "待审核"}
        </span>
      </div>

      {review.comment && (
        <div className="text-muted-foreground bg-muted/50 rounded p-2 text-xs">
          {review.comment}
        </div>
      )}

      {review.status === "pending" && (
        <>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="审核意见（可选）"
            className="w-full resize-none rounded border px-2 py-1 text-sm"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleAction("approved")}
              disabled={submitting}
              className="rounded bg-green-600 px-3 py-1 text-sm text-white hover:bg-green-700 disabled:opacity-50"
            >
              通过
            </button>
            <button
              onClick={() => handleAction("rejected")}
              disabled={submitting}
              className="rounded bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-700 disabled:opacity-50"
            >
              退回
            </button>
          </div>
        </>
      )}
    </div>
  );
}
