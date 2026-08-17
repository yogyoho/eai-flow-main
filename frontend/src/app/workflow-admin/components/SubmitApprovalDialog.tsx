"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { workflowApi } from "@/extensions/workflow/api";

interface SubmitApprovalDialogProps {
  templateId: string;
  templateName: string;
  onSubmit: () => void;
  onClose: () => void;
}

export function SubmitApprovalDialog({
  templateId,
  templateName,
  onSubmit,
  onClose,
}: SubmitApprovalDialogProps) {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await workflowApi.submitApproval(templateId);
      toast.success("已提交审批，等待超级管理员审核");
      onSubmit();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card mx-4 w-full max-w-sm overflow-hidden rounded-xl border shadow-lg">
        <div className="border-b px-6 py-4">
          <h3 className="text-base font-semibold">提交审批确认</h3>
        </div>
        <div className="px-6 py-4">
          <p className="text-muted-foreground text-sm">
            确认将「{templateName}」提交发布审批？
          </p>
          <p className="text-muted-foreground mt-2 text-xs">
            提交后模板状态将变为&quot;待审批&quot;，超级管理员审批通过后自动发布。
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 border-t px-6 py-4">
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground px-4 py-2 text-sm font-medium transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="bg-primary hover:bg-primary/90 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "确认提交"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
