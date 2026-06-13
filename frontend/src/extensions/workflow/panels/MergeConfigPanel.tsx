"use client";

import type { DAGNodeData, TaskNodeData, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface MergeConfigPanelProps {
  data: DAGNodeData | TaskNodeData;
  onUpdate: (partial: Partial<DAGNodeData | TaskNodeData>) => void;
}

export function MergeConfigPanel({ data, onUpdate: _onUpdate }: MergeConfigPanelProps) {
  const mode = ((data as Record<string, unknown>).mergeMode as string) ?? "wait_all";

  return (
    <div className="p-4 space-y-4">
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">汇聚模式</label>
        <div className="grid grid-cols-2 gap-1.5">
          {([
            { value: "wait_all", label: "全部完成", desc: "等待所有上游节点完成" },
            { value: "wait_any", label: "任一完成", desc: "任一上游完成即触发" },
          ]).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => _onUpdate({ mergeMode: opt.value })}
              className={`text-left px-3 py-2 rounded-lg border text-xs transition-colors ${
                mode === opt.value
                  ? "border-green-300 bg-green-50 text-green-700 font-semibold"
                  : "border-border text-muted-foreground hover:border-green-200"
              }`}
            >
              <div>{opt.label}</div>
              <div className="text-[10px] opacity-60 mt-0.5">{opt.desc}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="text-[10px] text-muted-foreground bg-muted/30 rounded-lg p-2">
        汇聚节点等待上游分支完成后继续。支持全部完成或任一完成两种模式。
      </div>
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => _onUpdate({ notifications })}
      />
    </div>
  );
}
