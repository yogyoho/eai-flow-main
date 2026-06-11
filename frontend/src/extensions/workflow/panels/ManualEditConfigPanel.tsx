"use client";

import { StyledCheckbox } from "@/components/ui/styled-checkbox";
import type { DAGNodeData, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface ManualEditConfigPanelProps {
  data: DAGNodeData;
  nodeId?: string;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

export function ManualEditConfigPanel({ data, onUpdate }: ManualEditConfigPanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-amber-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-amber-600">人工编辑属性</span>
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">节点名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-400 transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 编辑组"
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-400 transition-colors"
        />
      </div>

      <StyledCheckbox checked={data.aiAssist ?? false} onChange={(v) => onUpdate({ aiAssist: v })} label="AI 辅助" />

      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
