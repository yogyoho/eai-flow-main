"use client";

import { CheckCircle2, XCircle, Send, Undo2 } from "lucide-react";

import type { TemplateApproval } from "@/extensions/workflow/types";

interface ApprovalHistoryPanelProps {
  approvals: TemplateApproval[];
}

const ACTION_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  pending: { label: "提交审批", icon: Send, color: "text-amber-600" },
  approved: { label: "审批通过", icon: CheckCircle2, color: "text-green-600" },
  rejected: { label: "审批拒绝", icon: XCircle, color: "text-red-600" },
  withdrawn: { label: "撤回审批", icon: Undo2, color: "text-gray-500" },
};

function formatTime(s: string | null): string {
  if (!s) return "";
  try {
    const d = new Date(s);
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch { return ""; }
}

export function ApprovalHistoryPanel({ approvals }: ApprovalHistoryPanelProps) {
  if (approvals.length === 0) return <div className="text-xs text-muted-foreground py-2">暂无审批记录</div>;
  return (
    <div className="space-y-2">
      {approvals.map((a) => {
        const config = ACTION_CONFIG[a.status] ?? ACTION_CONFIG.pending!;
        const Icon = config.icon;
        return (
          <div key={a.id} className="flex items-start gap-2 text-xs">
            <Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${config.color}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{config.label}</span>
                <span className="text-muted-foreground">{formatTime(a.createdAt)}</span>
              </div>
              {a.comment && <p className="text-muted-foreground mt-0.5">{a.comment}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
