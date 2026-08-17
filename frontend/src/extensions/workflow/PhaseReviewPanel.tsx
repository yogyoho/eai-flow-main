"use client";

import { useCallback, useEffect, useState } from "react";

import { workflowApi } from "./api";
import { ChapterReviewCard } from "./ChapterReviewCard";
import { DimensionReviewCard } from "./DimensionReviewCard";
import { ReviewAssignmentDialog } from "./ReviewAssignmentDialog";
import type { ReviewStatus } from "./types";

interface PhaseReviewPanelProps {
  projectId: string;
  phaseNode: string;
}

export function PhaseReviewPanel({
  projectId,
  phaseNode,
}: PhaseReviewPanelProps) {
  const [status, setStatus] = useState<ReviewStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAssignDialog, setShowAssignDialog] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await workflowApi.getReviewStatus(projectId, phaseNode);
      setStatus(data);
    } finally {
      setLoading(false);
    }
  }, [projectId, phaseNode]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading)
    return (
      <div className="text-muted-foreground p-4 text-sm">加载审核状态...</div>
    );
  if (!status) return null;

  const chapterReviews = status.reviews.filter(
    (r) => r.reviewType === "chapter",
  );
  const dimensionReviews = status.reviews.filter(
    (r) => r.reviewType === "dimension",
  );

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">审核进度</div>
        <button
          onClick={() => setShowAssignDialog(true)}
          className="bg-primary text-primary-foreground rounded px-3 py-1 text-xs hover:opacity-90"
        >
          分配审核人
        </button>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="text-muted-foreground flex justify-between text-xs">
          <span>
            通过 {status.approved}/{status.total}
          </span>
          <span>
            {status.rejected} 退回 · {status.pending} 待审
          </span>
        </div>
        <div className="bg-muted h-2 overflow-hidden rounded-full">
          {status.total > 0 && (
            <div
              className="h-full rounded-full bg-green-500 transition-all"
              style={{ width: `${(status.approved / status.total) * 100}%` }}
            />
          )}
        </div>
      </div>

      {/* Chapter reviews */}
      {chapterReviews.length > 0 && (
        <div className="space-y-2">
          <div className="text-muted-foreground text-xs font-semibold">
            章节审核
          </div>
          {chapterReviews.map((r) => (
            <ChapterReviewCard key={r.id} review={r} onAction={refresh} />
          ))}
        </div>
      )}

      {/* Dimension reviews */}
      {dimensionReviews.length > 0 && (
        <div className="space-y-2">
          <div className="text-muted-foreground text-xs font-semibold">
            维度审核
          </div>
          {dimensionReviews.map((r) => (
            <DimensionReviewCard key={r.id} review={r} />
          ))}
        </div>
      )}

      {status.reviews.length === 0 && (
        <div className="text-muted-foreground py-4 text-center text-xs">
          尚未分配审核人，点击上方按钮开始分配
        </div>
      )}

      <ReviewAssignmentDialog
        projectId={projectId}
        phaseNode={phaseNode}
        open={showAssignDialog}
        onClose={() => setShowAssignDialog(false)}
        onAssigned={refresh}
      />
    </div>
  );
}
