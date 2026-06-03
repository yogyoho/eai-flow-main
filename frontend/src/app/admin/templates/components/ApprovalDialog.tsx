"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
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

export function ApprovalDialog({ templateId, templateName, approvals, onAction, onClose }: ApprovalDialogProps) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: "approved" | "rejected") => {
    setLoading(true);
    try {
      await workflowApi.reviewApproval(templateId, action, comment || undefined);
      toast.success(action === "approved" ? "已通过并发布" : "已拒绝");
      onAction();
      onClose();
    } catch (err) { toast.error(err instanceof Error ? err.message : "操作失败"); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card rounded-xl border shadow-lg w-full max-w-lg mx-4 overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h3 className="text-base font-semibold">模板审批</h3>
          <p className="text-sm text-muted-foreground mt-1">{templateName}</p>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">审批记录</div>
            <ApprovalHistoryPanel approvals={approvals} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">审批意见</label>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3}
              className="w-full px-3 py-2 text-sm border rounded-lg bg-background resize-none" placeholder="输入审批意见（可选）" />
          </div>
        </div>
        <div className="px-6 py-4 border-t flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">取消</button>
          <button onClick={() => handleAction("rejected")} disabled={loading}
            className="px-4 py-2 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "拒绝"}
          </button>
          <button onClick={() => handleAction("approved")} disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "通过并发布"}
          </button>
        </div>
      </div>
    </div>
  );
}
