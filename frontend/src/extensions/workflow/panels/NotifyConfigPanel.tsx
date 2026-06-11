"use client";

import type { DAGNodeData, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface NotifyConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

export function NotifyConfigPanel({ data, onUpdate }: NotifyConfigPanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-sky-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-sky-600">通知属性</span>
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">节点名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-400 transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 通知组"
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-400 transition-colors"
        />
      </div>

      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
