"use client";

import type { DAGNodeData, TaskNodeData, NotificationConfig } from "../types";

import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface MergeConfigPanelProps {
  data: DAGNodeData | TaskNodeData;
  onUpdate: (partial: Partial<DAGNodeData | TaskNodeData>) => void;
}

export function MergeConfigPanel({
  data,
  onUpdate: _onUpdate,
}: MergeConfigPanelProps) {
  const mode =
    ((data as Record<string, unknown>).mergeMode as string) ?? "wait_all";

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <label className="text-foreground text-xs font-semibold">
          汇聚模式
        </label>
        <div className="grid grid-cols-2 gap-1.5">
          {[
            {
              value: "wait_all",
              label: "全部完成",
              desc: "等待所有上游节点完成",
            },
            {
              value: "wait_any",
              label: "任一完成",
              desc: "任一上游完成即触发",
            },
          ].map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => _onUpdate({ mergeMode: opt.value })}
              className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                mode === opt.value
                  ? "border-green-300 bg-green-50 font-semibold text-green-700 dark:border-green-700 dark:bg-green-950/40 dark:text-green-300"
                  : "border-border text-muted-foreground hover:border-green-200 dark:border-green-800"
              }`}
            >
              <div>{opt.label}</div>
              <div className="mt-0.5 text-[10px] opacity-60">{opt.desc}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="text-muted-foreground bg-muted/30 rounded-lg p-2 text-[10px]">
        汇聚节点等待上游分支完成后继续。支持全部完成或任一完成两种模式。
      </div>
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) =>
          _onUpdate({ notifications })
        }
      />
    </div>
  );
}
