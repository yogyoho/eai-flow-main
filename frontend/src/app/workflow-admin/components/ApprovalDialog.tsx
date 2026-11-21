"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { workflowApi } from "@/extensions/workflow/api";
import type { TemplateApproval } from "@/extensions/workflow/types";

import { ApprovalHistoryPanel } from "./ApprovalHistoryPanel";

interface ApprovalDialogProps {
  templateId: string;
  templateName: string;
  approvals: TemplateApproval[];
  onAction: () => void;
  onClose: () => void;
}

export function ApprovalDialog({
  templateId,
  templateName,
  approvals,
  onAction,
  onClose,
}: ApprovalDialogProps) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: "approved" | "rejected") => {
    setLoading(true);
    try {
      await workflowApi.reviewApproval(
        templateId,
        action,
        comment || undefined,
      );
      toast.success(action === "approved" ? "已通过并发布" : "已拒绝");
      onAction();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card mx-4 w-full max-w-lg overflow-hidden rounded-xl border shadow-lg">
        <div className="border-b px-6 py-4">
          <h3 className="text-base font-semibold">模板审批</h3>
          <p className="text-muted-foreground mt-1 text-sm">{templateName}</p>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div>
            <div className="text-muted-foreground mb-2 text-xs font-medium">
              审批记录
            </div>
            <ApprovalHistoryPanel approvals={approvals} />
          </div>
          <div>
            <label className="text-muted-foreground mb-1 block text-xs">
              审批意见
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="bg-background w-full resize-none rounded-lg border px-3 py-2 text-sm"
              placeholder="输入审批意见（可选）"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t px-6 py-4">
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground px-4 py-2 text-sm font-medium transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => handleAction("rejected")}
            disabled={loading}
            className="rounded-lg bg-red-50 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-100 disabled:opacity-50 dark:bg-red-950/40 dark:text-red-300 dark:hover:bg-red-900/40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "拒绝"}
          </button>
          <button
            onClick={() => handleAction("approved")}
            disabled={loading}
            className="bg-success text-success-foreground hover:bg-success/90 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "通过并发布"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
