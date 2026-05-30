"use client";

import { useState } from "react";
import { workflowApi } from "./api";
import type { ReviewAssignmentItem } from "./types";

interface ReviewAssignmentDialogProps {
  projectId: string;
  phaseNode: string;
  open: boolean;
  onClose: () => void;
  onAssigned: () => void;
}

const PRESET_DIMENSIONS = [
  { value: "technical", label: "技术准确性" },
  { value: "compliance", label: "法规合规性" },
  { value: "language", label: "语言表述" },
  { value: "completeness", label: "内容完整性" },
  { value: "format", label: "格式规范" },
];

export function ReviewAssignmentDialog({ projectId, phaseNode, open, onClose, onAssigned }: ReviewAssignmentDialogProps) {
  const [mode, setMode] = useState<"chapter" | "dimension">("chapter");
  const [reviewerId, setReviewerId] = useState("");
  const [dimension, setDimension] = useState("technical");
  const [assignments, setAssignments] = useState<ReviewAssignmentItem[]>([]);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const addAssignment = () => {
    if (!reviewerId.trim()) return;
    setAssignments((prev) => [
      ...prev,
      {
        reviewerId: reviewerId.trim(),
        reviewType: mode,
        dimension: mode === "dimension" ? dimension : undefined,
      },
    ]);
    setReviewerId("");
  };

  const handleSubmit = async () => {
    if (assignments.length === 0) return;
    setSubmitting(true);
    try {
      await workflowApi.assignReviews(projectId, phaseNode, assignments);
      onAssigned();
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-[480px] max-h-[80vh] overflow-y-auto p-6 space-y-4">
        <div className="flex justify-between items-center">
          <div className="text-lg font-medium">分配审核人</div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setMode("chapter")}
            className={`px-3 py-1 text-sm rounded ${mode === "chapter" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
          >
            按章节
          </button>
          <button
            onClick={() => setMode("dimension")}
            className={`px-3 py-1 text-sm rounded ${mode === "dimension" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
          >
            按维度
          </button>
        </div>

        <div className="flex gap-2">
          <input
            value={reviewerId}
            onChange={(e) => setReviewerId(e.target.value)}
            placeholder="审核人 ID"
            className="flex-1 px-2 py-1 text-sm border rounded"
          />
          {mode === "dimension" && (
            <select
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
              className="px-2 py-1 text-sm border rounded"
            >
              {PRESET_DIMENSIONS.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          )}
          <button onClick={addAssignment} className="px-3 py-1 text-sm bg-muted rounded hover:bg-muted/80">添加</button>
        </div>

        {assignments.length > 0 && (
          <div className="space-y-1">
            {assignments.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-xs bg-muted/50 px-2 py-1 rounded">
                <span>{a.reviewType === "chapter" ? "章节" : `维度:${a.dimension}`}</span>
                <span className="flex-1 truncate">{a.reviewerId}</span>
                <button
                  onClick={() => setAssignments((prev) => prev.filter((_, j) => j !== i))}
                  className="text-red-500 hover:text-red-700"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded border">取消</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || assignments.length === 0}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded disabled:opacity-50"
          >
            确认分配 ({assignments.length})
          </button>
        </div>
      </div>
    </div>
  );
}
