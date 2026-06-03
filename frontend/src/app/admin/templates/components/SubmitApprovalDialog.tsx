"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { workflowApi } from "@/extensions/workflow/api";

interface SubmitApprovalDialogProps {
  templateId: string;
  templateName: string;
  onSubmit: () => void;
  onClose: () => void;
}

export function SubmitApprovalDialog({ templateId, templateName, onSubmit, onClose }: SubmitApprovalDialogProps) {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await workflowApi.submitApproval(templateId);
      toast.success("已提交审批，等待超级管理员审核");
      onSubmit();
      onClose();
    } catch (err) { toast.error(err instanceof Error ? err.message : "提交失败"); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card rounded-xl border shadow-lg w-full max-w-sm mx-4 overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h3 className="text-base font-semibold">提交审批确认</h3>
        </div>
        <div className="px-6 py-4">
          <p className="text-sm text-muted-foreground">确认将「{templateName}」提交发布审批？</p>
          <p className="text-xs text-muted-foreground mt-2">提交后模板状态将变为"待审批"，超级管理员审批通过后自动发布。</p>
        </div>
        <div className="px-6 py-4 border-t flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">取消</button>
          <button onClick={handleSubmit} disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "确认提交"}
          </button>
        </div>
      </div>
    </div>
  );
}
